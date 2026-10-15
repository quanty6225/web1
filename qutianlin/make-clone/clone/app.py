"""Make's isolated local application. No production integration requests."""
import json, os, secrets, smtplib, time, uuid, re, asyncio, contextlib
from urllib.parse import urlsplit,quote
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pathlib import Path
from email.message import EmailMessage
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.site_backend_integration import open_site_services
from auth_extensions import MakeAuthStore as LocalAuthStore
from websitebench.local_clone_auth.store import AuthError, AuthRateLimited

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_RUNTIME',str(ROOT/'backend/runtime.json'))
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(Path(os.getenv('WEBSITEBENCH_DATA_DIR',str(ROOT.parent/'data')))/'make.sqlite3'))
backend, _ = open_site_services()
WORKER = secrets.token_urlsafe(32)
auth = LocalAuthStore(backend.lifecycle.database_path, site_id='make', mail_mode='SMTP_PENDING', mail_worker_token=WORKER)
auth.ensure_schema()
with auth.connect() as db:
 db.executescript('''
 CREATE TABLE IF NOT EXISTS make_scenarios (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, graph TEXT NOT NULL,
 folder TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 0,
 interval_minutes INTEGER NOT NULL DEFAULT 15, version INTEGER NOT NULL DEFAULT 1,
 deleted INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS make_scenarios_owner ON make_scenarios(owner);
 CREATE TABLE IF NOT EXISTS make_runs (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, scenario TEXT NOT NULL, status TEXT NOT NULL,
 steps TEXT NOT NULL, started REAL NOT NULL, duration REAL NOT NULL, operations INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS make_resources (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
 config TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS make_settings (
 owner TEXT PRIMARY KEY, value TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS make_account_activity (
 owner TEXT PRIMARY KEY, last_login REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS make_starred_apps (
 owner TEXT NOT NULL, app TEXT NOT NULL, PRIMARY KEY(owner,app));
 CREATE TABLE IF NOT EXISTS make_module_counters (
 owner TEXT NOT NULL, scenario TEXT NOT NULL, module TEXT NOT NULL,
 value INTEGER NOT NULL, PRIMARY KEY(owner,scenario,module));
 CREATE TABLE IF NOT EXISTS make_registration_preferences (
 session_digest TEXT PRIMARY KEY, value TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS make_records (
 store TEXT NOT NULL REFERENCES make_resources(id) ON DELETE CASCADE,
 owner TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, updated REAL NOT NULL,
 PRIMARY KEY(store,key));
 INSERT OR IGNORE INTO websitebench_backend_migrations(migration_id,applied_at)
 VALUES ('make-business-v1',datetime('now'));
 INSERT OR IGNORE INTO websitebench_backend_migrations(migration_id,applied_at)
 VALUES ('make-native-tools-v6',datetime('now'));
 ''')
 if 'next_run' not in {r['name'] for r in db.execute('PRAGMA table_info(make_scenarios)')}:
  db.execute('ALTER TABLE make_scenarios ADD COLUMN next_run REAL NOT NULL DEFAULT 0')
 db.execute("INSERT OR IGNORE INTO websitebench_backend_migrations(migration_id,applied_at) VALUES('make-scheduler-v2',datetime('now'))")
 if 'labels' not in {r['name'] for r in db.execute('PRAGMA table_info(make_scenarios)')}:
  db.execute("ALTER TABLE make_scenarios ADD COLUMN labels TEXT NOT NULL DEFAULT '[]'")
 if 'trigger' not in {r['name'] for r in db.execute('PRAGMA table_info(make_runs)')}:
  db.execute("ALTER TABLE make_runs ADD COLUMN trigger TEXT NOT NULL DEFAULT 'manual'")
 db.execute("INSERT OR IGNORE INTO websitebench_backend_migrations(migration_id,applied_at) VALUES('make-scenario-metadata-v4',datetime('now'))")
 if 'outputs' not in {r['name'] for r in db.execute('PRAGMA table_info(make_runs)')}:
  db.execute("ALTER TABLE make_runs ADD COLUMN outputs TEXT NOT NULL DEFAULT '[]'")
 db.execute("INSERT OR IGNORE INTO websitebench_backend_migrations(migration_id,applied_at) VALUES('make-bundles-v5',datetime('now'))")
app=FastAPI(docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=list({'127.0.0.1','localhost','testserver',urlsplit(os.getenv('BASE_URL','http://127.0.0.1:18170')).hostname or 'localhost'}))
COOKIE='make_session'

