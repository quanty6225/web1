"""Current-user custom status and timed DND, shared with the local Projects shell."""
import json,time,secrets
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import HTTPException,Request
SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_feedback(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,rating INTEGER NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tw_chat_custom_status(owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,body TEXT NOT NULL,emoji TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(owner,actor));
CREATE TABLE IF NOT EXISTS tw_chat_dnd(owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,started REAL NOT NULL,ends REAL,timezone TEXT NOT NULL,period TEXT NOT NULL,PRIMARY KEY(owner,actor));
'''
DURATIONS={'30min':1800,'1hr':3600,'2hr':7200,'4hr':14400}
EMOJI={e['emoji'] for g in json.loads((Path(__file__).parent/'static/chat-emoji.json').read_text()) for e in g['entries']}
EMOJI.update(['💬','🏢','✈️','🏠','🥪'])
for tones in json.loads((Path(__file__).parent/'static/chat-emoji-tones.json').read_text()).values():EMOJI.update(tones.values())

def dnd(c,who,actor):
 row=c.execute('SELECT started,ends,timezone,period FROM tw_chat_dnd WHERE owner=? AND actor=?',(who,actor)).fetchone()
 return dict(row) if row and (row['ends'] is None or row['ends']>time.time()) else None

def custom(c,who,actor):
 row=c.execute('SELECT body,emoji,updated FROM tw_chat_custom_status WHERE owner=? AND actor=?',(who,actor)).fetchone()
 return dict(row) if row else None

def end_at(period,zone,now):
 if not isinstance(zone,str) or len(zone)>100:raise HTTPException(422,'Choose a valid timezone.')
 try:tz=ZoneInfo(zone)
 except (ZoneInfoNotFoundError,ValueError):raise HTTPException(422,'Choose a valid timezone.')
 if not isinstance(period,str) or period not in {*DURATIONS,'next_day','next_week','never'}:raise HTTPException(422,'Choose a DND duration.')
 if period in DURATIONS:return now+DURATIONS[period]
 if period=='never':return None
 local=datetime.fromtimestamp(now,tz)
 days=1 if period=='next_day' else 7-local.weekday()
 return (local+timedelta(days=days)).replace(hour=8,minute=30,second=0,microsecond=0).timestamp()

async def data(req):
 try:value=await req.json()
 except ValueError:raise HTTPException(422,'Check the status details.')
 if not isinstance(value,dict):raise HTTPException(422,'Check the status details.')
 return value

def install(app,db,identity,owner,account):
 with db() as c:c.executescript(SCHEMA)
 @app.post('/api/chat/feedback')
 async def feedback(req:Request):
  value=await data(req)
  with db() as c:
   who,actor=identity(req,c)
   if set(value)!={'rating','body'} or type(value['rating']) is not int or value['rating'] not in range(1,6) or not isinstance(value['body'],str) or len(value['body'])>20000:raise HTTPException(422,'Check your feedback and rating.')
   ident=secrets.token_hex(12);c.execute('INSERT INTO tw_chat_feedback VALUES(?,?,?,?,?,?)',(ident,who,actor,value['rating'],value['body'],time.time()));return {'id':ident,'message':'Thanks! We have received your feedback.'}
 @app.get('/api/chat/status')
 def get(req:Request):
  with db() as c:
   who,actor=identity(req,c);return {'custom_status':custom(c,who,actor),'dnd':dnd(c,who,actor)}
 @app.put('/api/chat/dnd')
 async def set_dnd(req:Request):
  value=await data(req)
  with db() as c:
   who,actor=identity(req,c)
   if set(value)!={'period','timezone'}:raise HTTPException(422,'Choose a DND duration and timezone.')
   now=time.time();ends=end_at(value['period'],value['timezone'],now)
   c.execute('INSERT INTO tw_chat_dnd VALUES(?,?,?,?,?,?) ON CONFLICT(owner,actor) DO UPDATE SET started=excluded.started,ends=excluded.ends,timezone=excluded.timezone,period=excluded.period',(who,actor,now,ends,value['timezone'],value['period']))
   # DND suppresses alerts, not conversation contents or read state. Do not replay old alerts later.
   c.execute('DELETE FROM tw_chat_alerts WHERE owner=? AND actor=?',(who,actor))
   c.execute("UPDATE tw_chat_mail SET state='cancelled' WHERE owner=? AND actor=? AND state='pending'",(who,actor))
   return dnd(c,who,actor)
 @app.delete('/api/chat/dnd')
 def cancel(req:Request):
  with db() as c:
   who,actor=identity(req,c);c.execute('DELETE FROM tw_chat_dnd WHERE owner=? AND actor=?',(who,actor));return {'dnd':None}
 def workspace_identity(req,c):return owner(req),account(req)['account_id']
 def save_status(req,value,identify):
  with db() as c:
   who,actor=identify(req,c);body=value.get('body');emoji=value.get('emoji','💬')
   if set(value)-{'body','emoji'} or not isinstance(body,str) or not body.strip():raise HTTPException(422,'Enter your status.')
   try:units=len(body.encode('utf-16-le'))//2
   except UnicodeEncodeError:raise HTTPException(422,'Enter a valid status.')
   if units>160:raise HTTPException(422,'Use up to 160 characters for your status.')
   if not isinstance(emoji,str) or emoji not in EMOJI:raise HTTPException(422,'Choose an emoji from the list.')
   c.execute('INSERT INTO tw_chat_custom_status VALUES(?,?,?,?,?) ON CONFLICT(owner,actor) DO UPDATE SET body=excluded.body,emoji=excluded.emoji,updated=excluded.updated',(who,actor,body,emoji,time.time()))
   return custom(c,who,actor)
 @app.put('/api/chat/status')
 async def save(req:Request):return save_status(req,await data(req),identity)
 @app.put('/api/account/status')
 async def project_save(req:Request):return save_status(req,await data(req),workspace_identity)
 @app.get('/api/account/status')
 def project_get(req:Request):
  with db() as c:
   who,actor=workspace_identity(req,c);return {'custom_status':custom(c,who,actor)}
 def clear_status(req,identify):
  with db() as c:
   who,actor=identify(req,c);c.execute('DELETE FROM tw_chat_custom_status WHERE owner=? AND actor=?',(who,actor));return {'custom_status':None}
 @app.delete('/api/chat/status')
 def clear(req:Request):return clear_status(req,identity)
 @app.delete('/api/account/status')
 def project_clear(req:Request):return clear_status(req,workspace_identity)
