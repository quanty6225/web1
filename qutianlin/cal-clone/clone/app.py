"""Cal.com local application API. Source cookies are never used at runtime."""
from __future__ import annotations
import json,os,secrets,smtplib
from pathlib import Path
from urllib.parse import urlsplit
from email.message import EmailMessage
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse,HTMLResponse,RedirectResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from backend.site_backend_integration import open_site_services
from websitebench.local_clone_auth import LocalAuthStore,AuthError,AuthConflict,AuthRateLimited,MAIL_SMTP_PENDING
from cal_core import Store,DomainError
from auth_local import CalAuthStore
from account_local import Accounts
from mail_local import deliver,mail_status
HERE=Path(__file__).resolve().parent
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_RUNTIME',str(HERE/'backend/runtime.json'))
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(HERE.parent/'data/cal.sqlite3'))
SERVICE,_=open_site_services();WORKER=secrets.token_urlsafe(32);AUTH=CalAuthStore(SERVICE.lifecycle.database_path,site_id='cal',mail_mode=MAIL_SMTP_PENDING,mail_worker_token=WORKER);AUTH.ensure_schema();STORE=Store(SERVICE.lifecycle.database_path);COOKIE='cal_session'
ACCOUNTS=Accounts(STORE,AUTH)
with STORE.db() as c:
 existing_demo=c.execute("SELECT account_id FROM local_auth_accounts WHERE subject_id='demo'").fetchone();deleted_demo=c.execute("SELECT 1 FROM cal_deleted_accounts WHERE subject_id='demo'").fetchone()
DEMO=None
if not deleted_demo:
 DEMO=existing_demo['account_id'] if existing_demo else AUTH.seed_account(subject_id='demo',email='demo@cal.offline.invalid',display_name='Demo User',password='Cal-Demo-2026!');demo_profile=STORE.profile(DEMO,'demo')
 if not demo_profile['display_name']:STORE.update_profile(DEMO,{'display_name':'Demo User'})
 # Create the three source-observed links exactly once. User-created accounts start empty.
 with STORE.db(True) as c:
  c.execute('CREATE TABLE IF NOT EXISTS cal_seed_state(key TEXT PRIMARY KEY)');seeded=c.execute("SELECT 1 FROM cal_seed_state WHERE key='initial-source-events'").fetchone()
 if not seeded:
  schedule=STORE.schedule(DEMO,{'name':'Working Hours','timezone':'Asia/Shanghai'})
  for title,slug,length,hidden in [('15 分钟会议','15min',15,False),('保密会议','secret',15,True),('30 分钟会议','30min',30,False)]:STORE.event(DEMO,{'title':title,'slug':slug,'length':length,'hidden':hidden,'schedule_id':schedule['id']})
  with STORE.db(True) as c:c.execute("INSERT INTO cal_seed_state VALUES('initial-source-events')")
 with STORE.db(True) as c:
  if not c.execute("SELECT 1 FROM cal_seed_state WHERE key='observed-booking-fields'").fetchone():
   for row in c.execute("SELECT id,options FROM cal_events WHERE owner=? AND slug IN ('15min','secret','30min')",(DEMO,)).fetchall():
    options=json.loads(row['options']);options.setdefault('requires_topic',True);options.setdefault('location','Cal Video');c.execute('UPDATE cal_events SET options=? WHERE id=?',(json.dumps(options),row['id']))
   c.execute("INSERT INTO cal_seed_state VALUES('observed-booking-fields')")
 with STORE.db(True) as c:
  if not c.execute("SELECT 1 FROM cal_seed_state WHERE key='source-template-aliases'").fetchone():
   for slug,template in [('15min','1cEZyqkKopqWRD7QcAnewG'),('secret','1cEZyqkKnWdrFU57epLiih'),('30min','1cEZyqkK8HXwsaHYDqk2Ka')]:
    row=c.execute('SELECT id,options FROM cal_events WHERE owner=? AND slug=?',(DEMO,slug)).fetchone()
    if row:
     options=json.loads(row['options']);options.update(source_template=template,source_alias=template);c.execute('UPDATE cal_events SET options=? WHERE id=?',(json.dumps(options),row['id']))
   c.execute("INSERT INTO cal_seed_state VALUES('source-template-aliases')")
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
def reply(data,token=None,status=200):
 r=JSONResponse(data,status_code=status)
 if token:r.set_cookie(COOKIE,token,httponly=True,samesite='lax',secure=os.environ.get('CAL_TLS')=='1',path='/',max_age=60*60*24*30)
 return r

