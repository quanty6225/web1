from __future__ import annotations
import logging
from contextlib import suppress
from datetime import datetime,timedelta,timezone
import os,json,time,secrets,hashlib,hmac,sqlite3,smtplib,html,re,copy,asyncio
from pathlib import Path
from email.message import EmailMessage
from urllib.parse import urlsplit,quote
from fastapi import FastAPI,Request,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,FileResponse,Response
from websitebench.site_backend import SiteBackend
from business import Business
from websitebench.local_clone_auth.store import LocalAuthStore,AuthError,AuthRateLimited
ROOT=Path(__file__).resolve().parent;DATA=Path(os.environ.get('RECLAIM_DATA_DIR',ROOT.parent/'data')).resolve();DATA.mkdir(parents=True,exist_ok=True)
def migrate(c):
 for statement in '''CREATE TABLE IF NOT EXISTS reclaim_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);CREATE TABLE IF NOT EXISTS reclaim_records(account_id TEXT NOT NULL,kind TEXT NOT NULL,id TEXT NOT NULL,data TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(account_id,kind,id));CREATE TABLE IF NOT EXISTS reclaim_magic(digest TEXT PRIMARY KEY,flow_id TEXT NOT NULL,expires_at INTEGER NOT NULL,consumed INTEGER NOT NULL DEFAULT 0);'''.split(';'):
  if statement.strip():c.execute(statement)
 c.execute('INSERT OR IGNORE INTO reclaim_metadata VALUES(?,?)',('csrf',secrets.token_hex(32)))
backend=SiteBackend.open(json.loads((ROOT/'backend/runtime.json').read_text()),data_root=DATA,migration_hook=migrate);backend.lifecycle.initialize();WORKER=secrets.token_urlsafe(32);auth=LocalAuthStore(backend.lifecycle.database_path,site_id='reclaim',mail_mode='SMTP_PENDING',mail_worker_token=WORKER);auth.ensure_schema()
with auth.connect()as c:migrate(c);c.commit();SECRET=c.execute("SELECT value FROM reclaim_metadata WHERE key='csrf'").fetchone()[0].encode()
COOKIE='reclaim_clone_session';app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None);FIXTURES=json.loads((ROOT/'frontend/api-fixtures.json').read_text());ROUTES=json.loads((ROOT/'frontend/routes.json').read_text());RSC=json.loads((ROOT/'frontend/rsc.json').read_text());NEXTDATA=json.loads((ROOT/'frontend/next-data.json').read_text())
def deliver_due_reminders():
 with auth.connect()as c:
  rows=c.execute("SELECT account_id,id FROM reclaim_records WHERE kind='booking'").fetchall()
 for row in rows:
  with auth.connect()as c:
   c.execute('BEGIN IMMEDIATE');account=c.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(row['account_id'],)).fetchone()
   if not account:continue
   business=Business(c,FIXTURES,dict(account));meeting=business.get('booking',row['id'])
   if not meeting or meeting.get('status')=='CANCELLED':continue
   link=meeting['schedulingLink'];start=datetime.fromisoformat(meeting['event']['startTime']);current_time=datetime.now(timezone.utc)
   if (link.get('reminderEmailActive')or link.get('reminderEmailDurationMins'))and start-timedelta(minutes=link.get('reminderEmailDurationMins',1440))<=current_time<start:
    # Reminder links use this instance's port, including isolated acceptance copies.
    origin=os.environ.get('RECLAIM_PUBLIC_ORIGIN','http://127.0.0.1:'+os.environ.get('PORT','18200'));business.notify_meeting(meeting,origin,purpose='reminder');c.commit()
async def reminder_loop():
 while True:
  try:await asyncio.to_thread(deliver_due_reminders)
  except Exception:logging.getLogger('reclaim.reminders').exception('Local meeting reminder will be retried')
  await asyncio.sleep(15)
