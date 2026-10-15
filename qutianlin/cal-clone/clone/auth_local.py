"""Site-local resend adapter using the vendored auth store and its same database."""
import sqlite3
from websitebench.local_clone_auth import LocalAuthStore,AuthConflict,AuthRejected
from websitebench.local_clone_auth.store import (
 CHALLENGE_TTL_SECONDS,_hash_secret,_verification_code,_token,_recipient_digest,
)

class CalAuthStore(LocalAuthStore):
 def start_registration(self,session_token,*,email,**kwargs):
  with self.connect() as c:
   if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cal_account_emails'").fetchone() and c.execute('SELECT 1 FROM cal_account_emails WHERE email=? AND verified=1',(str(email).strip().lower(),)).fetchone():raise AuthConflict('This email is already in use.')
  return super().start_registration(session_token,email=email,**kwargs)
 def complete_registration(self,*args,**kwargs):
  try:return super().complete_registration(*args,**kwargs)
  except sqlite3.IntegrityError as exc:raise AuthConflict('This email is already in use.') from exc
 def resend(self,session_token,*,purpose):
  configs={'registration':('local_auth_registration_flows','pending_id'),'password-reset':('local_auth_password_reset_flows','reset_id')}
  if purpose not in configs:raise AuthRejected('Unknown verification purpose.')
  table,id_column=configs[purpose];now=self._now();code=_verification_code();salt,digest=_hash_secret(code);new_id=_token('registration' if purpose=='registration' else 'reset')
  with self.connect() as c,self._transaction(c):
   session=self._session_row(c,session_token)
   if session is None or session['account_id'] is not None:raise AuthRejected('Please restart this verification flow.')
   flow=c.execute('SELECT * FROM '+table+' WHERE session_digest=?',(session['session_digest'],)).fetchone()
   if flow is None or flow['verified_at'] is not None:raise AuthRejected('Please restart this verification flow.')
   old_id=flow[id_column];mail=c.execute('SELECT recipient,status,claim_token FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?',(purpose,old_id)).fetchone()
   if mail is not None and mail['claim_token'] is not None:raise AuthConflict('An email delivery is already in progress.')
   # The vendored store removes transient outbox rows on startup. Recover only
   # the recipient from the durable flow; generate a fresh code, never recover OTPs.
   if purpose=='registration':recipient=flow['email_normalized']
   else:
    account=c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(flow['account_id'],)).fetchone()
    recipient=account['email_normalized'] if account else None
   scopes=[('session',session['session_digest'])]
   if recipient:scopes.append(('recipient',_recipient_digest(recipient)))
   self._rate_limit_unlocked(c,purpose=purpose,scopes=scopes,now=now,ignore_cooldown=bool(mail and mail['status']=='SMTP_FAILED'))
   # Keep the original registration password hash or reset account binding.
   # Changing only challenge data invalidates every previous verification code.
   c.execute('UPDATE '+table+' SET '+id_column+'=?,code_salt=?,code_hash=?,expires_at=?,attempts=0,verified_at=NULL,updated_at=? WHERE session_digest=?',(new_id,salt,digest,now+CHALLENGE_TTL_SECONDS,now,session['session_digest']))
   c.execute('DELETE FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?',(purpose,old_id))
   if recipient:self._insert_mail_unlocked(c,purpose=purpose,flow_id=new_id,session_digest=session['session_digest'],recipient=recipient,now=now)
  with self._mail_secrets_lock:self._mail_secrets.pop(self._mail_secret_key(purpose,old_id),None)
  if recipient:self._remember_mail_code(purpose,new_id,code)
  return {'accepted':True,'expires_at':now+CHALLENGE_TTL_SECONDS}