def account(req):
 state=AUTH.resolve_session(req.cookies.get(COOKIE))
 if not state or not state['authenticated']:raise HTTPException(401,'Please sign in.')
 return state['account']
def owner(req):return account(req)['account_id']
def safe_next(value):return value if isinstance(value,str) and value.startswith('/') and not value.startswith('//') and '\\' not in value else '/links'
@app.middleware('http')
async def headers(req,call_next):
 if req.method not in ['GET','HEAD','OPTIONS']:
  origin=req.headers.get('origin')
  if origin and urlsplit(origin).netloc!=req.headers.get('host'):return reply({'detail':'Request origin is not allowed.'},status=403)
 r=await call_next(req);r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'";return r
@app.exception_handler(DomainError)
async def domain_error(req,error):return reply({'detail':str(error)},status=error.status)
@app.exception_handler(AuthError)
async def auth_error(req,error):return reply({'detail':str(error)},status=429 if isinstance(error,AuthRateLimited) else 409 if isinstance(error,AuthConflict) else 400)
@app.get('/healthz')
def health():return {'status':'ok','site':'cal','implementation':'local scheduling and source-derived desktop pages; acceptance pending'}
@app.get('/api/session')
def session(req:Request):
 token,state=AUTH.ensure_session(req.cookies.get(COOKIE));return reply(state,token)

def auth_mail(token,purpose,base):
 claim=AUTH.claim_pending_mail_for_session(token,purpose=purpose,worker_token=WORKER)
 if not claim:return False
 route='/auth/verify' if purpose=='registration' else '/auth/reset-password';message=EmailMessage();message['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@cal.clone.test');message['To']=claim['recipient'];message['Subject']='Verify your Cal.com account' if purpose=='registration' else 'Reset your Cal.com password';message.set_content('Your verification code is '+claim['verification_code']+'\nOpen '+base.rstrip('/')+route+'?code='+claim['verification_code']+'\nThis code expires in 10 minutes and can only be used once.')
 try:
  with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(message)
 except (OSError,smtplib.SMTPException):
  AUTH.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='network',worker_token=WORKER);raise HTTPException(503,'Email could not be sent. Please retry.')
 AUTH.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,accepted_request_count=1,worker_token=WORKER);return True
@app.post('/api/auth/{action}')
async def authenticate(action:str,req:Request):
 d=dict(await req.form()) if 'application/x-www-form-urlencoded' in req.headers.get('content-type','') else await req.json();token,state=AUTH.ensure_session(req.cookies.get(COOKIE))
 if action=='login':
  result=AUTH.sign_in(token,email=d.get('email',''),password=d.get('password',''));p=STORE.profile(result['account']['account_id'])
  if not p['display_name']:STORE.update_profile(result['account']['account_id'],{'display_name':result['account']['display_name']})
  return reply({'ok':True,'redirect':safe_next(d.get('next'))},result['session_token'])
 if action=='logout':
  AUTH.sign_out(token);r=reply({'ok':True,'redirect':'/auth/login'});r.delete_cookie(COOKIE,path='/');return r
 if action=='register':
  AUTH.start_registration(token,email=d.get('email',''),display_name=d.get('name',''),password=d.get('password',''),restart_invalid_flow=True)
  try:auth_mail(token,'registration',str(req.base_url))
  except HTTPException as e:return reply({'detail':e.detail,'retry_url':'/auth/verify'},token,e.status_code)
  return reply({'ok':True,'redirect':'/auth/verify'},token)
 if action=='verify':
  AUTH.verify_registration_code(token,d.get('code',''));result=AUTH.complete_registration(token);AUTH.sign_out(result['session_token']);return reply({'ok':True,'redirect':'/auth/login?verified=1'})
 if action=='recover':
  AUTH.start_password_reset(token,email=d.get('email',''),restart_invalid_flow=True)
  try:auth_mail(token,'password-reset',str(req.base_url))
  except HTTPException as e:return reply({'detail':e.detail,'retry_url':'/auth/reset-password'},token,e.status_code)
  return reply({'ok':True,'redirect':'/auth/reset-password'},token)
 if action=='resend':
  purpose=d.get('purpose','registration');AUTH.resend(token,purpose=purpose)
  try:sent=auth_mail(token,purpose,str(req.base_url))
  except HTTPException as e:return reply({'detail':e.detail},token,e.status_code)
  return reply({'ok':True,'message':'If this account can receive a message, an email has been sent.'},token)
 if action=='reset':
  AUTH.verify_password_reset_code(token,d.get('code',''));newtoken=AUTH.complete_password_reset(token,new_password=d.get('password',''));AUTH.sign_out(newtoken);return reply({'ok':True,'redirect':'/auth/login?reset=1'})
 raise HTTPException(404)
