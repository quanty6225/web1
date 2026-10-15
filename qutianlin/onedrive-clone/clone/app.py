"""OneDrive local application: isolated SQLite state, SMTP and offline assets."""
from __future__ import annotations
import os,json,secrets,time,uuid,smtplib,re,hashlib,hmac,mimetypes,sqlite3,io,zipfile,tempfile
from pathlib import Path
from contextvars import ContextVar
from contextlib import asynccontextmanager
from email.message import EmailMessage
from urllib.parse import urlsplit,quote
from fastapi import FastAPI,Request,HTTPException,UploadFile,File
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,Response,FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from office_documents import TEXT_KINDS,original_office as office_bytes,extract_text
from file_storage import FileStorage,UploadTooLarge,MAX_FILE_BYTES
from backend.site_backend_integration import open_site_services
from websitebench.local_clone_auth.store import AuthRejected,AuthConflict,AuthExpired,AuthValidationError,AuthRateLimited,_hash_secret
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('ONEDRIVE_DATA_DIR',str(ROOT/'data'))).resolve();DATA.mkdir(parents=True,exist_ok=True)
FILE_STORAGE=FileStorage(DATA)
DRIVE_QUOTA=5*1024**3
os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(DATA/'onedrive.sqlite3'))
os.environ.setdefault('ONEDRIVE_MAIL_WORKER_TOKEN',secrets.token_urlsafe(32))
WORKER=os.environ['ONEDRIVE_MAIL_WORKER_TOKEN']
backend,auth=open_site_services()
COOKIE='onedrive_session'
SECURE=os.environ.get('ONEDRIVE_TLS')=='1'
REQUEST_TOKEN=ContextVar('request_token',default=None)
ASSET_MIME=json.loads((ROOT/'content/asset-mime.json').read_text())
@asynccontextmanager
async def lifespan(application):
 with db() as connection:
  application.state.storage_recovery=FILE_STORAGE.collect_unused(connection)
 yield

app=FastAPI(docs_url=None,redoc_url=None,lifespan=lifespan)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
DEMO_EMAIL='demo@onedrive.offline.invalid';DEMO_PASSWORD='OneDrive-Demo-2026!'
DEMO=auth.seed_account(subject_id='onedrive-demo',email=DEMO_EMAIL,display_name='演示用户',password=DEMO_PASSWORD)
def db():return auth.connect()
with db() as c:
 c.executescript('''
 CREATE TABLE IF NOT EXISTS drive_files(id TEXT PRIMARY KEY,owner TEXT NOT NULL,parent TEXT,name TEXT NOT NULL,kind TEXT NOT NULL,size INTEGER NOT NULL DEFAULT 0,modified TEXT NOT NULL,created TEXT NOT NULL,content BLOB,source_id TEXT,full_detail INTEGER DEFAULT 1,deleted INTEGER DEFAULT 0,favorite INTEGER DEFAULT 0,position INTEGER DEFAULT 0);
 CREATE INDEX IF NOT EXISTS files_owner_parent ON drive_files(owner,parent);
 CREATE TABLE IF NOT EXISTS preferences(owner TEXT PRIMARY KEY,body TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS account_profiles(owner TEXT PRIMARY KEY,first_name TEXT NOT NULL,last_name TEXT NOT NULL,birth_date TEXT NOT NULL DEFAULT '',country TEXT NOT NULL DEFAULT '');
 CREATE TABLE IF NOT EXISTS account_photos(owner TEXT PRIMARY KEY,content BLOB NOT NULL);
 CREATE TABLE IF NOT EXISTS account_language_settings(owner TEXT PRIMARY KEY,body TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_file_appearance(file_id TEXT PRIMARY KEY,owner TEXT NOT NULL,color TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_document_edits(file_id TEXT PRIMARY KEY,owner TEXT NOT NULL,body TEXT NOT NULL,modified TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_file_blobs(file_id TEXT PRIMARY KEY,owner TEXT NOT NULL,blob_key TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS file_blobs_key ON drive_file_blobs(blob_key);
 CREATE TABLE IF NOT EXISTS drive_shares(token TEXT PRIMARY KEY,file_id TEXT NOT NULL,owner TEXT NOT NULL,mode TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_share_bundles(token TEXT PRIMARY KEY,owner TEXT NOT NULL,mode TEXT NOT NULL,created INTEGER NOT NULL,items TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_share_options(token TEXT PRIMARY KEY,owner TEXT NOT NULL,audience TEXT NOT NULL,recipients TEXT NOT NULL,message TEXT NOT NULL DEFAULT '');
 CREATE TABLE IF NOT EXISTS drive_comments(id TEXT PRIMARY KEY,file_id TEXT NOT NULL,owner TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_albums(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS drive_album_files(album_id TEXT NOT NULL,file_id TEXT NOT NULL,owner TEXT NOT NULL,position INTEGER NOT NULL,PRIMARY KEY(album_id,file_id));
 CREATE TABLE IF NOT EXISTS seeded(owner TEXT PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS seed_catalog(owner TEXT NOT NULL,seed_id TEXT NOT NULL,PRIMARY KEY(owner,seed_id));
 CREATE TABLE IF NOT EXISTS sandbox_orders(id TEXT PRIMARY KEY,owner TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS local_feedback(id TEXT PRIMARY KEY,owner TEXT,body TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS vault_sessions(digest TEXT PRIMARY KEY,expires INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS cookie_preferences(digest TEXT PRIMARY KEY,persistent INTEGER NOT NULL);
 ''')
def install_captured_seed_content(c,seed,body):
 row=c.execute('SELECT content,source_id,modified FROM drive_files WHERE id=? AND owner=?',(seed['id'],DEMO)).fetchone()
 if not row:return
 if row['content'] is None:
  c.execute('UPDATE drive_files SET content=?,size=? WHERE id=? AND owner=?',(body,seed.get('bytes',len(body)),seed['id'],DEMO));return
 # Earlier local-equivalent notebook edits lived directly in the text BLOB.
 # Preserve them as annotations when the real captured notebook becomes available.
 if seed['id']=='notebook' and row['source_id']=='notebook' and body.startswith(b'PK\x03\x04') and not bytes(row['content']).startswith((b'PK\x03\x04',b'\xe4\x52\x5c\x7b')):
  try:text=bytes(row['content']).decode('utf8')
  except UnicodeDecodeError:return
  if len(text)>2000000:return
  c.execute('INSERT OR IGNORE INTO drive_document_edits VALUES(?,?,?,?)',(seed['id'],DEMO,text,row['modified']))
  c.execute('UPDATE drive_files SET content=?,size=? WHERE id=? AND owner=?',(body,seed.get('bytes',0),seed['id'],DEMO))

