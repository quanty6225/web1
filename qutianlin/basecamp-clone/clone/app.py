"""Basecamp's isolated local web application. No source connection at runtime."""
import hashlib,hmac,html,json,os,re,secrets,smtplib,sqlite3,time,base64,struct,io,zipfile
from contextlib import closing,contextmanager
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode,urlsplit,parse_qsl,quote
from fastapi import FastAPI,Request,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,FileResponse,Response
from fastapi.staticfiles import StaticFiles
from backend.site_backend_integration import open_site_services
from local_render import render as render_local, safe_rich_text
from websitebench.local_clone_auth import LocalAuthStore,AuthError,MAIL_SMTP_PENDING
from websitebench.local_clone_auth.store import _hash_secret,_validate_password,PASSWORD_SCHEME

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(ROOT.parent/'data/basecamp.sqlite3'))
backend,_=open_site_services()
WORKER=secrets.token_urlsafe(32)
auth=LocalAuthStore(backend.lifecycle.database_path,site_id='basecamp',mail_mode=MAIL_SMTP_PENDING,mail_worker_token=WORKER)
auth.ensure_schema()
auth.seed_account(subject_id='basecamp-demo',email='demo@basecamp.offline.invalid',display_name='Dee',password='Basecamp-Demo-2026!')
COOKIE='basecamp_local_session'
SECURE=os.environ.get('CLONE_TLS')=='1'
ORIGIN=os.environ.get('BASE_URL','http://127.0.0.1:18130').rstrip('/')
ROUTES=json.loads((ROOT/'frontend/routes.json').read_text())
for _info in ROUTES.values():
 if _info.get('final_route','').startswith('/6302022/'):_info['auth']=True
FAMILIES={}
for _path,_info in ROUTES.items():
 FAMILIES.setdefault(re.sub(r'/\d+(?=/|$)','/:id',_path.split('?')[0]),(_path.split('?')[0],_info))
UI=json.loads((ROOT/'frontend/ui.json').read_text())
ASSET_ALIASES=json.loads((ROOT/'frontend/asset-aliases.json').read_text()) if (ROOT/'frontend/asset-aliases.json').exists() else {}
DOWNLOADS=json.loads((ROOT/'frontend/downloads.json').read_text()) if (ROOT/'frontend/downloads.json').exists() else {}
XHR=json.loads((ROOT/'frontend/xhr.json').read_text()) if (ROOT/'frontend/xhr.json').exists() else {}
ASSET_NAMES=json.loads((ROOT/'frontend/asset-names.json').read_text()) if (ROOT/'frontend/asset-names.json').exists() else {}
WELCOME=json.loads((ROOT/'frontend/welcome.json').read_text()) if (ROOT/'frontend/welcome.json').exists() else []
PAGES=ROOT/'frontend/pages'
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
app.mount('/assets/js',StaticFiles(directory=ROOT/'assets/js'),name='source-public-modules')

@contextmanager
def db():
 # sqlite3.Connection's context manager commits/rolls back, but does not
 # close the connection. Release handles deterministically on every path.
 with closing(sqlite3.connect(backend.lifecycle.database_path,timeout=20)) as c:
  c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
  with c:yield c
with db() as c:
 c.executescript('''CREATE TABLE IF NOT EXISTS bc_mfa(session TEXT PRIMARY KEY, code_hash TEXT, expires INTEGER, attempts INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, sent INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS bc_settings(owner TEXT, name TEXT, value TEXT, PRIMARY KEY(owner,name));
 CREATE TABLE IF NOT EXISTS bc_records(id TEXT PRIMARY KEY,owner TEXT NOT NULL,parent TEXT,kind TEXT,title TEXT,body TEXT,data TEXT,created INTEGER);
 CREATE TABLE IF NOT EXISTS bc_mutations(owner TEXT,route TEXT,kind TEXT,payload TEXT,updated INTEGER,PRIMARY KEY(owner,route,kind));
 CREATE TABLE IF NOT EXISTS bc_comments(id TEXT PRIMARY KEY,owner TEXT,route TEXT,body TEXT,created INTEGER);
 CREATE TABLE IF NOT EXISTS bc_newsletter(email TEXT PRIMARY KEY,created INTEGER);
 CREATE TABLE IF NOT EXISTS bc_files(id TEXT PRIMARY KEY, owner TEXT, filename TEXT, content_type TEXT, size INTEGER, checksum TEXT, uploaded INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS bc_totp(owner TEXT PRIMARY KEY,secret TEXT,enabled INTEGER DEFAULT 0,last_counter INTEGER DEFAULT -1);
 CREATE TABLE IF NOT EXISTS bc_email_changes(owner TEXT PRIMARY KEY,email TEXT,code_hash TEXT,expires INTEGER,attempts INTEGER DEFAULT 0);
 CREATE INDEX IF NOT EXISTS bc_records_owner ON bc_records(owner);
 ''')

with db() as c:
 if 'uploader' not in {r['name'] for r in c.execute('PRAGMA table_info(bc_files)')}:c.execute('ALTER TABLE bc_files ADD COLUMN uploader TEXT')
 c.execute('UPDATE bc_files SET uploader=owner WHERE uploader IS NULL')

import workspaces
import trash
trash.initialize(db)
workspaces.initialize(db)
import tool_operations
tool_operations.initialize(db)
import comment_operations
comment_operations.initialize(db)
import payment_operations
payment_operations.initialize(db)
import activity_search
activity_search.initialize(db)
import social_operations
social_operations.initialize(db)

def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def safe_return(value):return value if value and value.startswith('/') and not value.startswith('//') and '\\' not in value else '/6302022/'
def session(request):return request.cookies.get(COOKIE)
def raw_user(request):
 s=auth.resolve_session(session(request));return s.get('account') if s else None
def user(request):
 account=raw_user(request)
 if not account:return None
 with db() as c:ok=c.execute('SELECT verified FROM bc_mfa WHERE session=?',(digest(session(request)),)).fetchone()
 return workspaces.context(db,account) if ok and ok['verified'] else None
def require_user(request):
 u=user(request)
 if not u:raise HTTPException(401,'Please log in to Basecamp.')
 return u
def cookie(response,token):
 response.set_cookie(COOKIE,token,httponly=True,samesite='lax',secure=SECURE,path='/',max_age=30*86400);return response
def anon(request):return auth.ensure_session(session(request))[0]
def csrf_for(token):return digest('basecamp-local-csrf:'+token)
def csrf_check(request,form):
 token=session(request)
 given=request.headers.get('x-csrf-token') or form.get('_csrf','')
 if not token or not hmac.compare_digest(csrf_for(token),str(given)):raise HTTPException(403,'This form has expired. Reload the page and try again.')
def send_mail(email,subject,text):
 host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1');port=int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025'))
 if host not in {'127.0.0.1','localhost','::1','mailpit','smtp'}:raise RuntimeError('Only local Mailpit SMTP is supported.')
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@basecamp.clone.test');msg['To']=email;msg['Subject']=subject;msg['X-Clone-Site']='basecamp';msg.set_content(text)
 with smtplib.SMTP(host,port,timeout=8) as smtp:smtp.send_message(msg)
def deliver_auth(token,purpose):
 claim=auth.claim_pending_mail_for_session(token,purpose=purpose,worker_token=WORKER)
 if not claim:return
 try:
  code=claim['verification_code'];email=claim['recipient'] if 'recipient'in claim else claim['recipient_email']
  link=ORIGIN+('/reset/verify' if purpose=='password-reset' else '/signup/verify')+'?code='+code
  send_mail(email,'Reset your Basecamp password' if purpose=='password-reset' else 'Verify your Basecamp account',f'Your Basecamp verification code is {code}.\n\n{link}\n\nThis code expires in 10 minutes and can be used once.')
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,accepted_request_count=1,worker_token=WORKER)
 except Exception:
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='Local SMTP delivery failed',worker_token=WORKER)
  raise RuntimeError('We couldn’t send the email. Please try again.')
def login_code(token,email):
 code=f'{secrets.randbelow(1000000):06d}';key=digest(token)
 with db() as c:c.execute('INSERT OR REPLACE INTO bc_mfa(session,code_hash,expires,attempts,verified,sent) VALUES(?,?,?,0,0,0)',(key,digest(key+code),int(time.time())+600))
 send_mail(email,'Your Basecamp security code',f'Your Basecamp security code is {code}.\n\nEnter it at {ORIGIN}/verify\n\nThis code expires in 10 minutes and can be used once.')
 with db() as c:c.execute('UPDATE bc_mfa SET sent=1 WHERE session=?',(key,))

def totp_code(secret,counter):
 result=hmac.new(base64.b32decode(secret),struct.pack('>Q',counter),hashlib.sha1).digest();offset=result[-1]&15
 return f'{(struct.unpack(">I",result[offset:offset+4])[0]&0x7fffffff)%1000000:06d}'

