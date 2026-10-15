"""Session-bound account identity changes using the local SMTP transport."""
import json
import re
import secrets
import sqlite3
from websitebench.local_clone_auth.store import (
    AuthRejected, AuthValidationError, AuthRateLimited, CHALLENGE_TTL_SECONDS,
    MAIL_COOLDOWN_SECONDS, MAIL_HOURLY_LIMIT, RATE_WINDOW_SECONDS,
    _normalize_email, _verification_code, _hash_secret, _verify_secret,
    _recipient_digest,
)
from backend.registration import CHOICES


def migrate(auth):
    with auth.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS icloud_identity_changes (
          account_id TEXT PRIMARY KEY, session_digest TEXT NOT NULL,
          flow_id TEXT NOT NULL UNIQUE, purpose TEXT NOT NULL,
          target TEXT NOT NULL, recipient TEXT NOT NULL,
          code_salt BLOB NOT NULL, code_hash BLOB NOT NULL,
          expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL,
          mail_status TEXT NOT NULL, created_at INTEGER NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS icloud_identity_mail_limits (
          scope_type TEXT NOT NULL, scope_key TEXT NOT NULL,
          window_started_at INTEGER NOT NULL, send_count INTEGER NOT NULL,
          last_sent_at INTEGER NOT NULL, PRIMARY KEY(scope_type,scope_key))''')


def rate_limit(db,owner,recipient,now):
    updates=[]
    for scope,key in [('account',owner),('recipient',_recipient_digest(recipient))]:
        row=db.execute('SELECT * FROM icloud_identity_mail_limits WHERE scope_type=? AND scope_key=?',(scope,key)).fetchone()
        if row and now-row['window_started_at']<RATE_WINDOW_SECONDS:
            if now-row['last_sent_at']<MAIL_COOLDOWN_SECONDS:
                raise AuthRateLimited(MAIL_COOLDOWN_SECONDS-(now-row['last_sent_at']))
            if row['send_count']>=MAIL_HOURLY_LIMIT:
                raise AuthRateLimited(RATE_WINDOW_SECONDS-(now-row['window_started_at']))
            updates.append((scope,key,row['window_started_at'],row['send_count']+1,now))
        else:updates.append((scope,key,now,1,now))
    db.executemany('INSERT OR REPLACE INTO icloud_identity_mail_limits VALUES (?,?,?,?,?)',updates)


def current(auth, db, token):
    session=auth._session_row(db,token)
    if session is None or not session['account_id']:
        raise AuthRejected('Sign in required.')
    account=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',
                       (session['account_id'],)).fetchone()
    return session,account


def status(auth, token):
    with auth.connect() as db:
        session,account=current(auth,db,token)
        flow=db.execute('SELECT * FROM icloud_identity_changes WHERE account_id=? AND session_digest=?',
                        (account['account_id'],session['session_digest'])).fetchone()
    if not flow:return None
    state='expired' if flow['expires_at']<=auth._now() else 'locked' if flow['attempts']>=5 else 'challenge'
    return {'purpose':flow['purpose'],'target':json.loads(flow['target']),
            'recipient':flow['recipient'],'expires_at':flow['expires_at'],
            'mail_status':flow['mail_status'],'state':state,
            'retry_after':max(0,MAIL_COOLDOWN_SECONDS-(auth._now()-flow['created_at']))}


def start(auth, token, data, deliver, *, resend=False):
    now=auth._now();code=_verification_code();identifier=secrets.token_hex(16)
    with auth.connect() as db,auth._transaction(db):
        session,account=current(auth,db,token);owner=account['account_id']
        old=db.execute('SELECT * FROM icloud_identity_changes WHERE account_id=?',(owner,)).fetchone()
        if resend:
            if not old or old['session_digest']!=session['session_digest']:
                raise AuthRejected('Start a new verification request.')
            purpose=old['purpose'];target=json.loads(old['target'])
        else:
            password=data.get('current_password')
            if not isinstance(password,str) or not _verify_secret(password,bytes(account['password_salt']),bytes(account['password_hash'])):
                raise AuthRejected('Your current password is incorrect.')
            purpose=data.get('purpose')
            if purpose=='email':target={'email':_normalize_email(data.get('email',''))}
            elif purpose=='phone':
                target={k:str(data.get(k,'')).strip() for k in ('phone','phone_code')}
                if target['phone_code'] not in {choice['value'] for choice in CHOICES['phone_codes']}:
                    raise AuthValidationError('Choose a phone country code.')
                if not re.fullmatch(r'[0-9 ()+\-]{4,25}',target['phone']) or not 4<=len(re.sub(r'\D','',target['phone']))<=18:
                    raise AuthValidationError('Enter a valid phone number.')
            else:raise AuthValidationError('Choose email or phone number.')
        recipient=target['email'] if purpose=='email' else account['email_normalized']
        if purpose=='email':
            if recipient==account['email_normalized']:
                raise AuthValidationError('Enter a different email address.')
            if db.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=?',(recipient,)).fetchone():
                raise AuthValidationError('This email address is not available.')
        rate_limit(db,owner,recipient,now)
        if old:
            while _verify_secret(code,bytes(old['code_salt']),bytes(old['code_hash'])):code=_verification_code()
        salt,digest=_hash_secret(code)
        db.execute('INSERT OR REPLACE INTO icloud_identity_changes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (owner,session['session_digest'],identifier,purpose,json.dumps(target),recipient,
             salt,digest,now+CHALLENGE_TTL_SECONDS,0,'SMTP_PENDING',now))
    try:
        deliver(recipient,code,purpose)
    except Exception:
        with auth.connect() as db:
            db.execute("UPDATE icloud_identity_changes SET mail_status='SMTP_FAILED' WHERE flow_id=?",(identifier,))
        raise
    with auth.connect() as db:
        db.execute("UPDATE icloud_identity_changes SET mail_status='SMTP_SENT' WHERE flow_id=?",(identifier,))
    return status(auth,token)


def cancel(auth,token):
    with auth.connect() as db,auth._transaction(db):
        session,account=current(auth,db,token)
        db.execute('DELETE FROM icloud_identity_changes WHERE account_id=? AND session_digest=?',
                   (account['account_id'],session['session_digest']))


def verify(auth,token,code):
    error=None;new_token=None;now=auth._now()
    with auth.connect() as db,auth._transaction(db):
        session,account=current(auth,db,token);owner=account['account_id']
        flow=db.execute('SELECT * FROM icloud_identity_changes WHERE account_id=? AND session_digest=?',
                        (owner,session['session_digest'])).fetchone()
        if not flow:error='Start a new verification request.'
        elif flow['expires_at']<=now:error='The verification code has expired. Request a new code.'
        elif flow['attempts']>=5:error='Too many incorrect codes. Request a new code.'
        elif flow['mail_status']!='SMTP_SENT':error='Email has not been sent. Please try again.'
        elif not isinstance(code,str) or not _verify_secret(code,bytes(flow['code_salt']),bytes(flow['code_hash'])):
            db.execute('UPDATE icloud_identity_changes SET attempts=attempts+1 WHERE account_id=?',(owner,))
            error='The verification code is incorrect.'
        else:
            target=json.loads(flow['target'])
            if flow['purpose']=='email':
                try:db.execute('UPDATE local_auth_accounts SET email_normalized=?,email_verified=1 WHERE account_id=?',(target['email'],owner))
                except sqlite3.IntegrityError:raise AuthValidationError('This email address is not available.')
            else:
                row=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='settings' AND id='profile'",(owner,)).fetchone()
                profile=json.loads(row[0]) if row else {'id':'profile'}
                profile.update(target)
                db.execute('INSERT OR REPLACE INTO icloud_entities VALUES (?,?,?,?,?)',
                           (owner,'settings','profile',json.dumps(profile),now))
            db.execute("DELETE FROM local_auth_mail_outbox WHERE purpose='password-reset' AND flow_id IN (SELECT reset_id FROM local_auth_password_reset_flows WHERE account_id=?)",(owner,))
            db.execute('DELETE FROM local_auth_password_reset_flows WHERE account_id=?',(owner,))
            db.execute('DELETE FROM icloud_identity_changes WHERE account_id=?',(owner,))
            db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL',(now,owner))
            new_token=auth._rotate_session_unlocked(db,session['session_digest'],owner,now,None)
    if error:raise AuthRejected(error)
    return new_token
