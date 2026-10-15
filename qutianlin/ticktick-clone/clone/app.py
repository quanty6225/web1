"""TickTick local application: source UI, isolated accounts, SQLite and loopback SMTP."""
from __future__ import annotations
import os,json,re,time,secrets,hashlib,sqlite3,smtplib,html as H,copy
from pathlib import Path
from email.message import EmailMessage
from urllib.parse import quote,urlsplit
from fastapi import FastAPI,Request,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,FileResponse,Response
from collaboration_local import SCHEMA as SHARE_SCHEMA,overlay,split_and_save_shared
from domain_api import handle as domain_handle, UNHANDLED
from websitebench.site_backend import SiteBackend
from websitebench.local_clone_auth import LocalAuthStore
from websitebench.local_clone_auth.store import _hash_secret,_verification_code,_recipient_digest,AuthError,AuthRejected,AuthValidationError,AuthConflict,AuthExpired,AuthRateLimited

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'backend/runtime.json'
DATA=Path(os.environ.get('TICKTICK_DATA_DIR',os.environ.get('WEBSITEBENCH_DATA_DIR',str(ROOT.parent/'data')))).resolve()
backend=SiteBackend.open(json.loads(RUNTIME.read_text()),data_root=DATA);backend.lifecycle.initialize()
WORKER=secrets.token_urlsafe(32)
auth=LocalAuthStore(backend.lifecycle.database_path,site_id='ticktick',mail_mode='SMTP_PENDING',mail_worker_token=WORKER);auth.ensure_schema()
COOKIE='ticktick_local_session';DEMO_PASSWORD='TickTick-Demo-2026!'
auth.seed_account(subject_id='ticktick-demo',email='demo@ticktick.offline.invalid',display_name='TickTick Demo',password='ticktick:'+DEMO_PASSWORD)
PAGES=json.loads((ROOT/'page-routes.json').read_text());ASSETS=json.loads((ROOT/'asset-routes.json').read_text());NEXT=json.loads((ROOT/'next-data.json').read_text())
BOUNDARIES=json.loads((ROOT/'boundaries.json').read_text())
SEED=json.loads((ROOT/'seed/batch.json').read_text());DEFAULTS=json.loads((ROOT/'seed/defaults.json').read_text())
app=FastAPI(docs_url=None,redoc_url=None)
@app.exception_handler(AuthError)
async def auth_error_handler(req,exc):return JSONResponse({'error':str(exc),'errorCode':'invalid_request','errorMessage':str(exc)},400)
with auth.connect() as db:
 db.executescript(SHARE_SCHEMA)
 from giftcards_local import SCHEMA as GIFT_SCHEMA
 db.executescript(GIFT_SCHEMA)
 db.executescript('''CREATE TABLE IF NOT EXISTS ticktick_actor_state(owner TEXT PRIMARY KEY, data TEXT NOT NULL, revision INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS ticktick_mfa_login(session_digest TEXT PRIMARY KEY,account_id TEXT NOT NULL,salt TEXT NOT NULL,code_hash TEXT NOT NULL,expires INTEGER NOT NULL,attempts INTEGER NOT NULL,dest TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS ticktick_unhandled(method TEXT,path TEXT,created_at INTEGER);
 CREATE TABLE IF NOT EXISTS ticktick_mail_links(token_hash TEXT PRIMARY KEY,session_digest TEXT NOT NULL,purpose TEXT NOT NULL,code_hash TEXT NOT NULL,expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);
 ''')
def password(p):
 if not isinstance(p,str) or not 6<=len(p)<=64 or not p.strip():raise AuthValidationError('Password must contain 6-64 characters')
 return 'ticktick:'+p
def token(req):return req.cookies.get(COOKIE)
def account(req):
 s=auth.resolve_session(token(req))
 if s and s['authenticated']:return s['account']
 bearer=req.headers.get('authorization','').removeprefix('Bearer ')
 if bearer.startswith('tt_local_'):
  with auth.connect() as db:
   for row in db.execute('SELECT owner,data FROM ticktick_actor_state'):
    if any(secrets.compare_digest(bearer,k['token']) for k in json.loads(row['data']).get('apiKeys',{}).values()):
     a=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(row['owner'],)).fetchone();return dict(a) if a else None
 return None
def member(req):
 a=account(req)
 if not a:raise HTTPException(401,'Please sign in')
 return a
def actorid(a):return 100000000+int(hashlib.sha256(a['account_id'].encode()).hexdigest()[:7],16)%800000000
def cookie(response,t):
 response.set_cookie(COOKIE,t,max_age=30*86400,httponly=True,samesite='lax',secure=os.environ.get('CLONE_TLS')=='1',path='/');return response
def clean_dest(s):return s if isinstance(s,str) and s.startswith('/') and not s.startswith('//') and '\\' not in s else '/webapp/'
def state(db,a):
 owner=a['account_id'];row=db.execute('SELECT data FROM ticktick_actor_state WHERE owner=?',(owner,)).fetchone()
 if row:
  data=json.loads(row[0])
  if data.get('seed_order_version',0)<1:
   # Repair only the exact original seed signature. User-reordered task lists
   # retain their ordering; newly created actors already receive version 1.
   original={t['id']:t for t in SEED['syncTaskBean']['update']}
   subscription='1e7a2f5d58060c80e83f1230'
   legacy={ident:t['sortOrder'] for ident,t in original.items()}
   legacy[subscription]=original['4f159184d1a37afcd31edf71']['sortOrder']
   if all(data.get('tasks',{}).get(ident,{}).get('sortOrder')==order and data['tasks'][ident].get('title')==original[ident]['title'] for ident,order in legacy.items()):
    data['tasks'][subscription]['sortOrder']=original[subscription]['sortOrder']
   data['seed_order_version']=1;save(db,a,data)
  return overlay(db,a,data)
 uid=actorid(a);seed=copy.deepcopy(SEED)
 for t in seed['syncTaskBean']['update']:t['creator']=uid
 data={'seed_order_version':1,'tasks':{t['id']:t for t in seed['syncTaskBean']['update']},'projects':{p['id']:p for p in seed['projectProfiles']},'columns':{},'tags':{},'filters':{},'projectGroups':{},'prefs':copy.deepcopy(DEFAULTS),'habits':{},'habitRecords':{},'pomodoros':{},'timings':{},'comments':{},'countdowns':{}}
 col=DEFAULTS.get('/api/v2/column',{})
 for item in col.get('update',[]) if isinstance(col,dict) else col:data['columns'][item['id']]=item
 save(db,a,data);return overlay(db,a,data)
