"""Independent Teamwork clone: persistent accounts, isolated workspace data and SMTP."""
from __future__ import annotations
import organization_local
import os,json,secrets,sqlite3,time,hashlib,smtplib,html,mimetypes,re
from pathlib import Path
from lxml import html as dom,etree
from email.message import EmailMessage
from urllib.parse import quote,urlsplit,urlencode
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,FileResponse
from local_assets import CapturedStaticFiles
from websitebench.local_clone_auth import LocalAuthStore,AuthError,AuthConflict,AuthValidationError,AuthRateLimited,MAIL_SMTP_PENDING
from backend.site_backend_integration import open_site_services
import task_assignees
from automation_fields import validate_definition,validate_definition_scope

HERE=Path(__file__).resolve().parent
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_RUNTIME',str(HERE/'backend/runtime.json'))
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(HERE.parent/'data/teamwork.sqlite3'))
SERVICE,_=open_site_services()
WORKER=secrets.token_urlsafe(32)
AUTH=LocalAuthStore(SERVICE.lifecycle.database_path,site_id='teamwork',mail_mode=MAIL_SMTP_PENDING,mail_worker_token=WORKER)
AUTH.ensure_schema()
with AUTH.connect() as c:
 c.execute('CREATE TABLE IF NOT EXISTS tw_seed_state(key TEXT PRIMARY KEY)');demo_deleted=c.execute("SELECT 1 FROM tw_seed_state WHERE key='demo-deleted'").fetchone()
with AUTH.connect() as c:existing_demo=c.execute("SELECT account_id FROM local_auth_accounts WHERE subject_id='demo'").fetchone()
DEMO=None if demo_deleted else existing_demo['account_id'] if existing_demo else AUTH.seed_account(subject_id='demo',email='demo@teamwork.offline.invalid',display_name='Sam Yu',password='Teamwork-Demo-2026!')
COOKIE='teamwork_session'
ROUTES=json.loads((HERE/'backend/routes.json').read_text())
HELP_SEARCH=json.loads((HERE/'backend/help-search.json').read_text()) if (HERE/'backend/help-search.json').exists() else []
QUERY_ROUTES=json.loads((HERE/'backend/query-routes.json').read_text()) if (HERE/'backend/query-routes.json').exists() else {}
STATES=json.loads((HERE/'backend/states.json').read_text())
FRAMES=json.loads((HERE/'backend/frames.json').read_text())
TOURS=json.loads((HERE/'backend/tour.json').read_text()) if (HERE/'backend/tour.json').exists() else {}
BOUNDARIES=json.loads((HERE/'backend/boundaries.json').read_text())
UPLOADS=Path(os.environ.get('TEAMWORK_UPLOAD_DIR',str(Path(os.environ['WEBSITEBENCH_SITE_BACKEND_DATABASE']).parent/'uploads')));UPLOADS.mkdir(parents=True,exist_ok=True)
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)

def db():
 c=sqlite3.connect(SERVICE.lifecycle.database_path,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
with db() as c:
 c.executescript('''
 CREATE TABLE IF NOT EXISTS tw_projects(id TEXT NOT NULL,owner TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',starred INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,id));
 CREATE TABLE IF NOT EXISTS tw_tasks(id TEXT NOT NULL,owner TEXT NOT NULL,project_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',priority TEXT NOT NULL DEFAULT 'None',stage TEXT NOT NULL DEFAULT 'Backlog',tag TEXT NOT NULL DEFAULT '',start_date TEXT,due_date TEXT,completed INTEGER NOT NULL DEFAULT 0,list_name TEXT NOT NULL DEFAULT 'My List',assignee TEXT NOT NULL DEFAULT '',estimate INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,id),FOREIGN KEY(owner,project_id) REFERENCES tw_projects(owner,id));
 CREATE TABLE IF NOT EXISTS tw_records(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,parent TEXT NOT NULL DEFAULT '',data TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS tw_preferences(owner TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(owner,key));
 CREATE TABLE IF NOT EXISTS tw_memberships(account TEXT NOT NULL,workspace_owner TEXT NOT NULL,PRIMARY KEY(account,workspace_owner));
 CREATE TABLE IF NOT EXISTS tw_invites(digest TEXT PRIMARY KEY,workspace_owner TEXT NOT NULL,email TEXT NOT NULL,expires INTEGER NOT NULL,accepted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS tw_auth_returns(session TEXT PRIMARY KEY,path TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS tw_feedback(id TEXT PRIMARY KEY,account TEXT NOT NULL,message TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS tw_public_forms(id TEXT PRIMARY KEY,session TEXT NOT NULL,data TEXT NOT NULL,created INTEGER NOT NULL);
 ''')
 if 'parent_id' not in [r['name'] for r in c.execute('PRAGMA table_info(tw_tasks)')]:c.execute("ALTER TABLE tw_tasks ADD COLUMN parent_id TEXT NOT NULL DEFAULT ''")
 if 'created_at' not in [r['name'] for r in c.execute('PRAGMA table_info(tw_tasks)')]:c.execute('ALTER TABLE tw_tasks ADD COLUMN created_at TEXT')
 if 'client_id' not in [r['name'] for r in c.execute('PRAGMA table_info(tw_projects)')]:c.execute("ALTER TABLE tw_projects ADD COLUMN client_id TEXT NOT NULL DEFAULT ''")
 c.execute('CREATE TABLE IF NOT EXISTS tw_seed_state(key TEXT PRIMARY KEY)')
 seeded=c.execute("SELECT 1 FROM tw_seed_state WHERE key='demo-v1'").fetchone()
 if not seeded:
  c.execute('INSERT OR IGNORE INTO tw_projects(id,owner,name) VALUES(?,?,?)',('372311',DEMO,'789'))
  for tid,title,priority,tag,due,assignee in [('18438851','1','High','Published','2026-10-13','Sam Yu'),('18438852','2','Medium','Draft','2026-10-20','Sam Yu'),('18438853','23','Low','Review',None,'')]:
   c.execute('INSERT OR IGNORE INTO tw_tasks(id,owner,project_id,title,priority,tag,start_date,due_date,assignee) VALUES(?,?,?,?,?,?,?,?,?)',(tid,DEMO,'372311',title,priority,tag,'2026-10-13',due,assignee))
  c.execute("INSERT INTO tw_seed_state(key) VALUES('demo-v1')")
 if not c.execute("SELECT 1 FROM tw_seed_state WHERE key='demo-client-v1'").fetchone():
  client=secrets.token_hex(12)
  c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(client,DEMO,'client','',json.dumps({'title':'tenspo','internal':True}),int(time.time())))
  c.execute("UPDATE tw_projects SET client_id=? WHERE owner=? AND id='372311'",(client,DEMO))
  c.execute("INSERT INTO tw_seed_state(key) VALUES('demo-client-v1')")
 # Historical rows have no reliable creation timestamp. Leave them unknown;
 # new tasks, including copies, imports and automation tasks, get their actual
 # local creation time through the same database path.
 c.execute("""CREATE TRIGGER IF NOT EXISTS tw_task_created_at AFTER INSERT ON tw_tasks
 BEGIN UPDATE tw_tasks SET created_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
 WHERE owner=NEW.owner AND id=NEW.id; END""")

def account(req:Request):
 s=AUTH.resolve_session(req.cookies.get(COOKIE))
 if not s or not s['authenticated']:raise HTTPException(401,'Please log in to continue.')
 return s['account']
def owner(req):
 who=account(req)['account_id']
 with db() as c:
  selected=c.execute("SELECT value FROM tw_preferences WHERE owner=? AND key='active_workspace'",(who,)).fetchone()
  if selected:
   target=json.loads(selected['value'])
   if c.execute('SELECT 1 FROM tw_memberships WHERE account=? AND workspace_owner=?',(who,target)).fetchone():return target
 return who
def safe_next(value):return value if isinstance(value,str) and value.startswith('/') and not value.startswith('//') and '\\' not in value else '/app/home'
def response(data,token=None,status=200,persistent=True):
 r=JSONResponse(data,status_code=status)
 if token:r.set_cookie(COOKIE,token,httponly=True,samesite='lax',secure=os.environ.get('TEAMWORK_TLS')=='1',max_age=60*60*24*30 if persistent else None,path='/')
 return r

def mail(session,purpose,base):
 claim=AUTH.claim_pending_mail_for_session(session,purpose=purpose,worker_token=WORKER)
 if not claim:return False
 route='/signup/verify' if purpose=='registration' else '/launchpad/resetpassword'
 code=claim['verification_code'];msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@teamwork.clone.test');msg['To']=claim['recipient'];msg['Subject']='Verify your Teamwork.com account' if purpose=='registration' else 'Reset your Teamwork.com password'
 msg.set_content(f"Your Teamwork.com verification code is {code}.\n\nOpen {base.rstrip('/')}{route}?code={code}\n\nThe code expires in 10 minutes and can only be used once. This is your local Teamwork workspace.")
 try:
  with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(msg)
 except (OSError,smtplib.SMTPException):
  AUTH.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='network',worker_token=WORKER)
  raise HTTPException(503,'Email could not be sent. Please retry.')
 AUTH.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,accepted_request_count=1,worker_token=WORKER)
 return True