def totp_secret(owner):
 with db() as c:
  row=c.execute('SELECT * FROM bc_totp WHERE owner=?',(owner,)).fetchone()
  if row:return row['secret']
  secret=base64.b32encode(secrets.token_bytes(20)).decode();c.execute('INSERT INTO bc_totp(owner,secret) VALUES(?,?)',(owner,secret));return secret

@app.get('/api/totp/qr.svg')
def totp_qr(request:Request):
 import qrcode,qrcode.image.svg
 account=require_user(request);secret=totp_secret(account['account_id']);uri='otpauth://totp/Basecamp:'+quote_error(account['email_normalized'])+'?'+urlencode({'secret':secret,'issuer':'Basecamp'})
 svg=qrcode.make(uri,image_factory=qrcode.image.svg.SvgPathImage);buffer=io.BytesIO();svg.save(buffer)
 return Response(buffer.getvalue(),media_type='image/svg+xml')

@app.post('/two_factor_authentication/profiles/totp')
async def totp_enable(request:Request):
 account=require_user(request);data=await request.form();csrf_check(request,data);secret=totp_secret(account['account_id']);code=str(data.get('code',''));counter=int(time.time())//30
 matched=next((n for n in [counter-1,counter,counter+1] if hmac.compare_digest(totp_code(secret,n),code)),None)
 if matched is None:return auth_page('Set up two-factor authentication',form('/two_factor_authentication/profiles/totp',field('Verification code','code'),'Verify'),session(request),'That code didn’t work. Please try again.',422)
 with db() as c:c.execute('UPDATE bc_totp SET enabled=1,last_counter=? WHERE owner=?',(matched,account['account_id']))
 return basic_page('Two-factor authentication is on','<p>Your authenticator is now linked to your local account.</p><a href="/identity/login_option">Back to account settings</a>',request)

@app.middleware('http')
async def headers(request,call_next):
 response=await call_next(request)
 # A response from an older tab must not restore its session after another
 # tab signs in. Only a newly created/rotated session needs a Set-Cookie;
 # replaying an unchanged token also races with logout/account switching.
 if session(request):
  unchanged=(COOKIE+'='+session(request)+';').encode()
  response.raw_headers=[(name,value) for name,value in response.raw_headers if not (name.lower()==b'set-cookie' and value.startswith(unchanged))]
 nonce=digest('basecamp-script:'+str(session(request)))
 response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'self' 'nonce-"+nonce+"'; connect-src 'self'; media-src 'self' blob:; frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
 response.headers['Referrer-Policy']='same-origin';response.headers['X-Content-Type-Options']='nosniff'
 if response.status_code==200 and request.url.path.startswith('/static/assets/') and request.query_params.get('disposition')=='attachment':
  asset=Path(request.url.path).name
  response.headers['Content-Disposition']="attachment; filename*=UTF-8''"+quote(ASSET_NAMES.get(asset,asset),safe='')
 if not request.url.path.startswith(('/static/','/assets/')):response.headers['Cache-Control']='no-store, private'
 return response