@app.on_event('startup')
async def start_reminders():app.state.reminders=asyncio.create_task(reminder_loop())
@app.on_event('shutdown')
async def stop_reminders():
 app.state.reminders.cancel()
 with suppress(asyncio.CancelledError):await app.state.reminders
def digest(x):return hashlib.sha256(x.encode()).hexdigest()
def csrf(token):return hmac.new(SECRET,token.encode(),hashlib.sha256).hexdigest()
def cookie(r,t):r.set_cookie(COOKIE,t,max_age=30*86400,path='/',httponly=True,samesite='lax',secure=os.environ.get('RECLAIM_TLS')=='1')
def current(request,required=False):
 t=request.cookies.get(COOKIE);s=auth.resolve_session(t)
 if required and(not s or not s['authenticated']):raise HTTPException(401,'Please log in.')
 return t,s
@app.middleware('http')
async def security(request,call_next):
 if request.method not in ['GET','HEAD','OPTIONS']:
  origin=request.headers.get('origin');token=request.cookies.get(COOKIE,'')
  if origin and origin!=str(request.base_url).rstrip('/'):return JSONResponse({'error':'Invalid origin'},403)
  if not token or not hmac.compare_digest(request.headers.get('x-reclaim-csrf',''),csrf(token)):return JSONResponse({'error':'Refresh the page and try again.'},403)
 try:r=await call_next(request)
 except AuthRateLimited:r=JSONResponse({'error':'Please wait before trying again.'},429)
 except AuthError as e:r=JSONResponse({'error':str(e)},400)
 port=request.scope.get('server',('127.0.0.1',18200))[1]
 r.headers['Referrer-Policy']='no-referrer';r.headers['X-Content-Type-Options']='nosniff';r.headers['Content-Security-Policy']=f"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://127.0.0.1:{port} ws://localhost:{port}; img-src 'self' data: blob:; font-src 'self' data:; frame-src 'self'; form-action 'self'"
 if not request.url.path.startswith(('/_next/','/static/')):r.headers['Cache-Control']='no-store, private';r.headers['Vary']='Cookie'
 return r
@app.get('/healthz')
def health():return {'status':'ok','site_id':'reclaim','database':'sqlite','mail':'local SMTP'}
@app.get('/local/session')
def session(request:Request):
 token,s=auth.ensure_session(request.cookies.get(COOKIE));r=JSONResponse({**s,'csrf':csrf(token)});cookie(r,token);return r
@app.post('/local/auth/challenge')
async def challenge(request:Request):
 token,s=current(request);d=await request.json()
 if not s:raise HTTPException(401,'Refresh this page.')
 flow=auth.start_passwordless_signin(token,email=d.get('email',''),restart_invalid_flow=True);claim=auth.claim_pending_mail_for_session(token,purpose='passwordless-signin',worker_token=WORKER)
 if not claim:raise HTTPException(503,'Could not prepare email.')
 magic=secrets.token_urlsafe(32)
 with auth.connect()as c:c.execute('INSERT INTO reclaim_magic VALUES(?,?,?,0)',(digest(magic),flow['signin_id'],flow['expires_at']));c.commit()
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@reclaim.clone.test');msg['To']=d['email'];msg['Subject']='Verify your Reclaim account';msg.set_content('Continue to Reclaim:\n'+str(request.base_url).rstrip('/')+'/auth/email?token='+magic+'\n\nLogin code: '+claim['verification_code']+'\n\nThis code expires in 10 minutes and can be used once.');host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
 if host not in ['127.0.0.1','localhost','::1','mailpit']:raise HTTPException(503,'Local SMTP only.')
 try:
  with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT',1025)),timeout=5)as smtp:smtp.send_message(msg)
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,target_request_count=1,accepted_request_count=1,worker_token=WORKER)
 except Exception:
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='transport',worker_token=WORKER);return JSONResponse({'mail_status':'SMTP_FAILED','error':'Could not send email. Please try again.'},503)
 return {'mail_status':'SMTP_SENT','expires_at':flow['expires_at']}