def process_schedules():
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  rows=db.execute('SELECT * FROM make_scenarios WHERE active=1 AND deleted=0 AND interval_minutes>0 AND next_run<=? ORDER BY next_run LIMIT 5',(time.time(),)).fetchall()
  for row in rows:
   result=perform_run(db,row['owner'],row['id'],row,trigger='schedule')
   db.execute('UPDATE make_scenarios SET next_run=?,active=? WHERE id=?',(time.time()+row['interval_minutes']*60,int(result['status']=='success'),row['id']))

@app.on_event('startup')
async def start_scheduler():
 async def loop():
  while True:
   await asyncio.sleep(1)
   try:
    await asyncio.to_thread(process_schedules)
    await asyncio.to_thread(process_hooks)
   except Exception:
    # Keep the scheduler alive; executions remain pending if the transaction failed.
    import logging
    logging.getLogger('make.scheduler').exception('Local scheduler transaction failed')
 app.state.scheduler=asyncio.create_task(loop())

@app.on_event('shutdown')
async def stop_scheduler():
 app.state.scheduler.cancel()
 with contextlib.suppress(asyncio.CancelledError): await app.state.scheduler

@app.middleware('http')
async def protect(request, call_next):
 if request.method not in ('GET','HEAD','OPTIONS') or request.url.path.startswith('/api/ingress/'):
  origin=request.headers.get('origin')
  if origin and origin != str(request.base_url).rstrip('/'):
   return JSONResponse({'error':'Invalid request origin'},status_code=403)
  if request.headers.get('sec-fetch-site')=='cross-site':
   return JSONResponse({'error':'Cross-site request rejected'},status_code=403)
 response=await call_next(request)
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['Referrer-Policy']='same-origin'
 response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
 if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
 return response

@app.exception_handler(AuthError)
async def auth_error(request, exc):
 limited=isinstance(exc,AuthRateLimited)
 return JSONResponse({'error':str(exc),**({'retry_after':exc.retry_after} if limited else {})},status_code=429 if limited else 400,headers={'Retry-After':str(exc.retry_after)} if limited else {})

def cookie(response,token):
 response.set_cookie(COOKIE,token,httponly=True,samesite='lax',secure=True,max_age=2592000,path='/')
 return response

def session(req): return auth.resolve_session(req.cookies.get(COOKIE))
def owner(req):
 s=session(req)
 if not s or not s['authenticated']: raise HTTPException(401,'Please sign in')
 return s['account']['account_id']

def send_mail(token,purpose):
 claim=auth.claim_pending_mail_for_session(token,purpose=purpose,worker_token=WORKER)
 if not claim: return
 host=os.getenv('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
 if host not in ('127.0.0.1','localhost','mailpit'): raise HTTPException(503,'Mail service unavailable')
 msg=EmailMessage();msg['From']=os.getenv('WEBSITEBENCH_SMTP_FROM','no-reply@make.clone.test')
 msg['To']=claim['recipient'];msg['Subject']={'registration':'Verify your Make account','password-reset':'Reset your Make password','passwordless-signin':'Verify your local Make sign-in'}[purpose]
 code=claim['verification_code']
 target={'registration':'verify','password-reset':'reset-password','passwordless-signin':'login'}[purpose]
 origin=os.getenv('BASE_URL','http://127.0.0.1:18170').rstrip('/')
 msg.set_content(f'{msg["Subject"]}\n\nYour verification code is {code}.\nThis code expires in 10 minutes and can only be used once.\nContinue in the same browser: {origin}/{target}#code={code}\n')
 try:
  with smtplib.SMTP(host,int(os.getenv('WEBSITEBENCH_SMTP_PORT','1025')),timeout=8) as smtp:
   smtp.send_message(msg)
 except (OSError,smtplib.SMTPException):
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='network',worker_token=WORKER)
  raise HTTPException(503,'Email could not be sent. Please try again.')
 auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,accepted_request_count=1,worker_token=WORKER)

@app.get('/api/health')
@app.get('/healthz')
def health(): return {'ok':True,'site':'make','database':'sqlite'}

@app.get('/api/session')
def get_session(req:Request):
 token,s=auth.ensure_session(req.cookies.get(COOKIE))
 if s['authenticated']:
  with auth.connect() as db:
   activity=db.execute('SELECT last_login FROM make_account_activity WHERE owner=?',(s['account']['account_id'],)).fetchone()
  s['account']['last_login']=activity['last_login'] if activity else None
 return cookie(JSONResponse(s),token)

def record_login(token):
 account=auth.resolve_session(token)['account']
 with auth.connect() as db:
  db.execute('INSERT INTO make_account_activity VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET last_login=excluded.last_login',(account['account_id'],time.time()))

APP_CATALOG={'Data store','Flow control','Google Sheets','Tools','Webhooks','HTTP','Gmail','Telegram Bot','JSON','OpenAI (ChatGPT, Whisper)'}

