"""Local incoming hooks. HTTP capabilities and real Mailpit SMTP ingestion."""
import asyncio, base64, hashlib, io, json, logging, secrets, time
from email import policy
from email.parser import BytesParser
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler
from fastapi import HTTPException, Request
from fastapi.responses import Response
import chat_users

SCHEMA = '''
CREATE TABLE IF NOT EXISTS tw_chat_hooks(owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,id TEXT NOT NULL,channel TEXT NOT NULL,creator TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,token TEXT UNIQUE NOT NULL,created REAL NOT NULL,avatar BLOB,avatar_type TEXT,PRIMARY KEY(owner,id),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_bot_messages(owner TEXT NOT NULL,message TEXT NOT NULL,hook TEXT NOT NULL,name TEXT NOT NULL,PRIMARY KEY(owner,message),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_hook_mail(owner TEXT NOT NULL,hook TEXT NOT NULL,mail TEXT NOT NULL,state TEXT NOT NULL,PRIMARY KEY(owner,hook,mail),FOREIGN KEY(owner,hook) REFERENCES tw_chat_hooks(owner,id) ON DELETE CASCADE);
'''
DOMAIN = 'hooks.teamwork.clone.test'
DEFAULT_AVATAR = '/static/chat-bot-avatar.svg'


def author(c, who, message):
    row = c.execute('SELECT * FROM tw_chat_bot_messages WHERE owner=? AND message=?', (who, message)).fetchone()
    return row['name'] if row else None


def decorate(c, who, value):
    row = c.execute('SELECT * FROM tw_chat_bot_messages WHERE owner=? AND message=?', (who, value['id'])).fetchone()
    if row:
        hook = c.execute('SELECT avatar FROM tw_chat_hooks WHERE owner=? AND id=?', (who, row['hook'])).fetchone()
        value.update(author_name=row['name'], bot=True, avatar_url='/api/chat/hooks/'+row['hook']+'/avatar' if hook and hook['avatar'] else DEFAULT_AVATAR)
    return value


def validate(data, previous=None):
    if not isinstance(data, dict) or set(data)-{'name','description','channel','avatar'}:
        raise HTTPException(422, 'Choose valid Incoming Hook settings.')
    name=data.get('name',previous['name'] if previous else '')
    description=data.get('description',previous['description'] if previous else '')
    if not isinstance(name,str) or not 2<=len(name.strip())<=50 or not isinstance(description,str) or len(description)>255:
        raise HTTPException(422, 'Enter a name of 2–50 characters and a description of up to 255 characters.')
    avatar=previous['avatar'] if previous else None;mime=previous['avatar_type'] if previous else None
    if 'avatar' in data:
        encoded=data['avatar']
        if encoded is None:avatar=None;mime=None
        elif not isinstance(encoded,str) or not encoded.startswith('data:image/') or len(encoded)>14_000_000:
            raise HTTPException(422, 'Only images can be used for the Incoming Hook avatar')
        else:
            try:raw=base64.b64decode(encoded.split(',',1)[1],validate=True)
            except (ValueError,IndexError):raise HTTPException(422, 'Invalid Incoming Hook avatar.')
            from chat_profile import resized_photo
            mime,avatar=resized_photo(io.BytesIO(raw))
    return name.strip(),description,avatar,mime


def receive(c, hook, text):
    # The hook belongs to the channel, not its creator's continuing membership.
    from chat_local import add_message
    from chat_mentions import apply
    mid=add_message(c,hook['owner'],hook['channel'],'hook:'+hook['id'],text,'bot')
    c.execute('INSERT INTO tw_chat_bot_messages VALUES(?,?,?,?)',(hook['owner'],mid,hook['id'],hook['name']))
    apply(c,hook['owner'],hook['channel'],'hook:'+hook['id'],mid,text,[])
    return mid


