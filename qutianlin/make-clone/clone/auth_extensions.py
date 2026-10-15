"""Make-local auth additions; vendored authentication code remains unchanged."""
from websitebench.local_clone_auth.store import (
 LocalAuthStore,AuthRejected,AuthValidationError,CHALLENGE_TTL_SECONDS,PASSWORD_SCHEME,
 _token,_verification_code,_hash_secret,_recipient_digest,_validate_display_name,_validate_password,_verify_secret,
)

class MakeAuthStore(LocalAuthStore):
 def update_profile(self,session_token,name):
  if not isinstance(name,str):raise AuthValidationError('Enter your full name.')
  name=_validate_display_name(name)
  with self.connect() as db,self._transaction(db):
   session=self._session_row(db,session_token)
   if session is None or session['account_id'] is None:raise AuthRejected('Please sign in.')
   db.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(name,session['account_id']))
  return self.resolve_session(session_token)['account']

 def change_password(self,session_token,current_password,new_password):
  if not isinstance(current_password,str) or not isinstance(new_password,str):raise AuthValidationError('Enter your current and new passwords.')
  _validate_password(new_password)
  now=self._now();salt,password_hash=_hash_secret(new_password)
  with self.connect() as db,self._transaction(db):
   session=self._session_row(db,session_token)
   if session is None or session['account_id'] is None:raise AuthRejected('Please sign in.')
   account=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(session['account_id'],)).fetchone()
   if not _verify_secret(current_password,bytes(account['password_salt']),bytes(account['password_hash'])):raise AuthRejected('Current password is incorrect.')
   if current_password==new_password:raise AuthValidationError('Choose a different new password.')
   db.execute('UPDATE local_auth_accounts SET password_salt=?,password_hash=?,password_scheme=?,password_updated_at=? WHERE account_id=?',(salt,password_hash,PASSWORD_SCHEME,now,session['account_id']))
   # Invalidate all prior sessions and outstanding reset challenges atomically.
   db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL',(now,session['account_id']))
   db.execute("DELETE FROM local_auth_mail_outbox WHERE purpose='password-reset' AND flow_id IN (SELECT reset_id FROM local_auth_password_reset_flows WHERE account_id=?)",(session['account_id'],))
   db.execute('DELETE FROM local_auth_password_reset_flows WHERE account_id=?',(session['account_id'],))
   return self._rotate_session_unlocked(db,str(session['session_digest']),str(session['account_id']),now,None)

 def resend_registration(self,session_token,email):
  self.ensure_schema();now=self._now();code=_verification_code();salt,digest=_hash_secret(code);pending_id=_token('registration')
  with self.connect() as db,self._transaction(db):
   session=self._session_row(db,session_token)
   if session is None or session['account_id'] is not None:raise AuthRejected('Start registration in this browser before requesting a new verification email.')
   flow=db.execute('SELECT * FROM local_auth_registration_flows WHERE session_digest=?',(session['session_digest'],)).fetchone()
   if flow is None or flow['verified_at'] is not None or not isinstance(email,str) or flow['email_normalized']!=email.strip().lower():
    raise AuthRejected('Start registration with this email in the same browser before requesting a new verification email.')
   self._rate_limit_unlocked(db,purpose='registration',scopes=[('session',session['session_digest']),('recipient',_recipient_digest(flow['email_normalized']))],now=now)
   db.execute("DELETE FROM local_auth_mail_outbox WHERE purpose='registration' AND flow_id=?",(flow['pending_id'],))
   db.execute('UPDATE local_auth_registration_flows SET pending_id=?,code_salt=?,code_hash=?,expires_at=?,attempts=0,updated_at=? WHERE session_digest=?',(pending_id,salt,digest,now+CHALLENGE_TTL_SECONDS,now,session['session_digest']))
   self._insert_mail_unlocked(db,purpose='registration',flow_id=pending_id,session_digest=session['session_digest'],recipient=flow['email_normalized'],now=now)
  with self._mail_secrets_lock:self._mail_secrets.pop(('registration',str(flow['pending_id'])),None)
  self._remember_mail_code('registration',pending_id,code)
  return {'expires_at':now+CHALLENGE_TTL_SECONDS}
