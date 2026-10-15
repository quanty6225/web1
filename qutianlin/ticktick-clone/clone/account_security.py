"""Local SMTP proof and second-factor state; no identity provider traffic."""
import secrets,time,hashlib,smtplib,os,hmac,base64,struct
from email.message import EmailMessage
from fastapi import HTTPException

def send_code(recipient,code):
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@ticktick.clone.test');msg['To']=recipient;msg['Subject']='TickTick Safety Verification';msg.set_content('Your verification code is '+code+'.\nIt expires in 10 minutes and can be used once.\n')
 try:
  host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
  if host not in ['127.0.0.1','localhost','::1']:raise ValueError('SMTP must be local')
  with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=10) as s:s.send_message(msg)
 except Exception:raise HTTPException(503,'Email could not be sent. Please try again.')

def challenge(d,recipient,purpose):
 now=int(time.time());challenges=d.setdefault('securityChallenges',{})
 recent=[x for x in challenges.values() if x['purpose']==purpose and x['created']>now-60]
 if recent:raise HTTPException(429,'Please wait before sending another code')
 ident=secrets.token_urlsafe(24);code=str(secrets.randbelow(1000000)).zfill(6);salt=secrets.token_hex(16)
 send_code(recipient,code)
 challenges.clear();challenges[ident]={'salt':salt,'hash':hashlib.sha256((salt+code).encode()).hexdigest(),'purpose':purpose,'recipient':recipient,'created':now,'expires':now+600,'attempts':0,'used':False}
 return ident

def verify(d,code,ident=None):
 records=d.setdefault('securityChallenges',{});ident=ident or next(reversed(records),None);row=records.get(ident)
 if not row or row['expires']<time.time() or row['used'] or row['attempts']>=5:raise HTTPException(400,'Verification code expired. Send a new code.')
 row['attempts']+=1
 if not hmac.compare_digest(row['hash'],hashlib.sha256((row['salt']+str(code)).encode()).hexdigest()):raise HTTPException(400,'Incorrect verification code')
 row['used']=True;proof=secrets.token_urlsafe(32);d['securityProof']={'hash':hashlib.sha256(proof.encode()).hexdigest(),'expires':int(time.time())+600,'purpose':row['purpose']};return proof

def require_proof(d,req):
 proof=req.headers.get('x-verify-id','');row=d.get('securityProof',{})
 if row.get('expires',0)<time.time() or not hmac.compare_digest(row.get('hash',''),hashlib.sha256(proof.encode()).hexdigest()):raise HTTPException(403,'Safety verification required')

def totp(secret,stamp=None):
 counter=int(stamp or time.time())//30;raw=hmac.new(base64.b32decode(secret),struct.pack('>Q',counter),hashlib.sha1).digest();offset=raw[-1]&15;return str((struct.unpack('>I',raw[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)

def handle(path,method,body,req,a,d,db,save,uid):
 mfa=d.setdefault('mfa',{})
 def persist():save(db,a,d)
 if path=='user/mfa':return bool(mfa.get('enabled'))
 if path=='user/mfa/setting':return {'id':uid,'mfaEnabled':bool(mfa.get('enabled')),'mailOption':{'enabled':bool(mfa.get('mailEnabled'))},'phoneOption':None,'appOption':{'enabled':bool(mfa.get('appEnabled'))},'backupOption':{'enabled':bool(mfa.get('backupCodes'))}}
 if path=='user/mfa/code':
  if body.get('method','mail')!='mail':raise HTTPException(400,'Use the configured email or authenticator')
  ident=challenge(d,a['email_normalized'],'account-security:'+str(body.get('type',1)));persist();return {'oid':ident}
 if path=='user/mfa/code/verify':
  try:proof=verify(d,body.get('code',body.get('verificationCode','')),body.get('oid'))
  except HTTPException:persist();db.commit();raise
  persist();return {'vid':proof,'expireTime':600}
 require_proof(d,req)
 if path=='user/mfa/secret/create':
  mfa['pendingSecret']=base64.b32encode(secrets.token_bytes(20)).decode();mfa['pendingOid']=secrets.token_urlsafe(24);mfa['pendingExpires']=int(time.time())+600;persist();return {'oid':mfa['pendingOid'],'secret':mfa['pendingSecret'],'url':'otpauth://totp/TickTick:'+a['email_normalized']+'?secret='+mfa['pendingSecret']+'&issuer=TickTick'}
 if path=='user/mfa/create':
  method_name=body.get('method','mail')
  if method_name=='app':
   code=str(body.get('code',''));secret=mfa.get('pendingSecret')
   if mfa.get('pendingExpires',0)<time.time() or body.get('oid')!=mfa.get('pendingOid') or not secret or not any(hmac.compare_digest(code,totp(secret,time.time()+shift)) for shift in [-30,0,30]):raise HTTPException(400,'Incorrect authenticator code')
   mfa['secret']=mfa.pop('pendingSecret');mfa['appEnabled']=True
  elif method_name=='mail':
   previous_proof=d.get('securityProof')
   try:verify(d,body.get('code',''),body.get('oid'))
   except HTTPException:persist();db.commit();raise
   d['securityProof']=previous_proof
   mfa['mailEnabled']=True
  else:raise HTTPException(400,'Unsupported verification method')
  mfa['enabled']=True;persist();return {'mfaEnabled':True}
 if path=='user/mfa/toggle':
  if body.get('mfaEnabled') and not (mfa.get('mailEnabled') or mfa.get('appEnabled')):raise HTTPException(400,'Configure a second factor before enabling verification')
  mfa['enabled']=bool(body.get('mfaEnabled'));persist();return {'mfaEnabled':mfa['enabled']}
 if path=='user/mfa/delete':
  method_name=body.get('method',req.query_params.get('method'))
  if method_name=='mail':mfa.pop('mailEnabled',None)
  elif method_name=='app':mfa.pop('appEnabled',None);mfa.pop('secret',None)
  elif method_name=='backup':mfa.pop('backupCodes',None)
  else:mfa.clear()
  if not (mfa.get('mailEnabled') or mfa.get('appEnabled')):mfa['enabled']=False
  persist();return {}
 if path in ['user/mfa/backup/create','user/mfa/backup/code']:
  if path.endswith('/create'):
   codes=[secrets.token_hex(5) for _ in range(10)];mfa['backupCodes']=[hashlib.sha256(x.encode()).hexdigest() for x in codes];persist();return {'codes':codes}
  return {'remaining':len(mfa.get('backupCodes',[]))}
 raise HTTPException(404,'Unknown security operation')