@app.get('/api/workspace')
def workspace(req:Request):return {**STORE.workspace(owner(req)),'account':account(req)}
@app.patch('/api/profile')
async def edit_profile(req:Request):return STORE.update_profile(owner(req),await req.json())
@app.get('/api/time-off')
def list_time_off(req:Request):return {'entries':STORE.list_time_off(owner(req))}
@app.post('/api/time-off')
async def add_time_off(req:Request):return STORE.time_off(owner(req),await req.json())
@app.patch('/api/time-off/{ident}')
async def edit_time_off(ident:str,req:Request):return STORE.time_off(owner(req),await req.json(),ident)
@app.delete('/api/time-off/{ident}')
def delete_time_off(ident:str,req:Request):return STORE.delete_time_off(owner(req),ident)
@app.get('/api/account/emails')
def account_emails(req:Request):return {'emails':ACCOUNTS.list(owner(req))}
def send_account_email(who,address,base,make_primary=False):
 import re
 if not re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):1821[0-9]',base.rstrip('/')):raise HTTPException(400,'Invalid local email origin.')
 challenge=ACCOUNTS.start(who,address,make_primary);message=EmailMessage();message['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@cal.clone.test');message['To']=challenge['recipient'];message['Subject']='Verify your Cal.com email address';message.set_content('Your verification code is '+challenge['code']+'\nOpen '+base.rstrip('/')+'/settings/my-account/profile?verify_email='+challenge['id']+'&code='+challenge['code']+'\nThis code expires in 10 minutes and can only be used once.')
 try:
  with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(message)
 except (OSError,smtplib.SMTPException):
  ACCOUNTS.finish(challenge['id'],challenge['generation'],False);return reply({'detail':'Email could not be sent. Use Resend email to try again.','email_id':challenge['id']},status=503)
 ACCOUNTS.finish(challenge['id'],challenge['generation'],True);return {'ok':True,'email_id':challenge['id']}
@app.post('/api/account/emails')
async def add_account_email(req:Request):
 d=await req.json();return send_account_email(owner(req),d.get('email'),str(req.base_url),bool(d.get('make_primary')))
@app.post('/api/account/emails/{ident}/{action}')
async def account_email_action(ident:str,action:str,req:Request):
 who=owner(req);d=await req.json();records=ACCOUNTS.list(who);record=next((x for x in records if x['id']==ident),None)
 if not record:raise HTTPException(404,'Email not found.')
 if action=='resend':return send_account_email(who,record['email'],str(req.base_url),d.get('make_primary'))
 if action=='verify':
  make_primary=ACCOUNTS.verify(who,ident,d.get('code',''));token=ACCOUNTS.make_primary(who,ident,req.cookies.get(COOKIE)) if make_primary else None
  return reply({'ok':True,'made_primary':make_primary},token)
 if action=='primary':return reply({'ok':True},ACCOUNTS.make_primary(who,ident,req.cookies.get(COOKIE)))
 if action=='delete':ACCOUNTS.delete_email(who,ident);return {'ok':True}
 raise HTTPException(404)
@app.post('/api/account/delete')
async def delete_account(req:Request):
 d=await req.json();ACCOUNTS.delete_account(owner(req),d.get('confirmation'));r=reply({'ok':True,'redirect':'/auth/login?deleted=1'});r.delete_cookie(COOKIE,path='/');return r
@app.post('/api/events/reorder')
async def reorder_events(req:Request):return STORE.reorder_events(owner(req),(await req.json()).get('order'))
@app.post('/api/schedules')
async def new_schedule(req:Request):return STORE.schedule(owner(req),await req.json())
@app.patch('/api/schedules/{ident}')
async def edit_schedule(ident:str,req:Request):return STORE.schedule(owner(req),await req.json(),ident)
@app.post('/api/events')
async def new_event(req:Request):return STORE.event(owner(req),await req.json())
@app.patch('/api/events/{ident}')
async def edit_event(ident:str,req:Request):return STORE.event(owner(req),await req.json(),ident)
@app.delete('/api/events/{ident}')
def delete_event(ident:str,req:Request):
 with STORE.db(True) as c:
  if not c.execute('DELETE FROM cal_events WHERE id=? AND owner=?',(ident,owner(req))).rowcount:raise HTTPException(404,'Link not found.')
 return {'ok':True}
