"""Site-owned extensions to the pinned local authentication runtime."""
import secrets
from backend.login_identifiers import resolve as resolve_phone
from websitebench.local_clone_auth import LocalAuthStore
from websitebench.local_clone_auth.store import (
 AuthRejected, AuthValidationError, CHALLENGE_TTL_SECONDS,
 _verification_code, _hash_secret, _recipient_digest, _verify_secret, _validate_password, PASSWORD_SCHEME,
)

class ICloudAuthStore(LocalAuthStore):
 def sign_in_identifier(self,token,*,identifier,password):
  if isinstance(identifier,str) and '@' in identifier:
   return self.sign_in(token,email=identifier,password=password)
  with self.connect() as db:email=resolve_phone(db,identifier)
  if email is None:
   # Consume the same password hashing work without revealing whether the
   # number is unknown, malformed or shared by more than one local account.
   salt,digest=_hash_secret('local-auth-dummy-password',salt=b'\0'*16)
   _verify_secret(password if isinstance(password,str) else '',salt,digest)
   raise AuthRejected('credentials are invalid')
  def unchanged(db,old_session,new_session):
   if resolve_phone(db,identifier)!=email:raise AuthRejected('credentials are invalid')
  return self.sign_in(token,email=email,password=password,session_rotation_callback=unchanged)

 def recovery_identifier(self,identifier):
  if isinstance(identifier,str) and '@' in identifier:return identifier
  with self.connect() as db:
   email=resolve_phone(db,identifier)
   if email:return email
   # Unknown/ambiguous numbers receive the normal non-disclosing reset state,
   # but no message. Do not accidentally address an existing local account.
   while True:
    missing='unresolved-'+secrets.token_hex(24)+'@icloud.offline.invalid'
    if not db.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=?',(missing,)).fetchone():return missing

 def change_password(self,token,*,current_password,new_password):
  password=_validate_password(new_password);salt,digest=_hash_secret(password);now=self._now()
  with self.connect() as db,self._transaction(db):
   session=self._session_row(db,token)
   if session is None or not session['account_id']:raise AuthRejected('Sign in required')
   owner=session['account_id'];row=db.execute('SELECT password_salt,password_hash FROM local_auth_accounts WHERE account_id=?',(owner,)).fetchone()
   if not isinstance(current_password,str) or not _verify_secret(current_password,bytes(row['password_salt']),bytes(row['password_hash'])):raise AuthRejected('Your current password is incorrect.')
   if _verify_secret(password,bytes(row['password_salt']),bytes(row['password_hash'])):raise AuthValidationError('Choose a password different from your current password.')
   db.execute('UPDATE local_auth_accounts SET password_salt=?,password_hash=?,password_scheme=?,password_updated_at=? WHERE account_id=?',(salt,digest,PASSWORD_SCHEME,now,owner))
   db.execute("DELETE FROM local_auth_mail_outbox WHERE purpose='password-reset' AND flow_id IN (SELECT reset_id FROM local_auth_password_reset_flows WHERE account_id=?)",(owner,))
   db.execute('DELETE FROM local_auth_password_reset_flows WHERE account_id=?',(owner,))
   db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL',(now,owner))
   return self._rotate_session_unlocked(db,session['session_digest'],owner,now,None)

 def prepare_mail_retry(self,token,*,purpose):
  if purpose not in ('registration','password-reset'):raise AuthValidationError('Unknown verification flow')
  owner=self.session_owner_digest(token)
  with self.connect() as db:row=db.execute('SELECT flow_id,status FROM local_auth_mail_outbox WHERE session_digest=? AND purpose=? ORDER BY mail_id DESC LIMIT 1',(owner,purpose)).fetchone()
  if row is None or row['status']!='SMTP_SENT' and self._mail_code(purpose,row['flow_id']) is None:
   # Restarted processes retain only hashes. Issue a new code rather than
   # pretending the old plaintext can be recovered from the database.
   return self.resend_verification(token,purpose=purpose)
  self.retry_failed_mail_for_session(token,purpose=purpose)

 def resend_verification(self, token, *, purpose):
  flows={'registration':('local_auth_registration_flows','pending_id'),
         'password-reset':('local_auth_password_reset_flows','reset_id')}
  if purpose not in flows:raise AuthValidationError('Unknown verification flow')
  table,key=flows[purpose];now=self._now();code=_verification_code()
  salt,digest=_hash_secret(code)
  with self.connect() as db,self._transaction(db):
   session=self._session_row(db,token)
   if session is None:raise AuthRejected('Sign in session has expired. Start again.')
   owner=session['session_digest']
   flow=db.execute(f'SELECT * FROM {table} WHERE session_digest=?',(owner,)).fetchone()
   if flow is None or flow['verified_at'] is not None:raise AuthRejected('Start a new verification request.')
   while _verify_secret(code,bytes(flow['code_salt']),bytes(flow['code_hash'])):
    code=_verification_code();salt,digest=_hash_secret(code)
   recipient=flow['email_normalized'] if purpose=='registration' else None
   scopes=[('session',owner)]
   if purpose=='password-reset' and flow['account_id']:
    account=db.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(flow['account_id'],)).fetchone()
    if account:recipient=account['email_normalized'];scopes.append(('account',flow['account_id']))
   if recipient:scopes.append(('recipient',_recipient_digest(recipient)))
   # Use the same persisted cooldown and hourly limits as initial delivery.
   self._rate_limit_unlocked(db,purpose=purpose,scopes=scopes,now=now)
   db.execute('DELETE FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?',(purpose,flow[key]))
   db.execute(f'UPDATE {table} SET code_salt=?,code_hash=?,expires_at=?,attempts=0,verified_at=NULL,updated_at=? WHERE {key}=?',
              (salt,digest,now+CHALLENGE_TTL_SECONDS,now,flow[key]))
   if recipient:self._insert_mail_unlocked(db,purpose=purpose,flow_id=flow[key],session_digest=owner,recipient=recipient,now=now)
  if recipient:self._remember_mail_code(purpose,flow[key],code)
  return {'ok':True,'expires_at':now+CHALLENGE_TTL_SECONDS}

 def cancel_verification(self,token,*,purpose):
  flows={'registration':('local_auth_registration_flows','pending_id'),
         'password-reset':('local_auth_password_reset_flows','reset_id')}
  if purpose not in flows:raise AuthValidationError('Unknown verification flow')
  table,key=flows[purpose]
  with self.connect() as db,self._transaction(db):
   session=self._session_row(db,token)
   if session is None:raise AuthRejected('Session has expired')
   row=db.execute(f'SELECT {key} FROM {table} WHERE session_digest=?',(session['session_digest'],)).fetchone()
   if row:
    db.execute('DELETE FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?',(purpose,row[key]))
    db.execute(f'DELETE FROM {table} WHERE session_digest=?',(session['session_digest'],))
