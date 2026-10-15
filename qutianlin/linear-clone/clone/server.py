from __future__ import annotations
import base64,hashlib,hmac,html,json,os,re,secrets,smtplib,sqlite3,time,sys,asyncio,logging
from contextlib import suppress
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote,urlsplit,urlencode
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from websitebench.site_backend import SiteBackend
from websitebench.local_clone_auth.store import LocalAuthStore,AuthError,AuthRateLimited,AuthExpired,AuthLocked,AuthValidationError
from model import WorkspaceStore,migrate
from projects import validate_project
from workspaces import workflow_states

ROOT=Path(__file__).resolve().parent
sys.path.append(str(ROOT/'vendor'))
RUNTIME=Path(os.environ.get('WEBSITEBENCH_SITE_BACKEND_RUNTIME',str(ROOT/'backend/runtime.json')))
DATA=Path(os.environ.get('LINEAR_DATA_DIR',os.environ.get('WEBSITEBENCH_DATA_DIR',str(ROOT.parent/'data')))).resolve();DATA.mkdir(parents=True,exist_ok=True)
backend=SiteBackend.open(json.loads(RUNTIME.read_text()),data_root=DATA,migration_hook=migrate);backend.lifecycle.initialize()
MAIL_WORKER=secrets.token_urlsafe(32)
auth=LocalAuthStore(backend.lifecycle.database_path,site_id='linear',mail_mode='SMTP_PENDING',mail_worker_token=MAIL_WORKER);auth.ensure_schema()
with auth.connect() as conn:
 migrate(conn)
 conn.execute('INSERT OR IGNORE INTO linear_schema VALUES(2,?)',(int(time.time()),))
 conn.commit()
store=WorkspaceStore(auth)
with auth.connect() as conn:CSRF_SECRET=conn.execute("SELECT value FROM linear_metadata WHERE key='csrf_secret'").fetchone()[0].encode()
COOKIE='linear_clone_session';KINDS={'issues','projects','views','documents','document-templates','issue-templates','recurring-issues','drafts','notifications','labels','project-labels','label-groups','workflow-states','project-statuses','teams','comments','loops','initiatives','releases','invites','integrations','webhooks'}
WEBHOOK_RESOURCES={'Comment','CustomerNeed','Customer','Cycle','Document','Reaction','InitiativeUpdate','Initiative','IssueLabel','Attachment','Issue','ProjectLabel','ProjectUpdate','Project','User','IssueSLA'}
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def csrf(token):return hmac.new(CSRF_SECRET,token.encode(),hashlib.sha256).hexdigest()
def safe_redirect(value):
 return value if isinstance(value,str) and value.startswith('/') and not value.startswith('//') and '\\' not in value and not any(ord(c)<32 for c in value) else '/qqq153/team/QQQ/active'
def set_cookie(response,token):response.set_cookie(COOKIE,token,httponly=True,samesite='lax',secure=os.environ.get('LINEAR_TLS')=='1',max_age=30*86400,path='/')
def session(request,required=False):
 token=request.cookies.get(COOKIE);data=auth.resolve_session(token)
 if required and (not data or not data['authenticated']):raise HTTPException(401,'Please log in to Linear.')
 return token,data
def actor(request):
 if getattr(request.state,'api_actor',None):return request.state.api_actor
 _,s=session(request,True);a=s['account'];return a,store.workspace(a,getattr(request.state,'workspace_id',None) or request.headers.get('x-linear-workspace') or request.cookies.get('linear_clone_workspace'))
def private_drafts(a,w):return [x for x in store.list(w['id'],'drafts') if x.get('draft_account_id',w['owner_id'])==a['account_id']]
def personal_settings(a,w,route):
 saved=store.settings(w['id'],route+'::'+a['account_id'])
 return saved if saved or a['account_id']!=w['owner_id'] else store.settings(w['id'],route)
def validate_configuration(wid,kind,data,id=None):
 if kind not in ('labels','label-groups','workflow-states','project-statuses'):return
 if kind in ('labels','label-groups'):
  previous=store.get(wid,kind,id)if id else {}
  value={**(previous or {}),**data}
  for key in ('is_group','archived'):
   if key in value and type(value[key])is not bool:raise HTTPException(422,'Invalid label setting.')
  if kind=='labels'and value.get('group')is not None:
   if value.get('is_group')or value['group']==id:raise HTTPException(422,'Label groups cannot be nested.')
   from issue_forms import label_group
   with auth.connect()as c:label_group(c,wid,value['group'],value.get('team'))
 if kind=='workflow-states':
  previous=store.get(wid,kind,id) if id else None
  if previous and previous.get('category')=='Duplicate' and any(key in data and data[key]!=previous.get(key) for key in ('title','category')):raise HTTPException(422,'The Duplicate status is reserved and cannot be changed.')
  if data.get('category')=='Duplicate' and not (previous and previous.get('category')=='Duplicate'):raise HTTPException(422,'The Duplicate status is reserved.')
 if 'title' in data and any(x['id']!=id and (kind!='workflow-states' or x.get('team','QQQ')==data.get('team',(store.get(wid,kind,id) or {}).get('team','QQQ'))) and x['title'].casefold()==str(data['title']).strip().casefold() for x in store.list(wid,kind)):raise HTTPException(409,'This name is already in use.')
 categories={'workflow-states':{'Backlog','Unstarted','Started','Completed','Canceled','Duplicate'},'project-statuses':{'Backlog','Planned','In Progress','Completed','Canceled'}}
 if kind in categories and data.get('category','Backlog') not in categories[kind]:raise HTTPException(422,'Invalid status category.')
