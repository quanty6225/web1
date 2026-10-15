"""Durable provider-shaped webhook and local SMS delivery from captured status data."""
import hashlib,http.client,json,secrets,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from automation_http import local_destination
ROOT=Path(__file__).parent
DOCUMENTATION='https://support.atlassian.com/statuspage/docs/enable-webhook-notifications/'
def model():return json.loads((ROOT/'static/status-data/notifications.json').read_text())
def install(db,send_mail,send_sms):
 with db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS tw_status_channel_snapshots(kind TEXT NOT NULL,id TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(kind,id));
 CREATE TABLE IF NOT EXISTS tw_status_channel_state(key TEXT PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS tw_status_channel_events(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS tw_status_channel_jobs(id TEXT PRIMARY KEY,event TEXT NOT NULL,subscription TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,started REAL,next_attempt REAL NOT NULL DEFAULT 0,http_status INTEGER,error TEXT,alert_sent INTEGER NOT NULL DEFAULT 0,UNIQUE(event,subscription));
 ''')
 with db() as c:
  if 'failure_notice' not in [r['name'] for r in c.execute('PRAGMA table_info(tw_status_channel_jobs)')]:c.execute('ALTER TABLE tw_status_channel_jobs ADD COLUMN failure_notice TEXT')
 def scan():
  data=model();now=time.time();page={'id':data['page']['id'],'status_indicator':data['status']['indicator'],'status_description':data['status']['description']}
  with db() as c:
   c.execute('BEGIN IMMEDIATE');baseline=c.execute("SELECT 1 FROM tw_status_channel_state WHERE key='baseline'").fetchone()
   for kind,items in [('incident',data['incidents']),('component',data['components'])]:
    for item in items:
     value=json.dumps(item,sort_keys=True);previous=c.execute('SELECT value FROM tw_status_channel_snapshots WHERE kind=? AND id=?',(kind,item['id'])).fetchone();old=json.loads(previous['value']) if previous else None
     if old==item:continue
     c.execute('INSERT INTO tw_status_channel_snapshots VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET value=excluded.value',(kind,item['id'],value))
     if not baseline:continue
     if kind=='component' and (not old or old['status']==item['status']):continue
     if kind=='incident' and item.get('incident_updates') and item['incident_updates'][0].get('deliver_notifications') is False:continue
     event=secrets.token_hex(16);payload={'page':page,kind:item};sms=False
     if kind=='component':payload['component_update']={'id':event,'component_id':item['id'],'old_status':old['status'],'new_status':item['status'],'created_at':item.get('updated_at') or datetime.now(timezone.utc).isoformat()}
     else:sms=not old or old['status']!=item['status'] and item['status'] in ['resolved','completed','in_progress']
     c.execute('INSERT INTO tw_status_channel_events VALUES(?,?,?)',(event,json.dumps(payload),now))
     eligible=c.execute("SELECT id FROM tw_status_channels WHERE active=1 AND created<=? AND (kind='webhook' OR (kind='sms' AND ?))",(now,sms)).fetchall()
     for sub in eligible:c.execute('INSERT INTO tw_status_channel_jobs(id,event,subscription) VALUES(?,?,?)',(secrets.token_hex(16),event,sub['id']))
   c.execute("INSERT OR IGNORE INTO tw_status_channel_state VALUES('baseline')")
 def deliver():
  now=time.time()
  with db() as c:
   c.execute("UPDATE tw_status_channel_jobs SET state='queued',error='Delivery interrupted; retry pending.' WHERE state='sending' AND started<?",(now-60,));ids=[r[0] for r in c.execute("SELECT id FROM tw_status_channel_jobs WHERE state IN ('queued','failed') AND next_attempt<=? ORDER BY rowid LIMIT 100",(now,))]
  for ident in ids:
   with db() as c:
    c.execute('BEGIN IMMEDIATE');job=c.execute("SELECT j.*,e.payload,e.created AS event_created FROM tw_status_channel_jobs j JOIN tw_status_channel_events e ON e.id=j.event WHERE j.id=? AND j.state IN ('queued','failed')",(ident,)).fetchone()
    if not job:continue
    job=dict(job);sub=c.execute('SELECT * FROM tw_status_channels WHERE id=?',(job['subscription'],)).fetchone()
    if not sub or not sub['active'] or sub['created']>job['event_created']:
     c.execute("UPDATE tw_status_channel_jobs SET state='cancelled' WHERE id=?",(ident,));continue
    sub=dict(sub);c.execute("UPDATE tw_status_channel_jobs SET state='sending',started=?,attempts=attempts+1 WHERE id=?",(time.time(),ident))
   payload=json.loads(job['payload']);payload['meta']={'unsubscribe':sub['origin']+'/status/unsubscribe?token='+sub['token'],'documentation':DOCUMENTATION};status=None;error=None;connection=None
   try:
    if sub['kind']=='sms':
     item=payload['incident'];body=item['name']+' — '+item['status']+'\n'+(item.get('incident_updates') or [{}])[0].get('body','')+'\n'+sub['origin']+item['shortlink']+'\nUnsubscribe: '+payload['meta']['unsubscribe']
     with db() as c:
      c.execute('BEGIN IMMEDIATE');active=c.execute('SELECT active FROM tw_status_channels WHERE id=?',(sub['id'],)).fetchone()
      if not active or not active['active']:raise RuntimeError('Subscription was cancelled before delivery.')
      send_sms(c,sub['session'],sub['address'],body)
    else:
     destination=local_destination(sub['address'])
     if destination is None:raise ValueError('External endpoints are not available in this offline workspace.')
     parsed,host=destination;connection=(http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection)(host,parsed.port,timeout=30)
     if 'incident' in payload:payload['incident']['shortlink']=sub['origin']+payload['incident']['shortlink']
     path=quote(parsed.path or '/',safe="/%:@!$&'()*+,;=-._~")+('?' + quote(parsed.query,safe="%=&?/:@!$'()*+,;~-._") if parsed.query else '')
     connection.request('POST',path,body=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Teamwork-Local-Delivery':job['event']});reply=connection.getresponse();status=reply.status;reply.read(65536)
     if not 200<=status<300:raise ValueError('The endpoint returned HTTP '+str(status)+('. Redirects are not followed.' if 300<=status<400 else '.'))
   except (OSError,ValueError,RuntimeError,http.client.HTTPException) as exc:error=str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Delivery could not be completed.'
   except Exception:error='The local message transport could not complete delivery.'
   finally:
    if connection:connection.close()
   with db() as c:c.execute('UPDATE tw_status_channel_jobs SET state=?,http_status=?,error=?,failure_notice=COALESCE(failure_notice,?),next_attempt=? WHERE id=?',('failed' if error else 'sent',status,error,error,time.time()+30 if error else 0,ident))
  notices()
 def notices():
  with db() as c:ids=[r[0] for r in c.execute("SELECT id FROM tw_status_channel_jobs WHERE failure_notice IS NOT NULL AND alert_sent=0 AND state IN ('sent','failed')")]
  for ident in ids:
   with db() as c:
    c.execute('BEGIN IMMEDIATE');r=c.execute("SELECT j.*,s.active,s.created AS subscribed_at,s.email,s.kind,s.origin,s.token,s.address,e.created AS event_created FROM tw_status_channel_jobs j JOIN tw_status_channels s ON s.id=j.subscription JOIN tw_status_channel_events e ON e.id=j.event WHERE j.id=?",(ident,)).fetchone()
    if not r or r['alert_sent'] or not r['active'] or r['kind']!='webhook' or r['subscribed_at']>r['event_created']:continue
    outcome='The endpoint has since accepted this update.' if r['state']=='sent' else 'Delivery will be retried.'
    try:send_mail(r['email'],'Teamwork.com status webhook delivery failed','Your status webhook endpoint could not receive an update.\n\n'+r['address']+'\n'+r['failure_notice']+'\n\n'+outcome+'\nTo unsubscribe: '+r['origin']+'/status/unsubscribe?token='+r['token']+'\n')
    except Exception:continue
    c.execute('UPDATE tw_status_channel_jobs SET alert_sent=1 WHERE id=?',(ident,))
 def tick():scan();deliver()
 scan()
 return {'scan':scan,'deliver':deliver,'tick':tick}
