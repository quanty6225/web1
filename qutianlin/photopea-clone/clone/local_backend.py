"""Independent local accounts and PeaDrive. No source sessions are consumed."""
import hashlib,hmac,json,os,re,secrets,smtplib,sqlite3,time
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request,Response
from fastapi.responses import Response as BytesResponse
from websitebench.site_backend import load_runtime
ROOT=Path(__file__).resolve().parent
RUNTIME=load_runtime(ROOT/'backend/runtime.json')
assert RUNTIME.site_id=='photopea'
DATA=Path(os.environ.get('PHOTOPEA_DATA_DIR',str(ROOT.parent/RUNTIME.data_dir))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/RUNTIME.database_filename
router=APIRouter(prefix='/api')
COOKIE='photopea_session'
TTL=7*86400
@contextmanager
def db():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL')
 try:yield c;c.commit()
 except: c.rollback();raise
 finally:c.close()
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def code_hash(code,salt=None):
 salt=salt or secrets.token_hex(16)
 return salt+':'+digest(salt+':'+str(code))
def password_hash(value,salt=None):
 salt=salt or secrets.token_hex(16)
 return 'scrypt:'+salt+':'+hashlib.scrypt(value.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def password_ok(value,encoded):
 if encoded.startswith('scrypt:'):return hmac.compare_digest(password_hash(value,encoded.split(':')[1]),encoded)
 # Read compatibility for accounts created during early local development.
 salt=encoded.split(':')[0]
 return hmac.compare_digest(salt+':'+hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),240000).hex(),encoded)
def validate_password(value):
 if not isinstance(value,str) or not 8<=len(value)<=128:raise HTTPException(400,'Use a password of 8–128 characters.')
 return value
def email_value(value):
 value=str(value or '').strip().lower()
 if len(value)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise HTTPException(400,'Enter a valid email address.')
 return value
def public_user(row):return {k:row[k] for k in ['id','email','name']}
def actor(request):
 token=request.cookies.get(COOKIE,'')
 with db() as c:r=c.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?',(digest(token),time.time())).fetchone()
 if not r:raise HTTPException(401,'Log in to use PeaDrive.')
 return r
def session(c,user_id,response,request):
 old=request.cookies.get(COOKIE)
 if old:c.execute('DELETE FROM sessions WHERE token=?',(digest(old),))
 value=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(value),user_id,time.time()+TTL))
 response.set_cookie(COOKIE,value,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=TTL,path='/')
def mail(email,code,kind):
 m=EmailMessage();m['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@photopea.clone.test');m['To']=email
 m['Subject']='Photopea '+('email verification' if kind=='register' else 'password reset')
 m.set_content('Your Photopea '+kind+' verification code is: '+code+'\nThis code expires in 10 minutes.\nUse it in your local Photopea account page.\n')
 try:
  with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=8) as smtp:smtp.send_message(m)
 except (OSError,smtplib.SMTPException):raise HTTPException(503,'Email could not be sent. Please try again.')
def challenge(c,email,kind,payload):
 old=c.execute('SELECT created FROM challenges WHERE email=? AND kind=?',(email,kind)).fetchone()
 if old and time.time()-old['created']<20:raise HTTPException(429,'Please wait 20 seconds before requesting another code.')
 code=str(secrets.randbelow(1000000)).zfill(6)
 mail(email,code,kind)
 c.execute('INSERT OR REPLACE INTO challenges VALUES(?,?,?,?,?,?,?)',(email,kind,code_hash(code),json.dumps(payload),time.time()+600,0,time.time()))
def consume(c,email,kind,code):
 row=c.execute('SELECT * FROM challenges WHERE email=? AND kind=?',(email,kind)).fetchone()
 if not row or row['expires']<time.time() or row['attempts']>=5:raise HTTPException(400,'Code expired or unavailable. Request a new code.')
 if not hmac.compare_digest(row['code'],code_hash(code,row['code'].split(':')[0])):
  c.execute('UPDATE challenges SET attempts=attempts+1 WHERE email=? AND kind=?',(email,kind));c.commit()
  raise HTTPException(400,'Incorrect verification code.')
 c.execute('DELETE FROM challenges WHERE email=? AND kind=?',(email,kind))
 return json.loads(row['payload'])
def initialize():
 with db() as c:
  c.executescript("""
  CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS challenges(email TEXT,kind TEXT,code TEXT,payload TEXT,expires REAL,attempts INTEGER,created REAL,PRIMARY KEY(email,kind));
  CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,body BLOB NOT NULL,created REAL,updated REAL);
  CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY,count INTEGER,started REAL);
 PRAGMA user_version=1;
  """)
  if not c.execute('SELECT id FROM users WHERE email=?',('demo@photopea.offline.invalid',)).fetchone():
   c.execute('INSERT INTO users VALUES(?,?,?,?)',(secrets.token_hex(16),'demo@photopea.offline.invalid','Demo',password_hash('PhotopeaLocal!2026')))
initialize()
@router.get('/session')
def session_status(request:Request):
 try:return {'user':public_user(actor(request))}
 except HTTPException as error:
  if error.status_code!=401:raise
  return {'user':None}
@router.get('/me')
def me(request:Request):return public_user(actor(request))
@router.post('/register')
async def register(request:Request):
 data=await request.json();email=email_value(data.get('email'));password=validate_password(data.get('password'));name=str(data.get('name','')).strip()[:100]
 if not name:raise HTTPException(400,'Enter your name.')
 with db() as c:
  if c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():raise HTTPException(409,'An account already exists. Log in or reset your password.')
  challenge(c,email,'register',{'name':name,'password':password_hash(password)})
 return {'sent':True}