seedpath=ROOT/'content/seed.json'
if seedpath.exists():
 with db() as c:
  seed_data=json.loads(seedpath.read_text())
  already_seeded=bool(c.execute('SELECT 1 FROM seeded WHERE owner=?',(DEMO,)).fetchone())
  catalog_file=ROOT/'content/seed-initial-ids.json'
  if already_seeded and not c.execute('SELECT 1 FROM seed_catalog WHERE owner=?',(DEMO,)).fetchone():
   # Old versions seeded these once. Preserve any files the demo user has since purged.
   initial=json.loads(catalog_file.read_text()) if catalog_file.exists() else [f['id'] for f in seed_data]
   c.executemany('INSERT OR IGNORE INTO seed_catalog VALUES(?,?)',[(DEMO,fid) for fid in initial])
  for i,f in enumerate(seed_data):
   if c.execute('SELECT 1 FROM seed_catalog WHERE owner=? AND seed_id=?',(DEMO,f['id'])).fetchone():
    if f.get('full_detail'):
     c.execute('UPDATE drive_files SET full_detail=1 WHERE owner=? AND source_id=? AND full_detail=0',(DEMO,f['id']))
    continue
   blob=None
   if f.get('content_file') and (ROOT/'content'/f['content_file']).exists():blob=(ROOT/'content'/f['content_file']).read_bytes()
   c.execute('INSERT OR IGNORE INTO drive_files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f['id'],DEMO,f.get('parent'),f['name'],f['kind'],f.get('bytes',0),f.get('modified',''),f.get('created',f.get('modified','')),blob,f['id'],int(f.get('full_detail',True)),0,0,i))
   c.execute('INSERT INTO seed_catalog VALUES(?,?)',(DEMO,f['id']))
  c.execute('INSERT OR IGNORE INTO seeded VALUES(?)',(DEMO,))

# Add newly captured source bytes only where no local content exists.
if seedpath.exists():
 with db() as c:
  for f in json.loads(seedpath.read_text()):
   if f.get('created'):c.execute("UPDATE drive_files SET created=? WHERE id=? AND owner=? AND created=''",(f['created'],f['id'],DEMO))
   content_path=ROOT/'content'/f.get('content_file','__unavailable__')
   if content_path.is_file():
    blob=content_path.read_bytes()
    install_captured_seed_content(c,f,blob)

# Correct captured identity only in untouched seed bytes. Preserve local document edits.
redactions=ROOT/'content/seed-content-redactions.json'
if redactions.exists():
 with db() as c:
  for correction in json.loads(redactions.read_text()):
   item=c.execute('SELECT id,content FROM drive_files WHERE owner=? AND source_id=?',(DEMO,correction['source_id'])).fetchone()
   if item and item['content'] is not None and hashlib.sha256(item['content']).hexdigest()==correction['previous_sha256']:
    body=(ROOT/'content'/correction['content_file']).read_bytes()
    c.execute('UPDATE drive_files SET content=? WHERE id=? AND owner=?',(body,item['id'],DEMO))

def session(request,required=True):
 token=request.cookies.get(COOKIE);s=auth.resolve_session(token)
 if required and (not s or not s['authenticated']):raise HTTPException(401,'请先登录')
 return token,s

def owner(request):return session(request)[1]['account']['account_id']
def set_cookie(response,token):
 with db() as c:pref=c.execute('SELECT persistent FROM cookie_preferences WHERE digest=?',(auth.session_owner_digest(token),)).fetchone()
 response.set_cookie(COOKIE,token,httponly=True,samesite='lax',secure=SECURE,path='/',max_age=86400*7 if not pref or pref['persistent'] else None)
 return response

def csrf(token):return hashlib.sha256(('onedrive-csrf:'+token).encode()).hexdigest()
def local_next(p):return p if p and p.startswith('/') and not p.startswith('//') and '\\' not in p else '/'

@app.middleware('http')
async def protect(request,call_next):
 if request.method not in ['GET','HEAD','OPTIONS']:
  origin=request.headers.get('origin')
  if origin and origin!=str(request.base_url).rstrip('/'):return JSONResponse({'detail':'请求来源无效'},403)
  token=request.cookies.get(COOKIE)
  if not token or not hmac.compare_digest(request.headers.get('x-csrf-token',''),csrf(token)):
   return JSONResponse({'detail':'会话已过期，请刷新页面后重试'},403)
  if request.url.path=='/api/upload':
   authenticated=auth.resolve_session(token)
   if not authenticated or not authenticated['authenticated']:return JSONResponse({'detail':'请先登录'},401)
   length=request.headers.get('content-length')
   if length:
    try:declared=int(length)
    except ValueError:return JSONResponse({'detail':'上传长度无效'},400)
    with db() as c:remaining=max(0,DRIVE_QUOTA-storage_used(c,authenticated['account']['account_id']))
    # Allow multipart metadata overhead here; the transaction checks exact
    # original file bytes. This avoids spooling plainly over-quota requests.
    if declared>remaining+2*1024*1024:return JSONResponse({'detail':'OneDrive 存储空间不足。请释放空间后重试。'},413)
 context=REQUEST_TOKEN.set(request.cookies.get(COOKIE))
 try:response=await call_next(request)
 finally:REQUEST_TOKEN.reset(context)
 response.headers['Cache-Control']='no-store' if not request.url.path.startswith('/static') else 'public, max-age=3600'
 response.headers['X-Content-Type-Options']='nosniff'
 if request.url.path.startswith('/static/assets/') and request.url.path.rsplit('/',1)[-1] in ASSET_MIME:response.headers['Content-Type']=ASSET_MIME[request.url.path.rsplit('/',1)[-1]]
 response.headers['Referrer-Policy']='no-referrer'
 response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; media-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; form-action 'self'; base-uri 'self'; frame-ancestors 'self'"
 return response

@app.exception_handler(AuthRejected)
@app.exception_handler(AuthConflict)
@app.exception_handler(AuthExpired)
@app.exception_handler(AuthValidationError)
@app.exception_handler(AuthRateLimited)
async def auth_error(request,exc):
 msg='That code didn\'t work. Take another look and try again.'
 if isinstance(exc,AuthExpired):msg='This code has expired. Request a new code.'
 elif isinstance(exc,AuthConflict):msg='This account already exists or this step has already been completed.'
 elif isinstance(exc,AuthValidationError):msg='Please enter a valid email address and a password of at least 8 characters.'
 elif isinstance(exc,AuthRateLimited):msg='Too many attempts. Please try again later.'
 elif 'credentials' in str(exc):msg='Your account or password is incorrect. If you don\'t remember your password, reset it now.'
 return JSONResponse({'detail':msg},400)

@app.get('/healthz')
@app.get('/__websitebench/health')
def health():return {'status':'ok','site_id':'onedrive'}
@app.get('/api/session')
def get_session(request:Request):
 token,s=auth.ensure_session(request.cookies.get(COOKIE))
 return set_cookie(JSONResponse({'authenticated':s['authenticated'],'account':s['account'],'csrf':csrf(token)}),token)

def smtp_message(to,subject,text):
 host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
 if host not in ['127.0.0.1','localhost','::1']:raise HTTPException(503,'SMTP must use the local Mailpit service.')
 m=EmailMessage();m['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@onedrive.clone.test');m['To']=to;m['Subject']=subject;m['X-Clone-Site']='onedrive';m.set_content(text)
 try:
  with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=8) as s:
   rejected=s.send_message(m)
   if rejected:raise smtplib.SMTPRecipientsRefused(rejected)
 except (OSError,smtplib.SMTPException):raise HTTPException(503,'Email could not be sent. Please try again.')

def deliver(token,purpose,base):
 claim=auth.claim_pending_mail_for_session(token,purpose=purpose,worker_token=WORKER)
 if not claim:
  if auth.session_mail_status(token,purpose=purpose)=='SMTP_SENT':return
  raise HTTPException(503,'Email could not be sent. Please request a new code.')
 mid=claim['mail_id'];ct=claim['claim_token']
 auth.reserve_mail_target_request(mid,ct,worker_token=WORKER)
 try:
  mail=backend.mail.issue(purpose,claim['recipient'],{'code':claim['verification_code'],'minutes':'10'})
  # Links remain on this local origin; verification is bound to the initiating session.
  link=base.rstrip('/')+'/verify?purpose='+purpose
  smtp_message(claim['recipient'],mail['subject'],mail['text']+'\n\n'+link)
 except Exception:
  auth.finish_mail_claim(mid,ct,sent=False,error='network',worker_token=WORKER)
  raise
 auth.finish_mail_claim(mid,ct,sent=True,accepted_request_count=1,worker_token=WORKER)

@app.post('/api/auth/{action}')
async def auth_action(action:str,request:Request):
 token,s=session(request,False)
 if not s:raise HTTPException(401,'Session expired')
 d=await request.json();email=d.get('email','').strip().lower()
 if action=='lookup':return {'exists':auth.account_exists(email)}
 if action=='login':
  result=auth.sign_in(token,email=email,password=d.get('password',''))
  return set_cookie(JSONResponse({'ok':True,'next':local_next(d.get('next'))}),result['session_token'])
 if action=='logout':
  auth.sign_out(token);r=JSONResponse({'ok':True});r.delete_cookie(COOKIE,path='/');return r
 if action=='stay':
  if not s['authenticated']:raise HTTPException(401,'Sign in first')
  with db() as c:c.execute('INSERT OR REPLACE INTO cookie_preferences VALUES(?,?)',(auth.session_owner_digest(token),int(bool(d.get('persistent')))))
  return set_cookie(JSONResponse({'ok':True}),token)
 if action in ['register','recover','code-login']:
  if s['authenticated'] and action!='recover':raise HTTPException(409,'Sign out before starting this flow.')
  if action=='register':
   # Source observed email → code; the post-verification profile/password adapter is explicitly authorized.
   purpose='registration';auth.start_registration(token,email=email,display_name='OneDrive 用户',password=secrets.token_urlsafe(30),restart_invalid_flow=True)
  elif action=='recover':purpose='password-reset';auth.start_password_reset(token,email=email,restart_invalid_flow=True)
  else:
   purpose='passwordless-signin';auth.start_passwordless_signin(token,email=email,restart_invalid_flow=True)
  deliver(token,purpose,str(request.base_url));return {'ok':True,'purpose':purpose}
 if action=='resend':
  purpose=d.get('purpose','registration')
  status=auth.session_mail_status(token,purpose=purpose)
  if status=='SMTP_FAILED':
   auth.retry_failed_mail_for_session(token,purpose=purpose);deliver(token,purpose,str(request.base_url));return {'ok':True}
  tables={'registration':'local_auth_registration_flows','password-reset':'local_auth_password_reset_flows','passwordless-signin':'local_auth_passwordless_flows'}
  table=tables.get(purpose)
  if not table:raise HTTPException(400,'Invalid flow')
  with db() as c:
   row=c.execute('SELECT email_normalized FROM '+table+' WHERE session_digest=?',(auth.session_owner_digest(token),)).fetchone()
  if not row:raise HTTPException(400,'Return to the email step to request a new code.')
  email=row['email_normalized']
  if purpose=='registration':auth.start_registration(token,email=email,display_name='OneDrive 用户',password=secrets.token_urlsafe(30),restart_invalid_flow=True)
  elif purpose=='password-reset':auth.start_password_reset(token,email=email,restart_invalid_flow=True)
  else:auth.start_passwordless_signin(token,email=email,restart_invalid_flow=True)
  deliver(token,purpose,str(request.base_url));return {'ok':True}
 if action=='verify':
  purpose=d.get('purpose');code=d.get('code','')
  if purpose=='registration':
   with db() as c:flow=c.execute('SELECT verified_at FROM local_auth_registration_flows WHERE session_digest=?',(auth.session_owner_digest(token),)).fetchone()
   if flow and flow['verified_at'] is not None:raise AuthConflict('Verification already completed')
   auth.verify_registration_code(token,code)
  elif purpose=='password-reset':auth.verify_password_reset_code(token,code)
  elif purpose=='passwordless-signin':
   auth.verify_passwordless_code(token,code);result=auth.complete_passwordless_signin(token)
   return set_cookie(JSONResponse({'ok':True,'next':'/'}),result['session_token'])
  else:raise HTTPException(400,'Invalid flow')
  return {'ok':True,'next':'profile' if purpose=='registration' else 'new-password'}
 if action=='complete-registration':
  name=d.get('name','').strip();password=d.get('password','')
  if not name or len(name)>100 or len(password)<8:raise HTTPException(400,'请输入姓名及至少 8 位的密码。')
  salt,digest=_hash_secret(password)
  with db() as c:
   changed=c.execute('UPDATE local_auth_registration_flows SET display_name=?,password_salt=?,password_hash=? WHERE session_digest=? AND verified_at IS NOT NULL AND expires_at>?',(name,salt,digest,auth.session_owner_digest(token),int(time.time()))).rowcount
  if not changed:raise HTTPException(400,'Verify your email first.')
  result=auth.complete_registration(token)
  # Registration ends on login, matching the required registration → login journey.
  auth.sign_out(result['session_token']);new=auth.create_anonymous_session()
  return set_cookie(JSONResponse({'ok':True,'next':'/login?registered=1'}),new)
 if action=='reset-password':
  new=auth.complete_password_reset(token,new_password=d.get('password',''));auth.sign_out(new)
  return set_cookie(JSONResponse({'ok':True,'next':'/login?reset=1'}),auth.create_anonymous_session())
 raise HTTPException(404,'Unknown authentication operation')