def save(db,a,data):
 data=split_and_save_shared(db,a,data)
 db.execute('INSERT INTO ticktick_actor_state VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET data=excluded.data,revision=excluded.revision',(a['account_id'],json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
def profile(a):
 return {'username':a['email_normalized'],'email':a['email_normalized'],'name':a['display_name'],'displayName':a['display_name'],'givenName':'','familyName':'','picture':'','locale':'en_US','userCode':hashlib.sha256(a['account_id'].encode()).hexdigest()[:32],'verifiedEmail':bool(a['email_verified']),'fakedEmail':False,'filledPassword':True,'phone':'','siteDomain':'local','externalId':'','link':'','gender':'','etimestamp':int(time.time()*1000)}
def userstatus(a):
 with auth.connect() as db:
  row=db.execute('SELECT data FROM ticktick_actor_state WHERE owner=?',(a['account_id'],)).fetchone();subscription=json.loads(row[0]).get('subscription',{}) if row else {}
 pro=subscription.get('ends',0)>time.time()
 return {'userId':actorid(a),'userCode':profile(a)['userCode'],'username':a['email_normalized'],'inboxId':'inbox'+str(actorid(a)),'pro':pro,'ds':False,'teamPro':False,'teamUser':False,'activeTeamUser':False,'freeTrial':False,'needSubscribe':not subscription.get('autoRenew',False),'proEndDate':__import__('datetime').datetime.fromtimestamp(subscription['ends'],__import__('datetime').timezone.utc).isoformat() if pro else '','timeStamp':int(time.time()*1000),'registerDate':'2026-10-13T00:00:00.000+0000'}
@app.middleware('http')
async def policy(req,call_next):
 if req.method not in ['GET','HEAD','OPTIONS']:
  origin=req.headers.get('origin')
  if origin and urlsplit(origin).netloc!=req.url.netloc:return JSONResponse({'error':'Invalid origin'},403)
 response=await call_next(req)
 response.headers['Cache-Control']='no-store' if not req.url.path.startswith(('/static/','/_next/static/','/sites/','/web/static/')) else 'public, max-age=3600'
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers.setdefault('Content-Security-Policy',"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws:; frame-src 'self'; media-src 'self' data: blob:; font-src 'self' data:; form-action 'self'; object-src 'none'")
 return response
@app.websocket('/web')
async def socket_endpoint(ws:WebSocket):
 if not account(ws):
  await ws.close(code=1008);return
 await ws.accept()
 try:
  while True:
   msg=await ws.receive_text()
   if msg=='ping':await ws.send_text('pong')
 except WebSocketDisconnect:pass
@app.post('/datacollect/pub/v1/ab/group')
@app.post('/datacollect/event/hc/push')
@app.post('/datacollect/event/push')
def telemetry():return {}
@app.get('/service-worker.js')
def service_worker():return Response("self.addEventListener('install',()=>self.skipWaiting());",media_type='application/javascript')
@app.get('/healthz')
def health():return {'ok':True,'site_id':'ticktick'}
@app.get('/local/session')
def session(req:Request):
 a=member(req);return {'authenticated':True,'email':a['email_normalized']}

def send_challenge(t,purpose,base):
 claim=auth.claim_pending_mail_for_session(t,purpose=purpose,worker_token=WORKER)
 if claim is None:return
 code=claim['verification_code'];link=base+('/signup/verify' if purpose=='registration' else '/sign/resetPassword')+'?code='+quote(code)+'&flow='+quote(t)
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@ticktick.clone.test');msg['To']=claim['recipient'];msg['Subject']='Verify your TickTick account' if purpose=='registration' else 'Reset your TickTick password'
 msg.set_content(f'TickTick\n\nYour verification code is {code}.\n\n{link}\n\nThis code expires in 10 minutes and can only be used once.\n')
 auth.reserve_mail_target_request(claim['mail_id'],claim['claim_token'],worker_token=WORKER)
 try:
  host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
  if host not in ['127.0.0.1','localhost','::1']:raise ValueError('SMTP must be local')
  with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=10) as smtp:smtp.send_message(msg)
 except Exception:
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,target_request_count=1,accepted_request_count=0,error='network',worker_token=WORKER)
  raise HTTPException(503,'Email could not be sent. Please try again.')
 auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,target_request_count=1,accepted_request_count=1,worker_token=WORKER)

def resend_challenge(t,purpose):
 if purpose not in ['registration','password-reset']:raise AuthValidationError('Invalid purpose')
 table,ident=('local_auth_registration_flows','pending_id') if purpose=='registration' else ('local_auth_password_reset_flows','reset_id')
 now=auth._now();code=_verification_code();salt,digest=_hash_secret(code)
 with auth.connect() as db,auth._transaction(db):
  session=auth._session_row(db,t)
  if not session:raise AuthRejected('Session expired')
  sd=session['session_digest'];row=db.execute('SELECT * FROM '+table+' WHERE session_digest=?',(sd,)).fetchone()
  if not row or row['verified_at']:raise AuthRejected('No pending verification')
  if purpose=='registration':recipient=row['email_normalized']
  else:
   a=db.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(row['account_id'],)).fetchone();recipient=a[0] if a else None
  auth._rate_limit_unlocked(db,purpose=purpose,scopes=[('session',sd)]+([('recipient',_recipient_digest(recipient))] if recipient else []),now=now)
  db.execute('UPDATE '+table+' SET code_salt=?,code_hash=?,expires_at=?,attempts=0,updated_at=? WHERE session_digest=?',(salt,digest,now+600,now,sd))
  db.execute('DELETE FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?',(purpose,row[ident]))
  if recipient:auth._insert_mail_unlocked(db,purpose=purpose,flow_id=row[ident],session_digest=sd,recipient=recipient,now=now)
 if recipient:auth._remember_mail_code(purpose,row[ident],code)