def auth_page(title,content,token,error='',status=200):
 logo=UI.get('logo','')
 document=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} — Basecamp</title><link rel="stylesheet" href="/static/local.css"></head><body class="local-auth"><header><a href="/"><img src="{logo}" alt="Basecamp" width="56" height="56"></a></header><main class="auth-card"><h1>{html.escape(title)}</h1>{'<p class="form-error" role="alert">'+html.escape(error)+'</p>' if error else ''}{content}</main><footer><a href="/signin">Log in</a> · <a href="/pricing">New to Basecamp? Sign up for free</a></footer><script src="/static/local.js" defer></script></body></html>'''
 document=document.replace('{{csrf}}',csrf_for(token))
 return cookie(HTMLResponse(document,status_code=status),token)
def field(label,name,typ='text',value='',attrs=''):
 return f'<label class="auth-label">{label}<input name="{name}" type="{typ}" value="{html.escape(value,quote=True)}" {attrs} required></label>'
def form(action,body,button):return '<form method="post" action="'+action+'"><input type="hidden" name="_csrf" value="{{csrf}}">'+body+'<button class="auth-submit" type="submit">'+button+'</button></form>'

@app.get('/healthz')
@app.get('/__websitebench/health')
def health():return {'status':'ok','site_id':'basecamp','persistence':'sqlite','mail':'local-smtp'}
@app.get('/service-worker.js')
def service_worker():return Response("self.addEventListener('install',()=>self.skipWaiting());",media_type='application/javascript')
@app.get('/assets/{asset_path:path}')
def asset_alias(asset_path:str):
 filename=ASSET_ALIASES.get('/assets/'+asset_path)
 if not filename:raise HTTPException(404,'Asset not found')
 return FileResponse(ROOT/'static/assets'/filename)
@app.get('/6302022/embeds/patterns.json')
def embed_patterns(request:Request):
 require_user(request)
 return json.loads((ROOT/'frontend/embed-patterns.json').read_text())

@app.get('/6302022/my/announcement')
def announcement(request:Request):require_user(request);return Response(status_code=204)
@app.api_route('/6302022/my/assignments/subscription.js',methods=['POST','PUT','PATCH','DELETE'])
async def assignments_subscription(request:Request):
 account=require_user(request);data=await request.json() if 'application/json' in request.headers.get('content-type','') else await request.form();csrf_check(request,data)
 enabled=str(data.get('_method',request.method)).upper()!='DELETE'
 with db() as c:scheduled_jobs.set_subscription(c,account['account_id'],enabled)
 return {'saved':True,'subscribed':enabled}

@app.get('/6302022/my/notifications.json')
def notifications(request:Request):
 u=require_user(request)
 from notification_preferences import state as notification_state,preferences
 with db() as c:
  state=notification_state(c,u['account_id']);settings=preferences(c,u['account_id'])
 return {'state':state,'hide_badge_counts':not settings['show_badge_counts'],'sort_pings_first':False,'refresh_in':60}
@app.get('/6302022/my/unreads')
def unreads(request:Request):
 account=require_user(request)
 with db() as c:return activity_search.native_unreads(c,account)

@app.post('/api/notifications/read')
async def read_notification(request:Request):
 account=require_user(request);data=await request.json();csrf_check(request,data);identifier=str(data.get('id',''))
 if identifier not in {r['id'] for r in WELCOME}:raise HTTPException(404,'Notification not found')
 with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(account['account_id'],'welcome-read-'+identifier,'true'))
 return {'saved':True}
@app.websocket('/cable')
async def cable(socket:WebSocket):
 import asyncio
 origin=str(socket.url.replace(path='',query='')).replace('ws:','http:').replace('wss:','https:').rstrip('/')
 if socket.headers.get('origin')!=origin:await socket.close(code=1008);return
 account=user(socket)
 if not account:await socket.close(code=1008);return
 workspace=account['workspace_id'];subscriptions=set();revision=None
 await socket.accept(subprotocol='actioncable-v1-json');await socket.send_json({'type':'welcome'})
 try:
  while True:
   try:message=await asyncio.wait_for(socket.receive_json(),timeout=1)
   except TimeoutError:message={}
   current=user(socket)
   if not current or current.get('closed') or current['workspace_id']!=workspace:await socket.close(code=1008);return
   if message.get('command')=='subscribe':
    identifier=message.get('identifier','')
    await socket.send_json({'type':'confirm_subscription','identifier':identifier})
    try:channel=json.loads(identifier).get('channel')
    except (ValueError,TypeError,AttributeError):channel=None
    if channel=='UnreadsChannel':subscriptions.add(identifier);revision=None
   elif message.get('command')=='unsubscribe':subscriptions.discard(message.get('identifier'))
   if subscriptions:
    items,changed=activity_search.sidebar_state(db,current)
    if changed!=revision:
     revision=changed
     for identifier in subscriptions:await socket.send_json({'identifier':identifier,'message':{'unreads':items}})
 except WebSocketDisconnect:pass

@app.get('/campfire/signin')
@app.get('/basecamp/signin')
@app.get('/signin')
@app.get('/login')
def signin(request:Request):
 token=anon(request);ret=safe_return(request.query_params.get('return_to'))
 if user(request):return RedirectResponse(ret,303)
 stage=request.query_params.get('stage','email');email=request.query_params.get('email','')
 body=field('Email or username','username','email',email,'autocomplete="username"')
 if stage=='password':body+=field('Password','password','password','','autocomplete="current-password"')
 body+=f'<input type="hidden" name="stage" value="{html.escape(stage)}"><input type="hidden" name="return_to" value="{html.escape(ret)}">'
 return auth_page('Log in to Basecamp','<a class="google-button" href="/google_sign_in/authorization">Sign in with Google</a><p class="auth-divider">Or, use my email address</p>'+form('/session',body,'Log in' if stage=='password' else 'Next')+'<p><a href="/forgot_password">Forgot your password?</a></p>',token,request.query_params.get('error',''))

@app.post('/session')
async def signin_post(request:Request):
 data=await request.form();csrf_check(request,data);email=str(data.get('username','')).strip();ret=safe_return(str(data.get('return_to','')))
 if data.get('stage')!='password':
  if not auth.account_exists(email):return RedirectResponse('/signin?'+urlencode({'error':'We couldn’t find that one. Want to try another?','return_to':ret}),303)
  return RedirectResponse('/signin?'+urlencode({'stage':'password','email':email,'return_to':ret}),303)
 try:
  result=auth.sign_in(session(request),email=email,password=str(data.get('password','')));token=result['session_token']
  with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(digest(token),'return_to',json.dumps(ret)))
  with db() as c:totp=c.execute('SELECT enabled FROM bc_totp WHERE owner=?',(result['account']['account_id'],)).fetchone()
  if totp and totp['enabled']:
   with db() as c:c.execute('INSERT OR REPLACE INTO bc_mfa(session,code_hash,expires,attempts,verified,sent) VALUES(?,NULL,?,0,0,1)',(digest(token),int(time.time())+600))
  else:login_code(token,result['account']['email_normalized'])
  return cookie(RedirectResponse('/verify',303),token)
 except AuthError:return RedirectResponse('/signin?'+urlencode({'stage':'password','email':email,'error':'That password didn’t work. Please try again.','return_to':ret}),303)
 except (OSError,RuntimeError,smtplib.SMTPException):
  return cookie(RedirectResponse('/verify?error='+quote_error('We couldn’t send the email. Please try again.'),303),token)
def quote_error(value):return urlencode({'x':value})[2:]

@app.get('/verify')
def verify_page(request:Request):
 token=session(request)
 if not raw_user(request):return RedirectResponse('/signin',303)
 with db() as c:totp=c.execute('SELECT enabled FROM bc_totp WHERE owner=?',(raw_user(request)['account_id'],)).fetchone()
 uses_totp=bool(totp and totp['enabled'])
 content=('<p>Enter the code from your authenticator app.</p>' if uses_totp else '<p>Enter the security code we sent to your email address.</p>')+form('/verify',field('Security code','code','text','','inputmode="numeric" autocomplete="one-time-code" maxlength="6"'),'Verify')+('' if uses_totp else form('/verify/resend','','Send a new code'))
 return auth_page('Two-factor authentication' if uses_totp else 'Check your email',content,token,request.query_params.get('error',''))
@app.post('/verify')
async def verify_post(request:Request):
 data=await request.form();csrf_check(request,data);token=session(request);key=digest(token);code=str(data.get('code','')).strip();now=int(time.time())
 with db() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM bc_mfa WHERE session=?',(key,)).fetchone()
  if not row or row['verified'] or not row['sent'] or row['expires']<=now or row['attempts']>=5:
   return RedirectResponse('/verify?error='+quote_error('This code has expired or has already been used. Request a new code.'),303)
  c.execute('UPDATE bc_mfa SET attempts=attempts+1 WHERE session=?',(key,))
  if row['code_hash'] is None:
   account=raw_user(request);totp=c.execute('SELECT * FROM bc_totp WHERE owner=?',(account['account_id'],)).fetchone() if account else None;counter=now//30
   matched=next((n for n in [counter-1,counter,counter+1] if totp and n>totp['last_counter'] and hmac.compare_digest(totp_code(totp['secret'],n),code)),None)
   if matched is None:return RedirectResponse('/verify?error='+quote_error('That code didn’t work. Please try again.'),303)
   c.execute('UPDATE bc_totp SET last_counter=? WHERE owner=?',(matched,account['account_id']))
  elif not hmac.compare_digest(row['code_hash'],digest(key+code)):return RedirectResponse('/verify?error='+quote_error('That code didn’t work. Please try again.'),303)
  c.execute('UPDATE bc_mfa SET verified=1,code_hash=NULL WHERE session=?',(key,));target=c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="return_to"',(key,)).fetchone()
 return RedirectResponse(safe_return(json.loads(target['value']) if target else ''),303)
@app.post('/verify/resend')
async def resend(request:Request):
 data=await request.form();csrf_check(request,data);account=raw_user(request)
 if not account:return RedirectResponse('/signin',303)
 with db() as c:totp=c.execute('SELECT enabled FROM bc_totp WHERE owner=?',(account['account_id'],)).fetchone()
 if totp and totp['enabled']:raise HTTPException(409,'Use the code from your authenticator app.')
 try:login_code(session(request),account['email_normalized']);return RedirectResponse('/verify',303)
 except (OSError,smtplib.SMTPException):return RedirectResponse('/verify?error='+quote_error('We couldn’t send the email. Please try again.'),303)

@app.get('/signup')
@app.get('/signup/account/new')
def signup(request:Request):
 token=anon(request)
 content=form('/signup/account',field('Your name','name')+field('Your email address','email','email')+field("Your organization's name",'company')+'<label class="auth-check"><input type="checkbox" name="terms" required> I agree to the <a href="/policies/terms">37signals Terms of Service</a> and <a href="/privacy">Privacy Policy</a>.</label>','Next: Set a password ➔')
 return auth_page('Create your new Basecamp account',content,token,request.query_params.get('error',''))
@app.post('/signup/account')
async def signup_details(request:Request):
 data=await request.form();csrf_check(request,data);token=session(request)
 if not all(str(data.get(k,'')).strip() for k in ['name','email','company','terms']):return RedirectResponse('/signup?error=Please+complete+all+fields.',303)
 with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(digest(token),'signup',json.dumps({k:str(data[k]) for k in ['name','email','company']})))
 return auth_page('Set your password',form('/signup/password',field('Password','password','password','','minlength="8" autocomplete="new-password"'),'Create your account'),token)
@app.post('/signup/password')
async def signup_password(request:Request):
 data=await request.form();csrf_check(request,data);token=session(request)
 with db() as c:row=c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="signup"',(digest(token),)).fetchone()
 if not row:return RedirectResponse('/signup',303)
 details=json.loads(row['value'])
 try:
  auth.start_registration(token,email=details['email'],display_name=details['name'],password=str(data.get('password','')),restart_invalid_flow=True);deliver_auth(token,'registration')
  return RedirectResponse('/signup/verify',303)
 except (AuthError,RuntimeError,OSError):return auth_page('Set your password',form('/signup/password',field('Password','password','password','','minlength="8"'),'Create your account'),token,'We couldn’t complete your registration. Check the details and try again.',400)
@app.get('/signup/verify')
def registration_verify(request:Request):
 token=anon(request);return auth_page('Check your email',form('/signup/verify',field('Verification code','code','text',request.query_params.get('code',''),'inputmode="numeric"'),'Verify email address'),token,request.query_params.get('error',''))
@app.post('/signup/verify')
async def registration_complete(request:Request):
 data=await request.form();csrf_check(request,data)
 try:
  auth.verify_registration_code(session(request),str(data.get('code','')));result=auth.complete_registration(session(request))
  with db() as c:
   details=c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="signup"',(digest(session(request)),)).fetchone()
   if details:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(result['account']['account_id'],'account_name',json.dumps(json.loads(details['value'])['company'])))
  auth.sign_out(result['session_token'])
  return cookie(RedirectResponse('/signin',303),auth.create_anonymous_session())
 except AuthError:return RedirectResponse('/signup/verify?error='+quote_error('That code is invalid, expired, or already used.'),303)

@app.get('/forgot_password')
@app.get('/password_resets/new')
def forgot(request:Request):
 token=anon(request);return auth_page('Forgot your password?','<p>Enter your email address below and we’ll send you password reset instructions.</p>'+form('/password_resets',field('Email address','email_address','email'),'Email me reset instructions')+'<p><a href="/signin">Never mind, go back</a></p>',token,request.query_params.get('error',''))
@app.post('/password_resets')
async def reset_start(request:Request):
 data=await request.form();csrf_check(request,data)
 try:
  auth.start_password_reset(session(request),email=str(data.get('email_address','')),restart_invalid_flow=True);deliver_auth(session(request),'password-reset');return RedirectResponse('/reset/verify',303)
 except (AuthError,RuntimeError,OSError):return RedirectResponse('/forgot_password?error='+quote_error('We couldn’t send the email. Please try again.'),303)
@app.get('/reset/verify')
def reset_verify(request:Request):
 token=anon(request);return auth_page('Reset your password',form('/reset/verify',field('Verification code','code','text',request.query_params.get('code',''))+field('New password','password','password','','minlength="8"'),'Reset password'),token,request.query_params.get('error',''))
@app.post('/reset/verify')
async def reset_complete(request:Request):
 data=await request.form();csrf_check(request,data)
 try:
  auth.verify_password_reset_code(session(request),str(data.get('code','')));token=auth.complete_password_reset(session(request),new_password=str(data.get('password','')));auth.sign_out(token)
  return cookie(RedirectResponse('/signin',303),auth.create_anonymous_session())
 except AuthError:return RedirectResponse('/reset/verify?error='+quote_error('That code is invalid, expired, or already used.'),303)
@app.post('/6302022/sign_out')
@app.delete('/6302022/sign_out')
@app.post('/logout')
@app.delete('/logout')
async def logout(request:Request):
 data=await request.form();csrf_check(request,data);auth.sign_out(session(request));response=RedirectResponse('/signin',303);response.delete_cookie(COOKIE,path='/');return response

@app.api_route('/identity/password',methods=['POST','PATCH','PUT'])
async def change_password(request:Request):
 account=require_user(request);data=await request.form();csrf_check(request,data);password=str(data.get('identity[password]',''))
 if password!=data.get('identity[password_confirmation]'):raise HTTPException(422,'The passwords do not match.')
 try:password=_validate_password(password)
 except AuthError:raise HTTPException(422,'Please choose a password with at least 8 characters.')
 salt,password_hash=_hash_secret(password)
 with db() as c:
  c.execute('UPDATE local_auth_accounts SET password_salt=?,password_hash=?,password_scheme=?,password_updated_at=? WHERE account_id=?',(salt,password_hash,PASSWORD_SCHEME,int(time.time()),account['account_id']))
  c.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=?',(int(time.time()),account['account_id']))
 response=RedirectResponse('/signin',303);response.delete_cookie(COOKIE,path='/');return response

@app.api_route('/identity',methods=['POST','PUT','PATCH'])
async def change_identity(request:Request):
 account=require_user(request);data=await request.form();csrf_check(request,data);name=str(data.get('identity[name]',account['display_name'])).strip();email=str(data.get('identity[email_address]',account['email_normalized'])).strip().casefold()
 if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Please enter your name and a valid email address.')
 if email!=account['email_normalized']:
  if auth.account_exists(email):raise HTTPException(422,'That email address is already in use.')
  code=f'{secrets.randbelow(1000000):06d}'
  try:send_mail(email,'Verify your new Basecamp email',f'Your Basecamp verification code is {code}.\n\n{ORIGIN}/identity/verify\n\nThis code expires in 10 minutes.')
  except (OSError,smtplib.SMTPException):raise HTTPException(503,'We couldn’t send the email. Please try again.')
  with db() as c:c.execute('INSERT OR REPLACE INTO bc_email_changes VALUES(?,?,?,?,0)',(account['account_id'],email,digest(account['account_id']+code),int(time.time())+600))
  target='/identity/verify'
 else:target='/identity/edit'
 with db() as c:c.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(name,account['account_id']))
 return RedirectResponse(target,303)

@app.get('/identity/verify')
def changed_email_page(request:Request):
 require_user(request);return auth_page('Verify your new email',form('/identity/verify',field('Verification code','code'),'Verify'),session(request))

@app.post('/identity/verify')
async def changed_email_verify(request:Request):
 account=require_user(request);data=await request.form();csrf_check(request,data)
 with db() as c:
  c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM bc_email_changes WHERE owner=?',(account['account_id'],)).fetchone()
  if not r or r['expires']<=int(time.time()) or r['attempts']>=5:raise HTTPException(422,'This verification code has expired.')
  c.execute('UPDATE bc_email_changes SET attempts=attempts+1 WHERE owner=?',(account['account_id'],))
  if not hmac.compare_digest(r['code_hash'],digest(account['account_id']+str(data.get('code','')))):return auth_page('Verify your new email',form('/identity/verify',field('Verification code','code'),'Verify'),session(request),'That code didn’t work.',422)
  if c.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=?',(r['email'],)).fetchone():raise HTTPException(422,'That email address is already in use.')
  c.execute('UPDATE local_auth_accounts SET email_normalized=? WHERE account_id=?',(r['email'],account['account_id']));c.execute('DELETE FROM bc_email_changes WHERE owner=?',(account['account_id'],))
 return RedirectResponse('/identity/edit',303)
@app.get('/google_sign_in/authorization')
def google_local(request:Request):
 token=anon(request);return auth_page('Sign in with Google','<p>Choose a local account to continue.</p>'+form('/google_sign_in/authorization',field('Email address','email','email'),'Continue')+'<p><a href="/signin">Or, use my email address</a></p>',token)
@app.post('/google_sign_in/authorization')
async def google_post(request:Request):
 data=await request.form();csrf_check(request,data)
 return RedirectResponse('/signin?'+urlencode({'stage':'password','email':str(data.get('email',''))}),303)

@app.middleware('http')
async def workspace_permissions(request:Request,call_next):
 if request.url.path.startswith(('/static/','/assets/')):return await call_next(request)
 account=user(request)
 if account:
  path=request.url.path
  if account.get('closed') and path.startswith(('/6302022/','/api/records','/api/uploads','/api/chats','/api/pings','/api/state','/api/calendar/','/api/events/','/api/members','/api/invitations','/api/settings/','/files/')):return JSONResponse({'detail':'This local Basecamp account is closed.'},403)
  if request.method in ('GET','HEAD'):
   base=path.removesuffix('/edit')
   with db() as c:relocated=c.execute('SELECT new_path FROM bc_card_relocations WHERE workspace=? AND old_path=?',(account['workspace_id'],base)).fetchone()
   if relocated:
    if not workspaces.allows(account,relocated['new_path']):return JSONResponse({'detail':'You do not have access to this project.'},403)
    return RedirectResponse(relocated['new_path']+('/edit' if path.endswith('/edit') else '')+('?' +request.url.query if request.url.query else ''),307)
  if not workspaces.allows(account,path):return JSONResponse({'detail':'You do not have access to this project.'},403)
  with db() as c:
   if any(trash.erased(c,account['workspace_id'],identifier) for identifier in re.findall(r'/([0-9]+)(?=/|$)',path)):
    return JSONResponse({'detail':'Item not found'},404)
  private_ping=path.startswith(('/api/pings/','/6302022/circles/','/6302022/my/sidebar/circles/'))
  for identifier in ([] if private_ping else re.findall(r'/([0-9]{12,})(?=/|$)',path)):
   with db() as c:exists=c.execute('SELECT 1 FROM bc_records WHERE id=? AND owner=?',(identifier,account['workspace_id'])).fetchone() or c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name=?',(account['workspace_id'],'card-column-'+identifier)).fetchone() or c.execute('SELECT 1 FROM bc_mutations WHERE owner=? AND kind="entity" AND route LIKE ?',(account['workspace_id'],'%/'+identifier)).fetchone()
   if not exists:
    with db() as c:exists=c.execute('SELECT 1 FROM bc_tools WHERE owner=? AND id=?',(account['workspace_id'],identifier)).fetchone()
   if not exists:return JSONResponse({'detail':'Item not found'},404)
  account_page=path=='/6302022/account' or path.startswith('/6302022/account/')
  overview_read=path.rstrip('/')=='/6302022/account' and request.method in ('GET','HEAD','OPTIONS')
  if account_page and not overview_read and account['role'] not in ['owner','admin']:return JSONResponse({'detail':'Only an account administrator can change Adminland settings.'},403)
  if workspaces.owner_action(path) and account['role']!='owner':return JSONResponse({'detail':'Only an account owner can access this account action.'},403)
  personal_project_preference=bool(re.fullmatch(r'/6302022/buckets/\d+/(user_customizations|stars|card_tables/lists/\d+/subscription|recordings/\d+/(?:bubble_up(?:/edit)?|subscription))',path))
  business=path.startswith(('/api/chats/','/api/records','/api/uploads/','/6302022/buckets/','/6302022/projects/')) and not personal_project_preference
  if request.method not in ['GET','HEAD','OPTIONS'] and business and account['role']=='viewer':return JSONResponse({'detail':'You have read-only access to this account.'},403)
 response=await call_next(request)
 if account and not personal_project_preference and not getattr(request.state,'activity_handled',False) and request.method not in ['GET','HEAD','OPTIONS'] and response.status_code<400 and path.startswith(('/6302022/buckets/','/api/chats/','/api/records')):
  activity_search.record_event(db,account,path,getattr(request.state,'activity_method',request.method),urlsplit(request.headers.get('referer','')).path,getattr(request.state,'activity_record',None))
 return response

@app.get('/api/me')
def me(request:Request):
 account=user(request)
 if not account:return JSONResponse({'authenticated':False},status_code=401)
 return {'authenticated':True,'name':account['display_name'],'email':account['email_normalized'],'csrf':csrf_for(session(request)),'account_id':account['account_id'],'workspace_id':account['workspace_id'],'role':account['role']}
@app.get('/api/avatar.svg')
@app.get('/6302022/my/avatar')
def avatar(request:Request):
 account=user(request);name=account['display_name'] if account else 'Dee';person=request.query_params.get('person')
 if person:
  if not account:raise HTTPException(404,'Person not found')
  with db() as c:
   member=c.execute('SELECT a.display_name FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.workspace=? AND m.account=?',(account['workspace_id'],person)).fetchone()
   if not member:
    from record_attribution import historical_person
    member=historical_person(c,account,person,request.query_params.get('recording',''))
  if not member:raise HTTPException(404,'Person not found')
  name=member['display_name']
 letter=html.escape(name[:1].upper())
 return Response(f'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80"><circle cx="40" cy="40" r="40" fill="#4d4d4d"/><text x="40" y="54" text-anchor="middle" font-family="Arial,sans-serif" font-size="43" fill="white">{letter}</text></svg>',media_type='image/svg+xml')
@app.get('/6302022/autocompletables/people/{kind}')
def autocomplete_people(kind:str,request:Request):
 account=require_user(request)
 from task_fields import people
 with db() as c:
  catalog=people(c,account)
  if kind in ('new_administrators','new_owners'):
   rows=workspaces.role_candidates(c,account,kind)
  else:rows=list(catalog.values())
 query=request.query_params.get('q',request.query_params.get('term','')).casefold()
 return [person for person in rows if not query or query in person['name'].casefold()]

@app.get('/6302022/autocompletables/buckets/{bucket}/people/{kind}')
@app.get('/6302022/autocompletables/buckets/{bucket}/people')
def project_autocomplete_people(bucket:str,request:Request,kind:str='users'):
 account=require_user(request)
 if not workspaces.allows(account,'/6302022/buckets/'+bucket+'/'):raise HTTPException(403,'You do not have access to this project.')
 from task_fields import project_people
 with db() as c:rows=list(project_people(c,account,bucket).values())
 query=request.query_params.get('q',request.query_params.get('term','')).casefold()
 return [person for person in rows if not query or query in person['name'].casefold()]

@app.get('/6302022/prompts/people')
def people_prompts(request:Request):
 account=require_user(request)
 return HTMLResponse((ROOT/'frontend/people-prompt.html').read_text().replace('{{name}}',html.escape(account['display_name'])))
@app.get('/6302022/autocompletables/circles/people')
def ping_people(request:Request):
 account=require_user(request)
 from pings import choices
 with db() as c:rows=choices(c,account)
 query=request.query_params.get('q',request.query_params.get('term','')).casefold()
 return [r for r in rows if not query or query in r['name'].casefold()]
@app.get('/6302022/prompts/buckets/{bucket}/people/users')
def bucket_people_prompts(bucket:str,request:Request):
 account=require_user(request)
 return HTMLResponse((ROOT/'frontend/bucket-people-prompt.html').read_text().replace('{{name}}',html.escape(account['display_name'])))
@app.get('/6302022/buckets/{bucket}/recordings/{recording}/drafts.text')
def drafts_text(bucket:str,recording:str,request:Request):
 require_user(request)
 return Response('',media_type='text/plain')
@app.get('/api/state')
def state(request:Request):
 u=require_user(request);owner=u['workspace_id']
 with db() as c:
  settings={r['name']:json.loads(r['value']) for r in c.execute('SELECT name,value FROM bc_settings WHERE owner=?',(u['account_id'],))}
  records=[dict(r) for r in c.execute('SELECT * FROM bc_records WHERE owner=? ORDER BY created',(owner,))]
  mutations=[dict(r) for r in c.execute('SELECT * FROM bc_mutations WHERE owner=?',(owner,))]
  comments=[dict(r) for r in c.execute('SELECT * FROM bc_comments WHERE owner=? ORDER BY created',(owner,))]
 records=[r for r in records if workspaces.allows(u,json.loads(r['data']).get('url',r['parent']))]
 mutations=[r for r in mutations if workspaces.allows(u,r['route']) and not r['route'].startswith('/6302022/my/')]
 with db() as c:mutations += [dict(r) for r in c.execute('SELECT * FROM bc_mutations WHERE owner=? AND route LIKE ?',(u['account_id'],'/6302022/my/%'))]
 comments=[r for r in comments if workspaces.allows(u,r['route'])]
 return {'settings':settings,'records':records,'mutations':mutations,'comments':comments,'name':u['display_name']}
@app.post('/api/settings/{name}')
async def settings(name:str,request:Request):
 u=require_user(request);data=await request.json();csrf_check(request,data)
 if name not in {'theme','grid','notifications'}:raise HTTPException(422,'This preference requires its own settings form.')
 with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(u['account_id'],name,json.dumps(data.get('value'))))
 return {'saved':True}
@app.get('/api/records/{record_id}')
def get_record(record_id:str,request:Request):
 u=require_user(request)
 with db() as c:row=c.execute('SELECT * FROM bc_records WHERE id=? AND owner=?',(record_id,u['workspace_id'])).fetchone()
 if not row or not workspaces.allows(u,json.loads(row['data']).get('url',row['parent'])):raise HTTPException(404,'Record not found')
 return dict(row)
@app.post('/api/records')
async def create_record(request:Request):
 u=require_user(request);d=await request.json();csrf_check(request,d);title=str(d.get('title','')).strip()
 if not title:raise HTTPException(422,'Please enter a title.')
 if not workspaces.allows(u,str(d.get('parent',''))):raise HTTPException(403,'You do not have access to this project.')
 identifier='local-'+secrets.token_hex(8)
 with db() as c:c.execute('INSERT INTO bc_records VALUES(?,?,?,?,?,?,?,?)',(identifier,u['workspace_id'],safe_return(str(d.get('parent',''))),str(d.get('kind','todo')),title,str(d.get('body','')),json.dumps(d.get('data',{})),int(time.time())))
 return {'id':identifier,'url':'/6302022/local/'+identifier}

@app.post('/api/newsletter')
async def newsletter(request:Request):
 data=await request.form();email=str(data.get('EMAIL','')).strip()
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Please enter a valid email address.')
 try:send_mail(email,'Thanks for subscribing to Basecamp news','You subscribed to Basecamp news in your local Basecamp copy. No external mailing list was contacted.\n\n'+ORIGIN)
 except (OSError,smtplib.SMTPException):raise HTTPException(503,'We couldn’t send the confirmation. Please try again.')
 with db() as c:c.execute('INSERT OR REPLACE INTO bc_newsletter VALUES(?,?)',(email,int(time.time())))
 return {'message':'Thanks for subscribing! Check your email.'}

@app.post('/api/uploads/direct')
async def upload_start(request:Request):
 u=require_user(request);data=await request.json();csrf_check(request,data);blob=data.get('blob',data)
 size=int(blob.get('byte_size',0))
 if size<0 or size>100*1024*1024:raise HTTPException(413,'The maximum file size is 100 MB.')
 file_id=secrets.token_urlsafe(24);filename=Path(str(blob.get('filename','attachment'))).name
 with db() as c:c.execute('INSERT INTO bc_files(id,owner,filename,content_type,size,checksum,uploaded,uploader) VALUES(?,?,?,?,?,?,0,?)',(file_id,u['workspace_id'],filename,str(blob.get('content_type','application/octet-stream')),size,str(blob.get('checksum','')),u['account_id']))
 return {'id':file_id,'signed_id':file_id,'key':file_id,'filename':filename,'content_type':blob.get('content_type','application/octet-stream'),'byte_size':size,'checksum':blob.get('checksum',''),'attachable_sgid':file_id,'direct_upload':{'url':ORIGIN+'/api/uploads/'+file_id,'headers':{'X-CSRF-Token':csrf_for(session(request))}}}

@app.put('/api/uploads/{file_id}')
async def upload_bytes(file_id:str,request:Request):
 u=require_user(request);csrf_check(request,{});body=await request.body()
 with db() as c:
  row=c.execute('SELECT * FROM bc_files WHERE id=? AND owner=?',(file_id,u['workspace_id'])).fetchone()
  if not row or row['uploader']!=u['account_id']:raise HTTPException(404,'File not found')
  if row['uploaded']:raise HTTPException(409,'This upload has already been completed. Upload a new version instead.')
  if len(body)!=row['size']:raise HTTPException(422,'The upload size does not match.')
  if row['checksum'] and not hmac.compare_digest(base64.b64encode(hashlib.md5(body).digest()).decode(),row['checksum']):raise HTTPException(422,'The upload checksum does not match.')
  folder=Path(backend.lifecycle.database_path).parent/'uploads';folder.mkdir(parents=True,exist_ok=True)
  (folder/file_id).write_bytes(body);c.execute('UPDATE bc_files SET uploaded=1 WHERE id=?',(file_id,))
 return Response(status_code=204)

@app.get('/files/{file_id}/{filename}')
def download_file(file_id:str,filename:str,request:Request):
 u=require_user(request)
 with db() as c:r=c.execute('SELECT * FROM bc_files WHERE id=? AND owner=? AND uploaded=1',(file_id,u['workspace_id'])).fetchone()
 if not r:raise HTTPException(404,'File not found')
 if u.get('projects') is not None and r['uploader']!=u['account_id']:
  from record_operations import metadata,fields_for
  with db() as c:
   records=[metadata(c,u['workspace_id'],row['id']) for row in c.execute('SELECT id FROM bc_records WHERE owner=? AND kind="uploads"',(u['workspace_id'],))]
   accessible=any(record and workspaces.allows(u,record['url']) and (lambda fields:file_id==fields.get('_file_id') or file_id in fields.get('_versions',[]))(fields_for(c,u['workspace_id'],record)) for record in records)
   if not accessible:
    from record_attachments import accessible as attachment_accessible
    accessible=attachment_accessible(c,u,file_id)
  if not accessible:raise HTTPException(404,'File not found')
 return FileResponse(Path(backend.lifecycle.database_path).parent/'uploads'/file_id,media_type=r['content_type'],filename=r['filename'])

def basic_page(title,content,request,boundary=False):
 token=anon(request);markup=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — Basecamp</title><link rel="stylesheet" href="/static/local.css"></head><body class="local-document" {'data-boundary-page' if boundary else ''}><header><a href="/6302022/">🌄 Basecamp</a> <a href="/">Home</a> <a href="/pricing">Pricing</a> <a href="/help">Support</a></header><main><h1>{html.escape(title)}</h1>{content}</main><footer><a href="javascript:history.back()" data-local-back>← Back</a> · <a href="/6302022/">Basecamp Home</a></footer><script src="/static/local.js" defer></script></body></html>'''
 return cookie(HTMLResponse(markup),token)