@app.middleware('http')
async def boundaries(request,call_next):
 bearer=request.headers.get('authorization','')
 if bearer:
  if not request.url.path.startswith('/api/entities/') or not bearer.startswith('Bearer '):return JSONResponse({'error':'API keys can only access the local entity API.'},403)
  with auth.connect() as c:
   key=c.execute('SELECT * FROM linear_api_keys WHERE digest=?',(digest(bearer[7:]),)).fetchone()
   if not key:return JSONResponse({'error':'Invalid or revoked API key.'},401)
   permissions=json.loads(key['permissions']);needed='read' if request.method in ('GET','HEAD') else 'create' if request.method=='POST' else 'write'
   if needed not in permissions:return JSONResponse({'error':'This API key does not have the required permission.'},403)
   account=c.execute('SELECT account_id,email_normalized,display_name FROM local_auth_accounts WHERE account_id=?',(key['account_id'],)).fetchone()
   workspace=c.execute('SELECT * FROM linear_workspaces WHERE id=?',(key['workspace_id'],)).fetchone()
   member=c.execute('SELECT role FROM linear_members WHERE workspace_id=? AND account_id=?',(key['workspace_id'],key['account_id'])).fetchone()
   if not account or not workspace or not member:return JSONResponse({'error':'API key owner is unavailable.'},401)
   c.execute('UPDATE linear_api_keys SET last_used_at=? WHERE id=?',(int(time.time()),key['id']));c.commit()
   request.state.api_actor=(dict(account),{**dict(workspace),'role':member['role']})
 if request.method not in ('GET','HEAD','OPTIONS'):
  origin=request.headers.get('origin')
  if origin and origin!=str(request.base_url).rstrip('/'):
   return JSONResponse({'error':'Invalid request origin.'},403)
  token=request.cookies.get(COOKIE,'')
  if not getattr(request.state,'api_actor',None) and (not token or not hmac.compare_digest(request.headers.get('x-linear-csrf',''),csrf(token))):
   return JSONResponse({'error':'Refresh this page and try again.'},403)
 try:r=await call_next(request)
 except AuthRateLimited as e:r=JSONResponse({'error':'Please wait before trying again.','retry_after':e.retry_after},429)
 except (AuthExpired,AuthLocked) as e:r=JSONResponse({'error':'This login code has expired. Request a new login link.'},400)
 except AuthValidationError as e:r=JSONResponse({'error':str(e)},400)
 except AuthError:r=JSONResponse({'error':'We could not complete the login code verification…'},400)
 if request.url.path.startswith('/static/pdf-renderer/'):
  r.headers['Content-Security-Policy']="default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'"
 elif 'Content-Security-Policy' not in r.headers:r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
 r.headers['Referrer-Policy']='no-referrer';r.headers['X-Content-Type-Options']='nosniff'
 if not request.url.path.startswith('/static/'):r.headers['Cache-Control']='no-store, private';r.headers['Vary']='Cookie'
 return r
@app.get('/healthz')
@app.get('/__websitebench/health')
def health():return {'status':'ok','site_id':'linear','database':'sqlite','mail':'smtp'}
@app.get('/api/session')
def get_session(request:Request):
 token,data=auth.ensure_session(request.cookies.get(COOKIE));payload={**data,'csrf':csrf(token)}
 if data['authenticated']:
  from workspaces import account_workspaces
  selected=getattr(request.state,'workspace_id',None) or request.cookies.get('linear_clone_workspace')
  available=account_workspaces(auth,data['account'])
  payload['workspaces']=available
  payload['workspace']=store.workspace(data['account'],selected if any(x['id']==selected for x in available) else None)
 r=JSONResponse(payload);set_cookie(r,token)
 if data['authenticated']:
  from workspaces import set_workspace
  set_workspace(r,payload['workspace'])
 return r

@app.get('/api/search')
def search_public(q:str='',collection:str='docs'):
 query=q.strip().lower()[:200]
 if len(query)<2:return []
 source=ROOT/'frontend/search-index.json'
 if not source.exists():return []
 words=query.split();hits=[]
 for item in json.loads(source.read_text()):
  if not item['path'].startswith('/'+('integrations' if collection=='integrations' else 'docs')+'/'):continue
  title=item['title'].lower();body=item['text'].lower()
  if not all(word in body or word in title for word in words):continue
  pos=body.find(query);start=max(0,pos-60);hits.append({'path':item['path'],'title':item['title'],'excerpt':item['text'][start:start+180],'score':sum(3 for word in words if word in title)+(10 if title==query else 0)})
 return sorted(hits,key=lambda item:-item['score'])[:20]

def smtp_send(recipient,subject,body):
 host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1');port=int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025'))
 if host not in ('127.0.0.1','localhost','::1','mailpit'):raise RuntimeError('Only local Mailpit SMTP is permitted.')
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@linear.clone.test');msg['To']=recipient;msg['Subject']=subject;msg.set_content(body)
 with smtplib.SMTP(host,port,timeout=5) as smtp:smtp.send_message(msg)

def run_recurring_worker():
 from recurring_issues import deliver_recurring_issues
 with auth.connect()as c:workspaces=[r[0]for r in c.execute('SELECT id FROM linear_workspaces')]
 for wid in workspaces:deliver_recurring_issues(store,wid)
async def recurring_worker():
 while True:
  try:await asyncio.to_thread(run_recurring_worker)
  except Exception:logging.getLogger('linear.recurring').exception('Recurring issues will be retried')
  await asyncio.sleep(30)
@app.on_event('startup')
async def start_recurring_worker():app.state.recurring_task=asyncio.create_task(recurring_worker())
@app.on_event('shutdown')
async def stop_recurring_worker():
 app.state.recurring_task.cancel()
 with suppress(asyncio.CancelledError):await app.state.recurring_task

@app.post('/api/auth/challenge')
async def challenge(request:Request):
 token,s=session(request)
 if not s:raise HTTPException(401,'Please refresh the login page.')
 if s['authenticated']:raise HTTPException(409,'You are already logged in.')
 d=await request.json();email=d.get('email','');flow=auth.start_passwordless_signin(token,email=email,restart_invalid_flow=True)
 claim=auth.claim_pending_mail_for_session(token,purpose='passwordless-signin',worker_token=MAIL_WORKER)
 if not claim:raise HTTPException(503,'Unable to prepare email. Please try again.')
 magic=secrets.token_urlsafe(32);redirect=safe_redirect(d.get('redirectTo'))
 with auth.connect() as c:c.execute('INSERT INTO linear_magic VALUES(?,?,?,?,?)',(digest(magic),flow['signin_id'],flow['expires_at'],0,redirect));c.commit()
 origin=str(request.base_url).rstrip('/');link=origin+'/auth/email?token='+magic
 body='Log in to Linear\n\n'+link+'\n\nOr enter this login code: '+claim['verification_code']+'\n\nThis login link and code expire in 10 minutes and can only be used once.\n\nLinear local workspace'
 try:
  smtp_send(email,'Your Linear login link',body)
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,target_request_count=1,accepted_request_count=1,worker_token=MAIL_WORKER)
 except Exception:
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='transport',worker_token=MAIL_WORKER)
  return JSONResponse({'error':'We couldn’t send the email. Please try again.','mail_status':'SMTP_FAILED'},503)
 return {'accepted':True,'email':email,'mail_status':'SMTP_SENT','expires_at':flow['expires_at']}

@app.post('/api/auth/verify')
async def verify(request:Request):
 token,s=session(request)
 if not s:raise HTTPException(401,'Please request a new login link.')
 d=await request.json();auth.verify_passwordless_code(token,d.get('code',''));result=auth.complete_passwordless_signin(token)
 store.workspace(result['account']);r=JSONResponse({'authenticated':True,'account_created':result['account_created'],'redirect':safe_redirect(d.get('redirectTo'))});set_cookie(r,result['session_token']);return r