@app.get('/api/public/{username}')
def public_profile(username:str):
 with STORE.db() as c:
  p=c.execute('SELECT * FROM cal_profiles WHERE username=?',(username,)).fetchone()
  if not p:raise HTTPException(404)
  return {k:p[k] for k in ['username','display_name','about','location','timezone']}|{'events':[STORE.event_dict(r) for r in c.execute('SELECT e.* FROM cal_events e LEFT JOIN cal_event_order o ON o.event_id=e.id AND o.owner=e.owner WHERE e.owner=? AND hidden=0 ORDER BY o.position IS NULL,o.position,e.created,e.rowid',(p['owner'],))]}
@app.get('/api/public/{username}/{slug}')
def public_event(username:str,slug:str):
 e=STORE.public_event(username,slug)
 with STORE.db() as c:
  p=c.execute('SELECT display_name,about,location FROM cal_profiles WHERE owner=?',(e['owner'],)).fetchone()
 return {**e,'organizer':dict(p),'time_off':STORE.list_time_off(e['owner'],public=True)}
@app.get('/api/public/{username}/{slug}/slots')
def public_slots(username:str,slug:str,date:str,timezone:str='UTC'):return {'slots':STORE.slots(STORE.public_event(username,slug)['id'],date,timezone)}
@app.post('/api/public/{username}/{slug}/book')
async def book(username:str,slug:str,req:Request):
 result=STORE.book(STORE.public_event(username,slug)['id'],await req.json(),str(req.base_url).rstrip('/'),req.headers.get('idempotency-key'));return {**result,'mail':deliver(STORE,result['id'])}
@app.post('/api/events/{ident}/private-link')
def create_private_link(ident:str,req:Request):return STORE.create_private_link(owner(req),ident)
@app.get('/api/private/{token}')
def private_event(token:str):
 e=STORE.private_event(token)
 with STORE.db() as c:p=c.execute('SELECT display_name,about FROM cal_profiles WHERE owner=?',(e['owner'],)).fetchone()
 return {k:e[k] for k in ['title','length','description']}|{'private':True,'organizer':dict(p),'options':{k:e['options'].get(k) for k in ['requires_topic','location']},'time_off':STORE.list_time_off(e['owner'],public=True)}
@app.get('/api/private/{token}/slots')
def private_slots(token:str,date:str,timezone:str='UTC'):return {'slots':STORE.slots(STORE.private_event(token)['id'],date,timezone)}
@app.post('/api/private/{token}/book')
async def private_book(token:str,req:Request):
 e=STORE.private_event(token);result=STORE.book(e['id'],await req.json(),str(req.base_url).rstrip('/'),req.headers.get('idempotency-key'),private_token=token)
 return {**result,'mail':deliver(STORE,result['id'])}
@app.get('/api/bookings/{ident}')
def booking(ident:str,req:Request,token:str|None=None):
 try:who=owner(req)
 except HTTPException:who=None
 with STORE.db() as c:
  b=STORE.booking_dict(STORE._authorized_booking(c,ident,who,token));event=c.execute('SELECT slug FROM cal_events WHERE id=?',(b['event_id'],)).fetchone();profile=c.execute('SELECT username FROM cal_profiles WHERE owner=?',(b['owner'],)).fetchone();private=bool(c.execute('SELECT 1 FROM cal_private_links WHERE used_booking_id=?',(ident,)).fetchone());return {**b,'slug':None if private else event['slug'] if event else None,'username':None if private else profile['username'],'private':private,'mail':mail_status(STORE,ident)}
@app.get('/api/bookings/{ident}/slots')
def booking_slots(ident:str,req:Request,date:str,token:str|None=None):
 try:who=owner(req)
 except HTTPException:who=None
 with STORE.db() as c:b=STORE._authorized_booking(c,ident,who,token)
 if b['status']=='cancelled':raise HTTPException(409,'This booking has been cancelled.')
 return {'slots':STORE.slots(b['event_id'],date,b['timezone'],ignore_booking=ident)}