@app.post('/local/auth/verify')
async def verify(request:Request):
 token,_=current(request);d=await request.json();auth.verify_passwordless_code(token,d.get('code',''));result=auth.complete_passwordless_signin(token);r=JSONResponse({'redirect':'/planner','account_created':result['account_created']});cookie(r,result['session_token']);return r
@app.get('/auth/email')
def email_verify(request:Request,token:str=''):
 new=auth.create_anonymous_session();now=int(time.time())
 with auth.connect()as c:
  c.execute('BEGIN IMMEDIATE');m=c.execute('SELECT * FROM reclaim_magic WHERE digest=?',(digest(token),)).fetchone()
  if not m or m['consumed']or m['expires_at']<=now:raise HTTPException(400,'This login link has expired. Request a new one.')
  c.execute('UPDATE local_auth_passwordless_flows SET session_digest=?,verified_at=? WHERE signin_id=?',(auth.session_owner_digest(new),now,m['flow_id']));c.execute('UPDATE reclaim_magic SET consumed=1 WHERE digest=?',(digest(token),));c.commit()
 result=auth.complete_passwordless_signin(new);r=RedirectResponse('/planner',303);cookie(r,result['session_token']);return r
@app.post('/local/auth/logout')
def logout(request:Request):
 token,_=current(request);auth.sign_out(token);r=JSONResponse({'redirect':'/login'});r.delete_cookie(COOKIE,path='/');return r
@app.get('/auth/local')
def local_auth(request:Request,provider:str='Microsoft'):
 token,s=auth.ensure_session(request.cookies.get(COOKIE));r=HTMLResponse((ROOT/'frontend/local-auth.html').read_text().replace('{{PROVIDER}}',html.escape(provider)).replace('{{CSRF}}',csrf(token)));cookie(r,token);return r
@app.api_route('/local/external-resource',methods=['GET','POST','PUT','HEAD'])
def external_resource():return Response('',media_type='application/javascript')
@app.get('/external')
def external(url:str=''):return HTMLResponse('<h1>Reclaim</h1><p>'+html.escape(url)+'</p><a href="/planner">Back to Planner</a>')
@app.websocket('/local/ws')
async def websocket(ws:WebSocket):
 session=auth.resolve_session(ws.cookies.get(COOKIE))
 if not session or not session['authenticated']:await ws.close(code=1008);return
 await ws.accept()
 try:
  while True:await ws.receive_text()
 except WebSocketDisconnect:pass

def transform(value,account):
 if isinstance(value,str):return value.replace('member@reclaim.offline.invalid',account['email_normalized']).replace('Reclaim Member',account['display_name'])
 if isinstance(value,list):return [transform(v,account)for v in value]
 if isinstance(value,dict):return {k:(''if k=='avatarUrl'else transform(v,account))for k,v in value.items()}
 return value
