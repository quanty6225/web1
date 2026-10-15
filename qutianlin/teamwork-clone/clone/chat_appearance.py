"""Source-backed channel avatars and actor/workspace-scoped emoji preference."""
import json
from pathlib import Path
from fastapi import HTTPException,Request
PALETTE=json.loads((Path(__file__).parent/'static/chat-avatar-palette.json').read_text())
SCHEMA='''CREATE TABLE IF NOT EXISTS tw_chat_avatars(owner TEXT NOT NULL,channel TEXT NOT NULL,color TEXT NOT NULL,icon TEXT NOT NULL,PRIMARY KEY(owner,channel),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE);'''
def avatar(c,who,cid):
 row=c.execute('SELECT color,icon FROM tw_chat_avatars WHERE owner=? AND channel=?',(who,cid)).fetchone()
 if row:return dict(row)
 value={'color':PALETTE['colors'][0],'icon':'initials'}
 if cid=='44055' and c.execute('SELECT 1 FROM tw_chat_channels WHERE owner=? AND id=? AND is_default=1',(who,cid)).fetchone():value['image_url']='/static/assets/afd31720931921ac50ee5400.png'
 return value
def save_avatar(c,who,cid,value):
 if not isinstance(value,dict) or value.get('color') not in PALETTE['colors'] or value.get('icon') not in {i['id'] for i in PALETTE['icons']}:raise HTTPException(422,'Choose a channel color and icon from the palette.')
 c.execute('INSERT INTO tw_chat_avatars VALUES(?,?,?,?) ON CONFLICT(owner,channel) DO UPDATE SET color=excluded.color,icon=excluded.icon',(who,cid,value['color'],value['icon']))
def install(app,db,identity):
 with db() as c:c.executescript(SCHEMA)
 @app.get('/api/chat/appearance')
 def get(req:Request):
  with db() as c:
   who,actor=identity(req,c);row=c.execute('SELECT value FROM tw_preferences WHERE owner=? AND key=?',(actor,'chat_emoji_tone:'+who)).fetchone()
   return {'emoji_tone':json.loads(row['value']) if row else 1}
 @app.put('/api/chat/appearance')
 async def save(req:Request):
  data=await req.json();tone=data.get('emoji_tone')
  if type(tone) is not int or tone not in range(1,7):raise HTTPException(422,'Choose one of the six skin tones.')
  with db() as c:
   who,actor=identity(req,c);c.execute('INSERT INTO tw_preferences VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value',(actor,'chat_emoji_tone:'+who,json.dumps(tone)))
  return {'emoji_tone':tone}