@app.middleware('http')
async def secure_headers(req,call_next):
 if req.method not in ['GET','HEAD','OPTIONS']:
  origin=req.headers.get('origin')
  if origin and urlsplit(origin).netloc!=req.headers.get('host'):return JSONResponse({'detail':'Request origin is not allowed.'},status_code=403)
 result=await call_next(req)
 result.headers['Cache-Control']='no-store' if not req.url.path.startswith('/static/') else 'public, max-age=86400'
 result.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
 result.headers['X-Content-Type-Options']='nosniff';result.headers['Referrer-Policy']='same-origin'
 return result

@app.exception_handler(AuthError)
async def auth_error(req,exc):
 code=429 if isinstance(exc,AuthRateLimited) else 409 if isinstance(exc,AuthConflict) else 400
 return JSONResponse({'detail':str(exc)},status_code=code)

@app.get('/healthz')
@app.get('/__websitebench/health')
def health():return {'status':'ok','site':'teamwork','persistence':'sqlite','mail':'smtp'}

@app.get('/api/session')
def session(req:Request):
 token,state=AUTH.ensure_session(req.cookies.get(COOKIE));return response(state,token)

@app.post('/api/auth/{action}')
async def auth_action(action:str,req:Request):
 d=dict(await req.form()) if 'application/x-www-form-urlencoded' in req.headers.get('content-type','') else await req.json();token,state=AUTH.ensure_session(req.cookies.get(COOKIE))
 if action=='login':
  result=AUTH.sign_in(token,email=d.get('email',''),password=d.get('password',''))
  if d.get('embedded')=='1':
   r=RedirectResponse(safe_next(d.get('next')),status_code=303);r.set_cookie(COOKIE,result['session_token'],httponly=True,samesite='lax',secure=os.environ.get('TEAMWORK_TLS')=='1',path='/');return r
  return response({'ok':True,'redirect':safe_next(d.get('next'))},result['session_token'],persistent=d.get('remember') in [True,'on','true'])
 if action=='logout':
  AUTH.sign_out(token);r=response({'ok':True,'redirect':'/launchpad/login'});r.delete_cookie(COOKIE,path='/');return r
 if action=='register':
  AUTH.start_registration(token,email=d.get('email',''),display_name=d.get('name',''),password=d.get('password',''),restart_invalid_flow=True)
  with db() as c:c.execute('INSERT INTO tw_auth_returns VALUES(?,?) ON CONFLICT(session) DO UPDATE SET path=excluded.path',(AUTH.session_owner_digest(token),safe_next(d.get('next'))))
  mail(token,'registration',str(req.base_url));return response({'ok':True,'redirect':'/signup/verify'},token)
 if action=='verify':
  registration_session=AUTH.session_owner_digest(token)
  AUTH.verify_registration_code(token,d.get('code',''));result=AUTH.complete_registration(token)
  with db() as c:
   saved=c.execute('SELECT path FROM tw_auth_returns WHERE session=?',(registration_session,)).fetchone();c.execute('DELETE FROM tw_auth_returns WHERE session=?',(registration_session,))
  return_path=safe_next(saved['path']) if saved else '/app/home'
  # Verification creates a genuine account; the user signs in explicitly afterwards.
  AUTH.sign_out(result['session_token']);return response({'ok':True,'redirect':'/launchpad/login?verified=1'+('&next='+quote(return_path,safe='') if return_path!='/app/home' else '')})
 if action=='recover':
  AUTH.start_password_reset(token,email=d.get('email',''),restart_invalid_flow=True);mail(token,'password-reset',str(req.base_url));return response({'ok':True,'redirect':'/launchpad/resetpassword'},token)
 if action=='reset':
  AUTH.verify_password_reset_code(token,d.get('code',''));newtoken=AUTH.complete_password_reset(token,new_password=d.get('password',''));AUTH.sign_out(newtoken)
  return response({'ok':True,'redirect':'/launchpad/login?reset=1'})
 if action=='resend':
  purpose=d.get('purpose','registration')
  if purpose not in ['registration','password-reset']:raise HTTPException(400,'Invalid verification purpose.')
  from websitebench.local_clone_auth.store import _hash_secret, _verification_code
  table,key=('local_auth_registration_flows','pending_id') if purpose=='registration' else ('local_auth_password_reset_flows','reset_id')
  digest=AUTH.session_owner_digest(token);now=int(time.time());code=_verification_code();salt,code_hash=_hash_secret(code)
  with AUTH.connect() as c:
   flow=c.execute(f'SELECT * FROM {table} WHERE session_digest=?',(digest,)).fetchone()
   prior=c.execute('SELECT * FROM local_auth_mail_outbox WHERE session_digest=? AND purpose=? ORDER BY mail_id DESC LIMIT 1',(digest,purpose)).fetchone()
   if not flow or not prior:raise HTTPException(409,'Start registration or recovery again.')
   if int(flow['expires_at'])<=now:raise HTTPException(400,'Verification expired. Start again.')
   if now-int(flow['updated_at'])<30 and prior['status']!='SMTP_FAILED':raise HTTPException(429,'Please wait 30 seconds before requesting another email.')
   c.execute(f'UPDATE {table} SET code_salt=?,code_hash=?,attempts=0,verified_at=NULL,updated_at=? WHERE session_digest=?',(salt,code_hash,now,digest))
   c.execute('DELETE FROM local_auth_mail_outbox WHERE session_digest=? AND purpose=?',(digest,purpose))
   AUTH._insert_mail_unlocked(c,purpose=purpose,flow_id=flow[key],session_digest=digest,recipient=prior['recipient'],now=now)
  AUTH._remember_mail_code(purpose,flow[key],code)
  mail(token,purpose,str(req.base_url))
  return response({'ok':True,'message':'Email sent.'},token)
 raise HTTPException(404)

@app.get('/logout')
def logout(req:Request):
 AUTH.sign_out(req.cookies.get(COOKIE));r=RedirectResponse('/launchpad/login',status_code=303);r.delete_cookie(COOKIE,path='/');return r

@app.patch('/api/profile')
async def update_profile(req:Request):
 a=account(req);d=await req.json();name=str(d.get('display_name','')).strip()
 if not name or len(name)>120:raise HTTPException(422,'Enter a display name between 1 and 120 characters.')
 with db() as c:
  task_assignees.migrate(c)
  c.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(name,a['account_id']))
  for row in c.execute('SELECT id,owner,options FROM tw_tasks').fetchall():
   opts=json.loads(row['options'])
   if a['account_id'] in opts.get('assignee_ids',[]):task_assignees.store(c,row['owner'],row['id'],opts['assignee_ids'],opts.get('assignee_labels',[]))
 return {'ok':True,'display_name':name}

@app.post('/api/feedback')
async def create_feedback(req:Request):
 who=account(req)['account_id'];d=await req.json();message=str(d.get('message','')).strip()
 if not message or len(message)>20000:raise HTTPException(422,'Enter feedback between 1 and 20000 characters.')
 fid=secrets.token_hex(12)
 with db() as c:c.execute('INSERT INTO tw_feedback VALUES(?,?,?,?)',(fid,who,message,int(time.time())))
 return {'ok':True,'id':fid,'message':'Feedback submitted.'}

@app.get('/api/feedback')
def feedback(req:Request):
 with db() as c:return [dict(r) for r in c.execute('SELECT id,message,created FROM tw_feedback WHERE account=? ORDER BY created',(account(req)['account_id'],))]

