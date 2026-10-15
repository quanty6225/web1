"""Private direct/group conversations, stable pairs and per-actor history clearing."""
import json,re,secrets,time
from fastapi import HTTPException,Request
import chat_mentions,chat_presence

SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_pairs(owner TEXT NOT NULL,pair TEXT NOT NULL,channel TEXT NOT NULL,PRIMARY KEY(owner,pair),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_history(owner TEXT NOT NULL,channel TEXT NOT NULL,actor TEXT NOT NULL,cutoff REAL NOT NULL DEFAULT 0,previous REAL NOT NULL DEFAULT 0,nonce TEXT,expires REAL,PRIMARY KEY(owner,channel,actor),FOREIGN KEY(owner,channel,actor) REFERENCES tw_chat_members(owner,channel,actor) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_roles(owner TEXT NOT NULL,actor TEXT NOT NULL,role TEXT NOT NULL,PRIMARY KEY(owner,actor),FOREIGN KEY(actor) REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE);
'''
KINDS=['pair','group']
def role(c,who,actor):
    if who==actor:return 'admin'
    row=c.execute('SELECT role FROM tw_chat_roles WHERE owner=? AND actor=?',(who,actor)).fetchone()
    return row['role'] if row else 'user'
def cutoff(c,who,cid,actor):
    row=c.execute('SELECT cutoff FROM tw_chat_history WHERE owner=? AND channel=? AND actor=?',(who,cid,actor)).fetchone()
    return row['cutoff'] if row else 0

def title(c,who,actor,cid,kind):
    from chat_local import people
    ids={r['actor'] for r in c.execute('SELECT actor FROM tw_chat_members WHERE owner=? AND channel=?',(who,cid))}
    others=[p['name'] for p in people(c,who) if p['id'] in ids and p['id']!=actor]
    if kind=='pair':return others[0] if others else 'Former member'
    names=[name.split()[0] if name.split() else name for name in others]
    if not names:return 'You'
    if len(names)==1:return 'You & '+names[0]
    if len(names)>4:return ', '.join(names[:3])+' & '+str(len(names)-3)+' others'
    return ', '.join(names[:-1])+' & '+names[-1]

def path(row):return '/workspace/chat/'+('conversations/' if row['kind'] in KINDS else 'channels/')+row['id']
def pair(c,who,a,b):
    row=c.execute('SELECT channel FROM tw_chat_pairs WHERE owner=? AND pair=?',(who,json.dumps(sorted([a,b])))).fetchone()
    return row['channel'] if row else None

def install(app,db,identity,serialize):
    from chat_local import people,channel,add_message
    import chat_files
    with db() as c:c.executescript(SCHEMA)

    @app.get('/api/chat/direct/{person}')
    def direct(person:str,req:Request):
        with db() as c:
            who,actor=identity(req,c);target=next((p for p in people(c,who) if p['id']==person and p['id']!=actor),None)
            if not target:raise HTTPException(404,'Person not found.')
            cid=pair(c,who,actor,person)
            if role(c,who,actor)=='guest' and not cid:raise HTTPException(403,'Guests cannot start conversations.')
            if cid:channel(c,who,actor,cid,member=True)
            return {'person':target,'conversation':cid}

    @app.post('/api/chat/conversations')
    async def create(req:Request):
        try:data=await req.json()
        except ValueError:raise HTTPException(422,'Choose people and enter a message.')
        if not isinstance(data,dict) or not isinstance(data.get('body',''),str):raise HTTPException(422,'Enter a valid message.')
        with db() as c:
            who,actor=identity(req,c);persons=people(c,who);members=data.get('members',[]);text=data.get('body','');mentions=data.get('mentions',[])
            if not isinstance(members,list) or any(not isinstance(x,str) for x in members):raise HTTPException(422,'Choose valid people.')
            chosen=set(members)
            if not chosen:
                for p in persons:
                    if p['id']!=actor and re.search(r'(?<!\w)@'+re.escape(p['handle'])+r'(?!\w)',text):chosen.add(p['id'])
                if re.search(r'(?<!\w)@all\b',text):chosen.update(p['id'] for p in persons if p['id']!=actor)
                elif re.search(r'(?<!\w)@online\b',text):chosen.update(p['id'] for p in persons if p['id']!=actor and chat_presence.status(c,who,p['id'])=='Online')
            if not chosen or actor in chosen or not chosen<={p['id'] for p in persons}:raise HTTPException(422,'Mention at least one other person in this workspace.')
            cid=pair(c,who,actor,next(iter(chosen))) if len(chosen)==1 else None
            if role(c,who,actor)=='guest' and not cid:raise HTTPException(403,'Guests cannot start conversations.')
            drafts=data.get('attachments',[])
            if not isinstance(drafts,list) or len(drafts)>1 or any(not isinstance(x,str) for x in drafts):raise HTTPException(422,'Choose a valid attachment.')
            files=[]
            for fid in drafts:
                row=c.execute('SELECT * FROM tw_chat_draft_files WHERE owner=? AND actor=? AND id=?',(who,actor,fid)).fetchone()
                if not row:raise HTTPException(404,'Pending attachment not found.')
                files.append(dict(row))
            if not text.strip() and not files or len(text)>20000:raise HTTPException(422,'Enter a message of up to 20,000 characters.')
            kind='pair' if len(chosen)==1 and not re.search(r'(?<!\w)@(all|online)\b',text) else 'group'
            if kind=='group':cid=None
            if role(c,who,actor)=='guest' and not cid:raise HTTPException(403,'Guests cannot start conversations.')
            if cid:channel(c,who,actor,cid,member=True)
            else:
                cid=secrets.token_hex(12)
                c.execute('INSERT INTO tw_chat_channels VALUES(?,?,?,?,?,?,?,?,?)',(who,cid,'','',kind,actor,'',0,time.time()))
                for person in sorted(chosen|{actor}):c.execute('INSERT INTO tw_chat_members VALUES(?,?,?,?,?)',(who,cid,person,0,0))
                if kind=='pair':c.execute('INSERT INTO tw_chat_pairs VALUES(?,?,?)',(who,json.dumps(sorted(chosen|{actor})),cid))
            # Resolve typed handles to stable IDs, including group mentions, before commit.
            if not isinstance(mentions,list) or any(not isinstance(m,str) for m in mentions):raise HTTPException(422,'Choose valid mentions.')
            tokens=list(dict.fromkeys(mentions+[p['id'] for p in persons if p['id'] in chosen and re.search(r'(?<!\w)@'+re.escape(p['handle'])+r'(?!\w)',text)]+[m for m in ['all','online'] if re.search(r'(?<!\w)@'+m+r'\b',text)]))
            mid=add_message(c,who,cid,actor,text or files[0]['name'],kind='message' if text.strip() else 'file',mentions=tokens)
            for f in files:
                c.execute('INSERT INTO tw_chat_files VALUES(?,?,?,?,?,?,?,?,?)',(who,f['id'],cid,actor,mid,f['name'],f['type'],f['size'],f['digest']))
                c.execute('DELETE FROM tw_chat_draft_files WHERE owner=? AND id=?',(who,f['id']))
            conversation=channel(c,who,actor,cid)
            return {'id':cid,'message':mid,'kind':conversation['kind'],'url':path(conversation)}

    @app.post('/api/chat/conversations/{cid}/clear')
    def clear(cid:str,req:Request):
        with db() as c:
            who,actor=identity(req,c);conversation=channel(c,who,actor,cid,member=True)
            if conversation['kind']!='pair':raise HTTPException(422,'Only direct conversation history can be cleared.')
            last=c.execute('SELECT MAX(created) FROM tw_chat_messages WHERE owner=? AND channel=?',(who,cid)).fetchone()[0] or 0
            previous=cutoff(c,who,cid,actor);nonce=secrets.token_urlsafe(24)
            c.execute('INSERT INTO tw_chat_history VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner,channel,actor) DO UPDATE SET cutoff=excluded.cutoff,previous=excluded.previous,nonce=excluded.nonce,expires=excluded.expires',(who,cid,actor,last,previous,nonce,time.time()+5))
            c.execute('UPDATE tw_chat_members SET last_read=? WHERE owner=? AND channel=? AND actor=?',(time.time(),who,cid,actor))
            return {'undo':nonce,'message':'Conversation history successfully cleared.'}

    @app.post('/api/chat/conversations/{cid}/clear/undo')
    async def undo(cid:str,req:Request):
        try:data=await req.json()
        except ValueError:raise HTTPException(422,'Choose a valid undo action.')
        with db() as c:
            who,actor=identity(req,c);channel(c,who,actor,cid,member=True)
            row=c.execute('SELECT * FROM tw_chat_history WHERE owner=? AND channel=? AND actor=?',(who,cid,actor)).fetchone()
            if not row or not row['nonce'] or not isinstance(data,dict) or data.get('undo')!=row['nonce'] or row['expires']<time.time():raise HTTPException(409,'Undo is no longer available.')
            c.execute('UPDATE tw_chat_history SET cutoff=previous,nonce=NULL,expires=NULL WHERE owner=? AND channel=? AND actor=?',(who,cid,actor))
            return {'ok':True}