@app.get('/api/starred-apps')
def starred_apps(req:Request):
 oid=owner(req)
 with auth.connect() as db:
  return [r['app'] for r in db.execute('SELECT app FROM make_starred_apps WHERE owner=? ORDER BY app',(oid,))]

@app.put('/api/starred-apps')
async def star_app(req:Request):
 oid=owner(req);data=await req.json()
 if not isinstance(data,dict) or not isinstance(data.get('app'),str) or data['app'] not in APP_CATALOG or type(data.get('starred')) is not bool:
  raise HTTPException(400,'Select a known app and a valid starred state')
 with auth.connect() as db:
  if data['starred']:db.execute('INSERT OR IGNORE INTO make_starred_apps VALUES(?,?)',(oid,data['app']))
  else:db.execute('DELETE FROM make_starred_apps WHERE owner=? AND app=?',(oid,data['app']))
 return {'app':data['app'],'starred':data['starred']}

@app.post('/api/auth/{action}')
async def auth_action(action:str,req:Request):
 data=await req.json();token=req.cookies.get(COOKIE)
 if not auth.resolve_session(token): raise HTTPException(401,'Please reload the page')
 if action=='resend':
  auth.resend_registration(token,data.get('email',''))
  send_mail(token,'registration')
  return {'ok':True,'step':'verify','mail_status':auth.session_mail_status(token,purpose='registration')}
 if action=='register':
  region=data.get('region','EU');country=str(data.get('country','United Kingdom (the)')).strip()
  countries={c['name'] for c in json.loads((ROOT/'static/countries.json').read_text())}
  if region not in ('EU','US') or country not in countries: raise HTTPException(400,'Select a valid hosting region and country')
  auth.start_registration(token,email=data.get('email',''),display_name=data.get('name',''),password=data.get('password',''),restart_invalid_flow=True)
  with auth.connect() as db:
   db.execute('INSERT INTO make_registration_preferences VALUES(?,?) ON CONFLICT(session_digest) DO UPDATE SET value=excluded.value',(auth.session_owner_digest(token),json.dumps({'region':region,'country':country})))
  send_mail(token,'registration');return {'ok':True,'step':'verify','mail_status':auth.session_mail_status(token,purpose='registration')}
 if action=='verify':
  digest=auth.session_owner_digest(token)
  auth.verify_registration_code(token,data.get('code',''))
  result=auth.complete_registration(token)
  with auth.connect() as db:
   prefs=db.execute('SELECT value FROM make_registration_preferences WHERE session_digest=?',(digest,)).fetchone()
   if prefs:
    value={'organization':'My Organization','team':'My Team','timezone':'America/Toronto','notifications':True,**json.loads(prefs['value'])}
    db.execute('INSERT OR IGNORE INTO make_settings VALUES(?,?)',(result['account']['account_id'],json.dumps(value)))
    db.execute('DELETE FROM make_registration_preferences WHERE session_digest=?',(digest,))
  record_login(result['session_token'])
  return cookie(JSONResponse({'ok':True}),result['session_token'])
 if action=='login':
  result=auth.sign_in(token,email=data.get('email',''),password=data.get('password',''))
  record_login(result['session_token'])
  return cookie(JSONResponse({'ok':True}),result['session_token'])
 if action=='provider-start':
  if data.get('provider') not in ('Google','SSO','Microsoft','Apple','GitHub','Facebook'): raise HTTPException(400,'Unknown local provider')
  auth.start_passwordless_signin(token,email=data.get('email',''),restart_invalid_flow=True)
  send_mail(token,'passwordless-signin')
  return {'ok':True,'adapter':'local-email-verified','step':'verify'}
 if action=='provider-verify':
  auth.verify_passwordless_code(token,data.get('code',''))
  result=auth.complete_passwordless_signin(token)
  record_login(result['session_token'])
  return cookie(JSONResponse({'ok':True,'adapter':'local-email-verified'}),result['session_token'])
 if action=='logout':
  auth.sign_out(token);r=JSONResponse({'ok':True});r.delete_cookie(COOKIE,path='/');return r
 if action=='forgot':
  auth.start_password_reset(token,email=data.get('email',''),restart_invalid_flow=True)
  send_mail(token,'password-reset');return {'ok':True,'step':'reset'}
 if action=='reset':
  auth.verify_password_reset_code(token,data.get('code',''))
  new_token=auth.complete_password_reset(token,new_password=data.get('password',''))
  return cookie(JSONResponse({'ok':True}),new_token)
 raise HTTPException(404,'Unknown action')

