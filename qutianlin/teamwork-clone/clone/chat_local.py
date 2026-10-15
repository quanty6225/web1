"""Local, workspace-isolated Teamwork Chat. Source records are seeded once only."""
import json,secrets,time
import chat_mentions
import chat_files
import chat_appearance
import chat_settings
import chat_profile
import chat_presence
import chat_delivery
import chat_status
import chat_conversations
import chat_users
import chat_hooks
import chat_productivity
from chat_markdown import render as markdown_render
from fastapi import HTTPException,Request,Query
from fastapi.responses import HTMLResponse,RedirectResponse
from pathlib import Path
GIFS={g['original_url']:g for g in json.loads((Path(__file__).parent/'static/chat-gifs.json').read_text())} if (Path(__file__).parent/'static/chat-gifs.json').exists() else {}
EFFECT='Send Chat message to channel'
SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_channels(owner TEXT NOT NULL,id TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,kind TEXT NOT NULL,creator TEXT NOT NULL,project_id TEXT NOT NULL DEFAULT '',is_default INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,PRIMARY KEY(owner,id));
CREATE TABLE IF NOT EXISTS tw_chat_members(owner TEXT NOT NULL,channel TEXT NOT NULL,actor TEXT NOT NULL,last_read REAL NOT NULL DEFAULT 0,starred INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,channel,actor),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_messages(owner TEXT NOT NULL,id TEXT NOT NULL,channel TEXT NOT NULL,author TEXT NOT NULL,body TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL,edited REAL,automation_id TEXT NOT NULL DEFAULT '',PRIMARY KEY(owner,id),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_bookmarks(owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL,PRIMARY KEY(owner,message,actor),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_users(owner TEXT NOT NULL,actor TEXT NOT NULL,PRIMARY KEY(owner,actor));
'''

def people(c,who):
 return [{**dict(r),**chat_profile.identity_for(c,who,r['id'],r['name'])} for r in c.execute('SELECT account_id AS id,display_name AS name FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?) ORDER BY account_id',(who,who)).fetchall() if chat_users.enabled(c,who,r['id'])]
def project_access(c,who,actor,pid):
 if not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,pid)).fetchone():return False
 if actor==who:return True
 policy=c.execute('SELECT projects FROM tw_member_policies WHERE workspace_owner=? AND account=?',(who,actor)).fetchone()
 return not policy or pid in json.loads(policy['projects'])
def channel(c,who,actor,cid,member=False):
 if not chat_users.enabled(c,who,actor):raise HTTPException(403,'Your access to Teamwork Chat has been removed.')
 r=c.execute('SELECT * FROM tw_chat_channels WHERE owner=? AND id=?',(who,cid)).fetchone()
 if not r:raise HTTPException(404,'Channel not found.')
 if r['kind']=='project' and project_access(c,who,actor,r['project_id']):c.execute('INSERT OR IGNORE INTO tw_chat_members VALUES(?,?,?,?,?)',(who,cid,actor,0,0))
 joined=c.execute('SELECT * FROM tw_chat_members WHERE owner=? AND channel=? AND actor=?',(who,cid,actor)).fetchone()
 if r['kind'] in ['private','pair','group'] and not joined or r['kind']=='project' and not project_access(c,who,actor,r['project_id']):raise HTTPException(404,'Channel not found.')
 if chat_conversations.role(c,who,actor)=='guest' and not joined:raise HTTPException(404,'Channel not found.')
 if member and not joined:raise HTTPException(403,'Join this channel before sending a message.')
 result={**dict(r),'avatar':chat_appearance.avatar(c,who,cid)}
 if r['kind'] in chat_conversations.KINDS:result['name']=chat_conversations.title(c,who,actor,cid,r['kind'])
 result['url']=chat_conversations.path(result)
 return result
def channels(c,who,actor):
 rows=[]
 for r in c.execute('SELECT id FROM tw_chat_channels WHERE owner=? ORDER BY created,id',(who,)).fetchall():
  try:x=channel(c,who,actor,r['id'])
  except HTTPException:continue
  m=c.execute('SELECT * FROM tw_chat_members WHERE owner=? AND channel=? AND actor=?',(who,x['id'],actor)).fetchone();x.update(joined=bool(m),starred=bool(m and m['starred']),members=[r['actor'] for r in c.execute('SELECT actor FROM tw_chat_members WHERE owner=? AND channel=?',(who,x['id'])) if any(p['id']==r['actor'] for p in people(c,who))],unread=bool(m and c.execute('SELECT 1 FROM tw_chat_messages WHERE owner=? AND channel=? AND created>? AND author!=?',(who,x['id'],m['last_read'],actor)).fetchone()));last=c.execute('SELECT MAX(created) FROM tw_chat_messages WHERE owner=? AND channel=?',(who,x['id'])).fetchone()[0];x['last_activity']=last or x['created'];rows.append(x)
 return sorted(rows,key=lambda x:(x['last_activity'],x['id']),reverse=True)
def body(value):
 if not isinstance(value,str) or not value.strip() or len(value)>20000:raise HTTPException(422,'Enter a message of up to 20,000 characters.')
 return value.strip()
def add_message(c,who,cid,actor,text,kind='message',automation_id='',mid=None,created=None,mentions=None):
 mid=mid or secrets.token_hex(12);c.execute('INSERT INTO tw_chat_messages VALUES(?,?,?,?,?,?,?,?,?)',(who,mid,cid,actor,body(text),kind,created if created is not None else time.time(),None,automation_id))
 if kind in ['message','file']:chat_mentions.apply(c,who,cid,actor,mid,text,mentions or [])
 return mid
def validate_action(action):
 if action['effect']!=EFFECT:return
 if not isinstance(action.get('channel_id'),str) or not action['channel_id']:raise HTTPException(422,'Choose a Chat channel.')
 action['message']=body(action.get('message'))
def validate_action_scope(c,who,action):
 if action['effect']==EFFECT:channel(c,who,who,action['channel_id'],member=True)
def execute(c,who,action,rule_id):
 try:channel(c,who,who,action['channel_id'],member=True)
 except HTTPException:return
 add_message(c,who,action['channel_id'],who,action['message'],automation_id=rule_id)

def install(app,db,owner,account,demo,uploads,workspace):
 with db() as c:
  c.executescript(SCHEMA+chat_mentions.SCHEMA+chat_files.SCHEMA+chat_appearance.SCHEMA+chat_profile.SCHEMA+chat_presence.SCHEMA+chat_delivery.SCHEMA+chat_conversations.SCHEMA+chat_users.SCHEMA+chat_status.SCHEMA)
  if demo and not c.execute("SELECT 1 FROM tw_seed_state WHERE key='chat-demo-v1'").fetchone():
   c.execute('INSERT INTO tw_chat_channels VALUES(?,?,?,?,?,?,?,?,?)',(demo,'44055','Playground',"Here's a place where anything goes. Mention a teammate, drop a gif, get comfortable 🙌",'public',demo,'',1,1791886644))
   c.execute('INSERT INTO tw_chat_members VALUES(?,?,?,?,?)',(demo,'44055',demo,1791886646,0));c.execute('INSERT INTO tw_chat_users VALUES(?,?)',(demo,demo))
   add_message(c,demo,'44055',demo,'Sam created the channel.','system',mid='8132602',created=1791886645);c.execute("INSERT INTO tw_seed_state VALUES('chat-demo-v1')")
 def identity(req,c):
  who=owner(req);actor=account(req)['account_id']
  if not chat_users.enabled(c,who,actor):raise HTTPException(403,'Your access to Teamwork Chat has been removed.')
  if not c.execute('SELECT 1 FROM tw_chat_users WHERE owner=? AND actor=?',(who,actor)).fetchone():
   for r in c.execute("SELECT * FROM tw_chat_channels WHERE owner=? AND is_default=1 AND kind='public'",(who,)).fetchall():c.execute('INSERT OR IGNORE INTO tw_chat_members VALUES(?,?,?,?,?)',(who,r['id'],actor,0,0))
   c.execute('INSERT OR IGNORE INTO tw_chat_users VALUES(?,?)',(who,actor))
  c.execute('INSERT INTO tw_chat_presence VALUES(?,?,?) ON CONFLICT(owner,actor) DO UPDATE SET seen=excluded.seen',(who,actor,time.time()))
  c.execute('INSERT INTO tw_chat_runtime_origins VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET origin=excluded.origin',(who,str(req.base_url).rstrip('/')))
  return who,actor
 file_root=chat_files.install(app,db,identity,uploads)
 @app.post('/api/chat/preview')
 async def preview(req:Request):
  account(req);d=await req.json();text=d.get('body','')
  if not isinstance(text,str) or len(text)>20000:raise HTTPException(422,'Enter up to 20,000 characters.')
  return {'html':markdown_render(text)}
 def serialize(c,who,actor,r):
  x=dict(r);x.pop('owner',None);x['reactions']=chat_productivity.reactions(c,who,actor,x['id']);x['attachments']=chat_files.attachments(c,who,x['id']);x['gif']=GIFS.get(x['body'].strip());x['body']='' if x['kind']=='file' else x['body'];x['body_html']=markdown_render(x['body']);x['author_name']=(c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(x['author'],)).fetchone() or ['Former member'])[0];x['bookmarked']=bool(c.execute('SELECT 1 FROM tw_chat_bookmarks WHERE owner=? AND message=? AND actor=?',(who,x['id'],actor)).fetchone());x['deletable']=(x['author']==actor or chat_conversations.role(c,who,actor)=='admin') and x['kind'] in ['message','file','bot'] and not x['automation_id'];x['editable']=x['author']==actor and x['kind'] in ['message','file'] and not x['automation_id'];x['mention_labels']={v['actor']:v['label'] for v in c.execute('SELECT actor,label FROM tw_chat_mention_tokens WHERE owner=? AND message=?',(who,x['id']))};x['mentions']=list(dict.fromkeys(r['actor'] if r['kind']=='direct' else r['kind'] for r in c.execute('SELECT actor,kind FROM tw_chat_mentions WHERE owner=? AND message=?',(who,x['id']))));return chat_hooks.decorate(c,who,x)
 def message(c,who,actor,mid):
  r=c.execute('SELECT * FROM tw_chat_messages WHERE owner=? AND id=?',(who,mid)).fetchone()
  if not r:raise HTTPException(404,'Message not found.')
  channel(c,who,actor,r['channel'])
  if r['created']<=chat_conversations.cutoff(c,who,r['channel'],actor):raise HTTPException(404,'Message not found.')
  return r
 @app.get('/api/chat')
 def state(req:Request):
  with db() as c:
   who,actor=identity(req,c);role=chat_conversations.role(c,who,actor);rooms=channels(c,who,actor);known={actor}
   for room in rooms:
    if room['joined']:known.update(room['members'])
   persons=[{**p,'status':chat_presence.status(c,who,p['id']),'custom_status':chat_status.custom(c,who,p['id']),'dnd':chat_status.dnd(c,who,p['id']),'can_converse':role!='guest' or bool(chat_conversations.pair(c,who,actor,p['id']))} for p in people(c,who) if role!='guest' or p['id'] in known or chat_conversations.pair(c,who,actor,p['id'])]
   return {'actor':actor,'owner':who,'chat_role':role,'dnd':chat_status.dnd(c,who,actor),'people':persons,'channels':rooms,'settings':chat_settings.settings(c,who,actor),'timezone':chat_settings.timezone(c,who,actor)}
 @app.post('/api/chat/channels')
 async def create(req:Request):
  d=await req.json()
  with db() as c:
   who,actor=identity(req,c);name=str(d.get('name','')).strip();kind=d.get('kind','public');description=str(d.get('description',''));pid=d.get('project_id','')
   if chat_conversations.role(c,who,actor)=='guest':raise HTTPException(403,'Guests cannot create channels.')
   if not name or len(name)>100 or len(description)>5000 or kind not in ['public','private','project']:raise HTTPException(422,'Enter a channel name and choose a valid channel type.')
   if kind=='project' and not project_access(c,who,actor,pid):raise HTTPException(403,'Project administrator access is required.')
   if kind=='project' and c.execute("SELECT 1 FROM tw_chat_channels WHERE owner=? AND project_id=? AND kind='project'",(who,pid)).fetchone():raise HTTPException(409,'This project already has a linked channel.')
   members=d.get('members',[])
   if not isinstance(members,list) or any(p not in [m['id'] for m in people(c,who)] for p in members):raise HTTPException(422,'Choose users in this workspace.')
   cid=secrets.token_hex(12);c.execute('INSERT INTO tw_chat_channels VALUES(?,?,?,?,?,?,?,?,?)',(who,cid,name,description,kind,actor,pid if kind=='project' else '',int(d.get('is_default') is True and kind=='public'),time.time()))
   if 'avatar' in d:chat_appearance.save_avatar(c,who,cid,d['avatar'])
   if kind=='project':members=[p['id'] for p in people(c,who) if project_access(c,who,p['id'],pid)]
   for person in set([actor]+members):
    if kind=='project' and not project_access(c,who,person,pid):raise HTTPException(422,'Selected user cannot access the linked project.')
    c.execute('INSERT INTO tw_chat_members VALUES(?,?,?,?,?)',(who,cid,person,0,0))
   add_message(c,who,cid,actor,account(req)['display_name']+' created the channel.','system');return {'id':cid}
 @app.get('/api/chat/channels/{cid}')
 def detail(cid:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);x=channel(c,who,actor,cid);x['messages']=[serialize(c,who,actor,r) for r in c.execute('SELECT * FROM tw_chat_messages WHERE owner=? AND channel=? AND created>? ORDER BY created,id',(who,cid,chat_conversations.cutoff(c,who,cid,actor)))];return x
 @app.patch('/api/chat/channels/{cid}')
 async def update(cid:str,req:Request):
  d=await req.json()
  with db() as c:
   who,actor=identity(req,c);x=channel(c,who,actor,cid)
   if chat_conversations.role(c,who,actor)=='guest' or actor!=x['creator'] and chat_conversations.role(c,who,actor)!='admin':raise HTTPException(403,'Only channel administrators can edit this channel.')
   if x['kind']=='pair':raise HTTPException(403,'Direct conversations cannot be converted or edited.')
   name=str(d.get('name',x['name'])).strip();description=str(d.get('description',x['description']))
   if not name or len(name)>100 or len(description)>5000:raise HTTPException(422,'Enter a valid name and description.')
   if x['kind']=='group' and c.execute('SELECT count(*) FROM tw_chat_members WHERE owner=? AND channel=?',(who,cid)).fetchone()[0]<3:raise HTTPException(422,'A conversation needs at least three people before conversion.')
   kind=d.get('kind',x['kind']);pid=d.get('project_id',x['project_id'])
   if kind not in ['public','private','project']:raise HTTPException(422,'Choose a valid channel type.')
   if kind=='project':
    if not project_access(c,who,actor,pid):raise HTTPException(403,'Project administrator access is required.')
    if c.execute("SELECT 1 FROM tw_chat_channels WHERE owner=? AND project_id=? AND kind='project' AND id!=?",(who,pid,cid)).fetchone():raise HTTPException(409,'This project already has a linked channel.')
   if kind=='project':
    for person in people(c,who):
     if project_access(c,who,person['id'],pid):c.execute('INSERT OR IGNORE INTO tw_chat_members VALUES(?,?,?,?,?)',(who,cid,person['id'],0,0))
   if 'avatar' in d:chat_appearance.save_avatar(c,who,cid,d['avatar'])
   c.execute('UPDATE tw_chat_channels SET name=?,description=?,kind=?,project_id=?,is_default=? WHERE owner=? AND id=?',(name,description,kind,pid if kind=='project' else '',int(d.get('is_default',bool(x['is_default'])) is True and kind=='public'),who,cid));return {'ok':True}
 @app.put('/api/chat/channels/{cid}/owner')
 async def transfer_owner(cid:str,req:Request):
  d=await req.json()
  with db() as c:
   who,actor=identity(req,c);x=channel(c,who,actor,cid)
   if chat_conversations.role(c,who,actor)=='guest' or actor!=x['creator'] and chat_conversations.role(c,who,actor)!='admin':raise HTTPException(403,'Only channel administrators can change the owner.')
   if x['kind']=='pair':raise HTTPException(403,'Direct conversations have no transferable owner.')
   target=d.get('actor')
   if target not in [p['id'] for p in people(c,who)]:raise HTTPException(422,'Choose a channel member.')
   channel(c,who,target,cid,member=True);c.execute('UPDATE tw_chat_channels SET creator=? WHERE owner=? AND id=?',(target,who,cid));return {'ok':True}
 @app.delete('/api/chat/channels/{cid}')
 def delete_channel(cid:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);x=channel(c,who,actor,cid)
   if chat_conversations.role(c,who,actor)=='guest' or actor!=x['creator'] and chat_conversations.role(c,who,actor)!='admin':raise HTTPException(403,'Only channel administrators can delete this channel.')
   if x['kind'] in ['pair','project']:raise HTTPException(403,'This conversation cannot be deleted.')
   files=chat_files.paths(c,file_root,who,cid=cid);chat_mentions.clean_channel_notifications(c,who,cid);c.execute('DELETE FROM tw_chat_channels WHERE owner=? AND id=?',(who,cid))
  for path in files:path.unlink(missing_ok=True)
  return {'ok':True}
 @app.put('/api/chat/channels/{cid}/membership')
 async def membership(cid:str,req:Request):
  d=await req.json()
  with db() as c:
   who,actor=identity(req,c);x=channel(c,who,actor,cid);person=d.get('actor',actor)
   if x['kind']=='pair':raise HTTPException(403,'Direct conversation members cannot be changed.')
   if x['kind']=='project':raise HTTPException(403,'Project channel membership follows the project.')
   if person==x['creator'] and d.get('joined') is False:raise HTTPException(403,'The creator cannot leave; transfer ownership first.')
   if chat_conversations.role(c,who,actor)=='guest' and not (person==actor and d.get('joined') is False):raise HTTPException(403,'Guests cannot manage conversation members.')
   if person!=actor and actor!=x['creator'] and chat_conversations.role(c,who,actor)!='admin':raise HTTPException(403,'Only channel administrators can manage members.')
   if person not in [p['id'] for p in people(c,who)]:raise HTTPException(422,'Choose a user in this workspace.')
   if x['kind']=='project' and not project_access(c,who,person,x['project_id']):raise HTTPException(403,'This user cannot access the linked project.')
   if d.get('joined') is True:c.execute('INSERT OR IGNORE INTO tw_chat_members VALUES(?,?,?,?,?)',(who,cid,person,0,0))
   elif d.get('joined') is False:c.execute('DELETE FROM tw_chat_members WHERE owner=? AND channel=? AND actor=?',(who,cid,person))
   else:raise HTTPException(422,'Choose whether to join or leave.')
   return {'ok':True}
 @app.put('/api/chat/channels/{cid}/state')
 async def read(cid:str,req:Request):
  d=await req.json()
  with db() as c:
   who,actor=identity(req,c);channel(c,who,actor,cid,member=True)
   if d.get('read') is True:c.execute('UPDATE tw_chat_members SET last_read=? WHERE owner=? AND channel=? AND actor=?',(time.time(),who,cid,actor))
   if 'starred' in d:
    if type(d['starred']) is not bool:raise HTTPException(422,'Choose a valid starred state.')
    c.execute('UPDATE tw_chat_members SET starred=? WHERE owner=? AND channel=? AND actor=?',(int(d['starred']),who,cid,actor))
   return {'ok':True}
 @app.post('/api/chat/channels/{cid}/messages')
 async def send(cid:str,req:Request):
  d=await req.json()
  if 'body' in d and not isinstance(d['body'],str):raise HTTPException(422,'Enter a valid message.')
  with db() as c:
   who,actor=identity(req,c);channel(c,who,actor,cid,member=True);files=chat_files.validate(c,who,cid,actor,d.get('attachments',[]));text=d.get('body') or (', '.join(f['name'] for f in files));kind='file' if files and not d.get('body','').strip() else 'message';mid=add_message(c,who,cid,actor,text,kind=kind,mentions=d.get('mentions',[]))
   for file in files:
    if c.execute('UPDATE tw_chat_files SET message=? WHERE owner=? AND id=? AND message IS NULL',(mid,who,file['id'])).rowcount!=1:raise HTTPException(409,'An attachment was already sent.')
   return serialize(c,who,actor,message(c,who,actor,mid))
 @app.get('/api/chat/messages/{mid}')
 def get_message(mid:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);return serialize(c,who,actor,message(c,who,actor,mid))
 @app.patch('/api/chat/messages/{mid}')
 async def edit_message(mid:str,req:Request):
  d=await req.json();removed=[]
  with db() as c:
   who,actor=identity(req,c);x=message(c,who,actor,mid);channel(c,who,actor,x['channel'],member=True)
   if x['author']!=actor or x['kind'] not in ['message','file'] or x['automation_id']:raise HTTPException(403,'This message cannot be edited by this user.')
   current=chat_files.attachments(c,who,mid);ids=d.get('attachments',[f['id'] for f in current]);same=ids==[f['id'] for f in current];files=current if same else chat_files.validate(c,who,x['channel'],actor,ids)
   text=d.get('body','')
   if not isinstance(text,str):raise HTTPException(422,'Enter a valid message.')
   kind='file' if files and not text.strip() else 'message';text=body(text or ', '.join(f['name'] for f in files));chat_mentions.apply(c,who,x['channel'],actor,mid,text,d.get('mentions',[]),notify=False)
   if not same:
    removed=chat_files.paths(c,file_root,who,mid=mid);c.execute('DELETE FROM tw_chat_files WHERE owner=? AND message=?',(who,mid))
    for file in files:
     if c.execute('UPDATE tw_chat_files SET message=? WHERE owner=? AND id=? AND message IS NULL',(mid,who,file['id'])).rowcount!=1:raise HTTPException(409,'An attachment was already sent.')
   c.execute('UPDATE tw_chat_messages SET body=?,edited=?,kind=? WHERE owner=? AND id=?',(text,time.time(),kind,who,mid));result=serialize(c,who,actor,message(c,who,actor,mid))
  for path in removed:path.unlink(missing_ok=True)
  return result
 @app.delete('/api/chat/messages/{mid}')
 def delete_message(mid:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);x=message(c,who,actor,mid);channel(c,who,actor,x['channel'],member=True)
   if x['kind']=='system' or x['author']!=actor and chat_conversations.role(c,who,actor)!='admin':raise HTTPException(403,'This message cannot be deleted by this user.')
   files=chat_files.paths(c,file_root,who,mid=mid);chat_mentions.clean_message_notifications(c,who,mid);c.execute('DELETE FROM tw_chat_messages WHERE owner=? AND id=?',(who,mid))
  for path in files:path.unlink(missing_ok=True)
  return {'ok':True}
 @app.put('/api/chat/messages/{mid}/bookmark')
 async def bookmark(mid:str,req:Request):
  d=await req.json()
  with db() as c:
   who,actor=identity(req,c);message(c,who,actor,mid)
   if d.get('bookmarked') is True:c.execute('INSERT OR IGNORE INTO tw_chat_bookmarks VALUES(?,?,?)',(who,mid,actor))
   elif d.get('bookmarked') is False:c.execute('DELETE FROM tw_chat_bookmarks WHERE owner=? AND message=? AND actor=?',(who,mid,actor))
   else:raise HTTPException(422,'Choose a valid bookmarked state.')
   return {'ok':True}
 @app.get('/api/chat/search-history')
 def search_history(req:Request):
  actor=account(req)['account_id'];key='chat_recent_searches:'+owner(req)
  with db() as c:r=c.execute("SELECT value FROM tw_preferences WHERE owner=? AND key=?",(actor,key)).fetchone()
  return json.loads(r['value']) if r else []
 @app.get('/api/chat/search')
 def search(req:Request,q:str='',view:str='search',channel_id:str=Query('',alias='channel'),author:str='',date_from:str=Query('',alias='from'),date_to:str=Query('',alias='to'),attachments:bool=False):
  from datetime import date,datetime,time as day_time,timedelta
  from zoneinfo import ZoneInfo
  if view not in ['search','bookmarked','mentions']:raise HTTPException(422,'Choose a valid message view.')
  with db() as c:
   who,actor=identity(req,c);allowed={r['id'] for r in channels(c,who,actor)};rows=[];zone=ZoneInfo(chat_settings.timezone(c,who,actor))
   try:
    start=datetime.combine(date.fromisoformat(date_from),day_time.min,zone).timestamp() if date_from else None;end=datetime.combine(date.fromisoformat(date_to)+timedelta(days=1),day_time.min,zone).timestamp() if date_to else None
   except ValueError:raise HTTPException(422,'Choose valid From and To dates.')
   if start is not None and end is not None and start>=end:raise HTTPException(422,'The To date must not precede the From date.')
   if channel_id:allowed.intersection_update([channel_id])
   if q.strip() and view=='search':
    key='chat_recent_searches:'+who;old=c.execute("SELECT value FROM tw_preferences WHERE owner=? AND key=?",(actor,key)).fetchone();recent=json.loads(old['value']) if old else [];recent=[q.strip()]+[x for x in recent if x!=q.strip()];c.execute("INSERT INTO tw_preferences VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value",(actor,key,json.dumps(recent[:10])))
   for r in c.execute('SELECT * FROM tw_chat_messages WHERE owner=? ORDER BY created DESC,id',(who,)):
    if r['channel'] not in allowed or author and r['author']!=author:continue
    if start is not None and r['created']<start or end is not None and r['created']>=end:continue
    if r['created']<=chat_conversations.cutoff(c,who,r['channel'],actor):continue
    x=serialize(c,who,actor,r)
    if view=='bookmarked' and not x['bookmarked']:continue
    if view=='mentions' and not c.execute('SELECT 1 FROM tw_chat_mentions WHERE owner=? AND message=? AND actor=?',(who,r['id'],actor)).fetchone():continue
    if attachments and not x['attachments']:continue
    search_text=r['body']+' '+ ' '.join(f['name'] for f in x['attachments'])
    if q.strip() and q.strip().casefold() not in search_text.casefold():continue
    if view=='search' and not any([q.strip(),channel_id,author,date_from,date_to,attachments]):continue
    rows.append(x)
   return rows
 from app import shell
 chat_users.install(app,db,identity,account,shell,uploads)
 chat_conversations.install(app,db,identity,serialize)
 chat_mentions.install(app,db,identity)
 chat_appearance.install(app,db,identity)
 chat_settings.install(app,db,identity)
 chat_profile.install(app,db,identity,uploads)
 chat_status.install(app,db,identity,owner,account)
 chat_productivity.install(app,db,identity,message,workspace)
 chat_presence.install(app,db,identity)
 delivery=chat_delivery.install(app,db,identity)
 delivery['ingest_hooks']=chat_hooks.install(app,db,identity)
 import chat_previews,chat_embedded
 chat_embedded.install(app,db,owner,account)
 chat_previews.install(app,db,identity,workspace)
 # The public /chat marketing pages are separate. Only /workspace/chat is authenticated Chat.
 @app.get('/workspace/chat')
 @app.get('/workspace/chat/{path:path}')
 def chat_page(req:Request,path:str=''):
  try:account(req)
  except HTTPException:return RedirectResponse('/launchpad/login?next='+str(req.url.path),status_code=303)
  if not path:return RedirectResponse('/workspace/chat/channels/44055' if owner(req)==demo else '/workspace/chat/channels/joined',status_code=303)
  parts=path.split('/')
  with db() as c:
   who,actor=identity(req,c)
   if len(parts)>=2 and parts[0] in ['channels','conversations'] and parts[1] not in ['joined','discover']:
    channel(c,who,actor,parts[1])
    if len(parts)!=2 and not (len(parts)==4 and parts[2]=='messages'):raise HTTPException(404,'Chat page not found.')
    if len(parts)==4 and parts[2]=='messages':
     if message(c,who,actor,parts[3])['channel']!=parts[1]:raise HTTPException(404,'Message not found.')
   elif len(parts)==2 and parts[0]=='people':
    if not any(p['id']==parts[1] and p['id']!=actor for p in people(c,who)):raise HTTPException(404,'Person not found.')
    if chat_conversations.role(c,who,actor)=='guest' and not chat_conversations.pair(c,who,actor,parts[1]):raise HTTPException(403,'Guests cannot start conversations.')
   elif path not in ['channels/joined','channels/discover','highlights/bookmarked','highlights/mentions','people','search','settings/localization','settings/profile','settings/notifications','settings/preferences','settings/users','settings/hooks','settings/integrations','embedded']:raise HTTPException(404,'Chat page not found.')
   if path in ['settings/users','settings/hooks']:chat_users.admin(c,who,actor)
  return HTMLResponse((Path(__file__).parent/'frontend/chat.html').read_text())
 return delivery