@app.get('/auth/email')
def magic_verify(request:Request,token:str=''):
 # Link authority is independent of the browser, email target and flow stay bound.
 new=auth.create_anonymous_session();owner=auth.session_owner_digest(new);now=int(time.time())
 with auth.connect() as c:
  c.execute('BEGIN IMMEDIATE');m=c.execute('SELECT * FROM linear_magic WHERE digest=?',(digest(token),)).fetchone()
  if not m or m['consumed'] or m['expires_at']<=now:
   c.rollback();return HTMLResponse(auth_page('This login link has expired.','Request a new login link to continue.'),400)
  flow=c.execute('SELECT * FROM local_auth_passwordless_flows WHERE signin_id=?',(m['signin_id'],)).fetchone()
  if not flow or flow['expires_at']<=now:
   c.rollback();return HTMLResponse(auth_page('This login link has expired.','Request a new login link to continue.'),400)
  c.execute('UPDATE local_auth_passwordless_flows SET session_digest=?,verified_at=? WHERE signin_id=?',(owner,now,m['signin_id']))
  c.execute('UPDATE linear_magic SET consumed=1 WHERE digest=?',(digest(token),));c.commit();redirect=m['redirect_to']
 result=auth.complete_passwordless_signin(new);store.workspace(result['account']);r=RedirectResponse(safe_redirect(redirect),303);set_cookie(r,result['session_token']);return r

@app.post('/api/auth/logout')
def logout(request:Request):
 token,_=session(request);auth.sign_out(token);r=JSONResponse({'redirect':'/login'});r.delete_cookie(COOKIE,path='/');return r

@app.post('/api/auth/local-origin')
def local_origin(request:Request):
 a,_=actor(request);token,_=session(request);ticket=secrets.token_urlsafe(32)
 with auth.connect() as c:
  c.execute('INSERT INTO linear_account_actions VALUES(?,?,?,?,?,?,0,0)',('origin_'+secrets.token_hex(12),a['account_id'],'local-origin',json.dumps({'session_digest':auth.session_owner_digest(token)}),digest(ticket),int(time.time())+60));c.commit()
 return {'url':'http://localhost:'+str(request.url.port or 18140)+'/auth/local-origin?token='+ticket}

@app.get('/auth/local-origin')
def consume_local_origin(request:Request,token:str=''):
 if request.url.hostname!='localhost':raise HTTPException(400,'Open this link on localhost.')
 with auth.connect() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM linear_account_actions WHERE digest=? AND purpose='local-origin' AND consumed=0 AND expires_at>?",(digest(token),int(time.time()))).fetchone()
  if not row:raise HTTPException(400,'This local sign-in link has expired.')
  new_token=auth._rotate_session_unlocked(c,json.loads(row['payload'])['session_digest'],row['account_id'],int(time.time()))
  c.execute('UPDATE linear_account_actions SET consumed=1 WHERE id=?',(row['id'],));c.commit()
 r=RedirectResponse('/qqq153/settings/account/security?register-passkey=1',303);set_cookie(r,new_token);return r

@app.get('/api/state')
def state(request:Request):
 from workspaces import team_state,account_workspaces
 a,w=actor(request);return {'account':a,'workspace':w,'workspaces':account_workspaces(auth,a),'issues':store.list(w['id'],'issues'),'workflow_states':workflow_states(store,w['id'],request.headers.get('x-linear-team','QQQ')),'projects':store.list(w['id'],'projects'),'project_labels':store.list(w['id'],'project-labels'),'project_statuses':store.list(w['id'],'project-statuses'),'teams':team_state(auth,w,a),'views':store.list(w['id'],'views'),'notifications':store.list(w['id'],'notifications'),'labels':store.list(w['id'],'labels'),'label_groups':store.list(w['id'],'label-groups'),'documents':store.list(w['id'],'documents'),'document_templates':store.list(w['id'],'document-templates'),'issue_templates':store.list(w['id'],'issue-templates'),'recurring_issues':store.list(w['id'],'recurring-issues'),'drafts':private_drafts(a,w),'default_issue_template':store.settings(w['id'],'/qqq153/settings/teams/'+request.headers.get('x-linear-team','QQQ')+'/templates').get('default-issue-template')}
@app.post('/api/uploads')
async def upload_file(request:Request):
 from uploads import save_upload
 a,w=actor(request);return await save_upload(request,store,w['id'])
@app.api_route('/api/uploads/{id}',methods=['GET','HEAD'])
def uploaded_file(id:str,request:Request):
 from uploads import read_upload
 a,w=actor(request);return read_upload(request,store,w['id'],id)
@app.get('/api/uploads/{id}/metadata')
def upload_metadata(id:str,request:Request):
 from uploads import metadata
 a,w=actor(request)
 with auth.connect() as connection:row=connection.execute('SELECT id,filename,mime,size,sha256,created_at,render_type FROM linear_uploads WHERE id=? AND workspace_id=?',(id,w['id'])).fetchone()
 if not row:raise HTTPException(404,'File not found.')
 return metadata(row)
@app.post('/api/document-import')
async def document_import(request:Request):
 from uploads import import_text_file
 actor(request);return import_text_file(await request.json())
@app.put('/api/issue-templates/default')
async def default_issue_template(request:Request):
 a,w=actor(request);data=await request.json()
 if not isinstance(data,dict):raise HTTPException(422,'Select an issue template.')
 team=data.get('team',request.headers.get('x-linear-team','QQQ'));key=data.get('template_id');template=store.get(w['id'],'issue-templates',key)if isinstance(key,str)else None
 if key is not None and (not template or template.get('scope_team')not in (None,team)):raise HTTPException(422,'Select an available template for this team.')
 store.setting(w['id'],'/qqq153/settings/teams/'+team+'/templates','default-issue-template',key)
 return {'template_id':key}

@app.post('/api/document-templates/order')
async def order_document_templates(request:Request):
 from document_templates import reorder_templates
 a,w=actor(request);return reorder_templates(store,w['id'],await request.json())
@app.post('/api/documents/{id}/template')
async def apply_document_template(id:str,request:Request):
 a,w=actor(request);document=store.get(w['id'],'documents',id)
 if not document:raise HTTPException(404,'Document not found.')
 data=await request.json()
 if not isinstance(data,dict):raise HTTPException(422,'Select a document template.')
 template=store.get(w['id'],'document-templates',str(data.get('template_id','')))
 if not template:raise HTTPException(404,'Template not found.')
 if document.get('description','').strip() or re.search(r'<(?:img|audio|video|table|hr|pre|ul|ol)\b|data-callout=|class="[^"]*collapsible-section',document.get('content_html','')):raise HTTPException(422,'Templates can only be applied to an empty document.')
 parent=document.get('parent')
 team=template.get('team')
 if team and parent:
  if parent['kind']=='teams':valid=parent['id']==team
  elif parent['kind']=='issues':valid=(store.get(w['id'],'issues',parent['id']) or {}).get('team','QQQ')==team
  else:valid=team in (store.get(w['id'],'projects',parent['id']) or {}).get('teams',[])
  if not valid:raise HTTPException(422,'This template belongs to another team.')
 try:return store.save(w['id'],'documents',{'title':template['title'],'content_html':template['content_html'],'icon':template.get('icon',''),'template_id':template['id'],'revision':data.get('revision',document['revision'])},id)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/document-templates/{id}/documents')