@app.delete('/api/account')
async def delete_account(req:Request):
 actor=account(req);who=actor['account_id'];d=await req.json()
 if owner(req)!=who:raise HTTPException(403,'Only the workspace owner can delete this account.')
 if d.get('confirmation') is not True:raise HTTPException(422,'Confirm permanent account deletion.')
 from websitebench.local_clone_auth.store import _verify_secret
 files=[]
 with db() as c:
  row=c.execute('SELECT password_salt,password_hash FROM local_auth_accounts WHERE account_id=?',(who,)).fetchone()
  if not _verify_secret(str(d.get('password','')),bytes(row['password_salt']),bytes(row['password_hash'])):raise HTTPException(400,'The password is incorrect.')
  files=[r['id'] for r in c.execute("SELECT id FROM tw_records WHERE owner=? AND kind='file'",(who,))]
  c.execute('DELETE FROM tw_reminders WHERE account=? OR workspace_owner=?',(who,who))
  import chat_files
  chat_uploads=chat_files.paths(c,UPLOADS/'chat',who)+[UPLOADS/'chat'/r['id'] for r in c.execute('SELECT id FROM tw_chat_draft_files WHERE actor=? AND owner!=?',(who,who))]
  c.execute('DELETE FROM tw_chat_runtime_origins WHERE owner=?',(who,))
  c.execute('DELETE FROM tw_chat_draft_files WHERE owner=? OR actor=?',(who,who))
  c.execute('DELETE FROM tw_chat_roles WHERE owner=?',(who,))
  c.execute('DELETE FROM tw_chat_channels WHERE owner=?',(who,));c.execute('DELETE FROM tw_chat_users WHERE owner=? OR actor=?',(who,who));c.execute('DELETE FROM tw_chat_members WHERE actor=?',(who,));c.execute('DELETE FROM tw_chat_bookmarks WHERE actor=?',(who,))
  c.execute('DELETE FROM tw_automation_fired WHERE rule IN (SELECT id FROM tw_records WHERE owner=?)',(who,));c.execute('DELETE FROM tw_automation_mail WHERE owner=?',(who,));c.execute('DELETE FROM tw_automation_http WHERE owner=?',(who,))
  c.execute('DELETE FROM tw_records WHERE owner=?',(who,));c.execute('DELETE FROM tw_tasks WHERE owner=?',(who,));c.execute('DELETE FROM tw_projects WHERE owner=?',(who,))
  c.execute('DELETE FROM tw_member_policies WHERE account=? OR workspace_owner=?',(who,who));c.execute('DELETE FROM tw_invite_groups WHERE digest IN (SELECT digest FROM tw_invites WHERE workspace_owner=? OR email=?)',(who,actor['email_normalized']))
  c.execute('DELETE FROM tw_settings WHERE owner=?',(who,));c.execute('DELETE FROM tw_webhook_events WHERE owner=?',(who,))
  c.execute('DELETE FROM tw_ai_drafts WHERE account=? OR workspace_owner=?',(who,who));c.execute('DELETE FROM tw_chats WHERE account=? OR workspace_owner=?',(who,who));c.execute('DELETE FROM tw_feedback WHERE account=?',(who,));c.execute('DELETE FROM tw_preferences WHERE owner=?',(who,));c.execute('DELETE FROM tw_memberships WHERE account=? OR workspace_owner=?',(who,who));c.execute('DELETE FROM tw_invites WHERE workspace_owner=? OR email=?',(who,actor['email_normalized']))
  c.execute('DELETE FROM local_auth_sessions WHERE account_id=?',(who,));c.execute('DELETE FROM local_auth_accounts WHERE account_id=?',(who,))
  if who==DEMO:c.execute("INSERT OR IGNORE INTO tw_seed_state VALUES('demo-deleted')")
 for name in files:
  if name and Path(name).name==name:(UPLOADS/name).unlink(missing_ok=True)
 for path in chat_uploads:path.unlink(missing_ok=True)
 result=response({'ok':True,'redirect':'/launchpad/login?deleted=1'});result.delete_cookie(COOKIE,path='/');return result

@app.get('/api/workspace')
def workspace(req:Request):
 who=owner(req)
 with db() as c:
  projects=[dict(r) for r in c.execute('SELECT * FROM tw_projects WHERE owner=?',(who,))]
  tasks=[dict(r) for r in c.execute('SELECT * FROM tw_tasks WHERE owner=?',(who,))]
  people=task_assignees.members(c,who)
  team_catalog=organization_local.teams(c,who)
  for task in tasks:task_assignees.decorate(task,people,team_catalog)
  hidden={task['id'] for task in tasks if task['options'].get('privacy')=='Only me' and task['options'].get('privacy_actor')!=account(req)['account_id']}
  tasks=[task for task in tasks if task['id'] not in hidden]
  records=[dict(r) for r in c.execute('SELECT * FROM tw_records WHERE owner=? ORDER BY created,id',(who,))]
  records=[r for r in records if r['parent'] not in hidden]
  for r in records:
   r['data']=json.loads(r['data'])
   if r['kind']=='team':r['data']['effective_member_ids']=team_catalog.get(r['id'],{}).get('effective_member_ids',[])
  records=[r for r in records if not r['data'].get('private_actor') or r['data']['private_actor']==account(req)['account_id']]
  import chat_mentions
  records=[r for r in records if chat_mentions.can_read_notification(c,who,account(req)['account_id'],r)]
  prefs={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM tw_preferences WHERE owner=?',(account(req)['account_id'],))}
 return ACL['filter'](req,{'workspace_owner':who,'account':account(req),'projects':projects,'tasks':tasks,'records':records,'preferences':prefs,'people':[{'id':p['account_id'],'name':p['display_name'],'email':p['email_normalized']} for p in people.values() if ACL['allowed'](req,'View People') or p['account_id']==account(req)['account_id']]})

@app.post('/api/projects')
async def create_project(req:Request):
 if ACL['policy'](req) is not None:raise HTTPException(403,'Only the workspace owner can create projects.')
 who=owner(req);d=await req.json();name=str(d.get('name','')).strip()
 if not name:raise HTTPException(422,'Project name is required.')
 pid=secrets.token_hex(6)
 with db() as c:
  client=organization_local.client_id(c,who,d.get('client_id',''));c.execute('INSERT INTO tw_projects(id,owner,name,description,client_id) VALUES(?,?,?,?,?)',(pid,who,name,str(d.get('description','')),client))
  defaults=workspace_settings(who)
  for title in defaults['default_task_lists']:c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),who,'list',pid,json.dumps({'title':title}),int(time.time())))
  c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),who,'preference',pid,json.dumps({'title':'Project category defaults',**{key:value for key,value in defaults.items() if key.endswith('_categories')}}),int(time.time())))
 return {'id':pid,'name':name,'redirect':'/app/projects/'+pid+'/tasks/list'}

@app.patch('/api/projects/{pid}/task-list')
async def rename_task_list(pid:str,req:Request):
 who=owner(req);ACL['record'](req,'list',pid,True);d=await req.json()
 old=d.get('name');title=d.get('title')
 if not isinstance(old,str) or not isinstance(title,str) or not title.strip():raise HTTPException(422,'Task list name is required.')
 title=title.strip()
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  if not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,pid)).fetchone():raise HTTPException(404,'Project not found.')
  records=[dict(r) for r in c.execute("SELECT * FROM tw_records WHERE owner=? AND parent=? AND kind='list'",(who,pid))]
  names={json.loads(r['data']).get('title') for r in records}|{r[0] for r in c.execute('SELECT DISTINCT list_name FROM tw_tasks WHERE owner=? AND project_id=?',(who,pid))}
  if old not in names and not (old=='My List' and not names):raise HTTPException(404,'Task list not found.')
  if title!=old and title in names:raise HTTPException(409,'A task list with this name already exists.')
  record=next((r for r in records if json.loads(r['data']).get('title')==old),None)
  rid=record['id'] if record else '1404857' if pid=='372311' and old=='My List' else secrets.token_hex(12)
  data=json.loads(record['data']) if record else {};data['title']=title
  if record:c.execute('UPDATE tw_records SET data=? WHERE owner=? AND id=?',(json.dumps(data),who,rid))
  else:c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(rid,who,'list',pid,json.dumps(data),int(time.time())))
  for before in c.execute('SELECT * FROM tw_tasks WHERE owner=? AND project_id=? AND list_name=?',(who,pid,old)).fetchall():
   c.execute('UPDATE tw_tasks SET list_name=? WHERE owner=? AND id=?',(title,who,before['id']))
   if title!=old:run_automations(c,who,before['id'],'Task list changes',actor=account(req)['account_id'],previous=dict(before))
 return {'ok':True,'id':rid,'title':title,'redirect':'/app/tasklists/'+rid+'/list'}

@app.post('/api/projects/{pid}/copy')
async def copy_project(pid:str,req:Request):
 ACL['project'](req,pid)
 if ACL['policy'](req) is not None:raise HTTPException(403,'Only the workspace owner can copy projects.')
 who=owner(req);d=await req.json();name=str(d.get('name','')).strip()
 if not name:raise HTTPException(422,'Project name is required.')
 new=secrets.token_hex(6)
 with db() as c:
  project=c.execute('SELECT * FROM tw_projects WHERE owner=? AND id=?',(who,pid)).fetchone()
  if not project:raise HTTPException(404,'Project not found.')
  c.execute('INSERT INTO tw_projects(id,owner,name,description,client_id) VALUES(?,?,?,?,?)',(new,who,name,project['description'],project['client_id']))
  rows=[dict(r) for r in c.execute('SELECT * FROM tw_tasks WHERE owner=? AND project_id=?',(who,pid))]
  actor=account(req)['account_id'];rows=[r for r in rows if json.loads(r['options']).get('privacy')!='Only me' or json.loads(r['options']).get('privacy_actor')==actor];ids={r['id']:secrets.token_hex(6) for r in rows}
  for row in rows:
   row['id']=ids[row['id']];row['project_id']=new;row['parent_id']=ids.get(row['parent_id'],'')
   if 'options' in row:
    options=json.loads(row['options']);options['dependencies']=[ids.get(i,i) for i in options.get('dependencies',[])]
    if options.get('repeat_next_id') in ids:options['repeat_next_id']=ids[options['repeat_next_id']]
    else:options.pop('repeat_next_id',None)
    row['options']=json.dumps(options)
   row['options']=json.dumps(task_assignees.canonical_options(c,who,row))
   c.execute('INSERT INTO tw_tasks('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
 return {'ok':True,'id':new,'redirect':'/app/projects/'+new+'/tasks/list'}

@app.post('/api/projects/{pid}/workflow')
async def apply_workflow(pid:str,req:Request):
 ACL['require'](req,'Can Manage Board',pid)
 who=owner(req);d=await req.json()
 with db() as c:
  if not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,pid)).fetchone():raise HTTPException(404,'Project not found.')
  rule=c.execute("SELECT data FROM tw_records WHERE owner=? AND id=? AND kind='workflow'",(who,d.get('workflow_id'))).fetchone()
  if not rule:raise HTTPException(404,'Workflow not found.')
  stages=json.loads(rule['data']).get('stages',[])
  for row in c.execute('SELECT id FROM tw_tasks WHERE owner=? AND project_id=?',(who,pid)).fetchall():get_task(row['id'],req)
  if not stages:raise HTTPException(422,'This workflow has no stages.')
  c.execute("DELETE FROM tw_records WHERE owner=? AND parent=? AND kind='stage'",(who,pid))
  for stage in stages:
   if stage not in ['Backlog','To do','In progress','Completed']:c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),who,'stage',pid,json.dumps({'title':stage}),int(time.time())))
  for task in c.execute('SELECT id,stage FROM tw_tasks WHERE owner=? AND project_id=?',(who,pid)).fetchall():
   if task['stage'] not in stages and not (task['stage']=='Done' and 'Completed' in stages):c.execute("UPDATE tw_tasks SET stage='Backlog' WHERE owner=? AND id=?",(who,task['id']))
 return {'ok':True,'stages':stages}