@app.get('/external')
def external(request:Request):
 target=request.query_params.get('target','');return HTMLResponse((PAGES/'external/index.html').read_text().replace('{{target}}',html.escape(target,quote=True)))

def route_info(path,query=''):
 if path=='/6302022/my/sidebar/bubble_ups':return ROUTES['/6302022/my/sidebar/inbox']
 full=path+('?' +query if query else '')
 if full in ROUTES:return ROUTES[full]
 if path in ROUTES:return ROUTES[path]
 candidates=[(k,v) for k,v in ROUTES.items() if k.split('?')[0].rstrip('/')==path.rstrip('/')]
 if candidates:return candidates[0][1]
 # Reuse only evidenced structural forms/fragments; never substitute another detail.
 if re.search(r'/(edit|new|options|backlinks|bubble_up|events|subtasks|subscribers|notified_recipients|recording_status)$',path):
  prototype=FAMILIES.get(re.sub(r'/\d+(?=/|$)','/:id',path))
  if prototype:
   old,info=prototype;return {**info,'substitutions':dict(zip(re.findall(r'/(?P<id>\d+)(?=/|$)',old),re.findall(r'/(?P<id>\d+)(?=/|$)',path)))}
 return None
import chat
chat.install(app,db,require_user,user,csrf_check,ROUTES)
import calendar_view
calendar_view.install(app,db,require_user)
activity_search.install(app,db,require_user,csrf_check)
import comment_replies
comment_replies.install(app,db,require_user)
import boost_controls
boost_controls.install(app,db,require_user,csrf_for,session,ROUTES)
import boost_reports
boost_reports.install(app,db,require_user,csrf_check)
import notification_preferences
notification_preferences.install(app,db,require_user,csrf_check)
workspaces.install(app,db,require_user,user,csrf_check,send_mail,ORIGIN,auth_page,form)