@app.api_route('/proxyApi/{path:path}',methods=['GET','POST','PUT','PATCH','DELETE'])
@app.api_route('/api/{path:path}',methods=['GET','POST','PUT','PATCH','DELETE'])
async def api(path:str,request:Request):
 token,s=current(request);key='/api/'+path
 if key in ['/api/anonymous/flags','/api/users/tzs','/api/statuspage/summary']and key in FIXTURES:return FIXTURES[key]
 public_account=None
 public_link=key.startswith(('/api/scheduling-link/for-user-slug/','/api/scheduling-link/for-user-link-slug/','/api/scheduling-link/group-by-slug/'))or bool(re.fullmatch(r'/api/scheduling-link/[^/]+/(availability/V[23]|meeting/availability/V2|meeting/V2|meeting)',key))
 booking_access=re.fullmatch(r'/api/scheduling-link/meeting/([^/]+)(?:/(V2|cancel))?',key)
 if booking_access:
  with auth.connect()as c:
   row=c.execute("SELECT account_id FROM reclaim_records WHERE kind='booking' AND id=?",(booking_access[1],)).fetchone()
   if row:public_account=dict(c.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(row['account_id'],)).fetchone())
  if not public_account:raise HTTPException(404,'Meeting not found.')
 elif public_link:
  with auth.connect()as c:
   parts=key.split('/');by_slug=parts[3]in ['for-user-slug','for-user-link-slug','group-by-slug'];slug=parts[4]if by_slug else None
   if not by_slug:
    row=c.execute("SELECT account_id,data FROM reclaim_records WHERE kind='link' AND id=?",(parts[3],)).fetchone()
    if row and json.loads(row['data']).get('enabled'):public_account=dict(c.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(row['account_id'],)).fetchone())
   else:
    for owner in c.execute('SELECT * FROM local_auth_accounts'):
     owner=dict(owner);business=Business(c,FIXTURES,owner)
     if business.group_by_slug(slug):public_account=owner;break
  if public_account is None:raise HTTPException(404,'Scheduling Link not found.')
 elif not booking_access and (not s or not s['authenticated']):raise HTTPException(401,'Please log in.')
 account=public_account or s['account']
 raw=await request.body()
 try:data=json.loads(raw)if raw.strip()else{}
 except ValueError:raise HTTPException(422,'Invalid JSON.')
 with auth.connect()as connection:
  connection.execute('BEGIN IMMEDIATE')
  business=Business(connection,FIXTURES,account);business.origin=str(request.base_url)
  handled,result=business.handle(key,request.method,data,dict(request.query_params))
  if handled and request.method in ['POST','PATCH','PUT','DELETE']and isinstance(result,dict):
   meeting=result.get('data',result)
   if isinstance(meeting,dict)and 'meetingId'in meeting and 'attendee'in meeting:business.notify_meeting(meeting,str(request.base_url))
  connection.commit()
 if handled:return transform(result,account)
 if key=='/api/availability/warm-cache':return Response(status_code=204)
 if key=='/api/integrations/zoom':return None
 if request.method=='GET'and key in FIXTURES:return transform(copy.deepcopy(FIXTURES[key]),account)
 if request.method=='POST'and key in ['/api/gtd-tasks/search/plan','/api/availability/warm-cache','/api/effective-time-policy','/api/team/connected-conferences','/api/interactions/update']and key in FIXTURES:
  raw=await request.body();data=json.loads(raw)if raw.strip()else{};wrapped=data.get('request',data);interactions=wrapped.get('interactions',[])
  if key!='/api/interactions/update'or all(x.get('type')in ['ChangeScheduleWindowRequest','ChangeMeetingHubViewRequest']for x in interactions):return transform(copy.deepcopy(FIXTURES[key]),account)
 log=DATA/'unimplemented-api.jsonl'
 with log.open('a')as f:f.write(json.dumps({'path':key,'method':request.method,'body':(await request.body()).decode(errors='replace')[:30000]})+'\n')
 raise HTTPException(501,'This operation is not implemented locally yet.')
def public_page_data(route):
 parts=route.strip('/').split('/');query={'page':parts[1]};props={}
 if len(parts)==3:
  query['meeting']=parts[2]
  with auth.connect()as c:
   for account in c.execute('SELECT * FROM local_auth_accounts'):
    business=Business(c,FIXTURES,dict(account));link=next((l for l in business.rows('link')if l['pageSlug']==parts[1]and l['slug']==parts[2]and l['enabled']),None)
    if link:props['schedulingLinkDto']=link;break
 return {'pageProps':props,'__N_SSP':True},query
@app.get('/avatar/streamed/{avatar_path:path}')
def local_avatar(avatar_path:str):
 # Captured credential names are sanitized to Calendar; never reuse private source photos.
 return Response('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40"><circle cx="20" cy="20" r="20" fill="#bdbdbd"/><text x="20" y="26" text-anchor="middle" font-family="Arial,sans-serif" font-size="22" fill="white">C</text></svg>',media_type='image/svg+xml',headers={'Cache-Control':'public, max-age=3600'})