@app.patch('/api/projects/{pid}')
async def patch_project(pid:str,req:Request):
 ACL['require'](req,'Project Administrator',pid)
 who=owner(req);d=await req.json()
 if 'name' in d:
  if not isinstance(d['name'],str) or not d['name'].strip():raise HTTPException(422,'Project name is required.')
  d['name']=d['name'].strip()
 with db() as c:
  if not c.execute('SELECT 1 FROM tw_projects WHERE id=? AND owner=?',(pid,who)).fetchone():raise HTTPException(404,'Project not found.')
  if 'client_id' in d:d['client_id']=organization_local.client_id(c,who,d['client_id'])
  for key in ['name','description','starred','client_id']:
   if key in d:c.execute(f'UPDATE tw_projects SET {key}=? WHERE id=? AND owner=?',(d[key],pid,who))
 return {'ok':True}

@app.delete('/api/projects/{pid}')
def delete_project(pid:str,req:Request):
 ACL['project'](req,pid);ACL['require'](req,'Project Administrator',pid);who=owner(req);files=[]
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  if not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,pid)).fetchone():raise HTTPException(404,'Project not found.')
  blocked_before=AUTOMATIONS['blocked'](c,who)
  task_ids={r['id'] for r in c.execute('SELECT id FROM tw_tasks WHERE owner=? AND project_id=?',(who,pid))}
  records=[r for r in c.execute('SELECT id,kind,parent FROM tw_records WHERE owner=?',(who,)) if r['parent']==pid or r['parent'] in task_ids]
  for record in records:
   if record['kind']=='file':files.append(record['id'])
   if record['kind']=='automation':c.execute('DELETE FROM tw_automation_fired WHERE rule=?',(record['id'],));c.execute('DELETE FROM tw_automation_http WHERE owner=? AND automation_id=?',(who,record['id']))
   c.execute('DELETE FROM tw_records WHERE id=?',(record['id'],))
  for tid in task_ids:
   c.execute('DELETE FROM tw_automation_activity WHERE owner=? AND task=?',(who,tid))
   c.execute('DELETE FROM tw_reminders WHERE workspace_owner=? AND task=?',(who,tid))
   c.execute('DELETE FROM tw_automation_fired WHERE task=? AND rule IN (SELECT id FROM tw_records WHERE owner=?)',(tid,who))
  for row in c.execute('SELECT id,options FROM tw_tasks WHERE owner=? AND project_id<>?',(who,pid)).fetchall():
   options=json.loads(row['options']);dependencies=options.get('dependencies',[])
   if task_ids.intersection(dependencies):options['dependencies']=[tid for tid in dependencies if tid not in task_ids];c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(options),who,row['id']))
  c.execute('DELETE FROM tw_tasks WHERE owner=? AND project_id=?',(who,pid));c.execute('DELETE FROM tw_projects WHERE owner=? AND id=?',(who,pid))
  AUTOMATIONS['unblocked'](c,who,blocked_before,account(req)['account_id'])
 for fid in files:(UPLOADS/fid).unlink(missing_ok=True)
 return {'ok':True}

@app.post('/api/tasks')
async def create_task(req:Request):
 return await create_task_data(req,await req.json())

async def create_task_data(req:Request,d):
 who=owner(req);title=str(d.get('title','')).strip();pid=str(d.get('project_id','372311'))
 ACL['require'](req,'Add Tasks',pid)
 if not title:raise HTTPException(422,'Task name is required.')
 if d.get('priority','None') not in ['None','Low','Medium','High']:raise HTTPException(422,'Choose a valid priority.')
 for key in ['start_date','due_date']:
  if d.get(key):
   try:__import__('datetime').date.fromisoformat(d[key])
   except (ValueError,TypeError):raise HTTPException(422,'Enter a valid date.')
 tid=secrets.token_hex(6)
 with db() as c:
  if not c.execute('SELECT 1 FROM tw_projects WHERE id=? AND owner=?',(pid,who)).fetchone():raise HTTPException(404,'Project not found.')
  assignment,labels,team_ids=task_assignees.input_assignment(c,who,pid,d)
  c.execute('INSERT INTO tw_tasks(id,owner,project_id,title,description,priority,stage,tag,start_date,due_date,list_name,assignee) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(tid,who,pid,title,str(d.get('description','')),d.get('priority','None'),d.get('stage','Backlog'),d.get('tag',''),d.get('start_date'),d.get('due_date'),d.get('list_name','My List'),d.get('assignee','')))
  c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps({'created_by':account(req)['account_id']}),who,tid))
  task_assignees.store(c,who,tid,assignment,labels,team_ids)
  if 'estimate' in d:
   try:estimate=int(d['estimate'])
   except (ValueError,TypeError):raise HTTPException(422,'Enter valid estimated minutes.')
   if estimate<0:raise HTTPException(422,'Estimated time cannot be negative.')
   c.execute('UPDATE tw_tasks SET estimate=? WHERE owner=? AND id=?',(estimate,who,tid))
  if d.get('parent_id'):
   get_task(d['parent_id'],req)
   if not c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=? AND project_id=?',(who,d['parent_id'],pid)).fetchone():raise HTTPException(404,'Parent task not found.')
   c.execute('UPDATE tw_tasks SET parent_id=? WHERE owner=? AND id=?',(d['parent_id'],who,tid))
  run_automations(c,who,tid,'Task added',actor=account(req)['account_id'])
 return {'ok':True,'id':tid,'redirect':'/app/tasks/'+tid}

@app.get('/api/tasks/{tid}')
def get_task(tid:str,req:Request):
 with db() as c:r=c.execute('SELECT * FROM tw_tasks WHERE id=? AND owner=?',(tid,owner(req))).fetchone()
 if not r:raise HTTPException(404,'Task not found.')
 ACL['project'](req,r['project_id']);ACL['require'](req,'View Tasks & Milestones',r['project_id'])
 with db() as c:result=task_assignees.decorate(dict(r),task_assignees.members(c,owner(req)),organization_local.teams(c,owner(req)))
 if req.method in ['PATCH','DELETE','PUT'] or req.url.path.endswith('/transfer'):
  own=result['options'].get('created_by')==account(req)['account_id'] or account(req)['account_id'] in result['assignee_ids']
  if not own:ACL['require'](req,'Can Edit All Tasks',r['project_id'])
 if result['options'].get('privacy')=='Only me' and result['options'].get('privacy_actor')!=account(req)['account_id']:raise HTTPException(404,'Task not found.')
 if req.method=='GET' and not ACL['allowed'](req,'View Estimated Time',r['project_id']):result['estimate']=0
 return result