@app.post('/api/bookings/{ident}/{action}')
async def booking_action(ident:str,action:str,req:Request):
 d=await req.json()
 try:who=owner(req)
 except HTTPException:who=None
 result=STORE.change_booking(ident,action,d,str(req.base_url).rstrip('/'),who,d.get('token'));return {**result,'mail':deliver(STORE,ident)}
@app.post('/api/bookings/{ident}/mail/retry')
async def retry_mail(ident:str,req:Request):
 d=await req.json() if await req.body() else {}
 try:who=owner(req)
 except HTTPException:who=None
 with STORE.db() as c:STORE._authorized_booking(c,ident,who,d.get('token'))
 return {'mail':deliver(STORE,ident,True)}

@app.post('/api/events/{ident}/duplicate')
def duplicate_event(ident:str,req:Request):
 who=owner(req)
 with STORE.db() as c:
  row=c.execute('SELECT * FROM cal_events WHERE id=? AND owner=?',(ident,who)).fetchone()
  if not row:raise HTTPException(404)
  d=STORE.event_dict(row)
 d['options'].pop('source_alias',None);d.update(title=d['title']+' (copy)',slug=d['slug']+'-'+secrets.token_hex(3));return STORE.event(who,d)

app.mount('/assets',StaticFiles(directory=str(HERE/'assets'),check_dir=False),name='assets')
app.mount('/static',StaticFiles(directory=str(HERE/'static'),check_dir=False),name='static')

def local_shell(title):
 from html import escape
 return HTMLResponse('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+' | Cal.com</title><link rel="stylesheet" href="/static/local.css"></head><body class="local-shell"><main id="local-main"></main><script src="/static/local.js" defer></script></body></html>')

@app.get('/{path:path}')
def page(path:str,req:Request):
 route='/'+path
 if route=='/bookings/canceled':return RedirectResponse('/bookings/cancelled',status_code=302)
 if route=='/download':return RedirectResponse('/external?url=https%3A%2F%2Fdl.todesktop.com%2F220806rvletlw4t',status_code=302)
 if route=='/':return RedirectResponse('/links' if (AUTH.resolve_session(req.cookies.get(COOKIE)) or {}).get('authenticated') else '/auth/login',status_code=302)
 public=route.startswith(('/auth/','/signup','/booking/','/external','/d/')) or route in ['/terms','/privacy']
 with STORE.db() as c:profile=c.execute('SELECT username FROM cal_profiles WHERE username=?',(path.split('/')[0],)).fetchone()
 if profile:public=True
 if not public:
  try:owner(req)
  except HTTPException:
   from urllib.parse import quote
   return RedirectResponse('/auth/login?next='+quote(route+('?' +req.url.query if req.url.query else ''),safe=''),status_code=302)
 if profile or route.startswith(('/booking/','/external','/d/')) or route in ['/auth/verify','/auth/reset-password','/auth/provider']:return local_shell('Cal.com')
 routes=json.loads((HERE/'pages/routes.json').read_text());key=route+('?' +req.url.query if req.url.query else '')
 if key not in routes:key=route
 if route.startswith('/links/'):
  who=owner(req);ident=route.split('/')[2]
  with STORE.db() as c:
   event=c.execute('SELECT options FROM cal_events WHERE id=? AND owner=?',(ident,who)).fetchone()
   if not event:
    event=next((r for r in c.execute('SELECT options FROM cal_events WHERE owner=?',(who,)) if json.loads(r['options']).get('source_alias')==ident),None)
  if not event:raise HTTPException(404,'Link not found.')
  template=json.loads(event['options']).get('source_template','1cEZyqkKopqWRD7QcAnewG')
  if template not in ['1cEZyqkKopqWRD7QcAnewG','1cEZyqkKnWdrFU57epLiih','1cEZyqkK8HXwsaHYDqk2Ka']:template='1cEZyqkKopqWRD7QcAnewG'
  tab=req.query_params.get('tabName','setup');key='/links/'+template+'?tabName='+tab
 if route=='/availability/troubleshoot' and key not in routes:key='/availability/troubleshoot?eventTypeId=7464080'
 if route.startswith('/availability/') and route.split('/')[-1]!='troubleshoot':key='/availability/2494511'
 if key not in routes:raise HTTPException(404,'This page has not been implemented.')
 return FileResponse(HERE/'pages'/routes[key],media_type='text/html')