def scenario_row(db,oid,sid):
 row=db.execute('SELECT * FROM make_scenarios WHERE id=? AND owner=?',(sid,oid)).fetchone()
 if row is None: raise HTTPException(404,'Scenario not found')
 return row

def scenario_json(row):
 d=dict(row);d.pop('owner',None);d['graph']=json.loads(d['graph']);d['active']=bool(d['active']);d['labels']=json.loads(d['labels']);return d

def validate_graph(graph):
 if not isinstance(graph,list) or len(graph)>50: raise HTTPException(400,'A scenario can contain up to 50 modules')
 ids=set()
 for module in graph:
  if not isinstance(module,dict) or module.get('type') not in {'set-variable','set-variables','get-variable','get-variables','increment','switch','basic-trigger','text-aggregator','numeric-aggregator','json-aggregate','store-put','store-get','store-update','store-delete','store-exists','store-count','store-search','json-parse','json-create','text','filter','iterator','sleep','webhook','google-sheets','gmail','openai','telegram','http'}:
   raise HTTPException(400,'Unknown module')
  mid=str(module.get('id',''))
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',mid) or mid in ids: raise HTTPException(400,'Module IDs must be unique alphanumeric identifiers')
  ids.add(mid)
  if module['type']=='basic-trigger' and len(ids)!=1:raise HTTPException(400,'The Basic trigger must be the first module')
  if not isinstance(module.get('config',{}),dict): raise HTTPException(400,'Invalid module configuration')
 try:encoded=json.dumps(graph,allow_nan=False)
 except (ValueError,TypeError):raise HTTPException(400,'Scenario must contain valid JSON values')
 if len(encoded)>200000: raise HTTPException(400,'Scenario is too large')
 return graph

@app.post('/api/blueprints/validate')
async def validate_blueprint(req:Request):
 owner(req)
 raw=await req.body()
 if len(raw)>250000:raise HTTPException(400,'Blueprint must be smaller than 250 KB')
 try:d=json.loads(raw)
 except (ValueError,UnicodeError):raise HTTPException(400,'Choose a valid JSON blueprint')
 if not isinstance(d,dict):raise HTTPException(400,'Blueprint must be a JSON object')
 graph=validate_graph(d.get('graph'))
 name=d.get('name','New scenario')
 if not isinstance(name,str) or not name.strip() or len(name)>160:raise HTTPException(400,'Blueprint name must contain 1–160 characters')
 return {'name':name.strip(),'graph':graph}

@app.get('/api/scenarios')
def scenarios(req:Request,trash:bool=False):
 oid=owner(req)
 with auth.connect() as db:
  return [scenario_json(r) for r in db.execute('SELECT * FROM make_scenarios WHERE owner=? AND deleted=? ORDER BY name COLLATE NOCASE',(oid,int(trash)))]

@app.post('/api/scenarios')
async def create_scenario(req:Request):
 oid=owner(req);d=await req.json();graph=validate_graph(d.get('graph',[]));name=str(d.get('name','New scenario')).strip()[:160]
 if not name: raise HTTPException(400,'Scenario name is required')
 sid=uuid.uuid4().hex;now=time.time()
 with auth.connect() as db:
  db.execute('INSERT INTO make_scenarios(id,owner,name,graph,created,updated) VALUES(?,?,?,?,?,?)',(sid,oid,name,json.dumps(graph),now,now))
  return scenario_json(scenario_row(db,oid,sid))

@app.get('/api/scenarios/{sid}')
def get_scenario(sid:str,req:Request):
 with auth.connect() as db: return scenario_json(scenario_row(db,owner(req),sid))

@app.put('/api/scenarios/{sid}')
async def update_scenario(sid:str,req:Request):
 oid=owner(req);d=await req.json();graph=validate_graph(d.get('graph',[]));name=str(d.get('name','')).strip()[:160]
 if not name: raise HTTPException(400,'Scenario name is required')
 minutes=d.get('interval_minutes',15)
 if not isinstance(minutes,int) or minutes<0 or minutes>525600: raise HTTPException(400,'Invalid scheduling interval')
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE');r=scenario_row(db,oid,sid)
  if d.get('version')!=r['version']: raise HTTPException(409,'This scenario changed in another tab. Reload before saving.')
  folder=str(d.get('folder',''))
  labels=d.get('labels',[])
  if not isinstance(labels,list) or len(labels)>50 or any(not isinstance(x,str) for x in labels):raise HTTPException(400,'Invalid labels')
  if folder:owned_resource(db,oid,folder,'folders')
  for label in labels:owned_resource(db,oid,label,'labels')
  active=bool(d.get('active',False))
  if active and not graph: raise HTTPException(400,'Add a module before activating your scenario')
  if active and graph[0]['type']=='webhook' and minutes!=0:raise HTTPException(400,'Choose On demand scheduling for this webhook scenario')
  due=(r['next_run'] if r['active'] and r['interval_minutes']==minutes else time.time()+minutes*60) if active and minutes>0 else 0
  db.execute('UPDATE make_scenarios SET name=?,graph=?,folder=?,labels=?,interval_minutes=?,active=?,next_run=?,version=version+1,updated=? WHERE id=? AND owner=?',(name,json.dumps(graph),folder,json.dumps(list(dict.fromkeys(labels))),minutes,int(active),due,time.time(),sid,oid))
  return scenario_json(scenario_row(db,oid,sid))