async def document_from_template(id:str,request:Request):
 a,w=actor(request);template=store.get(w['id'],'document-templates',id)
 if not template:raise HTTPException(404,'Template not found.')
 data=await request.json()
 if not isinstance(data,dict):raise HTTPException(422,'Invalid document options.')
 parent=data.get('parent')
 if template.get('team'):
  if parent is None:parent={'kind':'teams','id':template['team']}
  if not isinstance(parent,dict):raise HTTPException(422,'Select a document location.')
  team=template['team']
  if parent.get('kind')=='teams':valid=parent.get('id')==team
  elif parent.get('kind')=='issues':valid=(store.get(w['id'],'issues',parent.get('id','')) or {}).get('team','QQQ')==team
  elif parent.get('kind')=='projects':valid=team in (store.get(w['id'],'projects',parent.get('id','')) or {}).get('teams',[])
  else:valid=False
  if not valid:raise HTTPException(422,'This template belongs to another team.')
 return store.save(w['id'],'documents',{'title':template['title'],'content_html':template['content_html'],'icon':template.get('icon',''),'template_id':id,'parent':parent})
@app.post('/api/documents/{id}/comments')
async def add_document_comment(id:str,request:Request):
 from documents import change_document_comment
 a,w=actor(request);return change_document_comment(store,w['id'],id,a,await request.json())
@app.patch('/api/documents/{id}/comments/{comment_id}')
async def edit_document_comment(id:str,comment_id:str,request:Request):
 from documents import change_document_comment
 a,w=actor(request);return change_document_comment(store,w['id'],id,a,await request.json(),comment_id)
@app.get('/api/documents/{id}/pdf')
def document_pdf(id:str,request:Request):
 from document_pdf import export_pdf
 from fastapi.responses import Response
 a,w=actor(request);document=store.get(w['id'],'documents',id)
 if not document:raise HTTPException(404,'Document not found.')
 filename=re.sub(r'[\\/:*?"<>|\x00-\x1f]','-',document['title'])+'.pdf'
 def resolve_image(src):
  if re.fullmatch(r'/api/uploads/upload_[a-f0-9]{32}',src):
   with auth.connect()as c:row=c.execute('SELECT content,mime FROM linear_uploads WHERE workspace_id=? AND id=?',(w['id'],src.rsplit('/',1)[-1])).fetchone()
   return bytes(row['content'])if row and row['mime'].startswith('image/')else None
  if src.startswith('/static/assets/'):
   path=(ROOT/src.lstrip('/')).resolve();assets=(ROOT/'static/assets').resolve()
   if path.is_relative_to(assets)and path.is_file()and path.stat().st_size<=10*1024*1024:return path.read_bytes()
  return None
 return Response(export_pdf(document,resolve_image,str(request.base_url).rstrip('/')),media_type='application/pdf' ,headers={'Content-Disposition':"attachment; filename=document.pdf; filename*=UTF-8''"+quote(filename,safe=''),'Cache-Control':'private, no-store'})
@app.post('/api/projects/{id}/activity')
async def project_activity(id:str,request:Request):
 a,w=actor(request);project=store.get(w['id'],'projects',id)
 if not project:raise HTTPException(404,'Project not found.')
 d=await request.json()
 if not isinstance(d,dict) or d.get('type') not in ['comment','update'] or not isinstance(d.get('body'),str) or not d['body'].strip() or len(d['body'])>30000:raise HTTPException(422,'Enter a comment or project update.')
 if d['type']=='update' and d.get('health') not in ['onTrack','atRisk','offTrack']:raise HTTPException(422,'Select project health.')
 item={'id':secrets.token_hex(12),'type':d['type'],'body':d['body'].strip(),'author':a['display_name'],'author_id':a['email_normalized'],'created_at':int(time.time())}
 patch={'revision':project['revision'],'activity':project.get('activity',[])+[item]}
 if d['type']=='update':item['health']=d['health'];patch['health']=d['health'];patch['health_updated_at']=item['created_at']
 try:return store.save(w['id'],'projects',patch,id)
 except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/entities/{kind}')
def list_entities(kind:str,request:Request):
 if kind not in KINDS:raise HTTPException(404)
 a,w=actor(request);return workflow_states(store,w['id'],request.headers.get('x-linear-team','QQQ')) if kind=='workflow-states' else private_drafts(a,w) if kind=='drafts' else store.list(w['id'],kind)
@app.get('/api/entities/{kind}/{id}')
def get_entity(kind:str,id:str,request:Request):
 if kind not in KINDS:raise HTTPException(404)
 a,w=actor(request);d=store.get(w['id'],kind,id)
 if not d or kind=='drafts' and d.get('draft_account_id',w['owner_id'])!=a['account_id']:raise HTTPException(404,'Item not found.')
 return d
@app.post('/api/entities/{kind}')
async def create_entity(kind:str,request:Request):
 if kind not in KINDS:raise HTTPException(404)
 a,w=actor(request);d=await request.json()
 if not isinstance(d,dict):raise HTTPException(422,'Expected an object.')
 if kind=='drafts':d['draft_account_id']=a['account_id']
 if kind=='issues':
  if d.get('draft_id'):
   draft=store.get(w['id'],'drafts',str(d['draft_id']))
   if not draft or draft.get('draft_account_id',w['owner_id'])!=a['account_id']:raise HTTPException(404,'Draft not found.')
   d={**{key:value for key,value in draft.items()if key not in ['id','revision','created_at','updated_at']},**d,'draft_revision':d.get('draft_revision',draft['revision'])}
  from issue_templates import issue_template_defaults
  d=issue_template_defaults(store,w['id'],d)
 if kind in ('issues','projects','views','documents','teams','labels','project-labels','label-groups','workflow-states','project-statuses','loops','initiatives','releases') and not str(d.get('title',d.get('name',''))).strip():raise HTTPException(422,'Please enter a name.')
 if len(json.dumps(d))>100000:raise HTTPException(413)
 if kind=='workflow-states':d['team']=request.headers.get('x-linear-team',d.get('team','QQQ'))
 validate_configuration(w['id'],kind,d)
 if kind=='projects':
  validate_project(store,w['id'],a,d);d['creator']=a['email_normalized'];d['activity']=[]
 if kind=='views':validate_view_filters(d)
 if kind=='issues' and d.get('status','Todo') not in [s['title'] for s in workflow_states(store,w['id'],d.get('team',(store.get(w['id'],'issues',id) or {}).get('team','QQQ')) if 'id' in locals() else d.get('team','QQQ'))]:raise HTTPException(422,'Invalid status.')
 if kind=='issues':
  d['creator']=a['email_normalized']
  preferences=personal_settings(a,w,'/qqq153/settings/account/preferences')
  if preferences.get('automationsAndWorkflows.autoAssignToSelf-control',preferences.get('c66')) is True and not d.get('assignee'):d['assignee']=a['email_normalized']
 if kind=='webhooks':
  if not str(d.get('title','')).strip() or urlsplit(d.get('url','')).scheme not in ('http','https') or not urlsplit(d.get('url','')).hostname:raise HTTPException(422,'Enter a label and a valid webhook URL.')
  if not isinstance(d.get('resourceTypes'),list) or not d['resourceTypes'] or any(not isinstance(v,str) or v not in WEBHOOK_RESOURCES for v in d['resourceTypes']):raise HTTPException(422,'Select data change events.')
  d['secret']=str(d.get('secret') or secrets.token_urlsafe(32));d['enabled']=True;d['delivery_mode']='local-collection'
 if kind=='invites':return RedirectResponse('/api/invitations',307)
 if kind=='teams':return RedirectResponse('/api/teams',307)
 try:return store.save(w['id'],kind,d)
 except ValueError as e:raise HTTPException(409,str(e))
