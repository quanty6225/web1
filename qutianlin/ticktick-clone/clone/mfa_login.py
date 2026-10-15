"""Keep password-authenticated MFA users anonymous until a second proof succeeds."""
import json,time,secrets,hashlib,hmac
from fastapi import HTTPException
from account_security import send_code,totp

def start(auth,a,data,session_token,db,dest):
 token=auth.create_anonymous_session();row=auth._session_row(db,token);code=str(secrets.randbelow(1000000)).zfill(6);salt=secrets.token_hex(16)
 if data.get('mfa',{}).get('mailEnabled'):send_code(a['email_normalized'],code)
 db.execute('CREATE TABLE IF NOT EXISTS ticktick_mfa_login(session_digest TEXT PRIMARY KEY,account_id TEXT NOT NULL,salt TEXT NOT NULL,code_hash TEXT NOT NULL,expires INTEGER NOT NULL,attempts INTEGER NOT NULL,dest TEXT NOT NULL)')
 db.execute('INSERT OR REPLACE INTO ticktick_mfa_login VALUES(?,?,?,?,?,?,?)',(row['session_digest'],a['account_id'],salt,hashlib.sha256((salt+code).encode()).hexdigest(),int(time.time())+600,0,dest))
 return token

def complete(auth,token,code,db,state,save):
 session=auth._session_row(db,token)
 if not session:raise HTTPException(400,'Verification session expired')
 row=db.execute('SELECT * FROM ticktick_mfa_login WHERE session_digest=?',(session['session_digest'],)).fetchone()
 if not row or row['expires']<time.time() or row['attempts']>=5:raise HTTPException(400,'Verification session expired. Sign in again.')
 a=dict(db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(row['account_id'],)).fetchone());data=state(db,a);mfa=data.get('mfa',{})
 db.execute('UPDATE ticktick_mfa_login SET attempts=attempts+1 WHERE session_digest=?',(session['session_digest'],))
 valid=mfa.get('mailEnabled') and hmac.compare_digest(row['code_hash'],hashlib.sha256((row['salt']+str(code)).encode()).hexdigest())
 if mfa.get('appEnabled') and mfa.get('secret'):valid=valid or any(hmac.compare_digest(str(code),totp(mfa['secret'],time.time()+shift)) for shift in [-30,0,30])
 digest=hashlib.sha256(str(code).encode()).hexdigest()
 if digest in mfa.get('backupCodes',[]):mfa['backupCodes'].remove(digest);save(db,a,data);valid=True
 if not valid:db.commit();raise HTTPException(400,'Incorrect verification code')
 new=auth._rotate_session_unlocked(db,session['session_digest'],a['account_id'],int(time.time()));db.execute('DELETE FROM ticktick_mfa_login WHERE session_digest=?',(session['session_digest'],));return new,row['dest']