@app.post('/local/auth/{action}')
async def auth_action(action:str,req:Request):
 if 'application/x-www-form-urlencoded' in req.headers.get('content-type',''):
  from urllib.parse import parse_qsl
  body=dict(parse_qsl((await req.body()).decode()))
 else:body=await req.json()
 t,s=auth.ensure_session(token(req));base=str(req.base_url).rstrip('/')
 try:
  if action=='signin':
   r=auth.sign_in(t,email=body.get('email',''),password=password(body.get('password','')));t=r['session_token'];result={'redirect':clean_dest(body.get('dest'))}
   with auth.connect() as db:requires_mfa=bool(state(db,r['account']).get('mfa',{}).get('enabled'))
   if requires_mfa:
    auth.sign_out(t)
    from mfa_login import start
    with auth.connect() as db:t=start(auth,r['account'],state(db,r['account']),t,db,result['redirect'])
    result={'redirect':'/signin/mfa'}
  elif action=='mfa':
   from mfa_login import complete
   with auth.connect() as db:t,dest=complete(auth,t,body.get('code',''),db,state,save)
   result={'redirect':clean_dest(dest)}
  elif action=='signup':
   email=body.get('email','');auth.start_registration(t,email=email,display_name=email.split('@')[0],password=password(body.get('password','')),restart_invalid_flow=True);send_challenge(t,'registration',base);result={'redirect':'/signup/verify'}
  elif action=='verify':
   auth.verify_registration_code(t,body.get('code',''));r=auth.complete_registration(t);t=r['session_token'];auth.sign_out(t);t=auth.create_anonymous_session();result={'redirect':'/signin?verified=1'}
  elif action=='recover':
   auth.start_password_reset(t,email=body.get('email',''),restart_invalid_flow=True);send_challenge(t,'password-reset',base);result={'redirect':'/sign/resetPassword'}
  elif action=='reset':
   auth.verify_password_reset_code(t,body.get('code',''));t=auth.complete_password_reset(t,new_password=password(body.get('password','')));result={'redirect':'/signin?reset=1'}
  elif action=='resend':
   purpose=body.get('purpose','registration')
   resend_challenge(t,purpose)
   send_challenge(t,purpose,base);result={'sent':True}
  else:raise HTTPException(404)
  return cookie(JSONResponse(result),t)
 except HTTPException as e:
  return cookie(JSONResponse({'error':e.detail},e.status_code),t)
 except AuthError as e:
  return cookie(JSONResponse({'error':str(e)},400),t)

@app.api_route('/signout',methods=['GET','POST'])
@app.api_route('/logout',methods=['GET','POST'])
def logout(req:Request):
 auth.sign_out(token(req));r=RedirectResponse('/signin',303);r.delete_cookie(COOKIE);return r

@app.get('/webapp')
@app.get('/webapp/')
def webapp(req:Request):
 a=account(req)
 if not a:return RedirectResponse('/signin?dest='+quote('/webapp/'),303)
 st=userstatus(a)
 config={'user':{'isDS':False,'isGFS':False,'isTU':False,'isGP':st['pro'],'inboxId':st['inboxId'],'username':a['email_normalized'],'userCode':st['userCode']},'end_date':'','no_grace_date':'','errorType':None,'language':'en_US','domain':'ticktick.com','cdn':req.url.netloc+'/web','api_domain':req.url.netloc,'ex_api_domain':req.url.netloc,'protocol':'http://','productName':'TickTick','isCnSites':False,'is_product_mode':True,'is_package_mode':False}
 return HTMLResponse((ROOT/'pages/app.html').read_text().replace('__APPEST__',json.dumps(config).replace('<','\\u003c')))

@app.api_route('/local/invitations/{ident}',methods=['GET','POST'])
async def local_invitation(ident:str,req:Request):
 from collaboration_local import invitation
 a=account(req)
 if not a:return RedirectResponse('/signin?dest='+quote(req.url.path),303)
 return invitation(ident,req,a,auth,req.method,await req.json() if req.method=='POST' else {},AUTH_STYLE)

@app.post('/payment')
async def paypal_checkout(req:Request):
 from payments_local import create
 from urllib.parse import parse_qs
 fields=parse_qs((await req.body()).decode());frequency=fields.get('freq',['Year'])[0]
 result=create(req,member(req),auth,backend,state,save,frequency)
 return RedirectResponse(result['url'],303)

@app.get('/local/checkout/{ident}')
def checkout_page(ident:str,req:Request):
 from payments_local import checkout
 return checkout(ident,req,member(req),auth,state,AUTH_STYLE)
@app.post('/local/checkout/{ident}')
async def checkout_submit(ident:str,req:Request):
 from payments_local import pay
 return pay(ident,await req.json(),member(req),auth,backend,state,save)