@app.patch('/api/entities/{kind}/{id}')
async def update_entity(kind:str,id:str,request:Request):
 if kind not in KINDS:raise HTTPException(404)
 a,w=actor(request);d=await request.json()
 if not isinstance(d,dict):raise HTTPException(422,'Expected an object.')
 if kind=='drafts':
  draft=store.get(w['id'],'drafts',id)
  if not draft or draft.get('draft_account_id',w['owner_id'])!=a['account_id']:raise HTTPException(404,'Draft not found.')
  d['draft_account_id']=a['account_id']
 if kind=='teams':
  from workspaces import admin,teams
  admin(w)
  if 'identifier' in d or 'id' in d:raise HTTPException(422,'Team identifiers cannot be changed here.')
  with auth.connect() as c:
   if 'title' in d and any(t['id']!=id and t['title'].casefold()==str(d['title']).strip().casefold() for t in teams(c,w['id'])):raise HTTPException(409,'Team name is already in use.')
   if id=='QQQ' and not store.get(w['id'],'teams',id):
    now=int(time.time());c.execute("INSERT INTO linear_records VALUES(?,'teams','QQQ',?,1,?,?)",(w['id'],json.dumps({'id':'QQQ','title':'Qqq153','description':''}),now,now));c.commit()
 if len(json.dumps(d))>100000:raise HTTPException(413)
 validate_configuration(w['id'],kind,d,id)
 if kind=='projects':
  validate_project(store,w['id'],a,d,id);previous=store.get(w['id'],kind,id);d['creator']=previous.get('creator');d['activity']=previous.get('activity',[])
  if d.get('status')!=previous.get('status') and 'status' in d:
   closed=any(x['title']==d['status'] and x['category'] in ['Completed','Canceled'] for x in store.list(w['id'],'project-statuses'));d['completed_at']=int(time.time()) if closed else None
 if kind=='webhooks':
  if 'secret' in d and (not isinstance(d['secret'],str) or not d['secret']):raise HTTPException(422,'Invalid signing secret.')
  if 'resourceTypes' in d and (not isinstance(d['resourceTypes'],list) or not d['resourceTypes'] or any(not isinstance(v,str) or v not in WEBHOOK_RESOURCES for v in d['resourceTypes'])):raise HTTPException(422,'Invalid event selection.')
  if 'enabled' in d and not isinstance(d['enabled'],bool):raise HTTPException(422,'Invalid webhook state.')
  if 'url' in d and (urlsplit(str(d['url'])).scheme not in ('http','https') or not urlsplit(str(d['url'])).hostname):raise HTTPException(422,'Invalid webhook URL.')
 if kind=='views':validate_view_filters(d)
 if 'title' in d and not str(d['title']).strip():raise HTTPException(422,'Please enter a name.')
 if kind=='issues' and 'status' in d and d['status'] not in [s['title'] for s in workflow_states(store,w['id'],d.get('team',(store.get(w['id'],'issues',id) or {}).get('team','QQQ')) if 'id' in locals() else d.get('team','QQQ'))]:raise HTTPException(422,'Invalid status.')
 if kind=='issues' and 'status' in d:
  preferences=personal_settings(a,w,'/qqq153/settings/account/preferences');previous=store.get(w['id'],kind,id)
  started=any(s['title']==d['status'] and s['category']=='Started' for s in store.list(w['id'],'workflow-states'))
  if previous and previous.get('status')!=d['status'] and started and not d.get('assignee',previous.get('assignee')) and preferences.get('automationsAndWorkflows.assignToSelfWhenStarted-control',preferences.get('c67')) is True:d['assignee']=a['email_normalized']
 try:return store.save(w['id'],kind,d,id)
 except KeyError:raise HTTPException(404,'Item not found.')
 except ValueError as e:raise HTTPException(409,str(e))
@app.delete('/api/entities/{kind}/{id}')
def delete_entity(kind:str,id:str,request:Request):
 if kind not in KINDS:raise HTTPException(404)
 a,w=actor(request)
 if kind=='drafts' and not any(x['id']==id for x in private_drafts(a,w)):raise HTTPException(404,'Draft not found.')
 if kind=='teams':raise HTTPException(409,'Archive the team to retain its issues and history.')
 try:
  if not store.delete(w['id'],kind,id):raise HTTPException(404,'Item not found.')
 except ValueError as e:raise HTTPException(409,str(e))
 return {'deleted':True}

@app.get('/api/keys')
def list_keys(request:Request):
 a,w=actor(request)
 with auth.connect() as c:
  return [{**dict(r),'permissions':json.loads(r['permissions'])} for r in c.execute('SELECT id,name,prefix,permissions,created_at,last_used_at FROM linear_api_keys WHERE workspace_id=? AND account_id=? ORDER BY created_at',(w['id'],a['account_id']))]
@app.post('/api/keys')
async def create_key(request:Request):
 a,w=actor(request);d=await request.json();name=str(d.get('name','')).strip();permissions=d.get('permissions',['read','create','write'])
 if not name or not isinstance(permissions,list) or not permissions or set(permissions)-{'read','create','write'}:raise HTTPException(422,'Enter a key name and select valid permissions.')
 token='lin_local_'+secrets.token_urlsafe(32);id='key_'+secrets.token_hex(12)
 with auth.connect() as c:c.execute('INSERT INTO linear_api_keys VALUES(?,?,?,?,?,?,?,?,NULL)',(id,w['id'],a['account_id'],name,digest(token),token[:15],json.dumps(permissions),int(time.time())));c.commit()
 return {'id':id,'name':name,'token':token,'permissions':permissions}
@app.delete('/api/keys/{id}')
def revoke_key(id:str,request:Request):
 a,w=actor(request)
 with auth.connect() as c:
  n=c.execute('DELETE FROM linear_api_keys WHERE id=? AND workspace_id=? AND account_id=?',(id,w['id'],a['account_id'])).rowcount;c.commit()
 if not n:raise HTTPException(404,'API key not found.')
 return {'revoked':True}

@app.patch('/api/profile')
async def update_profile(request:Request):
 a,w=actor(request);d=await request.json();name=str(d.get('name','')).strip()
 if not name or len(name)>200:raise HTTPException(422,'Enter your name.')
 with auth.connect() as c:c.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(name,a['account_id']));c.commit()
 return {'name':name}