@router.post('/verify')
async def verify(request:Request,response:Response):
 data=await request.json();email=email_value(data.get('email'))
 with db() as c:
  c.execute('BEGIN IMMEDIATE');payload=consume(c,email,'register',data.get('code'));uid=secrets.token_hex(16)
  if c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():raise HTTPException(409,'An account already exists.')
  c.execute('INSERT INTO users VALUES(?,?,?,?)',(uid,email,payload['name'],payload['password']));session(c,uid,response,request)
 return {'id':uid,'email':email,'name':payload['name']}
@router.post('/login')
async def login(request:Request,response:Response):
 data=await request.json();email=email_value(data.get('email'));password=str(data.get('password',''))[:129]
 key=digest(email+':'+str(request.client.host if request.client else 'local'))
 with db() as c:
  limit=c.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
  if limit and time.time()-limit['started']<300 and limit['count']>=10:raise HTTPException(429,'Too many attempts. Try again in five minutes.')
  row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
  if not row or not password_ok(password,row['password']):
   if not limit or time.time()-limit['started']>=300:c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(key,1,time.time()))
   else:c.execute('UPDATE login_attempts SET count=count+1 WHERE key=?',(key,))
   c.commit();raise HTTPException(401,'Incorrect email or password.')
  c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
  if not row['password'].startswith('scrypt:'):c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(password),row['id']))
  session(c,row['id'],response,request)
 return public_user(row)
@router.post('/logout')
def logout(request:Request,response:Response):
 with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(digest(request.cookies.get(COOKIE,'')),))
 response.delete_cookie(COOKIE,path='/');return {'logged_out':True}
@router.post('/recover')
async def recover(request:Request):
 data=await request.json();email=email_value(data.get('email'))
 with db() as c:
  if c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():
   try:challenge(c,email,'reset',{})
   except HTTPException as error:
    if error.status_code!=429:raise
 return {'accepted':True}
@router.post('/reset')
async def reset(request:Request):
 data=await request.json();email=email_value(data.get('email'));password=validate_password(data.get('password'))
 with db() as c:
  c.execute('BEGIN IMMEDIATE');consume(c,email,'reset',data.get('code'));row=c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
  if not row:raise HTTPException(400,'Account unavailable.')
  c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(password),row['id']));c.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
 return {'reset':True}
@router.patch('/me')
async def profile(request:Request):
 user=actor(request);data=await request.json();name=str(data.get('name','')).strip()
 if not 1<=len(name)<=100:raise HTTPException(400,'Enter a name of 1–100 characters.')
 with db() as c:c.execute('UPDATE users SET name=? WHERE id=?',(name,user['id']))
 return {**public_user(user),'name':name}
@router.get('/projects')
def projects(request:Request):
 user=actor(request)
 with db() as c:rows=c.execute('SELECT id,name,length(body) AS size,created,updated FROM projects WHERE user_id=? ORDER BY updated DESC',(user['id'],)).fetchall()
 return {'projects':[dict(r) for r in rows],'used':sum(r['size'] for r in rows),'quota':500000000}
def project(c,pid,user):
 row=c.execute('SELECT * FROM projects WHERE id=? AND user_id=?',(pid,user['id'])).fetchone()
 if not row:raise HTTPException(404,'Project not found.')
 return row
async def save_project(request,pid=None):
 user=actor(request);name=request.query_params.get('name','New Project.psd').strip()
 if not 1<=len(name)<=180 or any(x in name for x in '/\\\0\r\n'):raise HTTPException(400,'Enter a valid project name.')
 body=bytearray()
 async for chunk in request.stream():
  body.extend(chunk)
  if len(body)>64*1024*1024:raise HTTPException(413,'The local project limit is 64 MiB. Save larger documents to your device.')
 if not body.startswith(b'8BPS'):raise HTTPException(400,'Expected a Photoshop PSD document.')
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  previous=project(c,pid,user) if pid else None
  used=c.execute('SELECT COALESCE(SUM(length(body)),0) FROM projects WHERE user_id=?',(user['id'],)).fetchone()[0]
  if used+len(body)-(len(previous['body']) if previous else 0)>500000000:raise HTTPException(413,'PeaDrive storage is full.')
  if previous:c.execute('UPDATE projects SET name=?,body=?,updated=? WHERE id=?',(name,bytes(body),time.time(),pid))
  else:
   pid=secrets.token_hex(16);c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(pid,user['id'],name,bytes(body),time.time(),time.time()))
 return {'id':pid,'name':name,'size':len(body)}
@router.post('/projects')
async def create_project(request:Request):return await save_project(request)
@router.put('/projects/{pid}')
async def update_project(pid:str,request:Request):return await save_project(request,pid)
@router.get('/projects/{pid}')
def get_project(pid:str,request:Request):
 user=actor(request)
 with db() as c:row=project(c,pid,user)
 return BytesResponse(row['body'],media_type='image/vnd.adobe.photoshop',headers={'Cache-Control':'no-store','Content-Disposition':"attachment; filename*=UTF-8''"+__import__('urllib.parse',fromlist=['quote']).quote(row['name'])})
@router.patch('/projects/{pid}')
async def rename_project(pid:str,request:Request):
 user=actor(request);data=await request.json();name=str(data.get('name','')).strip()
 if not 1<=len(name)<=180 or any(x in name for x in '/\\\0\r\n'):raise HTTPException(400,'Enter a valid project name.')
 with db() as c:project(c,pid,user);c.execute('UPDATE projects SET name=?,updated=? WHERE id=?',(name,time.time(),pid))
 return {'id':pid,'name':name}
@router.delete('/projects/{pid}')
def delete_project(pid:str,request:Request):
 user=actor(request)
 with db() as c:project(c,pid,user);c.execute('DELETE FROM projects WHERE id=?',(pid,))
 return {'deleted':True}