@app.patch('/api/tasks/{tid}')
async def update_task(tid:str,req:Request):
 who=owner(req);d=await req.json();before=get_task(tid,req)
 allowed=['title','description','priority','stage','tag','start_date','due_date','completed','list_name','assignee','estimate','parent_id']
 if 'title' in d and not str(d['title']).strip():raise HTTPException(422,'Task name is required.')
 if 'estimate' in d:
  try:d['estimate']=int(d['estimate'])
  except (TypeError,ValueError):raise HTTPException(422,'Enter valid estimated minutes.')
  if d['estimate']<0:raise HTTPException(422,'Estimated time cannot be negative.')
 if 'priority' in d and d['priority'] not in ['None','Low','Medium','High']:raise HTTPException(422,'Choose a valid priority.')
 for key in ['start_date','due_date']:
  if d.get(key):
   try:__import__('datetime').date.fromisoformat(d[key])
   except (ValueError,TypeError):raise HTTPException(422,'Enter a valid date.')
 with db() as c:
  blocked_before=AUTOMATIONS['blocked'](c,who) if 'completed' in d else set()
  if d.get('parent_id'):
   get_task(d['parent_id'],req)
   parent=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,d['parent_id'])).fetchone()
   if not parent or parent['project_id']!=before['project_id'] or parent['id']==tid:raise HTTPException(422,'Choose a parent task in the same project.')
   ancestor=parent
   while ancestor and ancestor['parent_id']:
    if ancestor['parent_id']==tid:raise HTTPException(422,'A task cannot be its own ancestor.')
    ancestor=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,ancestor['parent_id'])).fetchone()
  assignment_changed=bool({'assignee','assignee_ids','assignee_team_ids'}&set(d))
  if assignment_changed:
   values={'assignee_ids':before['direct_assignee_ids'],'assignee_team_ids':before['assignee_team_ids'],**d}
   if 'assignee' in d and 'assignee_ids' not in d:values.pop('assignee_ids')
   assignment,labels,team_ids=task_assignees.input_assignment(c,who,before['project_id'],values)
  for key in allowed:
   if key in d:c.execute(f'UPDATE tw_tasks SET {key}=? WHERE id=? AND owner=?',(d[key],tid,who))
  if assignment_changed:
   task_assignees.store(c,who,tid,assignment,labels,team_ids)
  after=dict(c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone())
  if blocked_before:AUTOMATIONS['unblocked'](c,who,blocked_before,account(req)['account_id'])
  for event in AUTOMATIONS['events'](before,after):run_automations(c,who,tid,event,actor=account(req)['account_id'],previous=before)
  if d.get('completed') and not before['completed']:complete_recurring(c,who,tid)
 return {'ok':True}

@app.delete('/api/tasks/{tid}')
def delete_task(tid:str,req:Request):
 get_task(tid,req);files=[]
 with db() as c:
  who=owner(req)
  blocked_before=AUTOMATIONS['blocked'](c,who)
  files=[r['id'] for r in c.execute("SELECT id FROM tw_records WHERE parent=? AND owner=? AND kind='file'",(tid,who))]
  c.execute("UPDATE tw_tasks SET parent_id='' WHERE parent_id=? AND owner=?",(tid,who))
  c.execute('DELETE FROM tw_records WHERE parent=? AND owner=?',(tid,who))
  c.execute('DELETE FROM tw_tasks WHERE id=? AND owner=?',(tid,who))
  c.execute('DELETE FROM tw_automation_activity WHERE owner=? AND task=?',(who,tid))
  c.execute('DELETE FROM tw_reminders WHERE workspace_owner=? AND task=?',(who,tid))
  for row in c.execute('SELECT id,options FROM tw_tasks WHERE owner=?',(who,)).fetchall():
   options=json.loads(row['options'])
   if tid in options.get('dependencies',[]):options['dependencies'].remove(tid);c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(options),who,row['id']))
  AUTOMATIONS['unblocked'](c,who,blocked_before,account(req)['account_id'])
 for fid in files:(UPLOADS/fid).unlink(missing_ok=True)
 return {'ok':True}


def validate_record(kind,d):
 if kind in ['customfield','webhook','contact']:
  if not str(d.get('title','')).strip():raise HTTPException(422,'Enter a name.')
 if kind=='customfield':
  validate_definition(d)
 if kind=='webhook':
  u=urlsplit(str(d.get('url','')))
  if u.scheme not in ['http','https'] or not u.netloc or u.username or u.password:raise HTTPException(422,'Enter a valid endpoint URL.')
  if not re.fullmatch(r'[A-Z]+\.[A-Z]+',str(d.get('event',''))) or d.get('content_type') not in ['JSON','XML','Form']:raise HTTPException(422,'Choose an event and content type.')
 if kind=='workflow':
  stages=d.get('stages',[])
  if not str(d.get('title','')).strip() or not isinstance(stages,list) or not stages or len(stages)>30 or any(not isinstance(s,str) or not s.strip() for s in stages):raise HTTPException(422,'Enter a workflow name and valid stages.')
  d['stages']=list(dict.fromkeys(['Backlog',*stages,'Completed']))
 if kind=='time':
  try:d['minutes']=int(d.get('minutes',0))
  except (ValueError,TypeError):raise HTTPException(422,'Enter a valid duration.')
  if d['minutes']<=0:raise HTTPException(422,'Duration must be greater than zero.')
  d['billable']=d.get('billable') in [True,'true','on',1]
  d.setdefault('date',time.strftime('%Y-%m-%d'))
 if kind=='automation':validate_automation(d)
 if kind in ['budget','quote','invoice']:
  for key in ['amount','rate']:
   if key in d:
    try:d[key]=float(d[key])
    except (ValueError,TypeError):raise HTTPException(422,'Enter a valid amount.')
    if d[key]<0:raise HTTPException(422,'Amount cannot be negative.')
 return d

def run_automations(c,who,tid,trigger,actor=None,previous=None):
 return AUTOMATIONS['run'](c,who,tid,trigger,actor=actor,previous=previous)

@app.patch('/api/records/{rid}')
async def update_record(rid:str,req:Request):
 who=owner(req);d=await req.json()
 with db() as c:
  row=c.execute('SELECT * FROM tw_records WHERE id=? AND owner=?',(rid,who)).fetchone()
  if not row or (json.loads(row['data']).get('private_actor') and json.loads(row['data'])['private_actor']!=account(req)['account_id']):raise HTTPException(404,'Record not found.')
  if c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(who,row['parent'])).fetchone():get_task(row['parent'],req)
  ACL['record'](req,row['kind'],row['parent'],True)
  if row['kind']=='file':
   name=Path(str(d.get('name',''))).name.strip()
   if not name:raise HTTPException(422,'Enter a file name.')
   d={'name':name}
  if row['kind'] in ['customfield','webhook','tag'] and account(req)['account_id']!=who:raise HTTPException(403,'Only the workspace owner can change these settings.')
  previous=json.loads(row['data']);original=dict(previous);new_parent=row['parent']
  if row['kind']=='automation' and 'parent' in d:
   new_parent=str(d['parent'])
   if new_parent and not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,new_parent)).fetchone():raise HTTPException(422,'Choose a project in this workspace.')
  else:d.pop('parent',None)
  if row['kind']=='automation' and set(d)&{'effect','value'} and 'actions' not in d:previous.pop('actions',None)
  previous.update(d);validate_record(row['kind'],previous);organization_local.validate(c,who,row['kind'],previous,rid)
  if row['kind']=='customfield':validate_definition_scope(c,who,previous)
  if row['kind']=='automation':AUTOMATIONS['validate_scope'](c,who,previous)
  created=row['created']
  if row['kind']=='automation' and previous['trigger']=='Task inactive' and any(original.get(k)!=previous.get(k) for k in ['trigger','inactive_count','inactive_unit','enabled','parent']):created=time.time()
  if row['kind']=='automation' and previous['trigger']=='Every day' and any(original.get(k)!=previous.get(k) for k in ['trigger','weekdays','run_at','enabled']):created=time.time()
  c.execute('UPDATE tw_records SET data=?,parent=?,created=? WHERE id=? AND owner=?',(json.dumps(previous),new_parent,created,rid,who))
 return {'ok':True}