@app.post('/api/profile/email')
async def change_email(request:Request):
 a,w=actor(request);email=str((await request.json()).get('email','')).strip().lower()
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Enter a valid email address.')
 if auth.account_exists(email):raise HTTPException(409,'This email address is already associated with an account.')
 token=secrets.token_urlsafe(32);id='email_'+secrets.token_hex(12)
 try:smtp_send(email,'Verify your new Linear email address','Confirm your new email address:\n\n'+str(request.base_url)+'auth/change-email?token='+token+'\n\nThis link expires in 10 minutes.')
 except Exception:raise HTTPException(503,'Unable to send the verification email. Please try again.')
 with auth.connect() as c:
  c.execute("UPDATE linear_account_actions SET consumed=1 WHERE account_id=? AND purpose='email'",(a['account_id'],))
  c.execute('INSERT INTO linear_account_actions VALUES(?,?,?,?,?,?,0,0)',(id,a['account_id'],'email',json.dumps({'email':email}),digest(token),int(time.time())+600));c.commit()
 return {'sent':True,'email':email}

@app.get('/auth/change-email')
def confirm_email(token:str=''):
 with auth.connect() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM linear_account_actions WHERE digest=? AND purpose='email' AND consumed=0 AND expires_at>?",(digest(token),int(time.time()))).fetchone()
  if not row:return HTMLResponse(auth_page('This verification link has expired.','Request another email change from your profile.'),400)
  try:c.execute('UPDATE local_auth_accounts SET email_normalized=? WHERE account_id=?',(json.loads(row['payload'])['email'],row['account_id']))
  except sqlite3.IntegrityError:return HTMLResponse(auth_page('Email address already in use.'),409)
  c.execute('UPDATE linear_account_actions SET consumed=1 WHERE id=?',(row['id'],));c.commit()
 return RedirectResponse('/qqq153/settings/account/profile',303)

@app.post('/api/export')
def export_issues(request:Request):
 a,w=actor(request);token=secrets.token_urlsafe(32);id='export_'+secrets.token_hex(12)
 with auth.connect() as c:c.execute('INSERT INTO linear_account_actions VALUES(?,?,?,?,?,?,0,0)',(id,a['account_id'],'export',json.dumps({'workspace_id':w['id']}),digest(token),int(time.time())+86400));c.commit()
 try:smtp_send(a['email_normalized'],'Your Linear export is ready',str(request.base_url)+'api/export/download?token='+token+'\n\nThis local download link expires in 24 hours.')
 except Exception:raise HTTPException(503,'Unable to send the download link. Please try again.')
 return {'sent':True}

@app.post('/api/workspace/deletion-code')
def workspace_deletion_code(request:Request):
 a,w=actor(request);code=''.join(secrets.choice('23456789abcdefghjkmnpqrstuvwxyz') for _ in range(10));id='delete_'+secrets.token_hex(12)
 try:smtp_send(a['email_normalized'],'Verify your Linear workspace deletion','Workspace: '+w['name']+'\n\nDeletion code: '+code+'\n\nThis code expires in 10 minutes. Deletion permanently removes this local workspace and its data.')
 except Exception:raise HTTPException(503,'Unable to send the deletion code. Please try again.')
 with auth.connect() as c:
  c.execute("UPDATE linear_account_actions SET consumed=1 WHERE account_id=? AND purpose='workspace-delete'",(a['account_id'],))
  c.execute('INSERT INTO linear_account_actions VALUES(?,?,?,?,?,?,0,0)',(id,a['account_id'],'workspace-delete',json.dumps({'workspace_id':w['id']}),digest(id+code),int(time.time())+600));c.commit()
 return {'id':id,'email':a['email_normalized']}

@app.post('/api/workspace/delete')
async def delete_workspace(request:Request):
 a,w=actor(request);d=await request.json()
 if d.get('acknowledged') is not True:raise HTTPException(422,'Acknowledge permanent deletion to continue.')
 with auth.connect() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM linear_account_actions WHERE id=? AND account_id=? AND purpose='workspace-delete'",(d.get('id',''),a['account_id'])).fetchone()
  if not row or row['consumed'] or row['expires_at']<=int(time.time()) or row['attempts']>=5 or json.loads(row['payload'])['workspace_id']!=w['id']:raise HTTPException(400,'This deletion code has expired. Request another code.')
  if not hmac.compare_digest(row['digest'],digest(row['id']+str(d.get('code','')).strip().lower())):
   c.execute('UPDATE linear_account_actions SET attempts=attempts+1 WHERE id=?',(row['id'],));c.commit();raise HTTPException(400,'Incorrect deletion code.')
  for table in ['linear_records','linear_settings','linear_api_keys','linear_counters','linear_webhook_events','linear_uploads','linear_members','linear_team_members','linear_invitations','linear_imports']:c.execute('DELETE FROM '+table+' WHERE workspace_id=?',(w['id'],))
  c.execute('DELETE FROM linear_workspaces WHERE id=? AND owner_id=?',(w['id'],a['account_id']))
  c.execute('UPDATE linear_account_actions SET consumed=1 WHERE id=?',(row['id'],))
  c.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=?',(int(time.time()),a['account_id']));c.commit()
 r=JSONResponse({'deleted':True,'redirect':'/login'});r.delete_cookie(COOKIE,path='/');return r

@app.get('/api/export/download')
def download_export(request:Request,token:str=''):
 import csv,io
 from fastapi.responses import Response
 a,w=actor(request)
 with auth.connect() as c:row=c.execute("SELECT * FROM linear_account_actions WHERE digest=? AND account_id=? AND purpose='export' AND expires_at>?",(digest(token),a['account_id'],int(time.time()))).fetchone()
 if not row:raise HTTPException(404,'Export not found or expired.')
 out=io.StringIO();writer=csv.writer(out);fields=['id','title','description','status','priority','assignee','project'];writer.writerow(fields)
 for issue in store.list(w['id'],'issues'):writer.writerow([("'"+str(issue.get(k,''))) if str(issue.get(k,'')).startswith(('=','+','-','@')) else issue.get(k,'') for k in fields])
 return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="linear-issues.csv"'})
@app.post('/api/issues/{id}/comments')
async def comment(id:str,request:Request):
 a,w=actor(request);d=store.get(w['id'],'issues',id)
 if not d:raise HTTPException(404)
 payload=await request.json();body=payload.get('body','')
 if not isinstance(body,str):raise HTTPException(422,'Write a comment.')
 body=body.strip()
 from issue_attachments import attachments
 with auth.connect()as c:files=attachments(c,w['id'],payload.get('attachments',[]))
 if not body and not files:raise HTTPException(422,'Write a comment or attach a file.')
 row={'id':'comment_'+secrets.token_hex(8),'body':body,'author':a['display_name'],'created_at':int(time.time()),'reactions':[],'attachments':files}
 return store.save(w['id'],'issues',{'comments':d.get('comments',[])+[row],'revision':d['revision']},id)