import account_operations
account_operations.install(app,db,require_user,csrf_check,send_mail,ORIGIN,basic_page,Path(backend.lifecycle.database_path).parent)

import scheduled_jobs
scheduled_jobs.initialize(db)
import card_wormholes
card_wormholes.initialize(db)
card_wormholes.install(app,db,require_user,csrf_check)
import due_reminders
due_reminders.initialize(db)
import bubble_up
bubble_up.initialize(db)
bubble_up.install(app,db,require_user,csrf_check,lambda request:csrf_for(session(request)))
app.router.lifespan_context=scheduled_jobs.lifespan(db,send_mail,ORIGIN,Path(backend.lifecycle.database_path).parent)

import public_operations
public_operations.install(app,db,csrf_check,send_mail,require_user)
import column_preferences
column_preferences.install(app,db,require_user,csrf_check)

import home_preferences
def home_for_preference(request,account):
 markup=(PAGES/ROUTES['/6302022/']['file']).read_text()
 with db() as c:markup=render_local(markup,'/6302022/',account['workspace_id'],c,account['display_name'],account=account)
 from lxml import html as dom,etree
 tree=dom.fromstring(markup)
 for form_node in tree.xpath('//form'):
  etree.SubElement(form_node,'input',{'type':'hidden','name':'_csrf','value':csrf_for(session(request))})
 return dom.tostring(tree,encoding='unicode')