def file_metadata_columns(connection):
 # Preserve all metadata fields while avoiding materializing legacy BLOB bodies.
 return ','.join('"'+row['name'].replace('"','""')+'"' for row in connection.execute('PRAGMA table_info(drive_files)') if row['name']!='content')

def file_for(fid,uid,allow_deleted=False,metadata_only=False,include_content=True):
 with db() as c:
  columns='*' if include_content else file_metadata_columns(c)
  r=c.execute('SELECT '+columns+' FROM drive_files WHERE id=? AND owner=?',(fid,uid)).fetchone()
  if not r or (r['deleted'] and not allow_deleted):raise HTTPException(404,'找不到此项')
  item=r;visited=set()
  while item:
   if item['id'] in visited:raise HTTPException(409,'文件夹结构无效')
   visited.add(item['id'])
   if item['deleted'] and not allow_deleted:raise HTTPException(404,'找不到此项')
   if item['kind']=='vault' and not (metadata_only and item['id']==fid and not item['parent']):
    token=REQUEST_TOKEN.get();s=auth.resolve_session(token)
    unlocked=c.execute('SELECT expires FROM vault_sessions WHERE digest=?',(auth.session_owner_digest(token),)).fetchone() if token else None
    if not s or not s['authenticated'] or s['account']['account_id']!=uid or not unlocked or unlocked['expires']<=int(time.time()):raise HTTPException(423,'个人保管库已锁定，请重新验证身份')
   item=c.execute('SELECT id,owner,parent,kind,deleted FROM drive_files WHERE id=? AND owner=?',(item['parent'],uid)).fetchone() if item['parent'] else None
  return dict(r)
def file_json(f):
 result={k:v for k,v in dict(f).items() if k not in ['content','owner']}
 if f['kind'] in ['folder','vault']:
  with db() as c:appearance=c.execute('SELECT color FROM drive_file_appearance WHERE file_id=? AND owner=?',(f['id'],f['owner'])).fetchone()
  result['color']=appearance['color'] if appearance else '#FFCE3C'
 return result

def stored_blob(f):
 with db() as c:row=c.execute('SELECT blob_key FROM drive_file_blobs WHERE file_id=? AND owner=?',(f['id'],f['owner'])).fetchone()
 return row['blob_key'] if row else None

def has_content(f):return f['content'] is not None or stored_blob(f) is not None

def open_content(f):
 key=stored_blob(f)
 if key:
  try:return FILE_STORAGE.path(key).open('rb')
  except FileNotFoundError:raise HTTPException(409,'原始文件内容不可用')
 if f['content'] is None:raise HTTPException(409,'原始文件内容尚未取得')
 return io.BytesIO(bytes(f['content']))

def original_office(f):
 if f['kind'] not in ['document','spreadsheet','presentation','notebook'] or not has_content(f):return False
 with open_content(f) as stream:return office_bytes({'kind':f['kind'],'content':stream.read(4)})

def storage_used(c,uid):
 used=c.execute('SELECT COALESCE(SUM(size),0) FROM drive_files WHERE owner=?',(uid,)).fetchone()[0]
 used+=c.execute('SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM drive_document_edits WHERE owner=?',(uid,)).fetchone()[0]
 if uid==DEMO:
  seed_size=sum(f.get('bytes',0) for f in json.loads(seedpath.read_text()))
  used=max(0,used+int(94.3*1024*1024)-seed_size)
 return used

def check_storage(c,uid,additional=0):
 if additional>=0 and storage_used(c,uid)+additional>DRIVE_QUOTA:raise HTTPException(413,'OneDrive 存储空间不足。请释放空间后重试。')

def discard_unused_blobs(keys):
 if not keys:return
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  for key in set(keys):
   if not c.execute('SELECT 1 FROM drive_file_blobs WHERE blob_key=?',(key,)).fetchone():FILE_STORAGE.discard(key)

NOTEBOOK_CATALOG=json.loads((ROOT/'content/onenote.json').read_text()) if (ROOT/'content/onenote.json').exists() else {}
NOTEBOOK_BY_HASH={item['sha256']:item for item in NOTEBOOK_CATALOG.values()}

def notebook_preview(f):
 if f['kind']!='notebook' or not has_content(f):return None
 with open_content(f) as stream:
  if stream.read(4) not in [b'\xe4\x52\x5c\x7b',b'PK\x03\x04']:return None
  stream.seek(0);digest=hashlib.file_digest(stream,'sha256').hexdigest()
 return NOTEBOOK_BY_HASH.get(digest)

def notebook_pages(f):
 preview=notebook_preview(f)
 return [{k:page[k] for k in ['number','title','ink_count','section_id','section_title'] if k in page} for page in preview['pages']] if preview else []

def notebook_page_response(f,number):
 preview=notebook_preview(f)
 if not preview or not 1<=number<=len(preview['pages']):raise HTTPException(404,'未找到笔记页面')
 page=ROOT/'content/onenote'/preview['pages'][number-1]['file']
 return FileResponse(page,media_type='text/html',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

def document_text(f):
 if f['kind'] not in TEXT_KINDS:return None
 with db() as c:edit=c.execute('SELECT body FROM drive_document_edits WHERE file_id=? AND owner=?',(f['id'],f['owner'])).fetchone()
 if edit:return edit['body']
 if not has_content(f):return None
 note=notebook_preview(f)
 if note:return note['text']
 with open_content(f) as stream:
  if original_office(f):return extract_text(stream,f['kind'])
  body=stream.read(8_000_001)
 if len(body)>8_000_000:return None
 try:
  text=body.decode('utf8');return text if len(text)<=2_000_000 else None
 except UnicodeDecodeError:return None

def save_document(c,f,text):
 if f['kind'] not in TEXT_KINDS:raise HTTPException(400,'此文件不支持文本编辑')
 modified=time.strftime('%Y-%m-%d %H:%M');old_keys=[]
 if original_office(f):
  if document_text(f) is None:raise HTTPException(400,'无法提取此文件的文本，请下载原始文件')
  previous=c.execute('SELECT length(CAST(body AS BLOB)) FROM drive_document_edits WHERE file_id=? AND owner=?',(f['id'],f['owner'])).fetchone()
  check_storage(c,f['owner'],len(text.encode())-(previous[0] if previous else 0))
  c.execute('INSERT INTO drive_document_edits VALUES(?,?,?,?) ON CONFLICT(file_id) DO UPDATE SET body=excluded.body,modified=excluded.modified',(f['id'],f['owner'],text,modified))
  c.execute('UPDATE drive_files SET modified=? WHERE id=? AND owner=?',(modified,f['id'],f['owner']))
 else:
  if has_content(f) and document_text(f) is None:raise HTTPException(400,'此文件不支持文本编辑')
  body=text.encode();check_storage(c,f['owner'],len(body)-f['size'])
  key=stored_blob(f)
  if key:old_keys.append(key);c.execute('DELETE FROM drive_file_blobs WHERE file_id=? AND owner=?',(f['id'],f['owner']))
  c.execute('UPDATE drive_files SET content=?,size=?,modified=? WHERE id=? AND owner=?',(body,len(body),modified,f['id'],f['owner']))
 return old_keys

def export_document(f):
 text=document_text(f)
 if text is None:raise HTTPException(400,'此文件没有可导出的文本')
 return Response(text.encode(),media_type='text/plain',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(str(Path(f['name']).with_suffix('.txt')))})
@app.get('/api/account/profile')
def account_profile(request:Request):
 uid=owner(request)
 with db() as c:
  row=c.execute('SELECT first_name,last_name,birth_date,country FROM account_profiles WHERE owner=?',(uid,)).fetchone()
  account=c.execute('SELECT display_name,email_normalized FROM local_auth_accounts WHERE account_id=?',(uid,)).fetchone()
  photo=c.execute('SELECT 1 FROM account_photos WHERE owner=?',(uid,)).fetchone()
 return {'source_snapshot':uid==DEMO,'has_photo':bool(photo),**dict(account),**(dict(row) if row else {'first_name':account['display_name'],'last_name':'','birth_date':'','country':''})}
@app.get('/api/account/language-options')
def account_language_options(request:Request):
 owner(request)
 return json.loads((ROOT/'content/account-language.json').read_text())
@app.get('/api/account/language')
def account_language(request:Request):
 uid=owner(request);catalog=json.loads((ROOT/'content/account-language.json').read_text())
 with db() as c:row=c.execute('SELECT body FROM account_language_settings WHERE owner=?',(uid,)).fetchone()
 return {**catalog['defaults'],**(json.loads(row['body']) if row else {})}