def install(app,db,identity):
    from chat_local import channel, channels
    with db() as c:c.executescript(SCHEMA)
    def get(c,who,hid):
        row=c.execute('SELECT * FROM tw_chat_hooks WHERE owner=? AND id=?',(who,hid)).fetchone()
        if not row:raise HTTPException(404,'Incoming Hook not found.')
        return row
    def output(c,who,actor,row,req):
        try:room=channel(c,who,actor,row['channel']);visible={'id':room['id'],'name':room['name']}
        except HTTPException:visible=None
        creator=c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(row['creator'],)).fetchone()
        return {'id':row['id'],'name':row['name'],'description':row['description'],'channel':visible,'creator':creator[0] if creator else 'Former member','created':row['created'],'url':str(req.base_url).rstrip('/')+'/api/chat/incoming/'+row['token'],'email':row['token']+'@'+DOMAIN,'avatar_url':'/api/chat/hooks/'+row['id']+'/avatar' if row['avatar'] else DEFAULT_AVATAR}
    @app.get('/api/chat/hooks')
    def listing(req:Request):
        with db() as c:
            who,actor=identity(req,c);chat_users.admin(c,who,actor)
            return [output(c,who,actor,r,req) for r in c.execute('SELECT * FROM tw_chat_hooks WHERE owner=? ORDER BY created DESC,id',(who,))]
    @app.get('/api/chat/hooks/channels')
    def choices(req:Request):
        with db() as c:
            who,actor=identity(req,c);chat_users.admin(c,who,actor)
            return [{'id':r['id'],'name':r['name']} for r in channels(c,who,actor) if r['kind'] not in ['pair','group']]
    @app.post('/api/chat/hooks')
    async def create(req:Request):
        data=await req.json()
        with db() as c:
            who,actor=identity(req,c);chat_users.admin(c,who,actor);name,description,avatar,mime=validate(data)
            cid=data.get('channel')
            if not isinstance(cid,str):raise HTTPException(422,'Choose a channel.')
            room=channel(c,who,actor,cid)
            if room['kind'] in ['pair','group']:raise HTTPException(422,'Choose a channel.')
            hid=secrets.token_hex(12);token=secrets.token_hex(24)
            c.execute('INSERT INTO tw_chat_hooks VALUES(?,?,?,?,?,?,?,?,?,?)',(who,hid,cid,actor,name,description,token,time.time(),avatar,mime))
            return output(c,who,actor,get(c,who,hid),req)
    @app.patch('/api/chat/hooks/{hid}')
    async def update(hid:str,req:Request):
        data=await req.json()
        with db() as c:
            who,actor=identity(req,c);chat_users.admin(c,who,actor);row=get(c,who,hid);name,description,avatar,mime=validate(data,row)
            if 'channel' in data and data['channel']!=row['channel']:raise HTTPException(422,'The channel cannot be changed after creation.')
            c.execute('UPDATE tw_chat_hooks SET name=?,description=?,avatar=?,avatar_type=? WHERE owner=? AND id=?',(name,description,avatar,mime,who,hid))
            c.execute('UPDATE tw_chat_bot_messages SET name=? WHERE owner=? AND hook=?',(name,who,hid))
            return output(c,who,actor,get(c,who,hid),req)
    @app.delete('/api/chat/hooks/{hid}')
    def delete(hid:str,req:Request):
        with db() as c:
            who,actor=identity(req,c);chat_users.admin(c,who,actor);get(c,who,hid)
            c.execute('DELETE FROM tw_chat_hooks WHERE owner=? AND id=?',(who,hid))
        return {'ok':True}
    @app.get('/api/chat/hooks/{hid}/avatar')
    def avatar(hid:str,req:Request):
        with db() as c:
            who,actor=identity(req,c);row=get(c,who,hid)
            try:chat_users.admin(c,who,actor)
            except HTTPException:channel(c,who,actor,row['channel'])
            if not row['avatar']:raise HTTPException(404,'Avatar not found.')
            return Response(row['avatar'],media_type=row['avatar_type'],headers={'Cache-Control':'no-store'})
    @app.post('/api/chat/incoming/{token}')
    async def incoming(token:str,req:Request):
        raw=bytearray()
        async for part in req.stream():
            raw.extend(part)
            if len(raw)>100000:raise HTTPException(413,'Message is too large.')
        try:data=json.loads(raw)
        except (ValueError,UnicodeDecodeError):raise HTTPException(422,'Send a JSON message body.')
        if not isinstance(data,dict):raise HTTPException(422,'Send a JSON message body.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM tw_chat_hooks WHERE token=?',(token,)).fetchone()
            if not row:raise HTTPException(404,'Incoming Hook not found.')
            return {'id':receive(c,row,data.get('body'))}

    def ingest_mail():
        # Query only this instance's actual hook addresses. Never delete shared mail.
        with db() as c:hooks=[dict(r) for r in c.execute('SELECT owner,id,token FROM tw_chat_hooks')]
        delivered=0
        http=build_opener(ProxyHandler({}))
        def fetch(path):
            with http.open('http://127.0.0.1:8025'+path,timeout=10) as response:return response.read()
        if hooks:
            for hook in hooks:
                address=hook['token']+'@'+DOMAIN;start=0
                while True:
                    items=json.loads(fetch('/api/v1/search?'+urlencode({'query':'to:'+address,'start':start,'limit':100})))['messages']
                    for mail in items:
                        with db() as c:
                            if c.execute('SELECT 1 FROM tw_chat_hook_mail WHERE owner=? AND hook=? AND mail=?',(hook['owner'],hook['id'],mail['ID'])).fetchone():continue
                        raw=fetch('/api/v1/message/'+mail['ID']+'/raw');parsed=BytesParser(policy=policy.default).parsebytes(raw)
                        part=parsed.get_body(preferencelist=('plain',)) if parsed.is_multipart() else parsed
                        text=part.get_content() if part and part.get_content_type()=='text/plain' and part.get_content_disposition()!='attachment' else ''
                        with db() as c:
                            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM tw_chat_hooks WHERE owner=? AND id=? AND token=?',(hook['owner'],hook['id'],hook['token'])).fetchone()
                            if not row:continue
                            if not c.execute('INSERT OR IGNORE INTO tw_chat_hook_mail VALUES(?,?,?,?)',(hook['owner'],hook['id'],mail['ID'],'received')).rowcount:continue
                            try:receive(c,row,text)
                            except HTTPException as error:
                                if error.status_code!=422:raise
                                c.execute("UPDATE tw_chat_hook_mail SET state='invalid-plain-body' WHERE owner=? AND hook=? AND mail=?",(hook['owner'],hook['id'],mail['ID']))
                            else:delivered+=1
                    if len(items)<100:break
                    start+=len(items)
        return delivered
    task=None
    @app.on_event('startup')
    async def start():
        nonlocal task
        async def loop():
            while True:
                try:await asyncio.to_thread(ingest_mail)
                except Exception as error:logging.getLogger(__name__).error('Local incoming email processing failed: %s',type(error).__name__)
                await asyncio.sleep(5)
        task=asyncio.create_task(loop())
    @app.on_event('shutdown')
    async def stop():
        if task:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    return ingest_mail