@app.post('/api/records/{kind}')
async def create_record(kind:str,req:Request):
 who=owner(req);d=await req.json();parent=str(d.get('parent',''));valid=['comment','time','message','notebook','link','milestone','list','client','person','team','role','skill','event','widget','notification','budget','quote','invoice','automation','template','risk','form','preference','invitation','expense','stage','workflow','customfield','webhook','contact']
 ACL['record'](req,kind,parent,True)
 if kind not in valid:raise HTTPException(422,'Unknown record type.')
 if kind in ['customfield','webhook'] and account(req)['account_id']!=who:raise HTTPException(403,'Only the workspace owner can change these settings.')
 if parent:
  with db() as c:
   if not c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=? UNION SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,parent,who,parent)).fetchone():raise HTTPException(404,'Parent not found.')
 if parent:
  with db() as c:is_task=c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(who,parent)).fetchone()
  if is_task:get_task(parent,req)
 if kind in ['comment','message','notebook'] and not str(d.get('text') or d.get('title') or '').strip():raise HTTPException(422,'Please enter some text.')
 if kind=='time':
  try:minutes=int(d.get('minutes',0))
  except (ValueError,TypeError):raise HTTPException(422,'Enter a valid duration.')
  if minutes<=0:raise HTTPException(422,'Duration must be greater than zero.')
 if kind=='invitation':
  group=d.get('permission_group','owner_company');ACL['defaults'](who,group)
  if 'all_projects' in d and type(d['all_projects']) is not bool:raise HTTPException(422,'Select whether to add users to all projects.')
  with db() as c:invite_projects=[r['id'] for r in c.execute('SELECT id FROM tw_projects WHERE owner=?',(who,))] if d.get('all_projects') else None
  email=str(d.get('email','')).strip().lower()
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Enter a valid email address.')
  token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest();msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@teamwork.clone.test');msg['To']=email;msg['Subject']='You are invited to a Teamwork.com workspace';msg.set_content(workspace_settings(who)['welcome_email']+"\n\n"+f"You have been invited to collaborate. Sign in with {email} and accept your invitation:\n{str(req.base_url).rstrip('/')}/invite/{token}\nThis invitation expires in 7 days.")
  from email.utils import formataddr
  name=account(req)['display_name'].split(' ',1);format=workspace_settings(who)['email_format'];sender=format.replace('[firstname]',name[0]).replace('[lastname]',name[1] if len(name)>1 else '').replace('[installationName]','Teamwork.com');msg.replace_header('From',formataddr((sender,os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@teamwork.clone.test'))))
  try:
   with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(msg)
  except (OSError,smtplib.SMTPException):raise HTTPException(503,'Invitation email could not be sent. Please retry.')
  with db() as c:
   c.execute('INSERT INTO tw_invites VALUES(?,?,?,?,0)',(digest,who,email,int(time.time())+7*86400));c.execute('INSERT INTO tw_invite_groups VALUES(?,?)',(digest,group))
   if invite_projects is not None:c.execute('INSERT INTO tw_invite_projects VALUES(?,?)',(digest,json.dumps(invite_projects)))
  d['status']='Invited'
 if kind=='time':
  d['actor']=account(req)['account_id']
  if 'billable' not in d:
   with db() as c:
    target=c.execute('SELECT project_id FROM tw_tasks WHERE owner=? AND id=?',(who,parent)).fetchone();project=target['project_id'] if target else parent
    config=c.execute("SELECT data FROM tw_records WHERE owner=? AND parent=? AND kind='project_configuration'",(who,project)).fetchone();d['billable']=bool(config and json.loads(config['data']).get('billable'))
 if kind in ['comment','message','notebook']:d['author']=account(req)['display_name'];d['actor']=account(req)['account_id']
 validate_record(kind,d)
 rid=secrets.token_hex(12)
 with db() as c:
  if kind=='automation':AUTOMATIONS['validate_scope'](c,who,d)
  if kind=='customfield':validate_definition_scope(c,who,d)
  organization_local.validate(c,who,kind,d)
  previous_total=sum(json.loads(r['data']).get('minutes',0) for r in c.execute("SELECT data FROM tw_records WHERE owner=? AND parent=? AND kind='time'",(who,parent))) if kind=='time' else 0
  c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(rid,who,kind,parent,json.dumps(d),time.time() if kind=='automation' else int(time.time())))
  if kind in ['time','comment']:
   run_automations(c,who,parent,'Task time logged' if kind=='time' else 'Task comment added',actor=account(req)['account_id'],previous={'event_record':d})
   if kind=='time':run_automations(c,who,parent,'Task logged time exceeds estimated',actor=account(req)['account_id'],previous={'logged_total':previous_total})
 return {'ok':True,'id':rid,'kind':kind,'data':d}

@app.delete('/api/records/{rid}')
def delete_record(rid:str,req:Request):
 with db() as c:
  row=c.execute('SELECT kind,parent,data FROM tw_records WHERE id=? AND owner=?',(rid,owner(req))).fetchone()
  if row and json.loads(row['data']).get('private_actor') not in [None,account(req)['account_id']]:raise HTTPException(404,'Record not found.')
  if row and c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(owner(req),row['parent'])).fetchone():get_task(row['parent'],req)
  if row:ACL['record'](req,row['kind'],row['parent'],True)
  if row and row['kind'] in ['customfield','webhook','tag'] and account(req)['account_id']!=owner(req):raise HTTPException(403,'Only the workspace owner can change these settings.')
  count=c.execute('DELETE FROM tw_records WHERE id=? AND owner=?',(rid,owner(req))).rowcount
  if row and row['kind']=='automation':c.execute('DELETE FROM tw_automation_http WHERE owner=? AND automation_id=?',(owner(req),rid))
  if row and row['kind']=='client':c.execute("UPDATE tw_projects SET client_id='' WHERE owner=? AND client_id=?",(owner(req),rid))
  if row and row['kind']=='team':organization_local.remove_team(c,owner(req),rid)
  if row and row['kind']=='file':(UPLOADS/rid).unlink(missing_ok=True)
 if not count:raise HTTPException(404)
 return {'ok':True}

@app.put('/api/preferences')
async def preferences(req:Request):
 who=account(req)['account_id'];d=await req.json()
 with db() as c:
  for key,value in d.items():c.execute('INSERT INTO tw_preferences VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value',(who,str(key),json.dumps(value)))
 return {'ok':True}

@app.post('/api/files')
async def upload(req:Request):
 who=owner(req);form=await req.form();file=form.get('file');parent=str(form.get('parent','372311'))
 def authorize():
  if owner(req)!=who:raise HTTPException(403,'The active workspace changed during upload.')
  ACL['record'](req,'file',parent,True)
  with db() as c:
   if not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=? UNION SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(who,parent,who,parent)).fetchone():raise HTTPException(404,'Project not found.')
   if c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(who,parent)).fetchone():get_task(parent,req)
 authorize()
 if not file or not hasattr(file,'read'):raise HTTPException(422,'Choose a file.')
 rid=secrets.token_hex(16);name=Path((file.filename or 'file').replace('\\','/')).name or 'file'
 from upload_stream import save
 try:
  uploaded=await save(file,UPLOADS/rid);authorize()
  with db() as c:
   c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(rid,who,'file',parent,json.dumps({'name':name,'size':uploaded['size'],'type':file.content_type,**({'private_actor':account(req)['account_id']} if form.get('private')=='true' else {})}),int(time.time())))
   AUTOMATIONS['touch'](c,who,parent)
 except BaseException:(UPLOADS/rid).unlink(missing_ok=True);raise
 return {'ok':True,'id':rid,'name':name}

@app.get('/api/files/{fid}')
def download(fid:str,req:Request):
 with db() as c:r=c.execute('SELECT data,parent FROM tw_records WHERE id=? AND owner=? AND kind=?',(fid,owner(req),'file')).fetchone()
 if not r:raise HTTPException(404)
 ACL['record'](req,'file',r['parent'])
 with db() as c:
  if c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(owner(req),r['parent'])).fetchone():get_task(r['parent'],req)
 d=json.loads(r['data'])
 if d.get('private_actor') not in [None,account(req)['account_id']]:raise HTTPException(404)
 inline=req.query_params.get('inline')=='1' and d['type'] in ['image/png','image/jpeg','image/gif','image/webp'];return FileResponse(UPLOADS/fid,filename=d['name'],media_type=d['type'] if inline else 'application/octet-stream',content_disposition_type='inline' if inline else 'attachment')

@app.post('/api/billing/plan')
async def billing_plan(req:Request):
 who=owner(req)
 if who!=account(req)['account_id']:raise HTTPException(403,'Only the workspace owner can manage billing.')
 d=await req.json();plan=d.get('plan');cycle=d.get('cycle','annual')
 prices={'Basics':{'annual':999,'monthly':1399},'Accelerate':{'annual':2499,'monthly':2999},'Optimize':{'annual':4999,'monthly':6999}}
 if plan not in prices or cycle not in ['annual','monthly']:raise HTTPException(422,'Choose a valid plan and payment cycle.')
 try:seats=int(d.get('seats',0))
 except (ValueError,TypeError):raise HTTPException(422,'Enter a valid seat count.')
 minimum=3 if plan=='Basics' else 5
 if seats<minimum or seats>10000:raise HTTPException(422,f'This plan requires at least {minimum} seats.')
 total=prices[plan][cycle]*seats*(12 if cycle=='annual' else 1);rid=secrets.token_hex(12)
 data={'plan':plan,'cycle':cycle,'seats':seats,'unit_price_cents':prices[plan][cycle],'total_cents':total,'adapter':'local-sandbox'}
 with db() as c:
  c.execute("INSERT INTO tw_preferences VALUES(?,'billing_plan',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value",(who,json.dumps(data)))
  c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(rid,who,'invoice','',json.dumps({'title':'Sandbox subscription receipt','amount':total/100,'currency':'USD','status':'Sandbox — no charge','plan':plan,'seats':seats,'cycle':cycle}),int(time.time())))
 return {'ok':True,'plan':data,'receipt_id':rid,'message':'Plan saved in the local sandbox. No payment was charged.'}

@app.post('/api/forms')
async def public_form(req:Request):
 token,_=AUTH.ensure_session(req.cookies.get(COOKIE));d=await req.json();rid=secrets.token_hex(12)
 with db() as c:c.execute('INSERT INTO tw_public_forms VALUES(?,?,?,?)',(rid,AUTH.session_owner_digest(token),json.dumps(d),int(time.time())))
 return response({'ok':True,'message':'Thank you. Your request has been received.','id':rid},token)

@app.get('/api/ui-state/{name:path}')
def ui_state(name:str,req:Request):
 entry=STATES.get(name)
 if not entry:raise HTTPException(404)
 if entry['auth']:account(req)
 raw=(HERE/entry['file']).read_text()
 if entry['auth']:raw=personalize(raw,account(req),entry.get('source_route','/app/home'),owner(req))
 return HTMLResponse(raw)

