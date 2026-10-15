"""Durable HTTP action delivery to this clone's isolated local endpoints."""
import http.client,json,re,secrets,time
from urllib.parse import urlsplit,quote
from fastapi import HTTPException,Request
METHODS=['GET','POST','PUT','PATCH','DELETE']
EFFECT='Send HTTP request'
TRANSPORT_HEADERS={'host','content-length','transfer-encoding','connection','proxy-connection'}

def validate(action):
 if action['effect']!=EFFECT:return
 url=action.get('url','');method=action.setdefault('method','POST');headers=action.setdefault('headers',[]);payload=action.setdefault('payload','')
 if not isinstance(url,str):raise HTTPException(422,'Enter a valid HTTP endpoint URL.')
 try:
  parsed=urlsplit(url);port=parsed.port
  if not isinstance(url,str) or re.search(r'[\s\x00-\x1f\x7f]',url) or parsed.scheme not in ['http','https'] or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:raise ValueError()
 except (TypeError,ValueError):raise HTTPException(422,'Enter a valid HTTP endpoint URL.')
 if method not in METHODS:raise HTTPException(422,'Choose a supported HTTP method.')
 if not isinstance(headers,list) or len(headers)>50:raise HTTPException(422,'Enter valid HTTP headers.')
 clean=[]
 for h in headers:
  if not isinstance(h,dict) or not isinstance(h.get('name'),str) or not isinstance(h.get('value'),str):raise HTTPException(422,'Enter a header name and value.')
  name=h['name'].strip();value=h['value']
  if not name and not value:continue
  if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name) or name.lower() in TRANSPORT_HEADERS or re.search(r'[\r\n\x00]',value):raise HTTPException(422,'Enter a valid header; transport headers are managed automatically.')
  try:value.encode('latin-1')
  except UnicodeEncodeError:raise HTTPException(422,'HTTP header values must use ISO-8859-1 characters.')
  clean.append({'name':name,'value':value})
 if not isinstance(payload,str) or len(payload.encode('utf-8'))>65536:raise HTTPException(422,'Enter a text payload of up to 64 KB.')
 action['headers']=clean;action['payload']=payload if method in ['POST','PUT','PATCH'] else ''

def enqueue(c,who,rule,task,action):
 ident=secrets.token_hex(12)
 c.execute('INSERT INTO tw_automation_http(id,owner,automation_id,task_id,url,method,headers,payload,state,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,who,rule,task,action['url'],action['method'],json.dumps(action['headers']),action['payload'],'queued',time.time()))
 return ident

def local_destination(url):
 parsed=urlsplit(url)
 if parsed.hostname not in ['127.0.0.1','localhost','::1'] or parsed.port not in range(18150,18160):return None
 return parsed,'127.0.0.1' if parsed.hostname=='localhost' else parsed.hostname

def install(app,db,owner,account):
 with db() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS tw_automation_http(id TEXT PRIMARY KEY,owner TEXT NOT NULL,automation_id TEXT NOT NULL,task_id TEXT NOT NULL,url TEXT NOT NULL,method TEXT NOT NULL,headers TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,started REAL,finished REAL,attempts INTEGER NOT NULL DEFAULT 0,status_code INTEGER,response TEXT,error TEXT)''')
 def admin(req):
  who=owner(req)
  if account(req)['account_id']!=who:raise HTTPException(403,'Only the workspace owner can manage automations.')
  return who
 @app.get('/api/automations/http-deliveries')
 def history(req:Request):
  with db() as c:return [dict(r) for r in c.execute('SELECT id,automation_id,task_id,url,method,state,created,started,finished,attempts,status_code,response,error FROM tw_automation_http WHERE owner=? ORDER BY created DESC,rowid DESC LIMIT 100',(admin(req),))]
 @app.post('/api/automations/http-deliveries/{ident}/retry')
 def retry(ident:str,req:Request):
  who=admin(req)
  with db() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM tw_automation_http WHERE owner=? AND id=?',(who,ident)).fetchone()
   if not row:raise HTTPException(404,'HTTP request not found.')
   if row['state'] not in ['failed','blocked','unknown']:raise HTTPException(409,'This request is not available to retry.')
   if not c.execute("SELECT 1 FROM tw_records WHERE owner=? AND id=? AND kind='automation'",(who,row['automation_id'])).fetchone():raise HTTPException(409,'The automation no longer exists.')
   c.execute("UPDATE tw_automation_http SET state='queued',started=NULL,finished=NULL,status_code=NULL,response=NULL,error=NULL WHERE id=?",(ident,))
  return {'ok':True,'state':'queued'}
 def deliver():
  with db() as c:
   c.execute("UPDATE tw_automation_http SET state='unknown',finished=?,error='The previous delivery was interrupted; its result is unknown. Retry only after checking the receiver.' WHERE state='sending' AND started<?",(time.time(),time.time()-60))
   identifiers=[r['id'] for r in c.execute("SELECT id FROM tw_automation_http WHERE state='queued' ORDER BY created,rowid LIMIT 100")]
  for ident in identifiers:
   with db() as c:
    c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM tw_automation_http WHERE id=? AND state='queued'",(ident,)).fetchone()
    if not row:continue
    row=dict(row)
    if not c.execute("SELECT 1 FROM tw_records WHERE owner=? AND id=? AND kind='automation'",(row['owner'],row['automation_id'])).fetchone():
     c.execute("UPDATE tw_automation_http SET state='cancelled',finished=?,error='The automation was deleted before delivery.' WHERE id=?",(time.time(),ident));continue
    c.execute("UPDATE tw_automation_http SET state='sending',started=?,attempts=attempts+1 WHERE id=?",(time.time(),ident))
   state='failed';status=None;response='';error=None;connection=None
   try:
    destination=local_destination(row['url'])
    if destination is None:state='blocked';error='External endpoints are unavailable in this offline workspace; no request was sent.'
    else:
     parsed,host=destination;connection=(http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection)(host,parsed.port,timeout=3);body=row['payload'].encode('utf-8') if row['method'] in ['POST','PUT','PATCH'] else b'';path=quote(parsed.path or '/',safe="/%:@!$&'()*+,;=-._~")+('?' + quote(parsed.query,safe="%=&?/:@!$'()*+,;~-._") if parsed.query else '')
     connection.putrequest(row['method'],path)
     for h in json.loads(row['headers']):connection.putheader(h['name'],h['value'])
     connection.putheader('Content-Length',str(len(body)));connection.endheaders(body);reply=connection.getresponse();status=reply.status;response=reply.read(65537)[:65536].decode('utf-8','replace');state='succeeded' if 200<=status<300 else 'failed'
     if state=='failed':error='The endpoint returned HTTP '+str(status)+('. Redirects are not followed.' if 300<=status<400 else '.')
   except (OSError,ValueError,http.client.HTTPException):error='The HTTP request could not be completed. Check the endpoint and retry.'
   finally:
    if connection:connection.close()
   with db() as c:c.execute('UPDATE tw_automation_http SET state=?,finished=?,status_code=?,response=?,error=? WHERE id=? AND state=\'sending\'',(state,time.time(),status,response,error,ident))
 return deliver
