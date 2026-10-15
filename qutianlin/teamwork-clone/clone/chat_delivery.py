"""Durable Chat alerts and local SMTP delivery, with authorization checked at delivery."""
import asyncio, json, logging, time
from urllib.parse import urlsplit
from fastapi import HTTPException, Query, Request
import chat_presence, chat_settings, chat_status, chat_replies
from status_subscriptions import send_mail

SCHEMA = '''
CREATE TABLE IF NOT EXISTS tw_chat_alerts(seq INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,created REAL NOT NULL,UNIQUE(owner,message,actor),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_mail(owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,origin TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,error TEXT,sent REAL,PRIMARY KEY(owner,message,actor),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_runtime_origins(owner TEXT PRIMARY KEY,origin TEXT NOT NULL);
'''


def important(c, who, cid, actor, mid):
    from chat_mentions import mode
    value = mode(c, who, cid, actor)
    if value == 'global':
        value = chat_settings.settings(c, who, actor)['defaultNotificationNoisiness']
    kinds = {r['kind'] for r in c.execute('SELECT kind FROM tw_chat_mentions WHERE owner=? AND message=? AND actor=?', (who, mid, actor))}
    return value == 'all' or value == 'mentions' and bool(kinds) or value == 'directMentions' and 'direct' in kinds


def enqueue(c, who, cid, mid, actor):
    if chat_status.dnd(c, who, actor):
        return
    now = time.time()
    c.execute('INSERT OR IGNORE INTO tw_chat_alerts(owner,message,actor,created) VALUES(?,?,?,?)', (who, mid, actor, now))
    if chat_settings.settings(c, who, actor)['emailNotifications'] != 'always' or chat_presence.viewing(c, who, actor, cid):
        return
    row = c.execute('SELECT origin FROM tw_chat_runtime_origins WHERE owner=?', (who,)).fetchone()
    origin = row['origin'] if row else 'http://127.0.0.1:18150'
    c.execute('INSERT OR IGNORE INTO tw_chat_mail(owner,message,actor,origin) VALUES(?,?,?,?)', (who, mid, actor, origin))


def accessible(c, who, actor, mid):
    from chat_local import channel
    if chat_status.dnd(c, who, actor):
        return None
    if actor != who and not c.execute('SELECT 1 FROM tw_memberships WHERE account=? AND workspace_owner=?', (actor, who)).fetchone():
        return None
    message = c.execute('SELECT * FROM tw_chat_messages WHERE owner=? AND id=?', (who, mid)).fetchone()
    if not message or message['author'] == actor:
        return None
    try:
        conversation = channel(c, who, actor, message['channel'], member=True)
    except HTTPException:
        return None
    if not important(c, who, message['channel'], actor, mid):
        return None
    member = c.execute('SELECT last_read FROM tw_chat_members WHERE owner=? AND channel=? AND actor=?', (who, message['channel'], actor)).fetchone()
    if member['last_read'] >= message['created']:
        return None
    return message, conversation