@app.post('/api/account/language')
async def save_account_language(request:Request):
 uid=owner(request);body=await request.json();catalog=json.loads((ROOT/'content/account-language.json').read_text())
 allowed={'display_language','translation_mode','translation_language','regional_format','preferred_language_codes','speech_language','date_format','time_format'}
 if not isinstance(body,dict) or not body or set(body)-allowed:raise HTTPException(400,'无效的语言设置')
 choices={'display_language':{r['value'] for r in catalog['display_languages']}|{'zh-CN'},'translation_mode':{'Yes','Ask','No'},'translation_language':set(catalog['translation_languages'])|{''},'regional_format':{r['value'] for r in catalog['regional_formats']}|{''},'speech_language':{r['value'] for r in catalog['speech_language_options']}|{''}}
 if any(not isinstance(v,str) or v not in choices[k] for k,v in body.items() if k in choices):raise HTTPException(400,'无效的语言设置')
 if 'preferred_language_codes' in body:
  codes=body['preferred_language_codes'];valid={r['value'] for r in catalog['preferred_language_options']}
  if not isinstance(codes,list) or len(codes)>len(valid) or any(not isinstance(x,str) or x not in valid for x in codes) or len(codes)!=len(set(codes)):raise HTTPException(400,'无效的首选语言')
 with db() as c:
  row=c.execute('SELECT body FROM account_language_settings WHERE owner=?',(uid,)).fetchone()
  current={**catalog['defaults'],**(json.loads(row['body']) if row else {})}
  if 'regional_format' in body and body['regional_format']!=current['regional_format']:current.update(date_format='',time_format='')
  current.update(body)
  region=catalog['regional_format_details'].get(current['regional_format'],{})
  for key in ['date_format','time_format']:
   if not isinstance(current[key],str) or current[key] not in {r['format'] for r in region.get(key+'s',[])}|{''}:raise HTTPException(400,'无效的区域格式')
  labels={r['value']:r['label'] for r in catalog['preferred_language_options']}
  current['preferred_languages']=[labels[code] for code in current['preferred_language_codes']]
  current['display_label']=next((r['label'] for r in catalog['display_languages'] if r['value']==current['display_language']),'中文(中国)')
  c.execute('INSERT INTO account_language_settings VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET body=excluded.body',(uid,json.dumps(current,ensure_ascii=False)))
 return current
@app.get('/api/account/photo')
def account_photo(request:Request):
 with db() as c:row=c.execute('SELECT content FROM account_photos WHERE owner=?',(owner(request),)).fetchone()
 if not row:raise HTTPException(404,'未添加照片')
 return Response(bytes(row['content']),media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
@app.post('/api/account/photo')
async def save_account_photo(request:Request,file:UploadFile=File(...)):
 uid=owner(request);content=await file.read(2*1024*1024+1)
 if len(content)>2*1024*1024:raise HTTPException(400,'照片文件过大')
 import struct
 if len(content)<33 or not content.startswith(b'\x89PNG\r\n\x1a\n') or content[12:16]!=b'IHDR':raise HTTPException(400,'请选择有效的图片')
 width,height=struct.unpack('>II',content[16:24])
 if not 1<=width<=2048 or not 1<=height<=2048:raise HTTPException(400,'请选择有效的图片')
 with db() as c:c.execute('INSERT INTO account_photos VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET content=excluded.content',(uid,content))
 return {'has_photo':True}
@app.delete('/api/account/photo')
def delete_account_photo(request:Request):
 with db() as c:c.execute('DELETE FROM account_photos WHERE owner=?',(owner(request),))
 return {'has_photo':False}
@app.post('/api/account/name')
async def update_account_name(request:Request):
 uid=owner(request);d=await request.json();first=d.get('first_name','');last=d.get('last_name','')
 if not isinstance(first,str) or not isinstance(last,str):raise HTTPException(400,'请输入姓名')
 first=first.strip();last=last.strip()
 if not (first or last) or len(first)>50 or len(last)>50:raise HTTPException(400,'请输入有效的姓名')
 display=' '.join(x for x in [last,first] if x)
 with db() as c:
  c.execute('INSERT INTO account_profiles(owner,first_name,last_name) VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET first_name=excluded.first_name,last_name=excluded.last_name',(uid,first,last))
  c.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(display,uid))
 return account_profile(request)
@app.get('/api/account/orders')
def account_orders(request:Request,category:str='all',period:int=3):
 uid=owner(request)
 if category not in ['all','processing','refunded','digital','physical'] or period not in [3,6,12,84]:raise HTTPException(400,'无效筛选条件')
 import datetime,calendar
 now=datetime.datetime.now(datetime.UTC);month_index=now.year*12+now.month-1-period;year,month0=divmod(month_index,12);month=month0+1
 since=now.replace(year=year,month=month,day=min(now.day,calendar.monthrange(year,month)[1])).timestamp()
 with db() as c:rows=[dict(r) for r in c.execute('SELECT id,plan,status,created FROM sandbox_orders WHERE owner=? AND created>=? ORDER BY created DESC',(uid,since))]
 if uid==DEMO and (ROOT/'content/account-orders.json').exists():rows.extend(r for r in json.loads((ROOT/'content/account-orders.json').read_text()) if r['created']>=since)
 rows.sort(key=lambda r:r['created'],reverse=True)
 if category=='physical':rows=[]
 elif category in ['processing','refunded']:rows=[r for r in rows if r['status']==category]
 return {'orders':rows,'category':category,'period':period}
@app.get('/api/storage')
def storage(request:Request):
 uid=owner(request)
 with db() as c:used=storage_used(c,uid)
 return {'used':used,'quota':DRIVE_QUOTA,'percentage':int(used/DRIVE_QUOTA*100)}
@app.get('/api/files')
def files(request:Request,parent:str='',q:str='',kind:str='',view:str='files'):
 uid=owner(request)
 with db() as c:
  if parent:file_for(parent,uid,include_content=False)
  clauses=['owner=?'];values=[uid]
  if view=='recycle':clauses.append('deleted=1')
  else:
   clauses.append('deleted=0')
   if view=='recent':clauses.append("kind IN ('document','presentation','spreadsheet','notebook') AND (source_id IS NULL OR source_id NOT LIKE 'note-section-%')")
   elif view=='largest':clauses.append("kind NOT IN ('folder','vault') AND (source_id IS NULL OR source_id<>'notebook')")
   elif view=='photos':clauses.append("kind IN ('image','video')")
   elif view=='favorites':clauses.append('favorite=1')
   elif view=='shared':clauses.append('id IN (SELECT file_id FROM drive_shares WHERE owner=? UNION SELECT member.value FROM drive_share_bundles bundle,json_each(bundle.items) member WHERE bundle.owner=?)');values.extend([uid,uid])
   elif not q:clauses.append('parent IS ?');values.append(parent or None)
  if q:clauses.append('name LIKE ?');values.append('%'+q+'%')
  if kind:clauses.append('kind=?');values.append(kind)
  rows=c.execute('SELECT '+file_metadata_columns(c)+' FROM drive_files WHERE '+' AND '.join(clauses)+' ORDER BY position',values).fetchall()
  data=[]
  for r in rows:
   try:
    if r['kind']!='vault':file_for(r['id'],uid,allow_deleted=view=='recycle',include_content=False)
    item=file_json(r)
    if view=='largest':
     parent_row=c.execute('SELECT name FROM drive_files WHERE id=? AND owner=?',(r['parent'],uid)).fetchone() if r['parent'] else None
     item['location_name']=parent_row['name'] if parent_row else '我的文件'
    data.append(item)
   except HTTPException as e:
    if e.status_code not in [404,423]:raise
  if view=='recent':
   order=['notebook','presentation1','math11','math1','math','intro-ppt','intro-doc','homework','notice','document1','schedule']
   data.sort(key=lambda f:order.index(f['source_id']) if f['source_id'] in order else -1)
  elif view=='largest':data.sort(key=lambda f:(-f['size'],f['position']))
  return {'files':data,'count':len(data)}
@app.get('/api/files/{fid}')
def detail(fid:str,request:Request):
 f=file_for(fid,owner(request),metadata_only=True);result=file_json(f)
 if f['kind']=='vault':return {**result,'comments':[],'shares':[]}
 with db() as c:
  result['comments']=[dict(r) for r in c.execute('SELECT id,body,created FROM drive_comments WHERE file_id=? AND owner=? ORDER BY created',(fid,owner(request)))];result['shares']=[dict(r) for r in c.execute('SELECT token,mode FROM drive_shares WHERE file_id=? AND owner=?',(fid,owner(request)))]
  result['shares'].extend(dict(r) for r in c.execute('SELECT token,mode FROM drive_share_bundles bundle WHERE owner=? AND EXISTS (SELECT 1 FROM json_each(bundle.items) WHERE value=?)',(owner(request),fid)))
 result['text']=document_text(f);result['original_office']=original_office(f)
 result['has_content']=has_content(f);result['notebook_pages']=notebook_pages(f)
 result['editable']=f['kind'] in TEXT_KINDS and (result['text'] is not None or not result['has_content'])
 return result
@app.get('/api/files/{fid}/note-page/{number}')
def note_page(fid:str,number:int,request:Request):
 return notebook_page_response(file_for(fid,owner(request)),number)

@app.get('/api/files/{fid}/export-text')
def export_text(fid:str,request:Request):
 return export_document(file_for(fid,owner(request)))
@app.get('/api/files/{fid}/download')
def download(fid:str,request:Request):
 uid=owner(request);f=file_for(fid,uid)
 return download_response(f,uid)

def download_response(f,uid):
 if f['kind']=='folder':
  return archive_response([f],uid,f['name']+'.zip')
 if not has_content(f):raise HTTPException(409,'此原始文件尚未取得。请使用本地编辑器保存内容，或上传文件。')
 name=f['name'];note=notebook_preview(f)
 if note and note.get('export_suffix'):name+=note['export_suffix']
 # Local text editor exports honest text; uploaded Office archives stay byte-identical.
 if f['kind'] in ['document','spreadsheet','presentation','notebook'] and not original_office(f):name=str(Path(name).with_suffix('.txt'))
 return file_response(f,mimetypes.guess_type(name)[0] or 'application/octet-stream',"attachment; filename*=UTF-8''"+quote(name))