@app.get('/{path:path}')
def page(path:str,request:Request):
 route='/'+path
 if re.fullmatch(r'/team-invite/[A-Za-z0-9_-]+',route):
  token,s=auth.ensure_session(request.cookies.get(COOKIE));invite=route.rsplit('/',1)[1]
  content='<!doctype html><html><head><title>Join your Reclaim team</title><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main style="max-width:480px;margin:100px auto;font-family:Arial,sans-serif"><h1>Join your Reclaim team</h1><p>Accept this invitation to schedule meetings with your team. Sign in with the email address that received the invitation.</p><button data-team-invite="'+invite+'">Accept invitation</button><p role="alert"></p><a href="/planner">Back to Planner</a></main><script src="/static/team-invite.js"></script></body></html>'
  r=HTMLResponse(content);cookie(r,token);return r
 for directory in ['public',None]:
  file=(ROOT/'public'/path)if directory else(ROOT/path if path.startswith('static/')else ROOT/'absent')
  if file.is_file()and file.resolve().is_relative_to(ROOT):return FileResponse(file)
 raw_file=ROOT/'public'/request.scope['raw_path'].decode().lstrip('/')
 if raw_file.is_file()and raw_file.resolve().is_relative_to(ROOT/'public'):return FileResponse(raw_file)
 if route.startswith('/_next/data/')and route.endswith('.json'):
  target='/'+('/'.join(route.split('/')[4:]))[:-5]
  if target.startswith('/m/'):return public_page_data(target)[0]
  if target in NEXTDATA:return NEXTDATA[target]
 if route=='/':return RedirectResponse('/planner',303)
 public=route in ['/login','/signup']or route.startswith(('/m/','/meeting/'));token,s=auth.ensure_session(request.cookies.get(COOKIE))
 if not public and not s['authenticated']:
  r=RedirectResponse('/login',303);cookie(r,token);return r
 if re.fullmatch(r'/scheduling-links/[^/]+/edit',route):route='/scheduling-links/new/edit'
 elif re.fullmatch(r'/scheduling-links/[^/]+',route):route='/scheduling-links/new'
 elif re.fullmatch(r'/meeting/[^/]+/reschedule',route):route='/meeting/[meetingId]/reschedule'
 elif re.fullmatch(r'/meeting/[^/]+',route):route='/meeting/[meetingId]'
 elif re.fullmatch(r'/m/[^/]+/[^/]+',route):route='/m/[page]/[meeting]'
 elif re.fullmatch(r'/m/[^/]+',route):route='/m/-75-qq'
 if route not in ROUTES:raise HTTPException(404,'Page not found')
 if '_rsc'in request.query_params and route in RSC:return Response(RSC[route],media_type='text/x-component')
 content=(ROOT/'frontend/pages'/ROUTES[route]).read_text()
 if path.startswith(('m/','meeting/')):
  props,query=public_page_data('/'+path)if path.startswith('m/')else({'pageProps':{}},{'meetingId':path.split('/')[1],**dict(request.query_params)})
  def bootstrap(match):
   data=json.loads(match.group(2));data['query']=query;data['props']=props;return match.group(1)+json.dumps(data).replace('<','\\u003c')+match.group(3)
  content=re.sub(r'(<script id="__NEXT_DATA__"[^>]*>)(.*?)(</script>)',bootstrap,content,flags=re.S)
 context='<script type="application/json" id="local-context">'+json.dumps({'csrf':csrf(token),'authenticated':s['authenticated']}).replace('<','\\u003c')+'</script>';content=content.replace('<script src="/static/local-bridge.js">',context+'<script src="/static/local-bridge.js">');r=HTMLResponse(content);cookie(r,token);return r