@app.post('/api/scenarios/{sid}/{action}')
async def scenario_action(sid:str,action:str,req:Request):
 oid=owner(req)
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE');r=scenario_row(db,oid,sid)
  if action in ('trash','restore'):
   db.execute('UPDATE make_scenarios SET deleted=?,active=0,version=version+1 WHERE id=? AND owner=?',(int(action=='trash'),sid,oid));return {'ok':True}
  if action=='clone':
   nid=uuid.uuid4().hex;now=time.time()
   db.execute('INSERT INTO make_scenarios(id,owner,name,graph,folder,labels,interval_minutes,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(nid,oid,r['name']+' (copy)',r['graph'],r['folder'],r['labels'],r['interval_minutes'],now,now));return scenario_json(scenario_row(db,oid,nid))
  if action!='run': raise HTTPException(404,'Unknown scenario action')
  if r['deleted']: raise HTTPException(400,'Restore the scenario before running it')
  return perform_run(db,oid,sid,r)

def perform_run(db,oid,sid,r,initial=None,trigger='manual'):
 from execution import execute
 graph=json.loads(r['graph'])
 if not graph:raise HTTPException(400,'Add a module before running this scenario')
 def increment(mid):
  row=db.execute('SELECT value FROM make_module_counters WHERE owner=? AND scenario=? AND module=?',(oid,sid,mid)).fetchone()
  value=(row['value'] if row else 0)+1
  if value>9007199254740991:raise ValueError('Counter exceeds the supported integer limit')
  db.execute('INSERT INTO make_module_counters VALUES(?,?,?,?) ON CONFLICT(owner,scenario,module) DO UPDATE SET value=excluded.value',(oid,sid,mid,value))
  return value
 def json_structure(rid):
  try:return json.loads(owned_resource(db,oid,rid,'udts')['config'])
  except HTTPException as exc:raise ValueError(str(exc.detail)) from exc
 result=execute(graph,initial=initial,trigger=trigger,increment=increment,store_action=lambda kind,cfg:execute_store(db,oid,kind,cfg),json_structure=json_structure)
 result.update(id=uuid.uuid4().hex,scenario=sid,trigger=trigger)
 db.execute('INSERT INTO make_runs(id,owner,scenario,status,steps,started,duration,operations,trigger,outputs) VALUES(?,?,?,?,?,?,?,?,?,?)',(result['id'],oid,sid,result['status'],json.dumps(result['steps']),result['started'],result['duration'],result['operations'],trigger,json.dumps(result['output'])))
 return result

@app.get('/api/scenarios/{sid}/runs')
def runs(sid:str,req:Request):
 oid=owner(req)
 with auth.connect() as db:
  scenario_row(db,oid,sid)
  result=[]
  for r in db.execute('SELECT * FROM make_runs WHERE owner=? AND scenario=? ORDER BY started DESC LIMIT 100',(oid,sid)):
   d=dict(r);d.pop('owner');d['steps']=json.loads(d['steps']);d['output']=json.loads(d.pop('outputs'));result.append(d)
  return result

KINDS={'folders','labels','data-stores','udts','hooks','connections','agents','agent-profiles','devices','keys','apps'}
@app.get('/api/resources/{kind}')
def resources(kind:str,req:Request):
 oid=owner(req)
 if kind not in KINDS: raise HTTPException(404,'Unknown resource')
 with auth.connect() as db:
  return [dict(r)|{'config':json.loads(r['config'])} for r in db.execute('SELECT id,kind,name,config,created FROM make_resources WHERE owner=? AND kind=? ORDER BY created',(oid,kind))]

@app.post('/api/resources/{kind}')
async def create_resource(kind:str,req:Request):
 oid=owner(req);d=await req.json()
 if kind not in KINDS: raise HTTPException(404,'Unknown resource')
 name=str(d.get('name','')).strip()[:160]
 if not name: raise HTTPException(400,'Name is required')
 rid=uuid.uuid4().hex;cfg=d.get('config',{})
 if not isinstance(cfg,dict) or len(json.dumps(cfg))>200000: raise HTTPException(400,'Invalid configuration')
 if kind=='data-stores' and cfg.get('maxSizeMB',1)!=1: raise HTTPException(400,'Data storage size must be equal to 1 MB on the Free plan')
 if kind in ('udts','data-stores') and not isinstance(cfg.get('schema',{}),dict): raise HTTPException(400,'A data structure must be a JSON object')
 if kind=='agent-profiles':
  ids=cfg.get('scenarios',[])
  if not isinstance(ids,list) or len(ids)>50: raise HTTPException(400,'Invalid scenario selection')
  with auth.connect() as db:
   for sid in ids:
    row=scenario_row(db,oid,str(sid))
    if row['deleted'] or not row['active'] or row['interval_minutes']!=0:raise HTTPException(400,'Tool scenarios must be active and scheduled on demand')
 if kind=='hooks':
  with auth.connect() as db:
   row=scenario_row(db,oid,str(cfg.get('scenario','')));graph=json.loads(row['graph'])
   if row['deleted'] or not graph or graph[0]['type']!='webhook':raise HTTPException(400,'Select a scenario beginning with a Webhook module')
  cfg={'scenario':row['id']}
 with auth.connect() as db: db.execute('INSERT INTO make_resources VALUES(?,?,?,?,?,?)',(rid,oid,kind,name,json.dumps(cfg),time.time()))
 return {'id':rid,'name':name,'kind':kind,'config':cfg}

def owned_resource(db,oid,rid,kind=None):
 row=db.execute('SELECT * FROM make_resources WHERE id=? AND owner=?',(rid,oid)).fetchone()
 if not row or (kind and row['kind']!=kind): raise HTTPException(404,'Resource not found')
 return row

@app.get('/api/stores/{rid}')
def get_records(rid:str,req:Request):
 oid=owner(req)
 with auth.connect() as db:
  resource=owned_resource(db,oid,rid,'data-stores')
  rows=db.execute('SELECT key,value,updated FROM make_records WHERE store=? AND owner=? ORDER BY key',(rid,oid)).fetchall()
  return {'name':resource['name'],'config':json.loads(resource['config']),'records':[{'key':r['key'],'value':json.loads(r['value']),'updated':r['updated']} for r in rows]}

def write_record(db,oid,rid,key,value,resource):
 if not isinstance(key,str) or not key.strip() or len(key)>200 or not isinstance(value,dict):raise HTTPException(400,'A key and a JSON object are required')
 try:encoded=json.dumps(value,allow_nan=False)
 except (ValueError,TypeError):raise HTTPException(400,'Record values must be valid JSON')
 cfg=json.loads(resource['config'])
 schema=cfg.get('schema',{});properties=schema.get('properties',{})
 if not isinstance(properties,dict): raise HTTPException(400,'The store data structure is invalid')
 for field in schema.get('required',[]):
  if field not in value: raise HTTPException(400,'Required field missing: '+str(field))
 types={'string':str,'number':(int,float),'integer':int,'boolean':bool,'object':dict,'array':list}
 for field,spec in properties.items():
  if field in value and isinstance(spec,dict) and spec.get('type') in types:
   if not isinstance(value[field],types[spec['type']]) or (spec['type'] in ('number','integer') and isinstance(value[field],bool)):
    raise HTTPException(400,'Invalid type for field: '+field)
 if cfg.get('strict') and any(k not in properties for k in value): raise HTTPException(400,'The record contains fields not in the data structure')
 used=db.execute('SELECT coalesce(sum(length(cast(value as blob))),0) FROM make_records WHERE store=? AND key<>?',(rid,key)).fetchone()[0]
 if used+len(encoded.encode())>1048576: raise HTTPException(400,'The data store has reached its 1 MB capacity')
 db.execute('INSERT INTO make_records VALUES(?,?,?,?,?) ON CONFLICT(store,key) DO UPDATE SET value=excluded.value,updated=excluded.updated',(rid,oid,key,encoded,time.time()))
 return {'key':key,'value':value}

@app.put('/api/stores/{rid}/records/{key:path}')
async def put_record(rid:str,key:str,req:Request):
 oid=owner(req);d=await req.json()
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE');resource=owned_resource(db,oid,rid,'data-stores')
  return write_record(db,oid,rid,key,d.get('value'),resource)


def execute_store(db,oid,kind,cfg):
 try:
  rid=cfg.get('store','')
  if not isinstance(rid,str) or not rid:raise ValueError('Select a data store')
  resource=owned_resource(db,oid,rid,'data-stores')
  if kind=='store-count':return {'count':db.execute('SELECT count(*) FROM make_records WHERE store=? AND owner=?',(rid,oid)).fetchone()[0]}
  if kind=='store-search':
   limit=cfg.get('limit',100)
   if isinstance(limit,bool) or not re.fullmatch(r'[0-9]+',str(limit)) or not 1<=int(limit)<=100:raise ValueError('Search limit must be an integer between 1 and 100')
   field=cfg.get('field','');query=cfg.get('query','');sort=cfg.get('order','ascending');operator=cfg.get('operator','Equal to')
   if not isinstance(field,str) or sort not in ('ascending','descending'):raise ValueError('Invalid search options')
   from execution import FILTER_OPERATORS
   if not isinstance(operator,str) or operator not in FILTER_OPERATORS:raise ValueError('Unknown filter operator')
   rows=db.execute('SELECT key,value FROM make_records WHERE store=? AND owner=? ORDER BY key '+('ASC' if sort=='ascending' else 'DESC'),(rid,oid))
   results=[]
   for row in rows:
    value=json.loads(row['value'])
    if field:
     from execution import filter_matches
     operand={'query':query}
     if field in value:operand['value']=value[field]
     if field not in value and operator not in ('Exists','Does not exist'):continue
     if not filter_matches({'left':'{{value}}','operator':operator,'right':'{{query}}'},operand):continue
    results.append({'key':row['key'],'record':value})
    if len(results)==int(limit):break
   return results
  key=cfg.get('key','')
  if kind=='store-put' and key=='':key=uuid.uuid4().hex
  if isinstance(key,(int,float)) and not isinstance(key,bool):key=str(key)
  if not isinstance(key,str) or not key.strip() or len(key)>200:raise ValueError('Enter a record key of 1–200 characters')
  row=db.execute('SELECT value FROM make_records WHERE store=? AND owner=? AND key=?',(rid,oid,key)).fetchone()
  if kind=='store-exists':return {'exists':row is not None,'key':key}
  if kind=='store-get':
   if row is None:raise ValueError('Record not found')
   return {'key':key,'record':json.loads(row['value'])}
  if kind=='store-delete':
   if row is None:raise ValueError('Record not found')
   db.execute('DELETE FROM make_records WHERE store=? AND owner=? AND key=?',(rid,oid,key))
   return {'key':key,'deleted':True}
  if kind not in ('store-put','store-update'):raise ValueError('Unknown data store operation')
  option=cfg.get('overwrite' if kind=='store-put' else 'insert_missing','no')
  if type(option) is not bool and option not in ('yes','no'):raise ValueError('Select yes or no for the record write option')
  enabled=option is True or option=='yes'
  if kind=='store-put' and row is not None and not enabled:raise ValueError('Record already exists; enable overwrite to replace it')
  if kind=='store-update' and row is None and not enabled:raise ValueError('Record not found; enable insert missing record to create it')
  value=cfg.get('record',{})
  if not isinstance(value,dict):raise ValueError('Record must be a JSON object')
  if kind=='store-update' and row is not None:value={**json.loads(row['value']),**value}
  write_record(db,oid,rid,key,value,resource)
  return {'key':key,'record':value}
 except HTTPException as exc:raise ValueError(str(exc.detail)) from exc

@app.delete('/api/stores/{rid}/records/{key:path}')
def delete_record(rid:str,key:str,req:Request):
 oid=owner(req)
 with auth.connect() as db:
  owned_resource(db,oid,rid,'data-stores')
  if not db.execute('DELETE FROM make_records WHERE store=? AND key=? AND owner=?',(rid,key,oid)).rowcount: raise HTTPException(404,'Record not found')
 return {'ok':True}

@app.delete('/api/resources/{kind}/{rid}')
def delete_resource(kind:str,rid:str,req:Request):
 oid=owner(req)
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE');owned_resource(db,oid,rid,kind)
  if kind=='folders':db.execute("UPDATE make_scenarios SET folder='',version=version+1 WHERE owner=? AND folder=?",(oid,rid))
  if kind=='labels':
   for row in db.execute('SELECT id,labels FROM make_scenarios WHERE owner=?',(oid,)).fetchall():
    labels=json.loads(row['labels'])
    if rid in labels:db.execute('UPDATE make_scenarios SET labels=?,version=version+1 WHERE id=?',(json.dumps([x for x in labels if x!=rid]),row['id']))
  changed=db.execute('DELETE FROM make_resources WHERE id=? AND owner=? AND kind=?',(rid,oid,kind)).rowcount
  if not changed: raise HTTPException(404,'Resource not found')
 return {'ok':True}

@app.put('/api/resources/{kind}/{rid}')
async def rename_resource(kind:str,rid:str,req:Request):
 oid=owner(req);d=await req.json();name=str(d.get('name','')).strip()[:160]
 if kind not in ('folders','labels'):raise HTTPException(400,'Use the resource settings to edit this item')
 if not name:raise HTTPException(400,'Name is required')
 with auth.connect() as db:
  owned_resource(db,oid,rid,kind)
  db.execute('UPDATE make_resources SET name=? WHERE id=? AND owner=?',(name,rid,oid))
 return {'ok':True}

@app.get('/api/settings')
def settings(req:Request):
 with auth.connect() as db:
  r=db.execute('SELECT value FROM make_settings WHERE owner=?',(owner(req),)).fetchone()
  return json.loads(r['value']) if r else {'organization':'My Organization','team':'My Team','timezone':'America/Toronto','notifications':True}

@app.get('/api/usage')
def usage(req:Request):
 with auth.connect() as db:
  row=db.execute('SELECT count(*) executions,coalesce(sum(operations),0) operations FROM make_runs WHERE owner=?',(owner(req),)).fetchone()
  return dict(row)

@app.get('/api/system-variables')
def system_variables(req:Request):
 oid=owner(req)
 from datetime import datetime,timezone
 month=datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
 with auth.connect() as db:
  row=db.execute('SELECT value FROM make_settings WHERE owner=?',(oid,)).fetchone()
  prefs=json.loads(row['value']) if row else {}
  operations=db.execute('SELECT coalesce(sum(operations),0) FROM make_runs WHERE owner=? AND started>=?',(oid,month)).fetchone()[0]
 def item(name,kind,value):return {'name':name,'data_type':kind,'value':value,'type':'System'}
 return {'organization':[item('Data left','number',536870912),item('Organization id','number',1),item('Organization name','text',prefs.get('organization','My Organization')),item('Operations left','number',max(0,1000-operations)),item('Zone domain','text',req.url.netloc)],'team':[item('Team id','number',1),item('Team name','text',prefs.get('team','My Team'))],'period_start':month}

@app.put('/api/account/profile')
async def update_profile(req:Request):
 owner(req);d=await req.json()
 if not isinstance(d,dict):raise HTTPException(400,'Invalid profile')
 return auth.update_profile(req.cookies.get(COOKIE),d.get('name',''))

@app.post('/api/account/password')
async def update_password(req:Request):
 owner(req);d=await req.json()
 if not isinstance(d,dict):raise HTTPException(400,'Invalid password request')
 token=auth.change_password(req.cookies.get(COOKIE),d.get('current_password',''),d.get('password',''))
 return cookie(JSONResponse({'ok':True}),token)

@app.put('/api/settings')
async def save_settings(req:Request):
 oid=owner(req);d=await req.json()
 if not isinstance(d,dict):raise HTTPException(400,'Invalid settings')
 changes={k:d[k] for k in ('organization','team','timezone','notifications','notification_options','region','country') if k in d}
 for key in ('organization','team','timezone','region','country'):
  if key in changes:
   if not isinstance(changes[key],str) or not changes[key].strip() or len(changes[key])>160:raise HTTPException(400,'Invalid '+key)
   changes[key]=changes[key].strip()
 if 'notifications' in changes and not isinstance(changes['notifications'],bool):raise HTTPException(400,'Invalid notification setting')
 options=changes.get('notification_options',{})
 if not isinstance(options,dict) or set(options)-{'warnings','errors','deactivation','credits','connections'} or any(not isinstance(x,bool) for x in options.values()):raise HTTPException(400,'Invalid notification options')
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT value FROM make_settings WHERE owner=?',(oid,)).fetchone()
  value=json.loads(row['value']) if row else {'organization':'My Organization','team':'My Team','timezone':'America/Toronto','notifications':True}
  if 'notification_options' in changes:changes['notification_options']={**value.get('notification_options',{}),**options}
  value.update(changes)
  if len(json.dumps(value))>2000:raise HTTPException(400,'Settings too large')
  db.execute('INSERT INTO make_settings VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET value=excluded.value',(oid,json.dumps(value)))
 return value

from integrations import install_integrations
process_hooks=install_integrations(app,auth,owner,owned_resource,scenario_row,perform_run)

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.get('/{path:path}')
def page(path:str,req:Request):
 public=path in ('login','register','resend-verification','forgot-password','verify','reset-password','','help','terms-and-conditions','privacy-notice','disclaimer') or path.startswith(('en/','help/'))
 if not public and not (session(req) or {}).get('authenticated'): return RedirectResponse('/login?next='+quote('/'+path+('?' + req.url.query if req.url.query else ''),safe=''),status_code=303)
 return FileResponse(ROOT/'static/index.html')

if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','18170')))
