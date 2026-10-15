"""Verified secondary email and account lifecycle operations for local accounts."""
import time
from cal_core import DomainError,email,uid
from websitebench.local_clone_auth.store import _hash_secret,_verify_secret,_verification_code

class Accounts:
 def __init__(self,store,auth):
  self.store,self.auth,self._now=store,auth,lambda:int(time.time())
  with store.db(True) as c:c.executescript('''
   CREATE TABLE IF NOT EXISTS cal_account_emails(id TEXT PRIMARY KEY,owner TEXT NOT NULL,email TEXT UNIQUE NOT NULL,verified INTEGER NOT NULL DEFAULT 0,code_salt BLOB,code_hash BLOB,expires_at INTEGER,attempts INTEGER NOT NULL DEFAULT 0,mail_state TEXT NOT NULL DEFAULT '',last_sent INTEGER NOT NULL DEFAULT 0,make_primary INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS cal_email_limits(owner TEXT PRIMARY KEY,window INTEGER NOT NULL,count INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS cal_deleted_accounts(subject_id TEXT PRIMARY KEY,deleted_at INTEGER NOT NULL);
   CREATE TRIGGER IF NOT EXISTS cal_verified_alias_insert BEFORE INSERT ON local_auth_accounts
   WHEN EXISTS(SELECT 1 FROM cal_account_emails WHERE email=NEW.email_normalized AND verified=1 AND owner!=NEW.account_id)
   BEGIN SELECT RAISE(ABORT,'email is already verified on another account'); END;
   CREATE TRIGGER IF NOT EXISTS cal_verified_alias_update BEFORE UPDATE OF email_normalized ON local_auth_accounts
   WHEN EXISTS(SELECT 1 FROM cal_account_emails WHERE email=NEW.email_normalized AND verified=1 AND owner!=NEW.account_id)
   BEGIN SELECT RAISE(ABORT,'email is already verified on another account'); END;
  ''')
 def _account(self,c,owner):
  row=c.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(owner,)).fetchone()
  if not row:raise DomainError('Account not found.',404)
  return row
 def _ensure_primary(self,c,owner):
  account=self._account(c,owner);existing=c.execute('SELECT owner FROM cal_account_emails WHERE email=?',(account['email_normalized'],)).fetchone()
  if existing and existing['owner']!=owner:
   if c.execute('SELECT verified FROM cal_account_emails WHERE email=?',(account['email_normalized'],)).fetchone()['verified']:raise DomainError('This email is already verified on another account.',409)
   c.execute('DELETE FROM cal_account_emails WHERE email=?',(account['email_normalized'],))
  c.execute('INSERT INTO cal_account_emails(id,owner,email,verified) VALUES(?,?,?,1) ON CONFLICT(email) DO UPDATE SET verified=1',(uid(),owner,account['email_normalized']))
  return account
 def list(self,owner):
  with self.store.db(True) as c:
   account=self._ensure_primary(c,owner)
   return [{'id':r['id'],'email':r['email'],'verified':bool(r['verified']),'primary':r['email']==account['email_normalized'],'mail_state':r['mail_state']} for r in c.execute('SELECT * FROM cal_account_emails WHERE owner=? ORDER BY email!=?,rowid',(owner,account['email_normalized']))]
 def start(self,owner,address,make_primary=None):
  address=email(address);now=self._now();code=_verification_code();salt,digest=_hash_secret(code)
  with self.store.db(True) as c:
   self._ensure_primary(c,owner)
   if c.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=? AND account_id!=?',(address,owner)).fetchone():raise DomainError('This email is already in use.',409)
   row=c.execute('SELECT * FROM cal_account_emails WHERE email=?',(address,)).fetchone()
   if row and row['owner']!=owner:raise DomainError('This email is already in use.',409)
   if row and row['mail_state']!='failed' and now-row['last_sent']<60:raise DomainError('Please wait before requesting another email.',429)
   limit=c.execute('SELECT * FROM cal_email_limits WHERE owner=?',(owner,)).fetchone();window=limit['window'] if limit and now-limit['window']<3600 else now;count=limit['count'] if limit and window==limit['window'] else 0
   if count>=6:raise DomainError('Too many verification emails. Please try again later.',429)
   c.execute('INSERT INTO cal_email_limits VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET window=excluded.window,count=excluded.count',(owner,window,count+1))
   ident=row['id'] if row else uid()
   if make_primary is None:make_primary=bool(row and row['make_primary'])
   c.execute("INSERT INTO cal_account_emails(id,owner,email,code_salt,code_hash,expires_at,mail_state,last_sent,make_primary) VALUES(?,?,?,?,?,?,'sending',?,?) ON CONFLICT(id) DO UPDATE SET code_salt=excluded.code_salt,code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0,mail_state='sending',last_sent=excluded.last_sent,make_primary=excluded.make_primary",(ident,owner,address,salt,digest,now+600,now,int(bool(make_primary))))
  return {'id':ident,'recipient':address,'code':code,'generation':digest}
 def finish(self,ident,generation,sent):
  with self.store.db(True) as c:c.execute('UPDATE cal_account_emails SET mail_state=? WHERE id=? AND code_hash=?',('sent' if sent else 'failed',ident,generation))
 def verify(self,owner,ident,code):
  failure=None;primary=False
  with self.store.db(True) as c:
   row=c.execute('SELECT * FROM cal_account_emails WHERE id=? AND owner=?',(ident,owner)).fetchone()
   if not row:raise DomainError('Email not found.',404)
   if not row['code_hash'] or row['attempts']>=5:raise DomainError('Request a new verification email.',400)
   if row['expires_at']<=self._now():raise DomainError('This verification code has expired.',400)
   if not _verify_secret(str(code).strip(),bytes(row['code_salt']),bytes(row['code_hash'])):
    c.execute('UPDATE cal_account_emails SET attempts=attempts+1 WHERE id=?',(ident,));failure=DomainError('The verification code is incorrect.',400)
   else:
    if c.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=? AND account_id!=?',(row['email'],owner)).fetchone():raise DomainError('This email is already in use.',409)
    c.execute('UPDATE cal_account_emails SET verified=1,code_salt=NULL,code_hash=NULL,expires_at=NULL WHERE id=?',(ident,));primary=bool(row['make_primary'])
  if failure:raise failure
  return primary
 def make_primary(self,owner,ident,session_token):
  with self.store.db(True) as c:
   account=self._ensure_primary(c,owner);row=c.execute('SELECT * FROM cal_account_emails WHERE id=? AND owner=?',(ident,owner)).fetchone()
   if not row:raise DomainError('Email not found.',404)
   if not row['verified']:raise DomainError('Verify this email before making it primary.',409)
   session=self.auth._session_row(c,session_token)
   if not session or session['account_id']!=owner:raise DomainError('Please sign in again.',401)
   if row['email']==account['email_normalized']:return session_token
   if c.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=? AND account_id!=?',(row['email'],owner)).fetchone():raise DomainError('This email is already in use.',409)
   c.execute('UPDATE local_auth_accounts SET email_normalized=?,email_verified=1 WHERE account_id=?',(row['email'],owner));now=self.auth._now();c.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL',(now,owner))
   c.execute("DELETE FROM local_auth_mail_outbox WHERE purpose='password-reset' AND flow_id IN (SELECT reset_id FROM local_auth_password_reset_flows WHERE account_id=?)",(owner,));c.execute('DELETE FROM local_auth_password_reset_flows WHERE account_id=?',(owner,))
   return self.auth._rotate_session_unlocked(c,session['session_digest'],owner,now)
 def delete_email(self,owner,ident):
  with self.store.db(True) as c:
   account=self._account(c,owner);row=c.execute('SELECT * FROM cal_account_emails WHERE id=? AND owner=?',(ident,owner)).fetchone()
   if not row:raise DomainError('Email not found.',404)
   if row['email']==account['email_normalized']:raise DomainError('Your primary email cannot be deleted.',409)
   c.execute('DELETE FROM cal_account_emails WHERE id=?',(ident,))
 def delete_account(self,owner,confirmation):
  with self.store.db(True) as c:
   account=self._account(c,owner)
   if confirmation!=account['email_normalized']:raise DomainError('Enter your primary email to confirm deletion.')
   c.execute('INSERT OR REPLACE INTO cal_deleted_accounts VALUES(?,?)',(account['subject_id'],self._now()))
   for table in ['cal_mail','cal_private_links','cal_event_order','cal_bookings','cal_events','cal_schedules','cal_time_off','cal_profiles','cal_account_emails','cal_email_limits']:c.execute('DELETE FROM '+table+' WHERE owner=?',(owner,))
   c.execute('DELETE FROM local_auth_mail_outbox WHERE session_digest IN (SELECT session_digest FROM local_auth_sessions WHERE account_id=?)',(owner,));c.execute('DELETE FROM local_auth_sessions WHERE account_id=?',(owner,));c.execute('DELETE FROM local_auth_accounts WHERE account_id=?',(owner,))