@app.api_route('/dida-help/api/{version}/{path:path}',methods=['GET','POST','PUT','DELETE'])
@app.api_route('/api/{version}/{path:path}',methods=['GET','POST','PUT','DELETE','PATCH'])
@app.api_route('/pub/api/{version}/{path:path}',methods=['GET','POST','PUT','DELETE'])
async def api(version:str,path:str,req:Request):
 if path in ['user/signout','user/logout']:return logout(req)
 if path=='user/signon':return await auth_action('signin',req)
 if path.startswith('article/fav/') and req.method=='GET' and not account(req):return {'isFaved':False,'isSaded':False}
 a=member(req);uid=actorid(a);inbox='inbox'+str(uid);method=req.method
 body={}
 if method not in ['GET','HEAD']:
  try:body=await req.json()
  except Exception:
   body={}
   if (path.startswith('import/') or path.startswith('attachment/upload/')) and 'multipart/form-data' in req.headers.get('content-type',''):
    from email.parser import BytesParser
    from email.policy import default
    payload=await req.body()
    if len(payload)>20*1024*1024:raise HTTPException(413,'Backup is too large')
    message=BytesParser(policy=default).parsebytes(('Content-Type: '+req.headers['content-type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+payload)
    part=next((p for p in message.iter_parts() if p.get_filename()),None)
    if part is None:raise HTTPException(400,'Choose a file')
    payload_bytes=part.get_payload(decode=True)
    raw=payload_bytes.decode('utf-8-sig') if path.startswith('import/') else ''
    if path.startswith('attachment/upload/'):
     body={'_file_bytes':payload_bytes,'_filename':part.get_filename(),'_mime':part.get_content_type()}
    elif path=='import/restore':
     try:body=json.loads(raw)
     except ValueError:raise HTTPException(400,'Invalid JSON backup')
    else:body={'_file_text':raw,'_filename':part.get_filename()}
 full=req.url.path
 if path in ['payment/gc/stripe','payment/gc']:
  from giftcards_local import validate
  from payments_local import create
  return create(req,a,auth,backend,state,save,frequency='Year',gift=validate(body,a))
 if path=='subscribe/stripe/create-checkout-session':
  from payments_local import create
  return create(req,a,auth,backend,state,save)
 with auth.connect() as db:
  d=state(db,a)
  template_match=re.fullmatch(r'templates/project/([a-f0-9]{24})/apply',path)
  if template_match and method=='POST':
   from templates_local import apply
   result=apply(template_match[1],d,uid);save(db,a,d);return result
  from giftcards_local import handle as gift_handle
  gift_result=gift_handle(path,method,body,req,a,d,db,save,actorid)
  if gift_result is not None:return gift_result
  from collaboration_local import handle as share_handle
  shared=share_handle(path,method,body,req,a,d,db,save,actorid)
  if shared is not None:return shared
  from attachments_local import handle as attachment_handle
  attachment_result=attachment_handle(path,method,body,req,a,d,db,save)
  if attachment_result is not None:return attachment_result
  from calendar_local import handle as calendar_handle
  calendar_result=calendar_handle(path,method,body,req,a,d,db,save,uid)
  if calendar_result is not None:return calendar_result
  from data_ops import handle as data_handle
  operation=data_handle(path,method,body,req,a,d,db,save,uid,SEED)
  if operation is not None:return operation
  result=domain_handle(path,method,body,req,a,d,db,auth,save,profile,actorid,password)
  if result is not UNHANDLED:return result
  for pref_path in ['/api/v2/user/preferences/settings','/api/v2/user/preferences/pomodoro']:
   if pref_path in d['prefs']:d['prefs'][pref_path]['id']=uid
  if path.startswith('article/fav/'):
   votes=d.setdefault('articleVotes',{});key=path.rsplit('/',1)[-1]
   if method!='GET':votes[key]=body.get('action') if body.get('status') else None;save(db,a,d)
   return {'isFaved':votes.get(key)=='like','isSaded':votes.get(key)=='sad'}
  if path=='projects':return list(d['projects'].values())
  if path=='project/all/closed':return [x for x in d['projects'].values() if x.get('closed')]
  if path=='projectTemplates/all':return list(d.setdefault('templates',{}).values())
  if path=='refer/code':return {'id':hashlib.sha256(a['account_id'].encode()).hexdigest()[:24],'name':a['display_name'],'code':hashlib.sha256(('refer'+a['account_id']).encode()).hexdigest()[:10],'remark':'','type':0,'creator':uid}
  if path in ['refer/pro','refer/free']:return []
  if path in ['ticket','tickets']:
   tickets=d.setdefault('tickets',{})
   if method=='GET':return {'total':len(tickets),'tickets':list(tickets.values())}
   if not body.get('description'):raise HTTPException(400,'Description is required')
   ident=secrets.token_hex(12);tickets[ident]={**body,'id':ident,'createdTime':int(time.time()*1000)};save(db,a,d);return tickets[ident]
  if path.startswith('batch/check/'):
   out=copy.deepcopy(SEED);out.update(checkPoint=int(time.time()*1000),inboxId=inbox,projectProfiles=list(d['projects'].values()),tags=list(d['tags'].values()),filters=list(d['filters'].values()),projectGroups=list(d['projectGroups'].values()))
   out['syncTaskBean']={'update':[x for x in d['tasks'].values() if not x.get('deleted') and x.get('status',0)==0],'delete':[],'add':[],'tagUpdate':[],'empty':False};return out
  if path=='app/config':return {'etag':'1a0eabf1005','interval':14400}
  if path=='user/profile':return profile(a)
  if path=='user/status':return userstatus(a)
  if path in ['user/mfa','user/isJustRegistered']:return False
  if path=='userPublicProfiles':
   requested=set(str(x) for x in body[:100]) if isinstance(body,list) else set();result=[]
   for row in db.execute('SELECT * FROM local_auth_accounts'):
    user=dict(row);code=profile(user)['userCode']
    if code in requested or str(actorid(user)) in requested:result.append({'userCode':code if code in requested else str(actorid(user)),'displayName':user['display_name'],'nickname':user['display_name'],'picture':''})
   return result
  if path=='user/userBindingInfo':return {'thirdSiteBinds':list(d.get('providerBindings',{}).values()),'fakedEmail':False,'email':a['email_normalized']}
  if path=='notification/unread':return {'notification':0,'activity':0}
  if path in ['notification','notification/all','activities','calendar/subscription','user/devices','user/apiKeys']:return []
  if path in ['chatmind/bind/check']:return False
  if path=='attachment/isUnderQuota':return True
  if path.startswith('user/preferences/') or (full in DEFAULTS and path!='column'):
   if method=='GET':return d['prefs'].get(full,{})
   old=d['prefs'].get(full,{})
   if isinstance(old,dict) and isinstance(body,dict):old.update(body)
   else:old=body
   d['prefs'][full]=old;save(db,a,d);return old
  if path.startswith('batch/'):
   kind='timing' if path=='batch/pomodoro/timing' else path.split('/')[1];table={'task':'tasks','project':'projects','tag':'tags','filter':'filters','projectGroup':'projectGroups','column':'columns','pomodoro':'pomodoros','pomodoros':'pomodoros','timing':'timings','habit':'habits'}.get(kind)
   if table:
    result={'id2etag':{},'id2error':{}}
    for action in ['add','update','delete']:
     for item in body.get(action,[]):
      ident=item if isinstance(item,str) else item.get('id') or item.get('taskId')
      if not ident:raise HTTPException(400,'Missing id')
      if action=='delete':
       if ident not in d[table]:raise HTTPException(404,'Not found')
       if table=='tasks':d[table][ident]['deleted']=1
       else:d[table].pop(ident)
      else:
       if action=='update' and ident not in d[table]:raise HTTPException(404,'Not found')
       item={**d[table].get(ident,{}),**item,'etag':secrets.token_hex(8)}
       if table=='tasks':
        if item.get('projectId') not in [inbox,'inbox','inbox-local',*d['projects']]:raise HTTPException(403,'Unknown list')
        item['creator']=uid;item['kind']=item.get('kind') or 'TEXT';item.setdefault('taskType',1);item.setdefault('isAllDay',not item.get('startDate'));item.setdefault('deleted',0);item.setdefault('reminder','')
       d[table][ident]=item;result['id2etag'][ident]=item['etag']
    save(db,a,d);return result
  if path.startswith('project/') and ('completed' in path.lower() or 'trash' in path.lower() or 'deleted' in path.lower()):
   pid=path.split('/')[1];trash='trash' in path.lower() or 'deleted' in path.lower()
   tasks=[t for t in d['tasks'].values() if (pid=='all' or t.get('projectId')==pid) and (t.get('deleted',0)>0 if trash else t.get('status',0)>0 and not t.get('deleted'))]
   return {'tasks':tasks,'next':-1} if path.endswith('/page') else tasks
  if path in ['project/all/trash','task/trash','trash']:return [t for t in d['tasks'].values() if t.get('deleted')]
  if path=='column' and method=='GET':return {'update':list(d['columns'].values())}
  if path.startswith('column/project/'):
   return [c for c in d['columns'].values() if c.get('projectId')==path.split('/')[-1]]
  if path.startswith('pomodoros/statistics/'):
   from datetime import datetime,timezone
   def stamp(value):
    try:return datetime.fromisoformat(value.replace('Z','+00:00'))
    except (TypeError,ValueError,AttributeError):return None
   def minutes(record):
    start,end=stamp(record.get('startTime')),stamp(record.get('endTime'))
    return max(0,round(((end-start).total_seconds()-record.get('pauseDuration',0))/60)) if start and end else record.get('duration',0)
   records=list(d['pomodoros'].values());all_focus=records+list(d['timings'].values());today=datetime.now(timezone.utc).date()
   def is_today(record):
    value=stamp(record.get('startTime'));return value and value.date()==today
   return {'todayPomoCount':sum(bool(is_today(x)) for x in records),'totalPomoCount':len(records),'todayPomoDuration':sum(minutes(x) for x in all_focus if is_today(x)),'totalPomoDuration':sum(minutes(x) for x in all_focus)}
  if path.startswith('pomodoro/record/'):return {'checkPoint':int(time.time()*1000),'pomodoroRecords':list(d['pomodoros'].values())}
  if path in ['pomodoros','pomodoros/timeline','pomodoros/timing','timer']:return list(d['pomodoros' if path=='pomodoros' else 'timings'].values())
  parts=path.split('/');table={'project':'projects','task':'tasks','tag':'tags','filter':'filters','column':'columns','habit':'habits','habits':'habits','countdown':'countdowns'}.get(parts[0])
  if table and len(parts)<=2:
   ident=parts[1] if len(parts)>1 else None
   if method=='GET':
    if ident and ident not in d[table]:raise HTTPException(404,'Not found')
    return d[table][ident] if ident else list(d[table].values())
   if method=='DELETE':
    if ident not in d[table]:raise HTTPException(404,'Not found')
    d[table].pop(ident);save(db,a,d);return {}
   ident=ident or body.get('id') or secrets.token_hex(12)
   if len(parts)>1 and ident not in d[table]:raise HTTPException(404,'Not found')
   item={**d[table].get(ident,{}),**body,'id':ident,'etag':secrets.token_hex(8)}
   if table=='tasks':
    if item.get('projectId') not in [inbox,'inbox','inbox-local',*d['projects']]:raise HTTPException(403,'Unknown list')
    item['creator']=uid
   if table=='projects':item={**SEED['projectProfiles'][0],**item,'isOwner':True,'userCount':1,'closed':False}
   d[table][ident]=item;save(db,a,d);return item
  if path.startswith('push/') or path in ['push','user/push','analytics','track']:return {}
  db.execute('INSERT INTO ticktick_unhandled VALUES(?,?,?)',(method,full,int(time.time())))
  db.commit()
  raise HTTPException(501,'Local endpoint is not implemented: '+full)

AUTH_STYLE='''body{font-family:Arial,sans-serif;margin:0;color:#333;background:#fff}a{color:#4772fa;text-decoration:none}header{padding:30px 5%;display:flex;align-items:center;justify-content:space-between}header img{width:126px}header{gap:20px}header span{max-width:55%;text-align:right}main{width:360px;max-width:85vw;margin:78px auto}h1{font-size:30px;margin-bottom:36px}input{box-sizing:border-box;width:100%;height:48px;border:1px solid #ddd;border-radius:4px;padding:12px;margin-bottom:18px;font-size:15px}button{font-size:15px;cursor:pointer;border-radius:4px;border:1px solid #ddd;background:white;padding:12px;width:100%;margin-bottom:14px}.primary{background:#4772fa;color:white;border:0;height:48px}p{font-size:13px;line-height:1.7;color:#777}.right{text-align:right}.error{color:#e34d59;white-space:pre-line;font-size:13px;margin:0 0 14px}.providers{border-top:1px solid #eee;margin-top:32px;padding-top:25px}.success{color:#38a36b}'''
def authpage(mode,req):
 signup=mode=='signup';signin=mode=='signin';recover=mode=='recover';verify=mode=='verify';reset=mode=='reset';mfa=mode=='mfa'
 title={'signup':'Sign Up','signin':'Sign In','recover':'Reset Password','verify':'Verify Email','reset':'Reset Password','mfa':'2-Step Verification'}[mode]
 fields=''
 if signup or signin or recover:fields+='<input name="email" aria-label="Email" placeholder="Email" autocomplete="email">'
 if verify or reset or mfa:fields+='<input name="code" aria-label="Verification Code" placeholder="Verification Code" autocomplete="one-time-code" value="'+H.escape(req.query_params.get('code',''))+'">'
 if signup or signin or reset:fields+='<input name="password" type="password" aria-label="Password" placeholder="'+('Password: 6-64 characters' if signup else 'New password' if reset else 'Password')+'" autocomplete="'+('current-password' if signin else 'new-password')+'">'
 extras='<div class="right"><a href="/sign/requestRestPassword">Forgot Password</a></div>' if signin else '<p>By signing up, you agree to our <a href="/about/tos">Terms of Service</a> and <a href="/about/privacy">Privacy Policy</a>.</p>' if signup else ''
 if signin or signup:extras+='<div class="providers"><button onclick="location.href=\'/local/provider/google\'">Continue with Google</button><button onclick="location.href=\'/local/provider/apple\'">Continue with Apple</button><details><summary>More</summary><button onclick="location.href=\'/local/provider/facebook\'">Continue with Facebook</button></details></div>'
 if verify or reset:extras+='<p>Check your email for your verification code.</p><button id="resend">Resend</button>'
 else:extras+='<p><a href="/signin">Back to Sign In</a>　<a href="/signup">Sign Up</a></p>'
 top='Already have an account? <a href="/signin">Sign In</a>' if signup else 'Don\'t have an account? <a href="/signup">Sign Up</a>'
 notice='Your email has been verified.' if 'verified' in req.query_params else 'Your password has been reset.' if 'reset' in req.query_params else ''
 script='''const form=document.querySelector('form'),error=document.querySelector('.error');form.addEventListener('submit',async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(form));data.dest=new URLSearchParams(location.search).get('dest');let errors=[];if('email'in data){if(!data.email)errors.push("Email address can't be empty");else if(!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(data.email))errors.push('Invalid email format')}if('password'in data&&!data.password)errors.push("Password can't be empty");if(errors.length){error.textContent=errors.join('\\n');return}const b=form.querySelector('button');b.disabled=true;try{const r=await fetch('/local/auth/MODE',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();if(!r.ok){error.textContent=d.error||d.detail;return}if('MODE'==='signin'){const templateIntent=sessionStorage.getItem('signTemplateHint')==='true'&&/^\\/templates\\/project\\/[a-f0-9]+\\/apply$/.test(data.dest||'');localStorage.clear();sessionStorage.clear();if(templateIntent)sessionStorage.setItem('signTemplateHint','true')}location.href=d.redirect}catch{error.textContent='Network connection failed. Please try again.'}finally{b.disabled=false}});document.querySelector('#resend')?.addEventListener('click',async()=>{const r=await fetch('/local/auth/resend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purpose:'PURPOSE'})});const d=await r.json();error.textContent=r.ok?'Email sent':d.error||d.detail});'''.replace('MODE',mode).replace('PURPOSE','registration' if verify else 'password-reset')
 return HTMLResponse('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+' - TickTick</title><style>'+AUTH_STYLE+'</style></head><body><header><a href="/"><img src="/sites/res/common/tickLogo.svg" alt="TickTick"></a><span>'+top+'</span></header><main><h1>'+title+'</h1><p class="success">'+notice+'</p><form novalidate>'+fields+'<div class="error" role="alert"></div><button class="primary">'+title+'</button></form>'+extras+'</main><script>'+script+'</script></body></html>')

@app.get('/signin')
@app.get('/signup')
@app.get('/signin/mfa')
@app.get('/signup/verify')
@app.get('/sign/requestRestPassword')
@app.get('/sign/resetPassword')
def auth_routes(req:Request):
 mode={'/signin':'signin','/signin/mfa':'mfa','/signup':'signup','/signup/verify':'verify','/sign/requestRestPassword':'recover','/sign/resetPassword':'reset'}[req.url.path]
 flow=req.query_params.get('flow') if mode in ['verify','reset'] else None
 pending=auth.resolve_session(flow) if flow else None
 t,s=auth.ensure_session(flow if pending and not pending['authenticated'] else token(req));return cookie(authpage(mode,req),t)

@app.get('/local/provider/{provider}')
def provider(provider:str,req:Request):
 if provider not in ['google','apple','facebook']:raise HTTPException(404)
 a=account(req)
 if a:
  return HTMLResponse('<!doctype html><html><head><title>Link '+provider.title()+' - TickTick</title><style>'+AUTH_STYLE+'</style></head><body><header><a href="/webapp/">TickTick</a></header><main><h1>Link '+provider.title()+'</h1><p>Local provider adapter. This creates an association with your current local account; no external identity provider is contacted.</p><p>'+H.escape(a['email_normalized'])+'</p><button class="primary">Link account</button><a href="/webapp/#p/inbox/tasks?modalType=settings&tabs=profile">Cancel</a><p role="alert"></p></main><script>document.querySelector("button").onclick=async()=>{const r=await fetch(location.pathname,{method:"POST"});const d=await r.json();if(r.ok)location.href=d.redirect;else document.querySelector("[role=alert]").textContent=d.detail}</script></body></html>')
 page=authpage('signup',req).body.decode()
 page=page.replace('<h1>Sign Up</h1>','<h1>Continue with '+provider.title()+'</h1><p>Local authentication adapter. Verify your email using the local mailbox to create an independent TickTick account.</p>')
 t,_=auth.ensure_session(token(req));return cookie(HTMLResponse(page),t)

@app.post('/local/provider/{provider}')
def bind_local_provider(provider:str,req:Request):
 if provider not in ['google','apple','facebook']:raise HTTPException(404)
 a=member(req)
 with auth.connect() as db:
  d=state(db,a);d.setdefault('providerBindings',{})[provider]={'siteId':provider,'email':a['email_normalized'],'name':a['display_name'],'localAdapter':True};save(db,a,d)
 return {'redirect':'/webapp/#p/inbox/tasks?modalType=settings&tabs=profile'}

@app.get('/pub/calendar/feeds/{code}/basic.ics')
def public_calendar(code:str):
 from calendar_local import ics
 with auth.connect() as db:
  for row in db.execute('SELECT data FROM ticktick_actor_state'):
   d=json.loads(row[0]);feed=next((x for x in d.get('calendarFeeds',{}).values() if secrets.compare_digest(x['code'],code)),None)
   if feed:
    tasks=[x for x in d['tasks'].values() if (feed['projectId']=='all' or x.get('projectId')==feed['projectId']) and (feed['includeDone'] or not x.get('status'))]
    return Response(ics(tasks),media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="ticktick.ics"'})
 raise HTTPException(404,'Calendar feed was not found or has been revoked')

@app.get('/local/calendar/{provider}')
def calendar_adapter(provider:str,req:Request):
 member(req)
 if provider not in ['google','outlook']:raise HTTPException(404)
 return HTMLResponse('<!doctype html><html><head><title>Import Calendar - TickTick</title><style>'+AUTH_STYLE+'</style></head><body><header><a href="/webapp/">TickTick</a></header><main><h1>Import Calendar</h1><p>This offline adapter imports a calendar file into your local account. It does not connect to '+provider.title()+' or synchronize remote events.</p><form><label>Calendar export (.ics)<input type="file" name="file" accept=".ics,text/calendar" required></label><button class="primary">Import</button><p role="status"></p></form><a href="/webapp/#c/all/calendar/m">Back to calendar</a></main><script>document.querySelector("form").onsubmit=async e=>{e.preventDefault();const r=await fetch("/api/v2/import/ics",{method:"POST",body:new FormData(e.target)});const d=await r.json();document.querySelector("[role=status]").textContent=r.ok?"Imported "+d.imported+" events into your local account.":d.detail;if(r.ok){const a=document.createElement("a");a.href="/webapp/#p/"+d.projectId+"/tasks";a.textContent="Open imported events";e.target.append(a)}};</script></body></html>')

@app.get('/local/apple-auth.js')
def apple_auth_adapter():
 return Response("window.AppleID={auth:{init:function(){},signIn:function(){location.href='/local/provider/apple';return new Promise(function(){})}}};",media_type='application/javascript')

@app.get('/pub/user/avatar/{user_code}/avatar.png')
def default_user_avatar(user_code:str):
 # The legacy gift-card header builds this URL from userCode. Accounts without
 # an uploaded avatar use the same captured default avatar as the main app.
 asset=ASSETS['/d3qg9zffrnl4ph.cloudfront.net/image/avatar.png']
 return FileResponse(ROOT/asset['file'],media_type=asset['type'])

@app.get('/local/stripe.js')
def stripe_stub():
 return Response("window.Stripe=function(){return {redirectToCheckout:function(options){location.href='/local/checkout/'+encodeURIComponent(options.sessionId);return Promise.resolve({})}}};",media_type='application/javascript')

def boundary_page(item):
 return HTMLResponse('<!doctype html><html><head><title>'+H.escape(item['title'])+' - TickTick</title><style>'+AUTH_STYLE+'</style></head><body data-boundary-page><header><a href="/">TickTick</a><nav><a href="/webapp/">Tasks</a> · <a href="/help">Help Center</a></nav></header><main><p>'+H.escape(item['collection'])+'</p><h1>'+H.escape(item['title'])+'</h1><p>Item: '+H.escape(item['id'])+'</p><p>This item is outside the captured detail selection. The original listing is retained; further detail is not included in this offline copy.</p><a href="'+H.escape(item['back'])+'">Back to '+H.escape(item['collection'])+'</a></main><footer><a href="/about">About TickTick</a> · <a href="/privacy">Privacy</a></footer></body></html>')

@app.get('/external')
def external(req:Request):
 target=req.query_params.get('target','');return HTMLResponse('<html><head><title>TickTick</title></head><body><header><a href="/">TickTick</a> · <a href="/webapp/">Tasks</a></header><main><h1>External link</h1><p>This offline copy does not connect to external websites.</p><input aria-label="Original destination" readonly value="'+H.escape(target)+'"><button onclick="navigator.clipboard.writeText(document.querySelector(\'input\').value)">Copy link</button><p><a href="javascript:history.back()">Back</a></p></main><footer>TickTick</footer></body></html>')

@app.api_route('/blog/wp-admin/admin-ajax.php',methods=['GET','POST'])
async def blog_ajax(req:Request):
 from blog_local import ajax
 return await ajax(req)

@app.get('/templates/project/{ident}/apply')
def template_apply_page(ident:str,req:Request):
 from templates_local import TEMPLATES
 if ident not in TEMPLATES:raise HTTPException(404,'Template is not included')
 if not account(req):return RedirectResponse('/signin?dest='+quote(req.url.path,safe=''),303)
 return HTMLResponse('<!doctype html><html><body><p id="status">正在保存到我的清单…</p><script>if(sessionStorage.getItem("signTemplateHint")!=="true"){location.replace("/pub/templates/project/'+ident+'")}else{sessionStorage.removeItem("signTemplateHint");fetch("/api/v2/templates/project/'+ident+'/apply",{method:"POST"}).then(async r=>{let d=await r.json();if(!r.ok)throw Error(d.detail||"保存失败");location.replace("/webapp/#p/"+d.projectId+"/tasks")}).catch(e=>document.getElementById("status").textContent=e.message)}</script></body></html>')

@app.get('/{path:path}')
def page(path:str,req:Request):
 route='/'+path
 blog_aliases=json.loads((ROOT/'blog-aliases.json').read_text())
 if route.rstrip('/') in blog_aliases:return RedirectResponse(blog_aliases[route.rstrip('/')]+('?' +req.url.query if req.url.query else ''),308)
 if route=='/blog/local-ui.js':return FileResponse(ROOT/'blog-ui.js',media_type='application/javascript')
 if route.rstrip('/')=='/blog' and 's' in req.query_params or re.fullmatch(r'/blog/page/\d+/?',route):
  from blog_local import search
  number=re.search(r'/page/(\d+)',route)
  return search(req.query_params.get('s',''),int(number[1]) if number else 1)
 if re.match(r'/20\d\d/\d\d/\d\d/',route):return RedirectResponse('/blog'+route+('?' +req.url.query if req.url.query else ''),308)
 canonical=re.sub(r'/+', '/', route).rstrip('/') or '/'
 suffix=('?'+req.url.query if req.url.query else '')
 if canonical != route and (canonical in PAGES or canonical in BOUNDARIES):return RedirectResponse(canonical+suffix,308)
 if route.startswith('/help/articles/'):
  target=route.removeprefix('/help')
  if target in PAGES or target in BOUNDARIES:return RedirectResponse(target+suffix,308)
 if route.startswith('/articles/') and route not in PAGES and route not in BOUNDARIES:
  ident=route.rsplit('/',1)[-1]
  target=next((p for p in [*PAGES,*BOUNDARIES] if (p=='/resources/article/'+ident or p.startswith('/resources/article/'+ident+'/'))),None)
  if target:return RedirectResponse(target+suffix,308)
 for prefix in ['/external/articles/','/dida-help/external/articles/']:
  if canonical.startswith(prefix):
   target=canonical.replace('/external/articles/','/articles/',1)
   if target in PAGES or target in BOUNDARIES:return RedirectResponse(target,308)
 if route=='/offline.js':return FileResponse(ROOT/'offline.js',media_type='application/javascript')
 if route.startswith('/static/assets/'):
  f=ROOT/'static/assets'/Path(path).name
  if f.is_file():return FileResponse(f,media_type=next((v['type'] for v in ASSETS.values() if v['file'].endswith(f.name)),None))
 if route in ASSETS:
  v=ASSETS[route];return FileResponse(ROOT/v['file'],media_type=v['type'])
 if route.startswith('/_next/data/'):
  key='/'+route.split('/',4)[-1].removesuffix('.json');key='/' if key=='/index' else key
  if key in NEXT:return JSONResponse(NEXT[key])
 aliases={'/about/tos':'/tos','/about/privacy':'/privacy','/about/security':'/security','/about/license/web':'/license/web','/v3/tickets/':'/v3/tickets','/about/upgrade':'/upgrade','/about/download':'/download'}
 if route in aliases:return RedirectResponse(aliases[route]+suffix,308)
 if route in ['/payment','/payment/card','/card','/refer','/v3/tickets']:
  a=account(req)
  if not a and route!='/card':return RedirectResponse('/signin?dest='+quote(route),303)
  src=(ROOT/PAGES[route]).read_text()
  if route=='/payment/card':
   status={'language':'*','name':a['display_name'],'isLogin':True,'username':a['email_normalized'],'userCode':profile(a)['userCode'],'displayName':a['display_name'],'phone':'','verifiedEmail':bool(a['email_verified']),'pro':userstatus(a)['pro'],'teamUser':False,'teamPro':False,'gracePeriod':False,'domain':req.url.netloc,'cdn':req.url.netloc+'/web','productName':'TickTick','isCnSite':False,'api_domain':req.url.netloc,'protocol':req.url.scheme+'://','isProductMode':'false','isPackageMode':'false','avatar':'/d3qg9zffrnl4ph.cloudfront.net/image/avatar.png'}
   src=re.sub(r'window\.SiteStatus\s*=\s*\{[\s\S]*?\};',lambda _: 'window.SiteStatus = '+json.dumps(status).replace('<','\\u003c')+';',src)
  def with_actor(match):
   data=json.loads(match.group(1));props=data['props']['pageProps'];props.update(isLogin=bool(a),userProfile=profile(a) if a else {},userStatus=userstatus(a) if a else {});return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data).replace('<','\\u003c')+'</script>'
  src=re.sub(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]*?)</script>',with_actor,src)
  return HTMLResponse(src.replace('https://js.stripe.com/v3/','/local/stripe.js'))
 if route.startswith('/pub/templates/project/') and route in PAGES:
  a=account(req);src=(ROOT/PAGES[route]).read_text()
  status={'language':'zh_CN','name':a['display_name'] if a else '', 'isLogin':bool(a),'username':a['email_normalized'] if a else '', 'displayName':a['display_name'] if a else '', 'userCode':profile(a)['userCode'] if a else '', 'phone':'','verifiedEmail':bool(a),'pro':False,'teamUser':False,'teamPro':False,'gracePeriod':False,'domain':req.url.netloc,'cdn':req.url.netloc+'/web','productName':'滴答清单','isCnSite':True,'api_domain':req.url.netloc,'protocol':req.url.scheme+'://','isProductMode':'false','isPackageMode':'false','avatar':''}
  src=re.sub(r'window\.SiteStatus\s*=\s*\{[\s\S]*?\};',lambda _: 'window.SiteStatus = '+json.dumps(status).replace('<','\\u003c')+';',src)
  return HTMLResponse(src)
 if route in PAGES:return FileResponse(ROOT/PAGES[route],media_type='text/html')
 if route in BOUNDARIES:return boundary_page(BOUNDARIES[route])
 if route in ['/forum','/blog/wp-admin/post.php','/ambassador_dashboard']:
  reason='The original forum URL returned HTTP 404 during acquisition.' if route=='/forum' else 'The original editor destination requires a separate WordPress editor account. No editor access was supplied for this public blog capture.'
  if route=='/ambassador_dashboard':
   if not account(req):return RedirectResponse('/signin?dest='+quote(route),303)
   reason='The original Ambassador dashboard redirects the supplied signed-in account to Page not found. No approved Ambassador dashboard was available to capture.'
  return HTMLResponse('<!doctype html><html><head><title>Source unavailable · TickTick</title><style>'+AUTH_STYLE+'</style></head><body data-source-unavailable><header><a href="/">TickTick</a></header><main><h1>Source unavailable</h1><p>'+reason+'</p><p>This notice is not a reproduction of the unavailable source page.</p><a href="javascript:history.back()">Back</a></main></body></html>')
 raise HTTPException(404,'Page not found')
