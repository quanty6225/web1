"""Account-owned commit signing keys; private material never leaves the backend."""
import base64,hashlib,os,secrets,shutil,sqlite3,subprocess,tempfile,time
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import UnsupportedAlgorithm,InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException,Request
from starlette.concurrency import run_in_threadpool

MAX_KEY_BYTES=100_000
MAX_COMMIT_BYTES=1_000_000

def command(args,*,input=None):
 try:return subprocess.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=True).stdout
 except (subprocess.SubprocessError,OSError):raise ValueError('Unable to use this unencrypted signing key.') from None

def gpg_args(home):
 return ['gpg','--no-options','--homedir',str(home),'--batch','--yes','--no-auto-key-retrieve','--no-auto-key-import','--disable-dirmngr','--pinentry-mode','loopback','--passphrase','']

def inspect_key(material):
 raw=material.encode()
 if 'BEGIN PGP PRIVATE KEY BLOCK' in material:
  if not shutil.which('gpg'):raise HTTPException(503,'GPG signing is unavailable on this server.')
  with tempfile.TemporaryDirectory(prefix='linear-gpg-') as directory:
   home=Path(directory);os.chmod(home,0o700)
   try:
    args=gpg_args(home);command(args+['--import'],input=raw)
    listing=command(args+['--with-colons','--list-secret-keys']).decode()
    rows=[line.split(':') for line in listing.splitlines()]
    if sum(r[0]=='sec' for r in rows)!=1:raise ValueError('Upload exactly one private key.')
    fingerprint=next(r[9] for r in rows if r[0]=='fpr')
    command(args+['--local-user',fingerprint,'--armor','--detach-sign'],input=b'Linear commit signing key validation')
    public=command(args+['--armor','--export',fingerprint]).decode()
    return {'scheme':'openpgp','fingerprint':fingerprint,'public_key':public},raw
   finally:
    if shutil.which('gpgconf'):subprocess.run(['gpgconf','--homedir',str(home),'--kill','gpg-agent'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
 try:
  key=serialization.load_ssh_private_key(raw,password=None) if 'BEGIN OPENSSH PRIVATE KEY' in material else serialization.load_pem_private_key(raw,password=None)
  public=key.public_key().public_bytes(serialization.Encoding.OpenSSH,serialization.PublicFormat.OpenSSH)
  canonical=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.OpenSSH,serialization.NoEncryption())
  fingerprint='SHA256:'+base64.b64encode(hashlib.sha256(base64.b64decode(public.split()[1])).digest()).decode().rstrip('=')
  return {'scheme':'ssh','fingerprint':fingerprint,'public_key':public.decode()},canonical
 except (ValueError,TypeError,NotImplementedError,UnsupportedAlgorithm):raise ValueError('Paste an unencrypted SSH or GPG private key.') from None

def sign_commit(material,metadata,payload):
 with tempfile.TemporaryDirectory(prefix='linear-sign-') as directory:
  home=Path(directory);os.chmod(home,0o700)
  if metadata['scheme']=='ssh':
   if not shutil.which('ssh-keygen'):raise HTTPException(503,'SSH signing is unavailable on this server.')
   key=home/'key';key.write_bytes(material);key.chmod(0o600);commit=home/'commit';commit.write_bytes(payload)
   command(['ssh-keygen','-Y','sign','-n','git','-f',str(key),str(commit)])
   return (home/'commit.sig').read_text()
  try:
   args=gpg_args(home);command(args+['--import'],input=material)
   return command(args+['--local-user',metadata['fingerprint'],'--armor','--detach-sign'],input=payload).decode()
  finally:
   if shutil.which('gpgconf'):subprocess.run(['gpgconf','--homedir',str(home),'--kill','gpg-agent'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)

def install(app,auth,actor,data_root):
 master=Path(data_root)/'.commit-signing-master'
 try:
  fd=os.open(master,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 except FileExistsError:pass
 else:
  with os.fdopen(fd,'wb') as file:file.write(secrets.token_bytes(32))
 if master.is_symlink() or len(master.read_bytes())!=32:raise RuntimeError('Invalid signing key encryption key file.')
 master.chmod(0o600);cipher=AESGCM(master.read_bytes())
 with auth.connect() as c:
  c.execute('''CREATE TABLE IF NOT EXISTS linear_commit_signing_keys(
   id TEXT PRIMARY KEY, account_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
   scheme TEXT NOT NULL, fingerprint TEXT NOT NULL, public_key TEXT NOT NULL,
   sealed_material BLOB NOT NULL, created_at INTEGER NOT NULL)''');c.commit()
 fields='id,name,scheme,fingerprint,public_key,created_at'
 def metadata(account):
  with auth.connect() as c:return [dict(r) for r in c.execute('SELECT '+fields+' FROM linear_commit_signing_keys WHERE account_id=?',(account['account_id'],))]
 @app.get('/api/commit-signing-keys')
 def list_keys(request:Request):
  account,_=actor(request);return metadata(account)
 @app.post('/api/commit-signing-keys')
 async def upload_key(request:Request):
  account,_=actor(request)
  body=await request.body()
  if len(body)>MAX_KEY_BYTES*2:raise HTTPException(413,'The key file is too large.')
  try:data=await request.json()
  except ValueError:raise HTTPException(422,'Enter a key name and private key.')
  name=data.get('name') if isinstance(data,dict) else None;material=data.get('material') if isinstance(data,dict) else None
  if not isinstance(name,str) or not name.strip() or len(name)>255:raise HTTPException(422,'Enter a key name of at most 255 characters.')
  if not isinstance(material,str) or not material.strip() or len(material.encode())>MAX_KEY_BYTES:raise HTTPException(422,'Paste an unencrypted SSH or GPG private key.')
  if metadata(account):raise HTTPException(409,'Remove the existing signing key before adding another.')
  try:info,raw=await run_in_threadpool(inspect_key,material)
  except ValueError as error:raise HTTPException(422,str(error))
  identity='signing_'+secrets.token_hex(16);nonce=secrets.token_bytes(12);associated=(account['account_id']+':'+identity).encode();sealed=nonce+cipher.encrypt(nonce,raw,associated)
  with auth.connect() as c:
   try:c.execute('INSERT INTO linear_commit_signing_keys VALUES(?,?,?,?,?,?,?,?)',(identity,account['account_id'],name.strip(),info['scheme'],info['fingerprint'],info['public_key'],sealed,int(time.time())));c.commit()
   except sqlite3.IntegrityError:raise HTTPException(409,'A signing key is already registered.')
  return metadata(account)[0]
 @app.delete('/api/commit-signing-keys/{identity}')
 def delete_key(identity:str,request:Request):
  account,_=actor(request)
  with auth.connect() as c:
   changed=c.execute('DELETE FROM linear_commit_signing_keys WHERE id=? AND account_id=?',(identity,account['account_id'])).rowcount;c.commit()
  if not changed:raise HTTPException(404,'Signing key not found.')
  return {'deleted':True}
 @app.post('/api/commit-signing-keys/{identity}/sign')
 async def sign(identity:str,request:Request):
  account,_=actor(request)
  with auth.connect() as c:row=c.execute('SELECT * FROM linear_commit_signing_keys WHERE id=? AND account_id=?',(identity,account['account_id'])).fetchone()
  if not row:raise HTTPException(404,'Signing key not found.')
  body=await request.body()
  if len(body)>MAX_COMMIT_BYTES*2:raise HTTPException(413,'Commit payload is too large.')
  try:
   data=await request.json();payload=base64.b64decode(data.get('payload',''),validate=True)
   if not payload or len(payload)>MAX_COMMIT_BYTES:raise ValueError()
  except (ValueError,TypeError,AttributeError):raise HTTPException(422,'Provide a base64 encoded commit payload.')
  sealed=row['sealed_material'];associated=(account['account_id']+':'+identity).encode()
  try:
   material=cipher.decrypt(sealed[:12],sealed[12:],associated)
   signature=await run_in_threadpool(sign_commit,material,dict(row),payload)
  except (ValueError,InvalidTag):raise HTTPException(422,'Unable to sign this commit.')
  return {'scheme':row['scheme'],'fingerprint':row['fingerprint'],'signature':signature}