@app.get('/__frames/{fid}')
def frame(fid:str,req:Request):
 entry=FRAMES.get(fid)
 if not entry:raise HTTPException(404)
 if entry['auth']:account(req)
 raw=(HERE/entry['file']).read_text()
 if entry['auth']:raw=personalize(raw,account(req),'/workspace',owner(req))
 return HTMLResponse(raw)

def shell(title,body):
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+' | Teamwork.com</title><link rel="stylesheet" href="/static/clone.css"><script defer src="/static/clone.js"></script></head><body class="local-shell"><header><a class="local-logo" href="/">t<span>•</span> teamwork.com</a><nav><a href="/app/home">Home</a><a href="/app/projects">Projects</a><a href="/pricing">Pricing</a><a href="/launchpad/login">Log in</a></nav></header><main>'+body+'</main><footer>© Teamwork.com 2026 <a href="/legal">Terms and Privacy</a></footer></body></html>'

@app.get('/signup/verify')
@app.get('/launchpad/resetpassword')
def verification(req:Request):
 reset='resetpassword' in req.url.path;title='Reset your password' if reset else 'Verify your email address'
 body=f'<section class="local-auth"><h1>{title}</h1><p>Enter the verification code from your email.</p><form data-local-auth="{"reset" if reset else "verify"}"><label>Verification code<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6" required></label>'
 if reset:body+='<label>New password<input name="password" type="password" minlength="8" autocomplete="new-password" required></label>'
 body+='<div role="alert" class="local-error"></div><button class="local-primary" type="submit">Continue</button></form><button data-action="resend" data-purpose="'+('password-reset' if reset else 'registration')+'">Resend email</button><a href="'+('/launchpad/forgotpassword' if reset else '/signup')+'">Start again</a></section>'
 return HTMLResponse(shell(title,body))

@app.get('/auth/provider/{provider}')
def provider_page(provider:str):
 # Local provider adapter never contacts a production OAuth service.
 return HTMLResponse(shell('Single Sign On',f'<section class="local-auth"><h1>{html.escape(provider.title())} sign in</h1><p>This local workspace uses your local Teamwork account.</p><form data-local-auth="login"><label>Email address<input name="email" type="email" required></label><label>Password<input name="password" type="password" required></label><div class="local-error" role="alert"></div><button class="local-primary">Log in</button></form><a href="/launchpad/login">Return to login</a></section>'))

@app.get('/outbound')
def outbound(req:Request):
 url=req.query_params.get('url','')
 if urlsplit(url).scheme not in ['http','https']:raise HTTPException(422,'Invalid destination.')
 return HTMLResponse(shell('External link','<section class="local-boundary"><h1>External link</h1><p>This destination is outside the local workspace.</p><label>Original destination<input readonly value="'+html.escape(url,quote=True)+'"></label><button data-action="copy">Copy destination</button><a href="/app/home">Return to workspace</a></section>'))

import status_local
status_local.install(app)
import status_subscriptions
STATUS_SUBSCRIPTIONS=status_subscriptions.install(app,db,AUTH,response)

@app.get('/boundary/{bid}')
@app.get('/external/{bid}')
def boundary(bid:str):
 alias=ROUTES.get('/boundary/'+bid,{})
 if alias.get('redirect'):return RedirectResponse(alias['redirect'],status_code=308)
 d=BOUNDARIES.get(bid)
 if not d:raise HTTPException(404)
 title=d.get('title','Teamwork.com');external=d.get('kind')=='external'
 unavailable=d.get('kind')=='unavailable'
 explanation='The source page returned HTTP 404 when captured and is unavailable.' if unavailable else 'This destination is outside the local workspace.' if external else 'This item is beyond the captured detail selection for this collection.'
 content='<section class="local-boundary" data-boundary-page'+(' data-source-unavailable' if unavailable else '')+'><h1>'+html.escape(title)+'</h1><p>'+explanation+'</p><p>Collection: '+html.escape(d.get('collection',''))+'</p>'
 if d.get('identity'):content+='<p>'+html.escape(d['identity'])+'</p>'
 if external:content+='<label>Original destination<input readonly value="'+html.escape(d.get('target',''),quote=True)+'"></label><button data-action="copy">Copy destination</button>'
 content+='<a href="'+html.escape(d.get('return_path','/'),quote=True)+'">Back to collection</a></section>'
 return HTMLResponse(shell(title,content))

@app.get('/tour/{flow}/{step}')
def tour(flow:str,step:int):
 entry=TOURS.get('/tour/'+flow+'/'+str(step))
 if not entry:raise HTTPException(404,'Tour step not found.')
 return HTMLResponse((HERE/entry['file']).read_text())

@app.get('/invite/{token}')
def invitation_page(token:str,req:Request):
 digest=hashlib.sha256(token.encode()).hexdigest()
 with db() as c:invite=c.execute('SELECT * FROM tw_invites WHERE digest=?',(digest,)).fetchone()
 if not invite or invite['accepted'] or invite['expires']<time.time():return HTMLResponse(shell('Invitation unavailable','<section class="local-auth"><h1>This invitation has expired or has already been accepted.</h1><a href="/app/home">Go to your workspace</a></section>'),status_code=410)
 try:a=account(req)
 except HTTPException:return HTMLResponse(shell('Workspace invitation','<section class="local-auth"><h1>You have been invited</h1><p>Sign in with the email address that received this invitation.</p><a href="/launchpad/login?next='+quote('/invite/'+token,safe='')+'">Log in</a><a href="/signup">Create an account</a></section>'))
 return HTMLResponse(shell('Accept invitation','<section class="local-auth"><h1>Join this workspace</h1><form data-business="accept-invitation"><input type="hidden" name="token" value="'+html.escape(token,quote=True)+'"><p>Accept this invitation to collaborate on its projects.</p><button class="local-primary" type="submit">Accept invitation</button><div class="local-error"></div></form></section>'))

@app.post('/api/invitations/accept')
async def accept_invitation(req:Request):
 a=account(req);d=await req.json();digest=hashlib.sha256(str(d.get('token','')).encode()).hexdigest()
 with db() as c:
  c.execute('BEGIN IMMEDIATE');invite=c.execute('SELECT * FROM tw_invites WHERE digest=?',(digest,)).fetchone()
  if not invite or invite['accepted'] or invite['expires']<time.time():raise HTTPException(410,'Invitation expired or already accepted.')
  if a['email_normalized'].lower()!=invite['email']:raise HTTPException(403,'Sign in with the invited email address.')
  c.execute('INSERT OR IGNORE INTO tw_memberships VALUES(?,?)',(a['account_id'],invite['workspace_owner']))
  ACL['accept'](invite['workspace_owner'],a['account_id'],digest,c)
  c.execute('UPDATE tw_invites SET accepted=1 WHERE digest=?',(digest,))
  c.execute("INSERT INTO tw_preferences VALUES(?,'active_workspace',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value",(a['account_id'],json.dumps(invite['workspace_owner'])))
 return {'ok':True,'redirect':'/app/home'}

@app.get('/app/onboarding')
def onboarding(req:Request):
 account(req)
 if owner(req)!=account(req)['account_id']:raise HTTPException(403,'Only the workspace owner can set up this workspace.')
 return HTMLResponse(shell('Set up your workspace','<section class="local-auth"><h1>Set up your workspace</h1><form data-business="project"><label>Project name<input name="name" required></label><label>Description<textarea name="description"></textarea></label><div class="local-error" role="alert"></div><button class="local-primary">Create project</button></form></section>'))