@app.get('/api/webhooks/{id}/deliveries')
def webhook_deliveries(id:str,request:Request):
 _,w=actor(request)
 if not store.get(w['id'],'webhooks',id):raise HTTPException(404,'Webhook not found.')
 with auth.connect() as c:return [{**dict(row),'status':'collected-locally'} for row in c.execute('SELECT id,event_type,body,signature,created_at FROM linear_webhook_events WHERE workspace_id=? AND webhook_id=? ORDER BY created_at DESC LIMIT 100',(w['id'],id))]
@app.post('/api/project-labels/batch')
async def project_label_batch(request:Request):
 from project_labels import batch_project_labels
 a,w=actor(request)
 return batch_project_labels(store,w['id'],await request.json())

@app.get('/api/settings')
def get_settings(request:Request,route:str):
 a,w=actor(request)
 if route.endswith('/commit-signing-key'):return {}
 route=route.replace('/'+w['slug']+'/', '/qqq153/',1)
 return personal_settings(a,w,route) if '/settings/account/' in route else store.settings(w['id'],route)
@app.put('/api/settings')
async def save_setting(request:Request):
 a,w=actor(request);d=await request.json()
 from workspaces import admin
 if '/settings/' in str(d.get('route','')) and '/settings/account/' not in str(d.get('route','')):admin(w)
 if str(d.get('route','')).endswith('/commit-signing-key'):raise HTTPException(422,'Use the signing key upload form.')
 route=str(d['route']).replace('/'+w['slug']+'/', '/qqq153/',1)
 if '/settings/account/' in route:route+='::'+a['account_id']
 store.setting(w['id'],route,str(d['key']),d['value']);return {'saved':True,'value':d['value']}
@app.post('/api/forms')
async def save_form(request:Request):
 d=await request.json();id='form_'+secrets.token_hex(12)
 if str(d.get('kind','')).endswith('/commit-signing-key'):raise HTTPException(422,'Use the signing key upload form.')
 if len(json.dumps(d))>100000:raise HTTPException(413)
 with auth.connect() as c:c.execute('INSERT INTO linear_forms VALUES(?,?,?,?)',(id,str(d.get('kind','contact')),json.dumps(d),int(time.time())));c.commit()
 return {'accepted':True,'id':id}

def auth_page(title,description=''):
 return '<!doctype html><html><head><title>Linear</title><link rel="stylesheet" href="/static/local.css"></head><body class="local-auth"><main class="auth-box"><div class="linear-logo">◒</div><h1>'+html.escape(title)+'</h1><p>'+html.escape(description)+'</p><a href="/login">Back to login</a></main></body></html>'
from passkeys import install as install_passkeys
install_passkeys(app,auth,actor,session,set_cookie)
from filters import validate_view_filters
from signing_keys import install as install_signing_keys
install_signing_keys(app,auth,actor,DATA)
from workspaces import install as install_workspaces
install_workspaces(app,auth,store,actor,session,smtp_send)
from issue_imports import install as install_issue_imports
install_issue_imports(app,auth,store,actor)
def routes():
 p=ROOT/'frontend/routes.json';return json.loads(p.read_text()) if p.exists() else {}
@app.get('/external')
def external(target:str=''):
 try:url=base64.urlsafe_b64decode(target+'='*(-len(target)%4)).decode()
 except Exception:url=''
 return HTMLResponse('<!doctype html><html><head><title>Linear · External link</title><link rel="stylesheet" href="/static/local.css"></head><body class="local-auth"><main class="auth-box"><a href="/">Linear</a><h1>External link</h1><p>This link leaves the local Linear workspace.</p><input aria-label="Original destination" readonly value="'+html.escape(url,quote=True)+'"><button data-copy-target>Copy link</button><a href="/">Back to Linear</a></main><script src="/static/local.js" defer></script></body></html>')