def file_response(f,mime,disposition):
 headers={'Content-Disposition':disposition,'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'}
 key=stored_blob(f)
 if key:
  path=FILE_STORAGE.path(key)
  if not path.is_file():raise HTTPException(409,'原始文件内容不可用')
  return FileResponse(path,media_type=mime,headers=headers)
 if f['content'] is None:raise HTTPException(409,'原始文件内容尚未取得')
 return Response(bytes(f['content']),media_type=mime,headers=headers)

def archive_response(items,uid,name):
 archive_dir=DATA/'download-temp';archive_dir.mkdir(mode=0o700,exist_ok=True)
 fd,temporary=tempfile.mkstemp(prefix='archive-',suffix='.zip',dir=archive_dir);os.close(fd);archive=Path(temporary);seen=set();paths=set()
 def write(z,path,body=None,blob=None):
  if path in paths:raise HTTPException(409,'压缩文件内存在同名项目')
  paths.add(path)
  if blob:z.write(FILE_STORAGE.path(blob),path)
  else:z.writestr(path,body)
 def append_item(z,item,path):
  if item['id'] in seen:raise HTTPException(409,'文件夹结构无效')
  seen.add(item['id']);file_for(item['id'],uid)
  if item['kind'] in ['folder','vault']:
   write(z,path+'/',b'')
   with db() as c:children=[dict(r) for r in c.execute('SELECT * FROM drive_files WHERE owner=? AND parent=? AND deleted=0 ORDER BY position',(uid,item['id']))]
   for child in children:append_item(z,child,path+'/'+safe_name(child['name']))
  elif not has_content(item):
   if item['kind']=='notebook':
    # Microsoft documents this ZIP behavior. The explanatory text is part of
    # the user-authorized local Office equivalent, not a captured original file.
    write(z,path+'-error.txt','此 OneNote 笔记本无法通过 OneDrive 下载。请使用 OneNote 导出笔记本。'.encode())
   else:raise HTTPException(409,'文件夹中的原始文件尚未取得：'+item['name'])
  else:
   note=notebook_preview(item)
   if note and note.get('export_suffix'):path+=note['export_suffix']
   elif item['kind'] in ['document','spreadsheet','presentation','notebook'] and not original_office(item):path+='.txt'
   key=stored_blob(item);write(z,path,bytes(item['content']) if key is None else None,key)
 try:
  with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
   for item in items:append_item(z,item,safe_name(item['name']))
  return FileResponse(archive,media_type='application/zip',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(name),'Cache-Control':'no-store'},background=BackgroundTask(archive.unlink,missing_ok=True))
 except BaseException:archive.unlink(missing_ok=True);raise

@app.get('/api/download')
def download_selection(request:Request,ids:str):
 uid=owner(request)
 return archive_response(download_roots(uid,ids),uid,'OneDrive.zip')

def download_roots(uid,ids):
 selected=list(dict.fromkeys(ids.split(',')))
 if not selected or len(selected)>200:raise HTTPException(400,'请选择文件')
 items=[file_for(fid,uid) for fid in selected];selected_set=set(selected);roots=[]
 for item in items:
  parent=item['parent'];nested=False
  while parent:
   if parent in selected_set:nested=True;break
   parent=file_for(parent,uid)['parent']
  if not nested:roots.append(item)
 return roots

@app.get('/api/download/check')
def check_download(request:Request,ids:str):
 uid=owner(request);selected=list(dict.fromkeys(ids.split(',')));roots=download_roots(uid,ids);seen=set()
 def check(item,inside_archive=False):
  if item['id'] in seen:raise HTTPException(409,'文件夹结构无效')
  seen.add(item['id']);file_for(item['id'],uid)
  if item['kind'] in ['folder','vault']:
   with db() as c:children=[dict(r) for r in c.execute('SELECT * FROM drive_files WHERE owner=? AND parent=? AND deleted=0',(uid,item['id']))]
   for child in children:check(child,True)
  elif not has_content(item):
   if not (inside_archive and item['kind']=='notebook'):raise HTTPException(409,'此原始文件尚未取得：'+item['name'])
  else:
   with open_content(item):pass
 for item in roots:check(item,len(selected)>1)
 return {'url':'/api/files/'+quote(selected[0],safe='')+'/download' if len(selected)==1 else '/api/download?ids='+quote(','.join(selected),safe='')}
@app.get('/api/files/{fid}/content')
def content(fid:str,request:Request):
 f=file_for(fid,owner(request))
 if f['kind'] not in ['pdf','image','video']:
  return file_response(f,'application/octet-stream','attachment')
 return file_response(f,mimetypes.guess_type(f['name'])[0] or 'application/octet-stream','inline')

def safe_name(n):
 if not isinstance(n,str) or not n or not n.strip():raise HTTPException(400,'请输入文件或文件夹名称。')
 if n!=n.strip():raise HTTPException(400,'文件或文件夹名称不能以空格开头或结尾。')
 if any(0xd800<=ord(ch)<=0xdfff for ch in n) or re.search(r'[\\/:*?"<>|\x00-\x1f]',n):raise HTTPException(400,'请输入未包含以下任一字符的名称: " * : < > ? / \\ |。')
 if path_characters(n)>400:raise HTTPException(400,'文件或文件夹名称不能超过 400 个字符。')
 if n.endswith('.'):raise HTTPException(400,'文件或文件夹名称不能以句点结尾。')
 if n.lower() in ['.lock','desktop.ini'] or '_vti_' in n.lower() or n.startswith('~$') or re.match(r'(?i)^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)',n):raise HTTPException(400,'此文件或文件夹名称不可用。')
 return n
def path_characters(value):
 # Browser strings and Microsoft's UTF-16 path handling count surrogate pairs.
 return len(value.encode('utf-16-le'))//2

def check_file_path(c,uid,parent,names,subtree=None,kind=None):
 """Validate the decoded library-relative path before a transactional mutation."""
 prefix=[];seen=set()
 while parent:
  if parent in seen:raise HTTPException(400,'文件夹结构无效')
  seen.add(parent)
  row=c.execute('SELECT name,parent FROM drive_files WHERE owner=? AND id=?',(uid,parent)).fetchone()
  if not row:raise HTTPException(404,'未找到文件夹')
  prefix.append(row['name']);parent=row['parent']
 prefix.reverse()
 path='/'.join(prefix+names)
 if path_characters(path)>400:raise HTTPException(400,'文件和文件夹的完整路径不能超过 400 个字符。')
 if not prefix and names[0].lower()=='forms':raise HTTPException(400,'根目录中不能使用此名称。')
 if kind=='folder' and names[-1].startswith(('゛','ဧ')):raise HTTPException(400,'文件夹不能以此字符开头。')
 if subtree:
  pending=[(subtree,path)];visited=set()
  while pending:
   item,base=pending.pop()
   if item in visited:raise HTTPException(400,'文件夹结构无效')
   visited.add(item)
   for child in c.execute('SELECT id,name FROM drive_files WHERE owner=? AND parent=? AND deleted=0',(uid,item)).fetchall():
    child_path=base+'/'+child['name']
    if path_characters(child_path)>400:raise HTTPException(400,'文件夹中的文件路径将超过 400 个字符。')
    pending.append((child['id'],child_path))

def check_parent(parent,uid,fid=None):
 if not parent:return
 p=file_for(parent,uid)
 if p['kind'] not in ['folder','vault']:raise HTTPException(400,'请选择文件夹')
 seen=set()
 while p:
  if p['id']==fid or p['id'] in seen:raise HTTPException(400,'不能将文件夹移动到其自身或子文件夹中')
  seen.add(p['id']);p=file_for(p['parent'],uid) if p['parent'] else None