home_preferences.install(app,db,require_user,csrf_check,home_for_preference)

import pings
pings.install(app,db,require_user,user,csrf_check,lambda request:page('6302022/',request),Path(backend.lifecycle.database_path).parent,lambda request:csrf_for(session(request)))

@app.get('/6302022/buckets/49234166/dock/tools/10398823035/name/edit')
def sample_tool_name(request:Request):
 require_user(request)
 raise HTTPException(403,'The sample project does not provide access to this tool-name form.')

@app.get('/{path:path}')
def page(path:str,request:Request):
 path='/'+path
 if path==bubble_up.OVERVIEW:
  account=require_user(request)
  with db() as c:reminders=bubble_up.pending(c,account,include_future=True)
  if not reminders:return RedirectResponse(bubble_up.INBOX,303)
 if path=='/favicon.ico':return FileResponse(ROOT/UI['logo'].lstrip('/'))
 if path.startswith(('/6302022/','/identity/','/two_factor_authentication/','/launchpad/','/settings/','/activity_logs')) and not user(request):return RedirectResponse('/signin?'+urlencode({'return_to':path+('?' +request.url.query if request.url.query else '')}),303)
 if path in DOWNLOADS:
  item=DOWNLOADS[path];return FileResponse(ROOT/'static/assets'/item['file'],filename=item['name'],media_type=item['type'])
 xhr_key=path+('?' + request.url.query if request.url.query else '');xhr_substitutions={}
 if xhr_key not in XHR:xhr_key=path
 if xhr_key not in XHR:
  family=re.sub(r'/\d+(?=/|$)','/:id',path)
  prototype=next((key for key in XHR if '?' not in key and re.sub(r'/\d+(?=/|$)','/:id',key)==family),None)
  if prototype:xhr_key=prototype;xhr_substitutions=dict(zip(re.findall(r'/([0-9]+)(?=/|$)',prototype),re.findall(r'/([0-9]+)(?=/|$)',path)))
 if xhr_key in XHR and (request.headers.get('x-requested-with')=='XMLHttpRequest' or 'turbo-stream' in request.headers.get('accept','')):
  item=XHR[xhr_key];fragment=(ROOT/'frontend/xhr'/item['file']).read_text().replace('__LOCAL_CSRF__',csrf_for(session(request)))
  for old,new in xhr_substitutions.items():fragment=fragment.replace(old,new)
  return Response(fragment,media_type=item['type'])
 export=re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/(folder_exports|attachment_exports)',path)
 if export:
  from lxml import html as lhtml
  require_user(request);record_id=export[2];matches=[i for route,i in ROUTES.items() if re.search(r'/(vaults|messages|documents)/'+record_id+'$',route)]
  if not matches:raise HTTPException(404,'Folder not found')
  tree=lhtml.fromstring((PAGES/matches[0]['file']).read_text());files={urlsplit(a.get('href')).path.rsplit('/',1)[-1] for a in tree.xpath('//a[starts-with(@href,"/static/assets/")]')};output=io.BytesIO()
  with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
   used=set()
   for filename in sorted(files):
    file=ROOT/'static/assets'/filename
    if not file.is_file():continue
    name=ASSET_NAMES.get(filename,filename)
    if name in used:name=filename
    used.add(name);archive.writestr(name,file.read_bytes())
  return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="basecamp-files.zip"'})
 if path.startswith('/6302022/local/'):
  u=require_user(request)
  with db() as c:r=c.execute('SELECT * FROM bc_records WHERE id=? AND owner=?',(path.rsplit('/',1)[-1],u['workspace_id'])).fetchone()
  if not r:raise HTTPException(404,'Record not found')
  return basic_page(r['title'],safe_rich_text(r['body'])+'<a href="'+html.escape(r['parent'],quote=True)+'">Back to project</a>',request)
 info=None
 if user(request):
  from record_operations import dynamic_info
  with db() as c:info=dynamic_info(c,user(request)['workspace_id'],path,ROUTES)
 if not info and user(request):
  from card_table import dynamic_info as dynamic_column_info
  with db() as c:info=dynamic_column_info(c,user(request)['workspace_id'],path,ROUTES)
 if not info and user(request):
  from settings_operations import dynamic_info as dynamic_settings_info
  with db() as c:info=dynamic_settings_info(c,user(request)['workspace_id'],path,ROUTES)
 if not info and user(request):
  with db() as c:info=tool_operations.dynamic_info(c,user(request)['workspace_id'],path,ROUTES)
 if not info:info=route_info(path,request.url.query)
 if info and info.get('local_record') and not workspaces.allows(user(request),info['local_record']['url']):raise HTTPException(403,'You cannot access this project.')
 if not info:
  if re.match(r'^/help/(5|2|classic)/article/',path):return basic_page('Basecamp Help','<p>This article is beyond the first five captured details in its collection.</p><p>Article: '+html.escape(path.rsplit('/',1)[-1])+'</p><p><a href="'+html.escape(safe_return(urlsplit(request.headers.get('referer','')).path),quote=True)+'">Return to the source collection</a></p>',request,True)
  if re.match(r'^/2914079/',path):return RedirectResponse('/6302022/',303)
  raise HTTPException(404,'Page not found')
 if info['auth'] and not user(request):return RedirectResponse('/signin?'+urlencode({'return_to':path}),303)
 if info.get('final_route')=='/6302022/' and not path.startswith('/6302022/'):return RedirectResponse('/6302022/',303)
 token=anon(request);text=(PAGES/(info.get('component_file',info['file']) if request.headers.get('turbo-frame') else info['file'])).read_text()
 # The native draft store calls new URL(key) without a base. Captured local
 # paths therefore need the current origin before the form connects.
 text=re.sub(r'data-autosave-key="(/[^\"]*)"',lambda m:'data-autosave-key="'+html.escape(str(request.base_url).rstrip('/')+html.unescape(m[1]),quote=True)+'"',text)
 if info['auth'] and not (info.get('component') or request.headers.get('turbo-frame') or request.headers.get('x-requested-with')=='XMLHttpRequest'):
  text=re.sub(r'<turbo-cable-stream-source\b.*?</turbo-cable-stream-source>','',text,flags=re.S)
  text=re.sub(r'<meta[^>]+name="action-cable-url"[^>]*>','',text)
  native=''.join('<script defer data-turbo-eval="false" src="/static/native/'+name+'"></script>' for name in ['658ddc860be15de4de7a.js','6605b7e0ce16110fc631.js','ab4c48cd470e61d37c47.js'])
  text=text.replace('<script defer src="/static/local.js"></script>',native+'<script defer data-turbo-eval="false" src="/static/native-bridge.js"></script><script defer data-turbo-eval="false" src="/static/column-preferences.js"></script><script defer data-turbo-eval="false" src="/static/chat.js"></script><link rel="stylesheet" href="/static/ping-actions.css">')
  text=text.replace('</head>','<meta name="cable-url" content="/cable"><meta name="csrf-param" content="_csrf"><meta name="csrf-token" content="'+csrf_for(token)+'"><meta name="turbo-cache-control" content="no-cache"></head>')
 if info.get('component') or request.headers.get('turbo-frame'):
  text=re.sub(r'<script\b.*?</script>','',text,flags=re.S)
 for old,new in info.get('substitutions',{}).items():text=text.replace(old,new)
 if info.get('local_tool'):text=tool_operations.prepare(text,info['local_tool'])
 if info.get('local_column'):
  from card_table import prepare_column
  text=prepare_column(text)
 if info.get('form_action'):
  action=info['form_action'];text=text.replace('action="'+action['from']+'"','action="'+action['to']+'"')
 text=re.sub(r'(<form\b[^>]*>)',lambda m:m[1]+'<input type="hidden" name="_csrf" value="'+csrf_for(token)+'">',text)
 text=text.replace('</head>','<meta name="local-csrf" content="'+csrf_for(token)+'"></head>')
 text=text.replace('</head>','<meta name="csp-nonce" content="'+digest('basecamp-script:'+str(token))+'"></head>')
 account=user(request)
 if path=='/6302022/account/exports/new' and request.query_params.get('ready')=='1':text=text.replace('<main', '<p role="status">Your export is ready. Check your email for the download link.</p><main',1)
 if account:
  with db() as c:workspace=c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="account_name"',(account['workspace_id'],)).fetchone()
  if workspace:text=text.replace('Dee Basecamp',html.escape(json.loads(workspace['value'])))
  text=re.sub(r'\bDee\b',lambda _:html.escape(account['display_name']),text);text=text.replace('demo@basecamp.offline.invalid',html.escape(account['email_normalized']))
  if info['auth'] or path.startswith(('/6302022/','/identity/','/settings/','/launchpad/')):
   with db() as c:text=render_local(text,path,account['workspace_id'],c,account['display_name'],request.query_params,account)
 text=re.sub(r'(<turbo-frame\b[^>]*?)\s+src="'+re.escape(path)+r'(?:\?[^"]*)?"',r'\1',text)
 text=re.sub(r'(<form\b[^>]*>)(?!<input type="hidden" name="_csrf")',lambda m:m[1]+'<input type="hidden" name="_csrf" value="'+csrf_for(token)+'">',text)
 with db() as c:text=public_operations.render(text,path,request.query_params,account,c)
 # Native calendar navigation fetches ?modal=true and expects only a dialog.
 # Returning the whole document duplicates the shell and hides the event form.
 if request.query_params.get('modal')=='true' and (path=='/6302022/calendar/entries/new' or re.fullmatch(r'/6302022/buckets/\d+/schedules/\d+/entries/new',path)):
  from lxml import html as lhtml, etree
  forms=lhtml.fromstring(text).xpath('//form[@id="form_schedule_entry"]')
  if forms:
   dialog=etree.Element('dialog',{'class':'modal-viewport','data-show-modal':'','aria-label':'Create a new event'})
   dialog.append(forms[0]);text=lhtml.tostring(dialog,encoding='unicode')
 # The native desktop modal expects the captured sheet, not a full document.
 if re.fullmatch(r'/6302022/projects/\d+/status',path) and request.headers.get('x-requested-with')=='XMLHttpRequest':
  from lxml import html as lhtml
  sheet=lhtml.fromstring(text).xpath('//*[@data-show-modal]')
  if sheet:text=lhtml.tostring(sheet[0],encoding='unicode')
 response=cookie(HTMLResponse(text),token)
 if account and not (info.get('component') or request.headers.get('turbo-frame') or request.headers.get('x-requested-with')=='XMLHttpRequest'):
  with db() as c:column_preferences.apply_cookie(response,c,account,SECURE)
  with db() as c:preferences={r['name']:json.loads(r['value']) for r in c.execute('SELECT name,value FROM bc_settings WHERE owner=? AND name IN ("theme","grid")',(account['account_id'],))}
  theme=preferences.get('theme');theme=int(theme) if str(theme).isdigit() and 1<=int(theme)<=6 else 1
  response.set_cookie('page_tint_6302022',str(theme),samesite='lax',secure=SECURE,path='/')
  if preferences.get('grid'):response.set_cookie('home_layout_grid','1',samesite='lax',secure=SECURE,path='/')
  else:response.delete_cookie('home_layout_grid',path='/')
 return response