@app.get('/{path:path}')
def page(path:str,request:Request):
 route='/'+path.rstrip('/');route='/' if route=='/' else route;token,s=session(request);private=route.startswith('/qqq153')
 if route=='/join':
  if not s or not s['authenticated']:return RedirectResponse('/login?redirectTo=/join',303)
  content=(ROOT/'static/workspaces/create.html').read_text().replace('demo@linear.offline.invalid',html.escape(s['account']['email_normalized'],quote=True)).replace('Offline Demo',html.escape(s['account']['display_name'],quote=True))
  return HTMLResponse(content)
 if private and (not s or not s['authenticated']):return RedirectResponse('/login?redirectTo='+quote(route,safe=''),303)
 if route=='/qqq153/settings/new-team':return HTMLResponse((ROOT/'static/workspaces/teams.html').read_text())
 if route=='/qqq153/settings/import-export/migration-assistant' and request.query_params.get('service')=='linearV2':return HTMLResponse((ROOT/'static/workspaces/import.html').read_text())
 if route in ('/','/login','/signup') and s and s['authenticated']:return RedirectResponse('/qqq153/team/QQQ/active',303)
 if route=='/qqq153':return RedirectResponse('/qqq153/team/QQQ/active',303)
 if route.startswith('/settings/') or route in ['/agent','/my-issues/subscribed','/enable-reviews','/reset']:
  target=routes().get(route,{}).get('redirect') or ('/qqq153'+route if route!='/reset' else '/login')
  return RedirectResponse(target if s and s['authenticated'] else '/login?redirectTo='+quote(target,safe=''),303)
 if route=='/new'or route.startswith('/team/')and route.endswith('/new'):
  allowed={'title','description','status','priority','assignee','label','labels','project','template','links'};params={key:value for key,value in request.query_params.items()if key in allowed};target='/qqq153/team/QQQ/active?'+urlencode({'new':'1',**params})
  return RedirectResponse(target if s and s['authenticated']else'/login?redirectTo='+quote(target,safe=''),303)
 if route.startswith('/qqq153/issue/'):
  identity=route.split('/issue/',1)[1].split('/')[0];a,w=actor(request)
  if not store.get(w['id'],'issues',identity):return HTMLResponse(auth_page('Issue not found','This issue does not exist in your workspace.'),404)
 if private and re.fullmatch(r'/qqq153/document/[^/]+',route):
  document_id=route.split('/document/',1)[1].split('/')[0];a,w=actor(request)
  if not store.get(w['id'],'documents',document_id):return HTMLResponse(auth_page('Document not found','This document does not exist in your workspace.'),404)
  content=(ROOT/'static/document-editor/page.html').read_text().replace('demo@linear.offline.invalid',html.escape(s['account']['email_normalized'],quote=True)).replace('Offline Demo',html.escape(s['account']['display_name'],quote=True))
  return HTMLResponse(content)
 recurring_match=re.fullmatch(r'/qqq153/settings/teams/QQQ/recurring-issues(?:/(new|[a-zA-Z0-9_-]+))?',route)
 if recurring_match:
  a,w=actor(request);key=recurring_match[1]
  if key and key!='new'and not store.get(w['id'],'recurring-issues',key):return HTMLResponse(auth_page('Recurring issue not found','This schedule does not exist in your workspace.'),404)
  content=(ROOT/'static/recurring-issues'/('editor.html'if key else'list.html')).read_text()
  return HTMLResponse(content.replace('demo@linear.offline.invalid',html.escape(a['email_normalized'],quote=True)).replace('Offline Demo',html.escape(a['display_name'],quote=True)))
 issue_template_match=re.fullmatch(r'/qqq153/settings/(teams/QQQ/)?templates/issue/(new|[a-zA-Z0-9_-]+)(/form)?',route)
 if issue_template_match:
  a,w=actor(request);key=issue_template_match[2]
  if key!='new':
   template=store.get(w['id'],'issue-templates',key)
   if not template or bool(template.get('scope_team'))!=bool(issue_template_match[1]):return HTMLResponse(auth_page('Template not found','This template does not exist in your workspace.'),404)
  content=(ROOT/'static/issue-templates'/('form.html'if issue_template_match[3]else'team.html'if issue_template_match[1]else'workspace.html')).read_text()
  return HTMLResponse(content.replace('demo@linear.offline.invalid',html.escape(a['email_normalized'],quote=True)).replace('Offline Demo',html.escape(a['display_name'],quote=True)))
 template_match=re.fullmatch(r'/qqq153/settings/(teams/QQQ/)?templates/document/(new|[a-zA-Z0-9_-]+)',route)
 if template_match:
  a,w=actor(request)
  if template_match[2]=='new' and request.query_params.get('copy') and not store.get(w['id'],'document-templates',request.query_params['copy']):raise HTTPException(404,'Template not found.')
  if template_match[2]!='new':
   template=store.get(w['id'],'document-templates',template_match[2])
   if not template or bool(template.get('team'))!=bool(template_match[1]):return HTMLResponse(auth_page('Template not found','This template does not exist in your workspace.'),404)
  content=(ROOT/'static/document-templates'/('team.html' if template_match[1] else 'workspace.html')).read_text()
  content=content.replace('demo@linear.offline.invalid',html.escape(a['email_normalized'],quote=True)).replace('Offline Demo',html.escape(a['display_name'],quote=True))
  return HTMLResponse(content)
 project_match=re.fullmatch(r'/qqq153/project/([a-zA-Z0-9_-]+)(?:/(overview|activity|issues))?',route)
 if project_match:
  a,w=actor(request);project=store.get(w['id'],'projects',project_match[1])
  if not project:return HTMLResponse(auth_page('Project not found','This project does not exist in your workspace.'),404)
  tab=project_match[2] or 'overview'
  content=(ROOT/'static/project-detail'/(tab+'-page.html')).read_text().replace('{{PROJECT_TITLE}}',html.escape(project['title'],quote=True)).replace('{{PROJECT_ID}}',html.escape(project['id'],quote=True))
  content=content.replace('<body ', '<body data-project-id="'+html.escape(project['id'],quote=True)+'" data-project-tab="'+tab+'" ',1)
  content=content.replace('demo@linear.offline.invalid',html.escape(a['email_normalized'],quote=True)).replace('Offline Demo',html.escape(a['display_name'],quote=True))
  return HTMLResponse(content)
 if route.startswith('/qqq153/project-label/'):
  a,w=actor(request);name=path.split('/project-label/',1)[1].lower();labels=store.list(w['id'],'project-labels');label=next((item for item in labels if item['title'].lower()==name),None)
  if not label:return HTMLResponse(auth_page('Project label not found','This label does not exist in your workspace.'),404)
  content=(ROOT/'static/project-label-page/page.html').read_text().replace('{{PROJECT_LABEL_TITLE}}',html.escape(label['title'],quote=True))
  content=content.replace('<body ', '<body data-project-label-id="'+html.escape(label['id'],quote=True)+'" ',1)
  content=content.replace('demo@linear.offline.invalid',html.escape(a['email_normalized'],quote=True)).replace('Offline Demo',html.escape(a['display_name'],quote=True))
  return HTMLResponse(content)
 allroutes=routes();entry=allroutes.get(route)
 if not entry and re.fullmatch(r'/qqq153/team/QQQ/view/views?_[a-zA-Z0-9]+(?:/edit)?',route):
  a,w=actor(request)
  view=store.get(w['id'],'views',route.split('/view/',1)[1].split('/')[0])
  if not view:return HTMLResponse(auth_page('View not found','This view does not exist in your workspace.'),404)
  content=(ROOT/'static/view-detail'/('edit.html' if route.endswith('/edit') else 'page.html')).read_text().replace('{{VIEW_TITLE}}',html.escape(view['title'],quote=True)).replace('{{VIEW_DESCRIPTION}}',html.escape(view.get('description',''),quote=True)).replace('{{VIEW_ID}}',html.escape(view['id'],quote=True))
  content=content.replace('<body ','<body data-view-id="'+html.escape(view['id'],quote=True)+'" ',1)
  content=content.replace('demo@linear.offline.invalid',html.escape(a['email_normalized'],quote=True)).replace('Offline Demo',html.escape(a['display_name'],quote=True))
  return HTMLResponse(content)
 if not entry and route=='/homepage':entry=allroutes.get('/')
 if not entry and re.search(r'/issue/[A-Z][A-Z0-9]*-\d+',route):
  issue_id=route.split('/issue/',1)[1].split('/')[0]
  entry=next((v for k,v in allroutes.items() if '/issue/'+issue_id+'/' in k),None) or next((v for k,v in allroutes.items() if '/issue/QQQ-2/' in k),None)
 if entry and entry.get('redirect'):return RedirectResponse(entry['redirect'],303)
 if entry:
  content=(ROOT/'frontend/pages'/entry['file']).read_text()
  if private and s:
   content=content.replace('demo@linear.offline.invalid',html.escape(s['account']['email_normalized'],quote=True)).replace('Offline Demo',html.escape(s['account']['display_name'],quote=True))
  return HTMLResponse(content)
 boundary_file=ROOT/'frontend/boundaries.json'
 b=json.loads(boundary_file.read_text()).get(route) if boundary_file.exists() else None
 if b:
  return HTMLResponse('<!doctype html><html><head><title>Linear · '+html.escape(b.get('text',route)[:80])+'</title><link rel="stylesheet" href="/static/local.css"></head><body data-boundary-page><header><a href="/">Linear</a><a href="/login">Log in</a></header><main class="boundary"><p>'+html.escape(b['parent'])+'</p><h1>'+html.escape(b.get('text',route))+'</h1><p>'+html.escape(route)+'</p><p>This collection includes full details for its first five items. This item is outside that captured detail range.</p><a href="'+html.escape(b['parent'],quote=True)+'">Back to collection</a></main><footer><a href="/">Linear</a></footer></body></html>')
 return HTMLResponse(auth_page('This page couldn’t load','Reload to try again, or go back.'),404)
