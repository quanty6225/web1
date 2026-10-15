"""Local inbound webhook queue and stateless MCP 2025-03-26 tools transport."""
import hashlib,json,secrets,time,uuid
from fastapi import HTTPException,Request
from fastapi.responses import JSONResponse,Response

def install_integrations(app,auth,owner,owned_resource,scenario_row,perform_run):
 with auth.connect() as db:
  db.executescript('''
  CREATE TABLE IF NOT EXISTS make_access_keys (
   resource TEXT PRIMARY KEY REFERENCES make_resources(id) ON DELETE CASCADE,
   owner TEXT NOT NULL, digest TEXT NOT NULL, created REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS make_hook_events (
   id TEXT PRIMARY KEY, hook TEXT NOT NULL REFERENCES make_resources(id) ON DELETE CASCADE,
   owner TEXT NOT NULL, scenario TEXT NOT NULL, payload TEXT NOT NULL,
   status TEXT NOT NULL, run TEXT, created REAL NOT NULL, finished REAL,
   idempotency TEXT, UNIQUE(hook,idempotency));
  CREATE TABLE IF NOT EXISTS make_integration_limits (
   resource TEXT PRIMARY KEY REFERENCES make_resources(id) ON DELETE CASCADE,
   started REAL NOT NULL, count INTEGER NOT NULL);
  INSERT OR IGNORE INTO websitebench_backend_migrations(migration_id,applied_at)
   VALUES('make-integrations-v3',datetime('now'));
  ''')

 def limited(db,rid):
  now=time.time();r=db.execute('SELECT * FROM make_integration_limits WHERE resource=?',(rid,)).fetchone()
  if not r or now-r['started']>=60:
   db.execute('INSERT INTO make_integration_limits VALUES(?,?,1) ON CONFLICT(resource) DO UPDATE SET started=excluded.started,count=1',(rid,now))
  elif r['count']>=60: raise HTTPException(429,'Integration request limit reached. Try again in one minute.')
  else:db.execute('UPDATE make_integration_limits SET count=count+1 WHERE resource=?',(rid,))

 def authorize(db,req,rid,kind):
  header=req.headers.get('authorization','')
  token=header[7:] if header.startswith('Bearer ') else ''
  row=db.execute('SELECT k.digest,r.* FROM make_access_keys k JOIN make_resources r ON r.id=k.resource WHERE k.resource=? AND r.kind=?',(rid,kind)).fetchone()
  digest=hashlib.sha256(token.encode()).hexdigest()
  if not row or not token or not secrets.compare_digest(digest,row['digest']):
   raise HTTPException(401,'Invalid integration token',headers={'WWW-Authenticate':'Bearer'})
  limited(db,rid)
  return row

 async def payload(req):
  raw=await req.body()
  if len(raw)>200000:raise HTTPException(413,'Payload exceeds 200 KB')
  try:d=json.loads(raw)
  except (ValueError,UnicodeError):raise HTTPException(400,'A JSON payload is required')
  if not isinstance(d,dict):raise HTTPException(400,'The payload must be a JSON object')
  return d

 @app.post('/api/integrations/{rid}/token')
 def issue_token(rid:str,req:Request):
  oid=owner(req);token=secrets.token_urlsafe(32)
  with auth.connect() as db:
   r=owned_resource(db,oid,rid)
   if r['kind'] not in ('hooks','agent-profiles'):raise HTTPException(400,'This resource has no integration endpoint')
   db.execute('INSERT INTO make_access_keys VALUES(?,?,?,?) ON CONFLICT(resource) DO UPDATE SET digest=excluded.digest,created=excluded.created',(rid,oid,hashlib.sha256(token.encode()).hexdigest(),time.time()))
  return {'token':token,'endpoint':str(req.base_url).rstrip('/')+'/api/ingress/'+('hooks/' if r['kind']=='hooks' else 'mcp/')+rid}

 @app.delete('/api/integrations/{rid}/token')
 def revoke_token(rid:str,req:Request):
  oid=owner(req)
  with auth.connect() as db:
   owned_resource(db,oid,rid)
   db.execute('DELETE FROM make_access_keys WHERE resource=? AND owner=?',(rid,oid))
  return {'ok':True}

 @app.get('/api/integrations/{rid}')
 def integration_detail(rid:str,req:Request):
  oid=owner(req)
  with auth.connect() as db:
   r=owned_resource(db,oid,rid)
   if r['kind'] not in ('hooks','agent-profiles'):raise HTTPException(404,'Integration not found')
   cfg=json.loads(r['config'])
   access=db.execute('SELECT created FROM make_access_keys WHERE resource=?',(rid,)).fetchone()
   events=[dict(x) for x in db.execute('SELECT id,scenario,status,run,created,finished FROM make_hook_events WHERE hook=? AND owner=? ORDER BY created DESC LIMIT 100',(rid,oid))]
   return {'id':rid,'name':r['name'],'kind':r['kind'],'config':cfg,'token_active':bool(access),'events':events}

 @app.put('/api/integrations/{rid}')
 async def edit_integration(rid:str,req:Request):
  oid=owner(req);d=await payload(req);name=str(d.get('name','')).strip()[:160]
  if not name:raise HTTPException(400,'Name is required')
  cfg=d.get('config',{})
  if not isinstance(cfg,dict):raise HTTPException(400,'Invalid configuration')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');r=owned_resource(db,oid,rid)
   if r['kind']=='hooks':
    scenario=scenario_row(db,oid,str(cfg.get('scenario','')));graph=json.loads(scenario['graph'])
    if scenario['deleted'] or not graph or graph[0]['type']!='webhook':raise HTTPException(400,'Select a scenario beginning with a Webhook module')
    cfg={'scenario':scenario['id']}
   elif r['kind']=='agent-profiles':
    ids=cfg.get('scenarios',[])
    if not isinstance(ids,list) or len(ids)>50 or any(not isinstance(x,str) for x in ids):raise HTTPException(400,'Invalid scenario selection')
    for sid in ids:
     row=scenario_row(db,oid,sid)
     if row['deleted'] or not row['active'] or row['interval_minutes']!=0:raise HTTPException(400,'Tool scenarios must be active and scheduled on demand')
    cfg={'scenarios':list(dict.fromkeys(ids))}
   else:raise HTTPException(404,'Integration not found')
   db.execute('UPDATE make_resources SET name=?,config=? WHERE id=? AND owner=?',(name,json.dumps(cfg),rid,oid))
  return {'ok':True}

 def enqueue(db,r,p,idem=None):
  cfg=json.loads(r['config']);scenario=scenario_row(db,r['owner'],str(cfg.get('scenario','')))
  graph=json.loads(scenario['graph'])
  if scenario['deleted'] or not graph or graph[0]['type']!='webhook':raise HTTPException(409,'The webhook scenario is unavailable')
  encoded=json.dumps(p,sort_keys=True,separators=(',',':'))
  if idem:
   if len(idem)>160:raise HTTPException(400,'Idempotency key is too long')
   old=db.execute('SELECT * FROM make_hook_events WHERE hook=? AND idempotency=?',(r['id'],idem)).fetchone()
   if old:
    if old['payload']!=encoded:raise HTTPException(409,'Idempotency key already belongs to a different payload')
    return {'event':old['id'],'status':old['status'],'duplicate':True}
  pending=db.execute("SELECT count(*) FROM make_hook_events WHERE hook=? AND status='queued'",(r['id'],)).fetchone()[0]
  if pending>=100:raise HTTPException(429,'Webhook queue is full')
  eid=uuid.uuid4().hex
  db.execute('INSERT INTO make_hook_events VALUES(?,?,?,?,?,\'queued\',NULL,?,NULL,?)',(eid,r['id'],r['owner'],scenario['id'],encoded,time.time(),idem))
  return {'event':eid,'status':'queued','duplicate':False}

 @app.post('/api/ingress/hooks/{rid}')
 async def incoming_webhook(rid:str,req:Request):
  p=await payload(req)
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');r=authorize(db,req,rid,'hooks')
   result=enqueue(db,r,p,req.headers.get('idempotency-key'))
  return JSONResponse(result,status_code=202)

 @app.post('/api/integrations/{rid}/test')
 async def test_webhook(rid:str,req:Request):
  oid=owner(req);p=await payload(req)
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');r=owned_resource(db,oid,rid,'hooks');limited(db,rid)
   result=enqueue(db,r,p)
  return JSONResponse(result,status_code=202)

 def process_hooks():
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   rows=db.execute("SELECT e.* FROM make_hook_events e JOIN make_scenarios s ON s.id=e.scenario WHERE e.status='queued' AND (s.active=1 OR s.deleted=1) ORDER BY e.created LIMIT 5").fetchall()
   for e in rows:
    r=scenario_row(db,e['owner'],e['scenario']);graph=json.loads(r['graph'])
    if r['deleted'] or not graph or graph[0]['type']!='webhook':
     db.execute("UPDATE make_hook_events SET status='cancelled',finished=? WHERE id=?",(time.time(),e['id']));continue
    result=perform_run(db,e['owner'],r['id'],r,initial=json.loads(e['payload']),trigger='webhook')
    db.execute('UPDATE make_hook_events SET status=?,run=?,finished=? WHERE id=?',(result['status'],result['id'],time.time(),e['id']))

 def rpc(db,r,message):
  ident=message.get('id') if isinstance(message,dict) else None
  def error(code,text):return {'jsonrpc':'2.0','id':ident,'error':{'code':code,'message':text}}
  if isinstance(message,dict) and message.get('jsonrpc')=='2.0' and 'method' not in message and ('result' in message or 'error' in message):return None
  if not isinstance(message,dict) or message.get('jsonrpc')!='2.0' or not isinstance(message.get('method'),str):return error(-32600,'Invalid JSON-RPC request')
  if 'id' not in message:return None
  if not isinstance(ident,(str,int)) or isinstance(ident,bool):return error(-32600,'Invalid request id')
  method=message['method'];params=message.get('params',{})
  if not isinstance(params,dict):return error(-32602,'Parameters must be an object')
  if method=='initialize':result={'protocolVersion':'2025-03-26','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'make-local-tools','version':'1.0.0'}}
  elif method=='ping':result={}
  elif method in ('tools/list','tools/call'):
   selected=json.loads(r['config']).get('scenarios',[]);available={}
   for sid in selected:
    row=db.execute('SELECT * FROM make_scenarios WHERE id=? AND owner=? AND active=1 AND deleted=0 AND interval_minutes=0',(sid,r['owner'])).fetchone()
    if row:available['scenario_'+sid]=row
   if method=='tools/list':
    result={'tools':[{'name':name,'description':row['name'],'inputSchema':{'type':'object','properties':{'input':{'type':'object','description':'Scenario input values'}},'additionalProperties':False}} for name,row in available.items()]}
   else:
    name=params.get('name');arguments=params.get('arguments',{})
    if not isinstance(name,str) or name not in available:return error(-32602,'Tool is not available in this toolbox')
    if not isinstance(arguments,dict) or set(arguments)-{'input'} or not isinstance(arguments.get('input',{}),dict):return error(-32602,'Expected an object containing optional input values')
    execution=perform_run(db,r['owner'],available[name]['id'],available[name],initial=arguments.get('input',{}),trigger='mcp')
    last=execution['steps'][-1] if execution['steps'] else {}
    result={'content':[{'type':'text','text':json.dumps({'run':execution['id'],'status':execution['status'],'output':(execution['output'][0] if len(execution['output'])==1 else execution['output']),'error':last.get('error')},ensure_ascii=False)}],'isError':execution['status']!='success'}
  else:return error(-32601,'Method not found')
  return {'jsonrpc':'2.0','id':ident,'result':result}

 @app.post('/api/ingress/mcp/{rid}')
 async def mcp(rid:str,req:Request):
  raw=await req.body()
  if len(raw)>200000:raise HTTPException(413,'Request exceeds 200 KB')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');r=authorize(db,req,rid,'agent-profiles')
   try:d=json.loads(raw)
   except ValueError:return JSONResponse({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}},status_code=400)
   if isinstance(d,list):
    if not d or len(d)>20:return JSONResponse({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid batch'}},status_code=400)
    result=[reply for item in d if (reply:=rpc(db,r,item)) is not None]
   else:result=rpc(db,r,d)
  return JSONResponse(result) if result else Response(status_code=202)

 @app.get('/api/ingress/mcp/{rid}')
 def mcp_stream(rid:str,req:Request):
  with auth.connect() as db:authorize(db,req,rid,'agent-profiles')
  return Response(status_code=405,headers={'Allow':'POST'})

 return process_hooks
