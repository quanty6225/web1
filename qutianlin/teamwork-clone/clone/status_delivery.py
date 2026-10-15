"""Persist and deliver changes in the local status archive without contacting the source."""
import asyncio,hashlib,json,time,logging
from urllib.parse import urlsplit
from status_local import data_for

def install(app,db,send_mail,channel_tick=None):
 with db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS tw_status_snapshots(code TEXT PRIMARY KEY,digest TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS tw_status_delivery_state(key TEXT PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS tw_status_events(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS tw_status_deliveries(event TEXT NOT NULL,email TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,error TEXT,PRIMARY KEY(event,email));
 ''')
 def scan():
  items=[i for m in data_for('history',1)['months'] for i in m['incidents']];now=time.time()
  with db() as c:
   c.execute('BEGIN IMMEDIATE');baseline=c.execute("SELECT 1 FROM tw_status_delivery_state WHERE key='archive-baseline'").fetchone()
   for item in items:
    payload=json.dumps({k:item[k] for k in ['code','name','message','timestamp_text','local_url']},sort_keys=True);source_value=json.dumps({k:item[k] for k in ['code','name','message','timestamp_text']},sort_keys=True);version=hashlib.sha256(source_value.encode()).hexdigest();prior=c.execute('SELECT digest FROM tw_status_snapshots WHERE code=?',(item['code'],)).fetchone()
    if prior and prior['digest']==version:continue
    c.execute('INSERT INTO tw_status_snapshots VALUES(?,?) ON CONFLICT(code) DO UPDATE SET digest=excluded.digest',(item['code'],version))
    if baseline:
     # A repeated value after a later update is a new transition, not a duplicate poll.
     event=hashlib.sha256((payload+str(now)).encode()).hexdigest();c.execute('INSERT INTO tw_status_events VALUES(?,?,?)',(event,payload,now))
     c.execute('INSERT INTO tw_status_deliveries(event,email) SELECT ?,email FROM tw_status_subscriptions WHERE active=1 AND created<=?',(event,now))
   c.execute("INSERT OR IGNORE INTO tw_status_delivery_state VALUES('archive-baseline')")
 def deliver():
  with db() as c:jobs=[dict(r) for r in c.execute('SELECT d.event,d.email,e.payload,e.created FROM tw_status_deliveries d JOIN tw_status_events e ON d.event=e.id WHERE d.sent=0 ORDER BY e.created')]
  for job in jobs:
   with db() as c:
    c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT active,origin,created FROM tw_status_subscriptions WHERE email=?',(job['email'],)).fetchone();state=c.execute('SELECT sent FROM tw_status_deliveries WHERE event=? AND email=?',(job['event'],job['email'])).fetchone()
    if not row or not row['active'] or row['created']>job['created'] or not state or state['sent']:continue
    item=json.loads(job['payload']);base=row['origin'];parts=urlsplit(base)
    if parts.hostname not in ['127.0.0.1','localhost','::1'] or parts.port not in range(18150,18160):continue
    c.execute('UPDATE tw_status_deliveries SET attempts=attempts+1 WHERE event=? AND email=?',(job['event'],job['email']))
    try:send_mail(job['email'],'Teamwork.com status: '+item['name'],item['name']+'\n\n'+item['message']+'\n\n'+item['timestamp_text']+'\n\n'+base+item['local_url']+'\n')
    except Exception as exc:c.execute('UPDATE tw_status_deliveries SET error=? WHERE event=? AND email=?',(type(exc).__name__,job['event'],job['email']))
    else:c.execute('UPDATE tw_status_deliveries SET sent=1,error=NULL WHERE event=? AND email=?',(job['event'],job['email']))
 def tick():
  scan();deliver()
  if channel_tick:channel_tick()
 task=None
 @app.on_event('startup')
 async def start():
  nonlocal task
  async def loop():
   while True:
    try:await asyncio.to_thread(tick)
    except Exception as error:logging.getLogger(__name__).error('Local status delivery failed: %s',type(error).__name__)
    await asyncio.sleep(30)
  task=asyncio.create_task(loop())
 @app.on_event('shutdown')
 async def stop():
  if task:
   task.cancel()
   try:await task
   except asyncio.CancelledError:pass
 # Preserve the starting archive so a change before the first background tick is observed.
 scan()
 return {'scan':scan,'deliver':deliver,'tick':tick}