def transfer_files(uid,ids,parent,action):
 if action not in ['move','copy'] or not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(i,str) or not i for i in ids):raise HTTPException(400,'请选择要移动或复制的文件')
 if parent is not None and not isinstance(parent,str):raise HTTPException(400,'请选择文件夹')
 ids=list(dict.fromkeys(ids))
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  items=[file_for(i,uid) for i in ids]
  if any(f['kind']=='vault' for f in items):raise HTTPException(400,'此操作不适用于个人保管库')
  for f in items:check_parent(parent,uid,f['id'])
  # A selected descendant travels with its selected folder, exactly once.
  selected=set(ids);roots=[]
  for f in items:
   ancestor=f['parent'];seen=set();nested=False
   while ancestor:
    if ancestor in selected:nested=True;break
    if ancestor in seen:raise HTTPException(400,'文件夹结构无效')
    seen.add(ancestor);row=c.execute('SELECT parent FROM drive_files WHERE id=? AND owner=?',(ancestor,uid)).fetchone();ancestor=row['parent'] if row else None
   if not nested:roots.append(f)
  names=set()
  for f in roots:
   check_file_path(c,uid,parent,[f['name']],subtree=f['id'],kind=f['kind'])
   if f['name'] in names:raise HTTPException(409,'此位置已存在同名文件')
   names.add(f['name'])
   matches=c.execute('SELECT id FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,parent,f['name'])).fetchall()
   if any(not (action=='move' and row['id']==f['id']) for row in matches):raise HTTPException(409,'此位置已存在同名文件')
  result=[]
  def copy_tree(item,target):
   src=c.execute('SELECT * FROM drive_files WHERE id=? AND owner=? AND deleted=0',(item,uid)).fetchone()
   if not src:raise HTTPException(404,'未找到文件')
   new=uuid.uuid4().hex
   c.execute('INSERT INTO drive_files(id,owner,parent,name,kind,size,modified,created,content,full_detail) VALUES(?,?,?,?,?,?,?,?,?,1)',(new,uid,target,src['name'],src['kind'],src['size'],src['modified'],time.strftime('%Y-%m-%d %H:%M'),src['content']))
   c.execute('INSERT INTO drive_file_appearance SELECT ?,owner,color FROM drive_file_appearance WHERE file_id=? AND owner=?',(new,item,uid))
   c.execute('INSERT INTO drive_document_edits SELECT ?,owner,body,modified FROM drive_document_edits WHERE file_id=? AND owner=?',(new,item,uid))
   c.execute('INSERT INTO drive_file_blobs SELECT ?,owner,blob_key FROM drive_file_blobs WHERE file_id=? AND owner=?',(new,item,uid))
   children=c.execute('SELECT id FROM drive_files WHERE parent=? AND owner=? AND deleted=0 ORDER BY position,name',(item,uid)).fetchall()
   for child in children:copy_tree(child['id'],new)
   return new
  for f in roots:
   if action=='move':c.execute('UPDATE drive_files SET parent=? WHERE id=? AND owner=?',(parent,f['id'],uid));result.append(f['id'])
   else:result.append(copy_tree(f['id'],parent))
  if action=='copy':check_storage(c,uid)
 return {'ok':True,'ids':result,**({'id':result[0]} if len(result)==1 else {})}
@app.post('/api/transfers')
async def transfer_selection(request:Request):
 uid=owner(request);d=await request.json()
 if not isinstance(d,dict):raise HTTPException(400,'请选择要移动或复制的文件')
 return transfer_files(uid,d.get('ids'),d.get('parent') or None,d.get('action'))
@app.post('/api/files')
async def create_file(request:Request):
 uid=owner(request);d=await request.json();name=safe_name(d.get('name'));parent=d.get('parent') or None;check_parent(parent,uid)
 kind=d.get('kind','folder')
 if kind not in ['folder','text','markdown','document','spreadsheet','presentation','notebook']:raise HTTPException(400,'不支持的文件类型')
 fid=uuid.uuid4().hex;now=time.strftime('%Y-%m-%d %H:%M');body=b'' if kind!='folder' else None
 with db() as c:
  c.execute('BEGIN IMMEDIATE');check_parent(parent,uid);check_file_path(c,uid,parent,[name],kind=kind)
  if c.execute('SELECT 1 FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,parent,name)).fetchone():raise HTTPException(409,'此位置已存在同名文件')
  c.execute('INSERT INTO drive_files(id,owner,parent,name,kind,modified,created,content) VALUES(?,?,?,?,?,?,?,?)',(fid,uid,parent,name,kind,now,now,body))
 return {'id':fid}

@app.post('/api/shares')
async def share_selection(request:Request):
 uid=owner(request);d=await request.json();ids=d.get('ids');mode=d.get('mode','view')
 if not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(fid,str) for fid in ids):raise HTTPException(400,'请选择文件')
 if mode not in ['view','edit']:raise HTTPException(400,'Invalid permission')
 audience=d.get('audience','anyone');recipients=d.get('recipients',[]);message=d.get('message','');send=d.get('send',False)
 if audience not in ['anyone','people'] or not isinstance(send,bool):raise HTTPException(400,'Invalid sharing settings')
 if not isinstance(recipients,list) or len(recipients)>50 or any(not isinstance(value,str) or not re.fullmatch(r'[^\s@,;<>\r\n]+@[^\s@,;<>\r\n]+\.[^\s@,;<>\r\n]+',value) for value in recipients):raise HTTPException(400,'请输入有效的电子邮件地址')
 recipients=list(dict.fromkeys(value.strip().lower() for value in recipients))
 if (audience=='people' or send) and not recipients:raise HTTPException(400,'请输入收件人的电子邮件地址')
 if not isinstance(message,str) or len(message)>5000:raise HTTPException(400,'消息太长')
 ids=list(dict.fromkeys(ids));token=secrets.token_urlsafe(24)
 link=str(request.base_url).rstrip('/')+'/s/'+token
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  for fid in ids:
   ancestor=file_for(fid,uid)
   while ancestor:
    if ancestor['kind']=='vault':raise HTTPException(400,'个人保管库中的文件不能共享')
    ancestor=c.execute('SELECT id,parent,kind FROM drive_files WHERE id=? AND owner=?',(ancestor['parent'],uid)).fetchone() if ancestor['parent'] else None
  if len(ids)==1:c.execute('INSERT INTO drive_shares VALUES(?,?,?,?,?)',(token,ids[0],uid,mode,int(time.time())))
  else:c.execute('INSERT INTO drive_share_bundles VALUES(?,?,?,?,?)',(token,uid,mode,int(time.time()),json.dumps(ids)))
  c.execute('INSERT INTO drive_share_options VALUES(?,?,?,?,?)',(token,uid,audience,json.dumps(recipients),message))
  if send:
   title=str(len(ids))+' Items' if len(ids)>1 else file_for(ids[0],uid)['name']
   smtp_message(', '.join(recipients),'OneDrive: '+title,'OneDrive\n'+title+'\n\n'+message+'\n\n'+link)
 return {'ok':True,'url':link,'sent':send}

@app.get('/api/incoming-shares')
def incoming_shares(request:Request):
 uid=owner(request);email=session(request)[1]['account']['email_normalized'];result=[]
 with db() as c:rows=c.execute('SELECT token FROM drive_share_options option WHERE owner<>? AND EXISTS (SELECT 1 FROM json_each(option.recipients) WHERE value=?)',(uid,email)).fetchall()
 for row in rows:
  try:
   r,root,f=shared_file(row['token']);data=share_json(f,r,root);data['shared_url']='/s/'+row['token'];result.append(data)
  except HTTPException as exc:
   if exc.status_code not in [401,403,404,423]:raise
 return {'files':result,'count':len(result)}
@app.post('/api/upload')
async def upload(request:Request,files:list[UploadFile]=File(...),parent:str='',conflict:str='fail'):
 uid=owner(request);check_parent(parent or None,uid);created=[];paths=[];staged=[];discarded=[];committed=False
 if conflict not in ['fail','replace','rename']:raise HTTPException(400,'请选择有效的同名文件处理方式')
 def collision(name):
  raise HTTPException(409,{'code':'upload_conflict','message':'此位置已存在同名文件：'+name,'name':name})
 for item in files:
  if not item.filename:raise HTTPException(400,'请选择文件')
  parts=[safe_name(part) for part in item.filename.split('/')]
  if item.size is not None and item.size>MAX_FILE_BYTES:raise HTTPException(413,'单个文件最大为 250 GB')
  paths.append(parts)
 with db() as c:
  credit=0;credited=set();incoming=set()
  for parts in paths:
   target=parent or None;missing=False
   for folder in parts[:-1]:
    row=c.execute('SELECT id,kind FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,target,folder)).fetchone()
    if not row:missing=True;break
    if row['kind']!='folder':raise HTTPException(409,'上传路径中已存在同名文件：'+folder)
    target=row['id']
   row=None if missing else c.execute('SELECT id,kind,size FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,target,parts[-1])).fetchone()
   if row and row['kind'] in ['folder','vault']:raise HTTPException(409,'此位置已存在同名文件夹：'+parts[-1])
   if conflict=='fail' and (row or tuple(parts) in incoming):collision('/'.join(parts))
   incoming.add(tuple(parts))
   if conflict=='replace' and row and row['id'] not in credited:
    credited.add(row['id']);credit+=row['size']
    edit=c.execute('SELECT length(CAST(body AS BLOB)) FROM drive_document_edits WHERE file_id=? AND owner=?',(row['id'],uid)).fetchone()
    if edit:credit+=edit[0]
  remaining=max(0,DRIVE_QUOTA-storage_used(c,uid)+credit)
  if sum(item.size or 0 for item in files)>remaining:raise HTTPException(413,'OneDrive 存储空间不足。请释放空间后重试。')
 now=time.strftime('%Y-%m-%d %H:%M')
 with FILE_STORAGE.writing():
  try:
   total=0
   for item in files:
    key,size=await FILE_STORAGE.stage(item,remaining-total);staged.append((key,size));total+=size
   with db() as c:
    c.execute('BEGIN IMMEDIATE');check_parent(parent or None,uid)
    for parts,(key,size) in zip(paths,staged):
     check_file_path(c,uid,parent or None,parts)
     for part in parts[:-1]:
      if part.startswith(('゛','ဧ')):raise HTTPException(400,'文件夹不能以此字符开头。')
     target=parent or None
     for folder in parts[:-1]:
      existing=c.execute('SELECT id,kind FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,target,folder)).fetchone()
      if existing:
       if existing['kind']!='folder':raise HTTPException(409,'上传路径中已存在同名文件：'+folder)
       target=existing['id']
      else:
       fid=uuid.uuid4().hex;c.execute('INSERT INTO drive_files(id,owner,parent,name,kind,modified,created) VALUES(?,?,?,?,?,?,?)',(fid,uid,target,folder,'folder',now,now));target=fid
     name=parts[-1]
     existing=c.execute('SELECT id,kind FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,target,name)).fetchone()
     if existing and existing['kind'] in ['folder','vault']:raise HTTPException(409,'此位置已存在同名文件夹：'+name)
     if existing and conflict=='fail':collision('/'.join(parts))
     if existing and conflict=='rename':
      suffix=Path(name).suffix;stem=name[:-len(suffix)] if suffix else name;number=1
      while c.execute('SELECT 1 FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0',(uid,target,name)).fetchone():
       name=safe_name(f'{stem} ({number}){suffix}');number+=1
      check_file_path(c,uid,target,[name]);existing=None
     ext=Path(name).suffix.lower();kind={'.pdf':'pdf','.one':'notebook','.docx':'document','.xlsx':'spreadsheet','.pptx':'presentation','.md':'markdown','.txt':'text','.json':'text','.png':'image','.jpg':'image','.jpeg':'image','.webp':'image','.gif':'image','.avif':'image','.mp4':'video','.webm':'video'}.get(ext,'file')
     if existing:
      fid=existing['id'];old=c.execute('SELECT blob_key FROM drive_file_blobs WHERE file_id=? AND owner=?',(fid,uid)).fetchone()
      if old:discarded.append(old['blob_key'])
      c.execute('UPDATE drive_files SET kind=?,size=?,modified=?,content=NULL,source_id=NULL,full_detail=1 WHERE id=? AND owner=?',(kind,size,now,fid,uid))
      c.execute('DELETE FROM drive_document_edits WHERE file_id=? AND owner=?',(fid,uid))
     else:
      fid=uuid.uuid4().hex;c.execute('INSERT INTO drive_files(id,owner,parent,name,kind,size,modified,created) VALUES(?,?,?,?,?,?,?,?)',(fid,uid,target,name,kind,size,now,now))
     c.execute('INSERT INTO drive_file_blobs VALUES(?,?,?) ON CONFLICT(file_id) DO UPDATE SET blob_key=excluded.blob_key',(fid,uid,key));created.append(fid)
    check_storage(c,uid)
   committed=True
  except UploadTooLarge:raise HTTPException(413,'文件超过剩余存储空间或 250 GB 单文件限制')
  except OSError:raise HTTPException(507,'本地磁盘空间不足或无法写入文件，请稍后重试。')
  finally:
   if not committed:
    for key,_ in staged:FILE_STORAGE.discard(key)
 discard_unused_blobs(discarded)
 return {'ids':created}
@app.post('/api/files/{fid}/{action}')
async def mutate(fid:str,action:str,request:Request):
 uid=owner(request);f=file_for(fid,uid,allow_deleted=action in ['restore','purge'],metadata_only=action=='rename',include_content=action=='save');d=await request.json();discarded=[]
 if f['kind']=='vault' and action!='rename':raise HTTPException(400,'此操作不适用于个人保管库')
 if action in ['move','copy']:return transfer_files(uid,[fid],d.get('parent') or None,action)
 with db() as c:
  c.execute('BEGIN IMMEDIATE');f=file_for(fid,uid,allow_deleted=action in ['restore','purge'],metadata_only=action=='rename',include_content=action=='save')
  if action=='rename':
   name=safe_name(d.get('name'));check_file_path(c,uid,f['parent'],[name],subtree=fid,kind=f['kind'])
   color=d.get('color')
   if color is not None:
    palette=json.loads((ROOT/'content/folder-colors.json').read_text())
    if f['kind'] not in ['folder','vault'] or color not in {r['color'] for r in palette}:raise HTTPException(400,'请选择有效的文件夹颜色')
    c.execute('INSERT INTO drive_file_appearance VALUES(?,?,?) ON CONFLICT(file_id) DO UPDATE SET color=excluded.color',(fid,uid,color))
   if c.execute('SELECT 1 FROM drive_files WHERE owner=? AND parent IS ? AND name=? AND deleted=0 AND id<>?',(uid,f['parent'],name,fid)).fetchone():raise HTTPException(409,'此位置已存在同名文件')
   c.execute('UPDATE drive_files SET name=? WHERE id=? AND owner=?',(name,fid,uid))
  elif action=='delete':c.execute('UPDATE drive_files SET deleted=1 WHERE id=? AND owner=?',(fid,uid))
  elif action=='restore':c.execute('UPDATE drive_files SET deleted=0 WHERE id=? AND owner=?',(fid,uid))
  elif action=='purge':
   removed=set()
   def remove(item):
    removed.add(item)
    for child in c.execute('SELECT id FROM drive_files WHERE parent=? AND owner=?',(item,uid)).fetchall():remove(child['id'])
    blob=c.execute('SELECT blob_key FROM drive_file_blobs WHERE file_id=? AND owner=?',(item,uid)).fetchone()
    if blob:discarded.append(blob['blob_key'])
    c.execute('DELETE FROM drive_file_blobs WHERE file_id=? AND owner=?',(item,uid))
    c.execute('DELETE FROM drive_shares WHERE file_id=? AND owner=?',(item,uid));c.execute('DELETE FROM drive_comments WHERE file_id=? AND owner=?',(item,uid));c.execute('DELETE FROM drive_file_appearance WHERE file_id=? AND owner=?',(item,uid));c.execute('DELETE FROM drive_document_edits WHERE file_id=? AND owner=?',(item,uid));c.execute('DELETE FROM drive_files WHERE id=? AND owner=?',(item,uid))
   remove(fid)
   for bundle in c.execute('SELECT token,items FROM drive_share_bundles WHERE owner=?',(uid,)).fetchall():
    old=json.loads(bundle['items']);remaining=[item for item in old if item not in removed]
    if remaining!=old:
     if remaining:c.execute('UPDATE drive_share_bundles SET items=? WHERE token=?',(json.dumps(remaining),bundle['token']))
     else:c.execute('DELETE FROM drive_share_bundles WHERE token=?',(bundle['token'],))
   c.execute('DELETE FROM drive_share_options WHERE owner=? AND token NOT IN (SELECT token FROM drive_shares UNION SELECT token FROM drive_share_bundles)',(uid,))
  elif action=='favorite':c.execute('UPDATE drive_files SET favorite=? WHERE id=? AND owner=?',(int(bool(d.get('value'))),fid,uid))
  elif action=='save':
   if f['kind'] in ['folder','vault','pdf','image','video']:raise HTTPException(400,'此文件不支持文本编辑')
   text=d.get('text','')
   if not isinstance(text,str) or len(text)>2000000:raise HTTPException(413,'文档太大')
   discarded.extend(save_document(c,f,text))
  elif action=='share':
   ancestor=f
   while ancestor:
    if ancestor['kind']=='vault':raise HTTPException(400,'个人保管库中的文件不能共享')
    ancestor=c.execute('SELECT id,parent,kind FROM drive_files WHERE id=? AND owner=?',(ancestor['parent'],uid)).fetchone() if ancestor['parent'] else None
   mode=d.get('mode','view')
   if mode not in ['view','edit']:raise HTTPException(400,'Invalid permission')
   token=secrets.token_urlsafe(24);c.execute('INSERT INTO drive_shares VALUES(?,?,?,?,?)',(token,fid,uid,mode,int(time.time())))
   return {'ok':True,'url':str(request.base_url).rstrip('/')+'/s/'+token}
  elif action=='unshare':
   c.execute('DELETE FROM drive_shares WHERE token=? AND file_id=? AND owner=?',(d.get('token'),fid,uid))
   bundle=c.execute('SELECT items FROM drive_share_bundles WHERE token=? AND owner=?',(d.get('token'),uid)).fetchone()
   if bundle and fid in json.loads(bundle['items']):c.execute('DELETE FROM drive_share_bundles WHERE token=? AND owner=?',(d.get('token'),uid))
   if not c.execute('SELECT 1 FROM drive_shares WHERE token=? UNION SELECT 1 FROM drive_share_bundles WHERE token=?',(d.get('token'),d.get('token'))).fetchone():c.execute('DELETE FROM drive_share_options WHERE token=? AND owner=?',(d.get('token'),uid))
  elif action=='comment':
   text=d.get('text','').strip()
   if not text or len(text)>5000:raise HTTPException(400,'请输入评论')
   c.execute('INSERT INTO drive_comments VALUES(?,?,?,?,?)',(uuid.uuid4().hex,fid,uid,text,int(time.time())))
  else:raise HTTPException(404,'Unknown operation')
 discard_unused_blobs(discarded)
 return {'ok':True}
@app.get('/api/preferences')
def preferences(request:Request):
 with db() as c:r=c.execute('SELECT body FROM preferences WHERE owner=?',(owner(request),)).fetchone()
 return json.loads(r['body']) if r else {'theme':'system','photoDark':True,'format':'xml','memories':True,'themes':True,'deletions':True,'loop':True,'tags':True,'people':True,'importDismissed':False}
@app.post('/api/preferences')
async def save_preferences(request:Request):
 uid=owner(request);d=await request.json();allowed={'theme','photoDark','format','memories','themes','deletions','loop','tags','people','importDismissed','bannerDismissed'}
 if set(d)-allowed:raise HTTPException(400,'Invalid preference')
 data=preferences(request);data.update(d)
 with db() as c:c.execute('INSERT INTO preferences VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET body=excluded.body',(uid,json.dumps(data)))
 return data
@app.get('/api/albums')
def albums(request:Request):
 with db() as c:return [dict(r) for r in c.execute('SELECT id,name,created FROM drive_albums WHERE owner=?',(owner(request),))]
@app.get('/api/albums/{aid}')
def album_details(aid:str,request:Request):
 uid=owner(request)
 with db() as c:
  album=c.execute('SELECT id,name,created FROM drive_albums WHERE id=? AND owner=?',(aid,uid)).fetchone()
  if not album:raise HTTPException(404,'找不到此相册')
  ids=[r['file_id'] for r in c.execute('SELECT file_id FROM drive_album_files WHERE album_id=? AND owner=? ORDER BY position',(aid,uid))]
 result=[]
 for fid in ids:
  try:result.append(file_json(file_for(fid,uid)))
  except HTTPException as e:
   if e.status_code not in [404,423]:raise
 return {**dict(album),'files':result}
@app.post('/api/albums')
async def create_album(request:Request):
 uid=owner(request);d=await request.json();name=safe_name(d.get('name'));aid=uuid.uuid4().hex;ids=d.get('file_ids',[])
 if not isinstance(ids,list) or not ids or len(ids)>1000 or any(not isinstance(fid,str) for fid in ids):raise HTTPException(400,'请选择照片')
 ids=list(dict.fromkeys(ids))
 for fid in ids:
  f=file_for(fid,uid)
  if f['kind'] not in ['image','video']:raise HTTPException(400,'请选择照片或视频')
 with db() as c:
  c.execute('INSERT INTO drive_albums VALUES(?,?,?,?)',(aid,uid,name,int(time.time())))
  c.executemany('INSERT INTO drive_album_files VALUES(?,?,?,?)',[(aid,fid,uid,i) for i,fid in enumerate(ids)])
 return {'id':aid}
@app.post('/api/feedback')
async def feedback(request:Request):
 d=await request.json();body=d.get('text','').strip()
 if not body or len(body)>5000:raise HTTPException(400,'请输入反馈')
 with db() as c:c.execute('INSERT INTO local_feedback VALUES(?,?,?,?)',(uuid.uuid4().hex,owner(request),body,int(time.time())))
 return {'ok':True}
def shared_file(token,item=None):
 with db() as c:options=c.execute('SELECT * FROM drive_share_options WHERE token=?',(token,)).fetchone()
 if options and options['audience']=='people':
  actor=auth.resolve_session(REQUEST_TOKEN.get()) if REQUEST_TOKEN.get() else None
  if not actor or not actor['authenticated']:raise HTTPException(401,'请登录以访问此共享项')
  if actor['account']['account_id']!=options['owner'] and actor['account']['email_normalized'] not in json.loads(options['recipients']):raise HTTPException(403,'你没有访问此共享项的权限')
 with db() as c:r=c.execute('SELECT file_id,owner,mode FROM drive_shares WHERE token=?',(token,)).fetchone()
 if not r:
  with db() as c:bundle=c.execute('SELECT * FROM drive_share_bundles WHERE token=?',(token,)).fetchone()
  if not bundle:raise HTTPException(404,'此链接不存在或已失效')
  ids=json.loads(bundle['items']);r=dict(bundle)
  root={'id':'bundle-'+token,'owner':r['owner'],'parent':None,'name':str(len(ids))+' Items','kind':'bundle','size':0,'modified':'','created':'','content':None,'full_detail':1}
  if not item:return r,root,root
  f=file_for(item,r['owner']);current=f;found=False;seen=set()
  while current:
   if current['id'] in seen or current['kind']=='vault':raise HTTPException(404,'此链接不存在或已失效')
   seen.add(current['id']);found|=current['id'] in ids
   with db() as c:current=c.execute('SELECT * FROM drive_files WHERE id=? AND owner=?',(current['parent'],r['owner'])).fetchone() if current['parent'] else None
  if not found:raise HTTPException(404,'找不到此共享项')
  return r,root,f
 root=file_for(r['file_id'],r['owner']);f=file_for(item or root['id'],r['owner']);current=f;found=False;seen=set()
 while current:
  if current['id'] in seen or current['kind']=='vault':raise HTTPException(404,'此链接不存在或已失效')
  seen.add(current['id']);found|=current['id']==root['id']
  with db() as c:current=c.execute('SELECT * FROM drive_files WHERE id=? AND owner=?',(current['parent'],r['owner'])).fetchone() if current['parent'] else None
 if not found or (f['id']!=root['id'] and root['kind']!='folder'):raise HTTPException(404,'找不到此共享项')
 return r,root,f

def share_json(f,r,root):
 data=file_json(f);data['mode']=r['mode'];data['root_id']=root['id'];data['root_name']=root['name']
 if f['id']==root['id']:data['parent']=None
 if root['kind']=='bundle' and f['id'] in json.loads(r['items']):data['parent']=root['id']
 data['text']=document_text(f);data['original_office']=original_office(f);data['notebook_pages']=notebook_pages(f)
 data['editable']=r['mode']=='edit' and data['text'] is not None
 return data

@app.get('/api/share/{token}')
def public_share(token:str,item:str|None=None):
 r,root,f=shared_file(token,item);data=share_json(f,r,root)
 if f['kind']=='bundle':
  data['files']=[]
  for fid in json.loads(r['items']):
   try:
    _,_,child=shared_file(token,fid);data['files'].append(share_json(child,r,root))
   except HTTPException as exc:
    if exc.status_code not in [404,423]:raise
 elif f['kind']=='folder':
  with db() as c:children=c.execute('SELECT * FROM drive_files WHERE owner=? AND parent=? AND deleted=0 AND kind!=? ORDER BY position,name',(r['owner'],f['id'],'vault')).fetchall()
  data['files']=[share_json(dict(child),r,root) for child in children]
 return data

@app.get('/api/share/{token}/download')
def download_share(token:str,item:str|None=None):
 r,root,f=shared_file(token,item)
 if f['kind']=='bundle':
  ids=json.loads(r['items']);items=[shared_file(token,fid)[2] for fid in ids];roots=[]
  for selected in items:
   parent=selected['parent'];nested=False
   while parent:
    if parent in ids:nested=True;break
    parent=file_for(parent,r['owner'])['parent']
   if not nested:roots.append(selected)
  return archive_response(roots,r['owner'],'OneDrive.zip')
 return download_response(f,r['owner'])

@app.get('/api/share/{token}/content')
def content_share(token:str,item:str|None=None):
 r,root,f=shared_file(token,item)
 kind=mimetypes.guess_type(f['name'])[0] or 'application/octet-stream'
 inline=kind in ['application/pdf','image/png','image/jpeg','image/webp','image/gif','image/avif','video/mp4','video/webm']
 return file_response(f,kind if inline else 'application/octet-stream','inline' if inline else 'attachment')

@app.get('/api/share/{token}/note-page/{number}')
def share_note_page(token:str,number:int,item:str|None=None):
 r,root,f=shared_file(token,item)
 return notebook_page_response(f,number)

@app.get('/api/share/{token}/export-text')
def export_share_text(token:str,item:str|None=None):
 r,root,f=shared_file(token,item)
 return export_document(f)

@app.post('/api/share/{token}')
async def edit_share(token:str,request:Request,item:str|None=None):
 r,root,f=shared_file(token,item)
 if r['mode']!='edit':raise HTTPException(403,'此链接只有查看权限')
 d=await request.json();text=d.get('text')
 if not share_json(f,r,root)['editable']:raise HTTPException(400,'此文件不支持文本编辑')
 if not isinstance(text,str) or len(text)>2000000:raise HTTPException(400,'请输入有效内容')
 with db() as c:
  c.execute('BEGIN IMMEDIATE');r,root,f=shared_file(token,item)
  if r['mode']!='edit':raise HTTPException(403,'此链接只有查看权限')
  discarded=save_document(c,f,text)
 discard_unused_blobs(discarded)
 return {'ok':True}
@app.get('/api/public-pages')
def public_pages():
 p=ROOT/'content/public-routes.json';return json.loads(p.read_text()) if p.exists() else {}
@app.get('/api/boundaries/{bid}')
def boundary(bid:str):
 p=ROOT/'content/boundaries.json';d=json.loads(p.read_text()) if p.exists() else {}
 if bid not in d:raise HTTPException(404,'Unknown navigation target')
 return d[bid]
@app.post('/api/vault/unlock')
async def unlock_vault(request:Request):
 token,s=session(request);d=await request.json()
 result=auth.sign_in(token,email=s['account']['email_normalized'],password=d.get('password',''))
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS vault_sessions(digest TEXT PRIMARY KEY,expires INTEGER NOT NULL)')
  c.execute('INSERT OR REPLACE INTO vault_sessions VALUES(?,?)',(auth.session_owner_digest(result['session_token']),int(time.time())+1200))
 return set_cookie(JSONResponse({'ok':True}),result['session_token'])
@app.post('/api/legacy')
async def legacy(request:Request):
 uid=owner(request);d=await request.json();email=d.get('email','')
 if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise HTTPException(400,'请输入有效的电子邮件地址')
 smtp_message(email,'OneDrive 数字遗产邀请','你收到了本地 OneDrive 的受信任联系人邀请。\n'+str(request.base_url)+'account')
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS legacy_invites(id TEXT PRIMARY KEY,owner TEXT,recipient TEXT,created INTEGER)')
  c.execute('INSERT INTO legacy_invites VALUES(?,?,?,?)',(uuid.uuid4().hex,uid,email,int(time.time())))
 return {'ok':True}
from community import register as register_community
register_community(app,db,session,auth)
from community_editor import register as register_community_editor
register_community_editor(app,db,owner)

@app.get('/{path:path}',response_class=HTMLResponse)
def page(path:str,request:Request):
 _,s=session(request,False);logged=bool(s and s['authenticated'])
 public_offer=path.startswith('checkout/offer-') and '/'+path in json.loads((ROOT/'static/help.json').read_text())
 protected=path in ['my','shared','recycle','people','search'] or path.startswith(('folder/','file/','photos','settings','account')) or (path.startswith('checkout') and not public_offer)
 if protected and not logged:return RedirectResponse('/login?next='+quote(request.url.path+('?' + request.url.query if request.url.query else '')),303)
 if path=='' and not logged:
  p=ROOT/'templates/public-home.html'
  if p.exists():return HTMLResponse(p.read_text())
 if path.startswith('marketing/'):
  slug=path.removeprefix('marketing/')
  if re.fullmatch('[a-z0-9-]+',slug):
   p=ROOT/'templates'/('public-'+slug+'.html')
   if p.exists():return HTMLResponse(p.read_text())
 valid=path in ['','login','signup','verify','recover','logout','my','shared','recycle','people','search','plans','help','privacy','terms'] or path.startswith(('folder/','file/','photos','settings','account','checkout','boundary/','s/','help/'))
 if not valid:return HTMLResponse((ROOT/'templates/index.html').read_text(),status_code=404)
 return HTMLResponse((ROOT/'templates/index.html').read_text())
