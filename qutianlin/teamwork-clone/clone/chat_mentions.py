"""Structured Chat mentions and real per-recipient notification preferences."""
import json,re,secrets,time
from fastapi import HTTPException,Request
SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_mentions(owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(owner,message,actor,kind),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_notifications(owner TEXT NOT NULL,channel TEXT NOT NULL,actor TEXT NOT NULL,mode TEXT NOT NULL,PRIMARY KEY(owner,channel,actor),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_presence(owner TEXT NOT NULL,actor TEXT NOT NULL,seen REAL NOT NULL,PRIMARY KEY(owner,actor),FOREIGN KEY(owner,actor) REFERENCES tw_chat_users(owner,actor) ON DELETE CASCADE);
'''
MODES=['global','all','mentions','directMentions','none']
def present(c,who,actor):
 from chat_presence import status
 return status(c,who,actor)=='Online'
def mode(c,who,cid,actor):
 room=c.execute('SELECT kind FROM tw_chat_channels WHERE owner=? AND id=?',(who,cid)).fetchone()
 if room and room['kind']=='pair':return 'global'
 row=c.execute('SELECT mode FROM tw_chat_notifications WHERE owner=? AND channel=? AND actor=?',(who,cid,actor)).fetchone();return row['mode'] if row else 'global'
def mention_label(c,who,mid,person,text):
 previous=c.execute('SELECT label FROM tw_chat_mention_tokens WHERE owner=? AND message=? AND actor=?',(who,mid,person['id'])).fetchone() if mid else None
 for label in [person['handle'],person['name']]+([previous['label']] if previous else []):
  if re.search(r'(?<!\w)@'+re.escape(label)+r'(?!\w)',text):return label
 return None
def tokens(c,who,cid,text,value,mid=None):
 from chat_local import people,channel
 if not isinstance(value,list) or any(not isinstance(x,str) for x in value):raise HTTPException(422,'Choose valid message mentions.')
 people_by_id={p['id']:p for p in people(c,who)};result=[]
 for token in dict.fromkeys(value):
  if token in ['all','online']:
   if not re.search(r'(?<!\w)@'+token+r'\b',text):raise HTTPException(422,'The mention token is not in the message.')
  else:
   if token not in people_by_id or not mention_label(c,who,mid,people_by_id[token],text):raise HTTPException(422,'Choose a mentioned user from this channel.')
   try:channel(c,who,token,cid,member=True)
   except HTTPException:raise HTTPException(422,'The mentioned user cannot access this channel.')
  result.append(token)
 return result

def apply(c,who,cid,author,mid,text,mentions,notify=True):
 from chat_local import people,channel
 mentions=tokens(c,who,cid,text,mentions,mid);persons={p['id']:p for p in people(c,who)};labels={token:mention_label(c,who,mid,persons[token],text) for token in mentions if token in persons};c.execute('DELETE FROM tw_chat_mentions WHERE owner=? AND message=?',(who,mid));c.execute('DELETE FROM tw_chat_mention_tokens WHERE owner=? AND message=?',(who,mid));members=set(persons)
 for token,label in labels.items():c.execute('INSERT INTO tw_chat_mention_tokens VALUES(?,?,?,?)',(who,mid,token,label))
 for r in c.execute('SELECT actor FROM tw_chat_members WHERE owner=? AND channel=?',(who,cid)).fetchall():
  actor=r['actor']
  if actor not in members:continue
  try:channel(c,who,actor,cid,member=True)
  except HTTPException:continue
  kinds=[]
  if actor in mentions:kinds.append('direct')
  if 'all' in mentions:kinds.append('all')
  if 'online' in mentions and present(c,who,actor):kinds.append('online')
  for kind in kinds:c.execute('INSERT INTO tw_chat_mentions VALUES(?,?,?,?)',(who,mid,actor,kind))
  from chat_settings import settings
  preference=mode(c,who,cid,actor);preference=settings(c,who,actor)['defaultNotificationNoisiness'] if preference=='global' else preference
  if notify and actor!=author and (preference=='all' or preference=='mentions' and kinds or preference=='directMentions' and 'direct' in kinds):
   payload={'title':'New Chat message','text':text,'private_actor':actor,'chat_message_id':mid,'chat_channel_id':cid,'url':__import__('chat_conversations').path(channel(c,who,actor,cid))+'/messages/'+mid}
   c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),who,'notification',cid,json.dumps(payload),int(time.time())))
   from chat_delivery import enqueue
   enqueue(c,who,cid,mid,actor)
 return mentions

def can_read_notification(c,who,actor,record):
 from chat_local import channel
 cid=record['data'].get('chat_channel_id')
 if not cid:return True
 try:channel(c,who,actor,cid,member=True)
 except HTTPException:return False
 from chat_conversations import cutoff
 return bool(c.execute('SELECT 1 FROM tw_chat_messages WHERE owner=? AND id=? AND channel=? AND created>?',(who,record['data'].get('chat_message_id'),cid,cutoff(c,who,cid,actor))).fetchone())

def clean_message_notifications(c,who,mid):
 c.execute("DELETE FROM tw_records WHERE owner=? AND kind='notification' AND json_extract(data,'$.chat_message_id')=?",(who,mid))
def clean_channel_notifications(c,who,cid):
 c.execute("DELETE FROM tw_records WHERE owner=? AND kind='notification' AND json_extract(data,'$.chat_channel_id')=?",(who,cid))

def install(app,db,identity):
 from chat_local import channel
 with db() as c:c.executescript(SCHEMA)
 @app.get('/api/chat/channels/{cid}/notifications')
 def get(cid:str,req:Request):
  with db() as c:
   from chat_settings import settings
   who,actor=identity(req,c);channel(c,who,actor,cid,member=True);return {'mode':mode(c,who,cid,actor),'global_mode':settings(c,who,actor)['defaultNotificationNoisiness'],'modes':MODES}
 @app.put('/api/chat/channels/{cid}/notifications')
 async def save(cid:str,req:Request):
  d=await req.json();value=d.get('mode')
  if value not in MODES:raise HTTPException(422,'Choose a valid notification setting.')
  with db() as c:
   who,actor=identity(req,c);room=channel(c,who,actor,cid,member=True)
   if room['kind']=='pair':raise HTTPException(403,'Direct conversations use global notification settings.')
   c.execute('INSERT INTO tw_chat_notifications VALUES(?,?,?,?) ON CONFLICT(owner,channel,actor) DO UPDATE SET mode=excluded.mode',(who,cid,actor,value));return {'mode':value}