@app.api_route('/{path:path}',methods=['POST','PUT','PATCH','DELETE'])
async def mutation(path:str,request:Request):
 path='/'+path
 data=await request.json() if 'application/json' in request.headers.get('content-type','') else await request.form();csrf_check(request,data);u=require_user(request);owner=u['account_id'] if path.startswith('/6302022/my/') or path=='/6302022/out_of_office' else u['workspace_id']
 # Private conversation writes must have a dedicated participant-aware route.
 # Never let an unsupported native action enter workspace-wide form storage.
 if any(path==root or path.startswith(root+'/') for root in ('/api/pings','/6302022/circles','/6302022/my/sidebar/circles')):raise HTTPException(501,'This Ping action is not available yet.')
 if not path.startswith('/6302022/my/') and path!='/6302022/out_of_office' and not re.fullmatch(r'/6302022/buckets/\d+/(?:recordings|card_tables/lists)/\d+/subscription',path):workspaces.writable(u)
 if path.startswith('/6302022/account/'):workspaces.manager(u)
 if any('password' in k.casefold() for k in data):raise HTTPException(501,'This password action is unavailable.')
 payload={k:v if isinstance(v,(dict,list)) else str(v) for k,v in data.items() if k not in {'_csrf','authenticity_token','_method'}};payload={**dict(request.query_params),**payload};referer=safe_return(urlsplit(request.headers.get('referer','')).path);method=str(data.get('_method',request.method)).upper()
 request.state.activity_method=method
 from project_lifecycle import mutate as mutate_project
 with db() as c:project_change=mutate_project(c,u,path,method)
 if project_change:
  trash.cleanup_files(db,Path(backend.lifecycle.database_path).parent)
  await app.state.revoke_chat_rooms(u['workspace_id'],project_change.pop('chat_rooms'))
  request.state.activity_handled=True
  if request.headers.get('accept')=='application/json':return project_change
  if 'javascript' in request.headers.get('accept',''):return Response('Turbo.visit('+json.dumps(project_change['redirect'])+');',media_type='text/javascript')
  return RedirectResponse(project_change['redirect'],303)
 with db() as c:trash_change=trash.mutate(c,u,path,method)
 if trash_change:
  trash.cleanup_files(db,Path(backend.lifecycle.database_path).parent)
  request.state.activity_handled=True
  if request.headers.get('accept')=='application/json':return trash_change
  return RedirectResponse(trash_change['redirect'],303)
 if hasattr(data,'getlist'):
  for key in data:
   if '[]' in key:payload[key]=data.getlist(key)
 if path=='/6302022/account/enrollments/employees' or re.fullmatch(r'/6302022/projects/\d+/invitations/users',path):
  names=payload.get('people[][name]',[]);emails=payload.get('people[][email_address]',[])
  if not isinstance(names,list):names=[names]
  if not isinstance(emails,list):emails=[emails]
  invitees=payload.get('invitees[]',[]);invitees=invitees if isinstance(invitees,list) else [invitees]
  people=[{'email':email,'name':names[i] if i<len(names) else ''} for i,email in enumerate(emails) if email.strip()]+[{'email':email} for email in invitees if email.strip()]
  count=workspaces.enroll(db,u,people,send_mail,ORIGIN,path.split('/')[3] if '/projects/' in path else '')
  if request.headers.get('accept')=='application/json':return {'sent':count}
  return RedirectResponse('/6302022/account/people' if '/account/' in path else referer,303)
 with db() as c:social_change=social_operations.mutate(c,u,path,payload,method,referer)
 if social_change:
  if request.headers.get('accept')=='application/json':return social_change
  if 'javascript' in request.headers.get('accept',''):return Response('Turbo.visit('+json.dumps(social_change['redirect'])+');',media_type='text/javascript')
  return RedirectResponse(social_change['redirect'],303)
 with db() as c:tool_change=tool_operations.mutate(c,owner,path,payload,method)
 if tool_change:
  if request.headers.get('accept')=='application/json':return tool_change
  return RedirectResponse(tool_change['redirect'],303)
 from task_fields import mutate as mutate_assignment
 with db() as c:assignment_change=mutate_assignment(c,u,path,payload,method)
 if assignment_change:
  request.state.activity_handled=assignment_change.get('activity_handled',False)
  if assignment_change.get('no_content'):return Response(status_code=204)
  if request.headers.get('accept')=='application/json':return {'saved':True,**assignment_change}
  if 'javascript' in request.headers.get('accept',''):return Response('Turbo.visit('+json.dumps(assignment_change['redirect'])+');',media_type='text/javascript')
  return RedirectResponse(assignment_change['redirect'],303)
 payment_change=payment_operations.mutate(db,backend,u,path,payload)
 if payment_change:
  if request.headers.get('accept')=='application/json':return payment_change
  return RedirectResponse(payment_change['redirect'],303)
 from comment_operations import mutate as mutate_comment
 with db() as c:comment_change=mutate_comment(c,u,path,payload,method)
 if comment_change:
  if request.headers.get('accept')=='application/json':return {'saved':True,**comment_change}
  if 'turbo-stream' in request.headers.get('accept',''):
   return Response('<turbo-stream action="local_visit" url="'+html.escape(comment_change['redirect'],quote=True)+'"></turbo-stream>',media_type='text/vnd.turbo-stream.html')
  if 'javascript' in request.headers.get('accept',''):return Response('Turbo.visit('+json.dumps(comment_change['redirect'])+');',media_type='text/javascript')
  return RedirectResponse(comment_change['redirect'],303)
 from settings_operations import mutate as mutate_settings
 with db() as c:settings_change=mutate_settings(c,owner,path,payload,method,u)
 if settings_change:
  if request.headers.get('accept')=='application/json':return {'saved':True,**settings_change}
  if 'javascript' in request.headers.get('accept',''):return Response('Turbo.visit('+json.dumps(settings_change['redirect'])+');',media_type='text/javascript')
  return RedirectResponse(settings_change['redirect'],303)
 from card_table import mutate_column
 with db() as c:column_change=mutate_column(c,owner,path,payload,method)
 if column_change:
  if request.headers.get('accept')=='application/json':return {'saved':True,**column_change}
  return RedirectResponse(column_change['redirect'],303)
 from file_operations import mutate as mutate_file
 with db() as c:file_change=mutate_file(c,owner,path,payload,method)
 if file_change:
  if 'json' in file_change:return file_change['json']
  if request.headers.get('accept')=='application/json':return {'saved':True,**file_change}
  return RedirectResponse(file_change['redirect'],303)
 from record_operations import mutate as mutate_record
 with db() as c:record_change=mutate_record(c,owner,path,payload,method,referer,u)
 if record_change:
  request.state.activity_record=record_change['record']
  request.state.activity_handled=record_change.get('activity_handled',False)
  destination=record_change['redirect']
  if request.headers.get('accept')=='application/json':return {'saved':True,'redirect':destination}
  if 'javascript' in request.headers.get('accept',''):return Response('Turbo.visit('+json.dumps(destination)+');',media_type='text/javascript')
  return RedirectResponse(destination,303)
 from card_table import move as move_card
 with db() as c:moved=move_card(c,u,path,payload,method)
 if moved:
  request.state.activity_handled=True
  destination=moved['redirect'] if isinstance(moved,dict) else referer
  if request.headers.get('accept')=='application/json':return {'saved':True,'redirect':destination}
  if 'source_id' in payload:return Response(status_code=204)
  return RedirectResponse(destination,303)
 welcome=next((r for r in WELCOME if r['unread_path']==path),None)
 if welcome:
  with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(owner,'welcome-read-'+welcome['id'],json.dumps(method=='DELETE')))
  return Response(status_code=204)
 if '/comments' in path and any('content'in k for k in payload):
  body=next((v for k,v in payload.items() if 'content'in k),'').strip()
  if not body:raise HTTPException(422,'Please write a comment.')
  raise HTTPException(404,'The item to comment on was not found.')
 elif re.search(r'/(todos|messages|documents|entries|cards|projects|todolists)$',path):
  title=next((v for k,v in payload.items() if re.search(r'\[(subject|title|name|summary)\]$',k)),payload.get('todo[content]',payload.get('title',''))).strip()
  if not title:raise HTTPException(422,'Please enter a title.')
  identifier='local-'+secrets.token_hex(8);parent=referer.split('/new')[0];body=next((v for k,v in payload.items() if any(s in k for s in ['description','notes','body']) or (k.endswith('[content]') and k!='todo[content]')),'')
  if re.search(r'/(message_boards|todolists|vaults|schedules)/\d+/(messages|todos|documents|entries)$',path):parent=path.rsplit('/',1)[0]
  with db() as c:c.execute('INSERT INTO bc_records VALUES(?,?,?,?,?,?,?,?)',(identifier,owner,parent,path.rsplit('/',1)[-1],title,body,json.dumps(payload),int(time.time())))
  referer='/6302022/local/'+identifier
 else:
  kind='bookmarks' if '/my/bookmarks/' in path else path.rsplit('/',1)[-1]
  if path=='/6302022/account/name' and payload.get('account[name]','').strip():
   with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(owner,'account_name',json.dumps(payload['account[name]'].strip())))
  if kind=='bookmarks':
   local_bookmark=re.fullmatch(r'/6302022/my/bookmarks/local-(\d+)',path)
   tool_bookmark=re.fullmatch(r'/6302022/my/bookmarks/local-tool-(\d+)',path)
   if tool_bookmark:
    with db() as c:target=tool_operations.bookmark_target(c,u['workspace_id'],tool_bookmark[1])
    if not workspaces.allows(u,target['url']):raise HTTPException(403,'You cannot access this project.')
    referer=target['url'];payload['title']=target['title']
   elif local_bookmark:
    from record_operations import metadata,fields_for,PREFIX,TITLE
    with db() as c:
     record=metadata(c,u['workspace_id'],local_bookmark[1])
     if not record or not record.get('is_new'):raise HTTPException(404,'Bookmark item not found')
     if not workspaces.allows(u,record['url']):raise HTTPException(403,'You cannot access this project.')
     state=fields_for(c,u['workspace_id'],record)
    referer=record['url'];payload['title']=state.get(PREFIX[record['kind']]+'['+TITLE[record['kind']]+']',record['title'])
   else:payload['title']=ROUTES.get(referer,{}).get('title','Bookmark')
   payload['recording_path']=referer
  with db() as c:
   old=c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind=?',(owner,path,kind)).fetchone()
   if kind in ('stars','completion','completed','bookmarks','on_hold'):payload['active']=method!='DELETE'
   c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,path,kind,json.dumps(payload),int(time.time())))
   if path=='/6302022/my/profile' and payload.get('person[name]','').strip():c.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(payload['person[name]'].strip(),u['account_id']))
 if path.endswith('/completion') or path.endswith('/recent_visit'):return Response(status_code=204)
 if request.headers.get('accept')=='application/json':return {'saved':True,'redirect':referer}
 if path=='/6302022/my/navigation/notes':return Response(status_code=204)
 return RedirectResponse(referer,303)
