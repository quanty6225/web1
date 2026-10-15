"""Session-authorized browser activity, with the source four-minute away threshold."""
import hashlib, re, time
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect

SCHEMA = '''CREATE TABLE IF NOT EXISTS tw_chat_clients(owner TEXT NOT NULL,actor TEXT NOT NULL,client TEXT NOT NULL,session TEXT NOT NULL,heartbeat REAL NOT NULL,active REAL NOT NULL,focused INTEGER NOT NULL,channel TEXT NOT NULL,origin TEXT NOT NULL,PRIMARY KEY(owner,actor,client),FOREIGN KEY(owner,actor) REFERENCES tw_chat_users(owner,actor) ON DELETE CASCADE);'''


def live(c, who, actor):
    now = time.time()
    return c.execute('SELECT p.* FROM tw_chat_clients p JOIN local_auth_sessions s ON s.session_digest=p.session WHERE p.owner=? AND p.actor=? AND p.heartbeat>? AND s.account_id=p.actor AND s.revoked_at IS NULL AND s.expires_at>?', (who, actor, now - 90, int(now))).fetchall()


def status(c, who, actor):
    rows = live(c, who, actor)
    if rows:
        return 'Online' if any(r['active'] > time.time() - 240 for r in rows) else 'Away'
    # Legacy/API-only actors have no browser heartbeat. Preserve their explicit API presence.
    if not c.execute('SELECT 1 FROM tw_chat_clients WHERE owner=? AND actor=?', (who, actor)).fetchone():
        row = c.execute('SELECT seen FROM tw_chat_presence WHERE owner=? AND actor=?', (who, actor)).fetchone()
        if row and row['seen'] > time.time() - 90:
            return 'Online'
    return 'Offline'


def viewing(c, who, actor, cid):
    return any(r['focused'] and r['channel'] == cid and r['active'] > time.time() - 240 for r in live(c, who, actor))


def install(app, db, identity):
    from chat_local import channel
    with db() as c:
        c.executescript(SCHEMA)

    @app.post('/api/chat/presence')
    async def update(req: Request):
        try:
            data = await req.json()
        except ClientDisconnect:
            # A tab can close while sending its final heartbeat. No complete
            # activity payload means no presence/session state may be updated.
            raise HTTPException(400, 'Chat activity request interrupted.')
        except ValueError:
            raise HTTPException(422, 'Invalid Chat activity.')
        if not isinstance(data, dict) or not isinstance(data.get('client'), str) or not re.fullmatch(r'[A-Za-z0-9-]{16,64}', data['client']):
            raise HTTPException(422, 'Invalid Chat client.')
        if any(type(data.get(key)) is not bool for key in ['focused', 'active', 'alive']) or not isinstance(data.get('channel', ''), str):
            raise HTTPException(422, 'Invalid Chat activity.')
        origin = str(req.base_url).rstrip('/')
        url = urlsplit(origin)
        if url.hostname not in ['127.0.0.1', 'localhost', '::1'] or url.port not in range(18150, 18160):
            raise HTTPException(400, 'Use the local Chat site.')
        with db() as c:
            who, actor = identity(req, c)
            cid = data.get('channel', '')
            if cid:
                channel(c, who, actor, cid, member=True)
            c.execute('DELETE FROM tw_chat_clients WHERE actor=? AND client=? AND owner!=?', (actor, data['client'], who))
            now = time.time()
            c.execute('INSERT INTO tw_chat_clients VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(owner,actor,client) DO UPDATE SET session=excluded.session,heartbeat=excluded.heartbeat,active=CASE WHEN excluded.active>0 THEN excluded.active ELSE tw_chat_clients.active END,focused=excluded.focused,channel=excluded.channel,origin=excluded.origin',
                      (who, actor, data['client'], hashlib.sha256(req.cookies.get('teamwork_session', '').encode()).hexdigest(), now if data['alive'] else 0, now if data['active'] and data['focused'] and data['alive'] else 0, int(data['focused'] and data['alive']), cid, origin))
            return {'status': status(c, who, actor)}