def personalize(raw,a,path,workspace_owner=None):
 """Reuse the captured application structure with only this actor's entities."""
 who=workspace_owner or a['account_id']
 with db() as c:
  projects=[dict(r) for r in c.execute('SELECT * FROM tw_projects WHERE owner=?',(who,))]
  tasks=[dict(r) for r in c.execute('SELECT * FROM tw_tasks WHERE owner=?',(who,))]
  people=task_assignees.members(c,who)
  team_catalog=organization_local.teams(c,who)
  for task in tasks:task_assignees.decorate(task,people,team_catalog)
  hidden={task['id'] for task in tasks if task['options'].get('privacy')=='Only me' and task['options'].get('privacy_actor')!=a['account_id']}
  tasks=[task for task in tasks if task['id'] not in hidden]
 with db() as c:policy=c.execute('SELECT permissions,projects FROM tw_member_policies WHERE account=? AND workspace_owner=?',(a['account_id'],who)).fetchone()
 if policy:
  permitted=json.loads(policy['projects']);rights=json.loads(policy['permissions']);projects=[p for p in projects if p['id'] in permitted]
  hidden.update(t['id'] for t in tasks if t['project_id'] not in permitted or not (rights.get('Project Administrator') or rights.get('View Tasks & Milestones')));tasks=[t for t in tasks if t['id'] not in hidden]
 if not projects:return shell('Projects','<section class=local-auth><h1>No projects</h1><p>Ask the workspace owner to add you to a project.</p><a href=/logout>Log out</a></section>')
 task=next((t for t in tasks if path=='/app/tasks/'+t['id']),None)
 selected=next((p for p in projects if (task and task['project_id']==p['id']) or '/projects/'+p['id'] in path),projects[0])
 tree=dom.document_fromstring(raw)
 body=tree.find('body');body.set('data-route',path);body.set('data-project-id',selected['id'])
 if path.endswith('/tasks/table'):
  rows=tree.xpath('//tr[@data-task-id]')
  if rows:
   import copy
   rows[0].getparent().set('data-local-tasks','true');template=dom.Element('template',id='local-task-table-template');row=copy.deepcopy(rows[0]);row.attrib.pop('data-task-id',None);row.attrib.pop('data-item-selection-task-id',None)
   for cell in row:
    for child in list(cell):cell.remove(child)
    cell.text=''
   template.append(row);body.append(template)
 for node in tree.xpath('//*[@data-task-id]'):
  if node.get('data-task-id') in hidden and node.getparent() is not None:node.getparent().remove(node)
 if task:
  for node in tree.xpath('//*[@data-task-id]'):node.set('data-task-id',task['id'])
  for node in tree.xpath('//*[@data-identifier="task-details-title"]'):node.text=task['title']
 elif who!=DEMO:
  for node in tree.xpath('//*[@data-task-id]'):
   if node.getparent() is not None:node.getparent().remove(node)
  if ('/tasks/' in path and not path.endswith(('/tasks/table','/tasks/board'))) or path in ['/app/work/tasks','/app/tasks/tasks']:
   main=tree.xpath('//main')
   if main:
    host=dom.Element('div',id='local-tasks');main[0].append(host)
 for node in tree.iter():
  if not isinstance(node.tag,str):continue
  for attr in ['href','data-project-id']:
   value=node.get(attr)
   if value and (who!=DEMO or selected['id']!='372311'):node.set(attr,value.replace('/projects/372311','/projects/'+selected['id']))
  for part in ['text','tail']:
   value=getattr(node,part)
   if value:
    if value.strip()=='789':setattr(node,part,value.replace('789',selected['name']))
    elif a['account_id']!=DEMO and value.strip() in ['Sam Yu','Sam','Studio']:setattr(node,part,a['display_name'])
 if task:
  for node in tree.xpath('//*[@data-identifier="task-details-title"]'):node.text=task['title']
 return '<!doctype html>'+dom.tostring(tree,encoding='unicode',method='html')

from settings_local import install as install_settings
workspace_settings=install_settings(app,db,owner,account,workspace,UPLOADS,create_record,json.loads((HERE/'default-permissions.json').read_text()))

from permissions_local import install as install_permissions
PERMISSION_DEFAULTS=json.loads((HERE/'default-permissions.json').read_text())
ACL=install_permissions(db,owner,account,PERMISSION_DEFAULTS)

from planning import install as install_planning
install_planning(app,db,owner,account,workspace)

from assistant_local import install as install_assistant

from chat_local import install as install_chat
CHAT_NOTIFICATIONS=install_chat(app,db,owner,account,DEMO,UPLOADS,workspace)

from automations_local import install as install_automations,validate as validate_automation
AUTOMATIONS=install_automations(app,db,owner,account)
from advanced import install,complete_recurring
deliver_reminders=install(app,db,owner,account,get_task,ACL,AUTOMATIONS)
with db() as c:task_assignees.migrate(c)

from local_inference import LocalInference
from ai_wizards import install as install_ai_wizards
INFERENCE=LocalInference(Path(SERVICE.lifecycle.database_path).parent)
install_assistant(app,db,owner,account,workspace,HELP_SEARCH,INFERENCE,UPLOADS)
install_ai_wizards(app,db,owner,account,workspace,ACL,get_task,INFERENCE,run_automations,workspace_settings)
app.router.add_event_handler('shutdown',INFERENCE.close)

app.mount('/static',CapturedStaticFiles(directory=HERE/'static'),name='static')

@app.get('/{path:path}')
def page(path:str,req:Request):
 path='/'+path.strip('/');query=urlencode(sorted((k,v) for k,v in req.query_params.multi_items() if k in ['page','query','order'] and v));entry=QUERY_ROUTES.get(path+'?'+query) or ROUTES.get(path)
 if path=='/product-tour' and TOURS:
  data=json.loads((HERE/'static/tour.json').read_text());return HTMLResponse((HERE/TOURS['/tour/'+data['initial']+'/0']['file']).read_text())
 if path.startswith('/app') or path.startswith('/workspace'):
  try:a=account(req)
  except HTTPException:return RedirectResponse('/launchpad/login?next='+quote(path,safe=''),status_code=303)
  with db() as c:projects=list(c.execute('SELECT * FROM tw_projects WHERE owner=?',(owner(req),)))
  if not projects and owner(req)==a['account_id'] and path!='/app/onboarding':return RedirectResponse('/app/onboarding',status_code=303)
  match=re.match(r'/app/projects/([^/]+)(?:/|$)',path)
  if match and re.fullmatch(r'[0-9a-f]{6,32}',match[1]):
   if not any(p['id']==match[1] for p in projects):raise HTTPException(404,'Project not found.')
   if not entry:entry=ROUTES.get(path.replace('/app/projects/'+match[1],'/app/projects/372311',1))
  if re.match(r'/app/projects/[^/]+',path):ACL['project'](req,path.split('/')[3])
  if re.search(r'/app/tasks/[^/]+$',path) and path.rsplit('/',1)[-1] not in ['tasks','board','table','completedTasks']:
   get_task(path.rsplit('/',1)[-1],req)
  # Dynamic user-created tasks reuse the source detail template and update through the local API.
  if not entry and re.search(r'/app/tasks/[^/]+$',path):
   get_task(path.rsplit('/',1)[-1],req);entry=ROUTES.get('/app/tasks/18438851')
  list_match=re.fullmatch(r'/app/tasklists/([^/]+)/list',path)
  if list_match:
   with db() as c:list_record=c.execute("SELECT parent,data FROM tw_records WHERE owner=? AND id=? AND kind='list'",(owner(req),list_match[1])).fetchone()
   if list_record:pid=list_record['parent'];list_name=json.loads(list_record['data'])['title']
   elif list_match[1]=='1404857' and any(p['id']=='372311' for p in projects):pid='372311';list_name='My List'
   else:raise HTTPException(404,'Task list not found.')
   ACL['project'](req,pid);entry=ROUTES.get('/app/projects/372311/tasks/list')
   raw=personalize((HERE/entry['file']).read_text(),a,'/app/projects/'+pid+'/tasks/list',owner(req));tree=dom.document_fromstring(raw);body=tree.find('body');body.set('data-route',path);body.set('data-tasklist-name',list_name)
   return HTMLResponse('<!doctype html>'+dom.tostring(tree,encoding='unicode'))
  if not entry and re.match(r'/app/projects/[^/]+',path):
   pid=path.split('/')[3]
   with db() as c:exists=c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(owner(req),pid)).fetchone()
   if exists and path.count('/')==3:entry=ROUTES.get('/app/projects/372311/tasks/list')
 if entry:
  if 'redirect' in entry:return RedirectResponse(entry['redirect'],status_code=308)
  raw=(HERE/entry['file']).read_text()
  if path=='/help/projects/search' and path+'?'+query not in QUERY_ROUTES:
   term=req.query_params.get('query','').strip();words=term.casefold().split();results=[r for r in HELP_SEARCH if words and all(w in (r['title']+' '+r['text']).casefold() for w in words)]
   if req.query_params.get('order')=='title':results.sort(key=lambda r:r['title'].casefold())
   tree=dom.document_fromstring(raw)
   for node in tree.xpath('//input[@name="query"]'):node.set('value',term)
   regions=tree.xpath('//section[contains(@class,"right-content")]')
   if regions:
    region=regions[0];region.clear();region.set('class','right-content');heading=etree.SubElement(region,'h2');heading.text=f'Search for "{term}" yielded {len(results)} results in this local Help Center'
    listing=etree.SubElement(region,'ul',{'class':'articles-list'})
    for result in results:
     item=etree.SubElement(listing,'li');link=etree.SubElement(item,'a',href=result['url']);link.text=result['title'];etree.SubElement(item,'br');etree.SubElement(item,'small').text=result['text'][:220]
    if not results:etree.SubElement(region,'p').text='No results found. Try another search term.'
   raw='<!doctype html>'+dom.tostring(tree,encoding='unicode')
  if entry.get('auth'):raw=personalize(raw,account(req),path,owner(req))
  if entry.get('auth') and path.endswith('/tasks/list') and req.query_params.get('list'):
   tree=dom.document_fromstring(raw);tree.find('body').set('data-tasklist-name',req.query_params['list']);raw='<!doctype html>'+dom.tostring(tree,encoding='unicode')
  return HTMLResponse(raw)
 return HTMLResponse(shell('Page unavailable','<section class="local-boundary"><h1>This page is unavailable</h1><p>The requested page could not be found in this workspace.</p><a href="/">Return to Teamwork.com</a></section>'),status_code=404)