def install(app, db, identity):
    from chat_local import channels
    from chat_mentions import mode
    with db() as c:
        c.executescript(SCHEMA)
    ingest_replies = chat_replies.install(db)

    @app.get('/api/chat/notification-channels')
    def notification_channels(req: Request):
        with db() as c:
            who, actor = identity(req, c)
            return [{**row, 'mode': mode(c, who, row['id'], actor)} for row in channels(c, who, actor) if row['joined'] and row['kind'] not in ['pair','group']]

    @app.get('/api/chat/notifications')
    def notifications(req: Request, after: int | None = Query(None, ge=0)):
        with db() as c:
            who, actor = identity(req, c)
            cursor = c.execute('SELECT COALESCE(MAX(seq),0) AS seq FROM tw_chat_alerts WHERE owner=? AND actor=?', (who, actor)).fetchone()['seq']
            if after is None:
                return {'cursor': cursor, 'notifications': [], 'settings': chat_settings.settings(c, who, actor), 'dnd': chat_status.dnd(c, who, actor)}
            rows = c.execute('SELECT seq,message FROM tw_chat_alerts WHERE owner=? AND actor=? AND seq>? ORDER BY seq LIMIT 100', (who, actor, after)).fetchall()
            result = []
            for row in rows:
                pair = accessible(c, who, actor, row['message'])
                if not pair:
                    continue
                message, channel = pair
                if chat_presence.viewing(c, who, actor, channel['id']):
                    continue
                author = c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?', (message['author'],)).fetchone()
                result.append({'seq': row['seq'], 'message': message['id'], 'channel': channel['id'], 'title': (__import__('chat_hooks').author(c, who, message['id']) or (author['display_name'] if author else 'Former member')) + ' - ' + channel['name'], 'text': message['body'], 'url': __import__('chat_conversations').path(channel) + '/messages/' + message['id']})
            return {'cursor': rows[-1]['seq'] if rows else max(after, cursor), 'notifications': result, 'settings': chat_settings.settings(c, who, actor), 'dnd': chat_status.dnd(c, who, actor)}

    def deliver():
        with db() as c:
            jobs = [dict(r) for r in c.execute("SELECT owner,message,actor FROM tw_chat_mail WHERE state='pending' AND next_attempt<=? ORDER BY rowid LIMIT 100", (time.time(),))]
        for job in jobs:
            keys = (job['owner'], job['message'], job['actor'])
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row = c.execute("SELECT * FROM tw_chat_mail WHERE owner=? AND message=? AND actor=? AND state='pending' AND next_attempt<=?", (*keys, time.time())).fetchone()
                if not row:
                    continue
                pair = accessible(c, job['owner'], job['actor'], job['message'])
                settings = chat_settings.settings(c, job['owner'], job['actor'])
                if not pair or settings['emailNotifications'] != 'always':
                    c.execute("UPDATE tw_chat_mail SET state='cancelled' WHERE owner=? AND message=? AND actor=?", keys)
                    continue
                message, channel = pair
                if chat_presence.viewing(c, job['owner'], job['actor'], channel['id']):
                    c.execute("UPDATE tw_chat_mail SET state='cancelled' WHERE owner=? AND message=? AND actor=?", keys)
                    continue
                if chat_presence.status(c, job['owner'], job['actor']) == 'Online' and settings['sendNotificationsWhenOnline'] != 'always':
                    continue
                url = urlsplit(row['origin'])
                if url.hostname not in ['localhost', '127.0.0.1', '::1'] or url.port not in range(18150, 18160):
                    c.execute("UPDATE tw_chat_mail SET state='cancelled',error='Invalid local origin' WHERE owner=? AND message=? AND actor=?", keys)
                    continue
                recipient = c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?', (job['actor'],)).fetchone()
                author = c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?', (message['author'],)).fetchone()
                subject = (__import__('chat_hooks').author(c, job['owner'], message['id']) or (author['display_name'] if author else 'Former member')) + ' - ' + channel['name']
                body = message['body'] + '\n\n' + row['origin'] + __import__('chat_conversations').path(channel) + '/messages/' + message['id']
                c.execute('UPDATE tw_chat_mail SET attempts=attempts+1 WHERE owner=? AND message=? AND actor=?', keys)
                try:
                    reply_to = chat_replies.address(c, job['owner'], job['message'], job['actor'], recipient['email_normalized'])
                    send_mail(recipient['email_normalized'], subject, body + '\n\nReply to this email to post to the conversation. Put #end before your signature.', reply_to)
                except Exception as error:
                    c.execute('UPDATE tw_chat_mail SET error=?,next_attempt=? WHERE owner=? AND message=? AND actor=?', (type(error).__name__, time.time() + 30, *keys))
                else:
                    c.execute("UPDATE tw_chat_mail SET state='sent',sent=?,error=NULL WHERE owner=? AND message=? AND actor=?", (time.time(), *keys))

    task = None
    @app.on_event('startup')
    async def start():
        nonlocal task
        async def loop():
            while True:
                try:
                    await asyncio.to_thread(deliver)
                    await asyncio.to_thread(ingest_replies)
                except Exception as error:
                    logging.getLogger(__name__).error('Chat mail delivery failed: %s', type(error).__name__)
                await asyncio.sleep(5)
        task = asyncio.create_task(loop())

    @app.on_event('shutdown')
    async def stop():
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    return {'deliver': deliver, 'ingest_replies': ingest_replies}
