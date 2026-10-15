"""IFTTT account preferences and credential updates on the shared auth store."""
import json
import time
import base64
import hashlib
import hmac
import secrets
import struct
import re
from websitebench.local_clone_auth.store import _verify_secret, _hash_secret, _validate_password, _normalize_email, _verification_code, _recipient_digest


class Accounts:
    def __init__(self, backend, auth, automation):
        self.backend, self.auth, self.automation = backend, auth, automation

    def check_password(self, conn, owner, password):
        row = conn.execute('SELECT * FROM local_auth_accounts WHERE account_id=?', (owner,)).fetchone()
        if not row or not isinstance(password, str) or not _verify_secret(password, bytes(row['password_salt']), bytes(row['password_hash'])):
            raise ValueError('Current password is incorrect')
        return row

    def contact_sales(self, owner, body, options):
        fields = {}
        for key in ('name','title','email','phone','company_name','company_size','country'):
            value = body.get(key, '')
            if not isinstance(value, str) or not value.strip() or len(value) > 300: raise ValueError('Complete the '+key.replace('_',' ')+' field')
            fields[key] = value.strip()
        fields['email'] = _normalize_email(fields['email'])
        if not re.fullmatch(r'[\d ()+\-]+', fields['phone']): raise ValueError('Enter a valid phone number')
        if any(fields[key] not in choices for key, choices in options.items()): raise ValueError('Choose a valid company size and country')
        operation = body.get('operation_key','')
        if not isinstance(operation,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',operation): raise ValueError('Reload the form before submitting')
        key = 'contact-request:'+operation
        with self.backend.lifecycle.connection(transaction=True) as conn:
            previous = conn.execute('SELECT value FROM ifttt_preferences WHERE owner=? AND key=?',(owner,key)).fetchone()
            if previous:
                record=json.loads(previous['value'])
                if record['fields']!=fields: raise ValueError('This submission already contains different details')
            else:
                record={'reference':'IFTTT-'+secrets.token_hex(5).upper(),'fields':fields,'created_at':int(time.time()),'adapter':'local contact request'}
                conn.execute('INSERT INTO ifttt_preferences VALUES (?,?,?)',(owner,key,json.dumps(record)))
        return {'reference':record['reference'],'message':'Your request was saved locally. No message was sent to IFTTT or an external sales team.'}

    def settings(self, owner, body):
        username = body.get('username', '')
        if not isinstance(username, str) or not 1 <= len(username.strip()) <= 80:
            raise ValueError('Enter a username of 1–80 characters')
        timezone = body.get('timezone', 'UTC')
        if not isinstance(timezone, str) or len(timezone) > 80: raise ValueError('Choose a time zone')
        if self.automation.timezones and timezone not in self.automation.timezones: raise ValueError('Choose a valid time zone')
        # Source select uses Rails display aliases; retain its exact selected
        # value, while scheduler zones are supplied separately as IANA names.
        allowed = {'auto_shorten_urls','send_alerts','is_newsletter_subscriber','is_promotions_subscriber','is_beta_subscriber'}
        settings = {'timezone': timezone}
        for key in allowed:
            value = body.get(key, False)
            if type(value) is not bool: raise ValueError('Invalid preference')
            settings[key] = value
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.automation.ensure_owner(conn, owner)
            other = conn.execute('SELECT 1 FROM local_auth_accounts WHERE lower(display_name)=lower(?) AND account_id<>?', (username.strip(), owner)).fetchone()
            if other: raise ValueError('Username is already in use')
            conn.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?', (username.strip(), owner))
            conn.execute('UPDATE ifttt_profiles SET settings=? WHERE owner=?', (json.dumps(settings), owner))
        return {'message': 'Account settings saved'}

    def password(self, owner, body):
        password = body.get('password')
        _validate_password(password)
        if password != body.get('confirmation'): raise ValueError('New passwords do not match')
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.check_password(conn, owner, body.get('current_password'))
            salt, digest = _hash_secret(password)
            conn.execute('UPDATE local_auth_accounts SET password_salt=?,password_hash=? WHERE account_id=?', (salt, digest, owner))
            conn.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL', (int(time.time()), owner))
        return {'redirect': '/login?password_changed=1'}

    def profile(self, owner, body):
        value = body.get('provider')
        if value not in {'None', 'Facebook', 'Foursquare', 'SoundCloud', 'X (Twitter)', 'Vimeo'}:
            raise ValueError('Choose a profile service')
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.automation.ensure_owner(conn, owner)
            conn.execute("INSERT INTO ifttt_preferences VALUES (?,'profile',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value", (owner, json.dumps({'provider': value, 'adapter': 'local profile'})))
        return {'redirect': '/settings'}

    def public(self, owner):
        with self.backend.lifecycle.connection(transaction=True) as conn:
            profile = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='profile'", (owner,)).fetchone()
            sessions = [dict(row) for row in conn.execute('SELECT created_at,expires_at FROM local_auth_sessions WHERE account_id=? AND revoked_at IS NULL AND expires_at>? ORDER BY created_at DESC', (owner, int(time.time())))]
            mfa = conn.execute("SELECT 1 FROM ifttt_preferences WHERE owner=? AND key='totp'", (owner,)).fetchone()
            preferences = {row['key']: json.loads(row['value']) for row in conn.execute("SELECT key,value FROM ifttt_preferences WHERE owner=? AND key IN ('linked-accounts','discovery','developer')", (owner,))}
            referral = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='referral'", (owner,)).fetchone()
            if referral: referral_code = json.loads(referral['value'])
            else:
                referral_code = secrets.token_urlsafe(18)
                conn.execute("INSERT INTO ifttt_preferences VALUES (?,'referral',?)", (owner, json.dumps(referral_code)))
        return {'profile': json.loads(profile['value']) if profile else {'provider': 'None'}, 'sessions': sessions, 'two_step_enabled': bool(mfa), 'referral_code': referral_code, **preferences}

    def preference(self, owner, body):
        kind = body.get('kind')
        if kind == 'discovery':
            value = body.get('goal')
            if value not in {'home','business','other'}: raise ValueError('Choose an automation goal')
            value = {'goal': value}
        elif kind == 'developer':
            name = body.get('name', '')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100: raise ValueError('Enter an integration name of 1–100 characters')
            value = {'name': name.strip(), 'adapter': 'local developer workspace'}
        elif kind == 'linked-accounts':
            provider = body.get('provider')
            if provider not in {'Google','Apple','Facebook','Bitly'}: raise ValueError('Choose a supported provider')
            value = None
        else: raise ValueError('Unknown account preference')
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.automation.ensure_owner(conn, owner)
            if kind == 'linked-accounts':
                self.check_password(conn, owner, body.get('password'))
                row = conn.execute('SELECT value FROM ifttt_preferences WHERE owner=? AND key=?', (owner, kind)).fetchone()
                value = json.loads(row['value']) if row else {}
                value[provider] = {'adapter': 'local identity', 'connected': True}
            conn.execute('INSERT INTO ifttt_preferences VALUES (?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value', (owner, kind, json.dumps(value)))
        return {'message': 'Local preference saved', 'value': value}

    @staticmethod
    def totp(secret, counter):
        key = base64.b32decode(secret)
        digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
        offset = digest[-1] & 15
        return str((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)

    def two_step_start(self, owner, body):
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.check_password(conn, owner, body.get('password'))
            if conn.execute("SELECT 1 FROM ifttt_preferences WHERE owner=? AND key='totp'", (owner,)).fetchone():
                raise ValueError('Two-step verification is already enabled')
            secret = base64.b32encode(secrets.token_bytes(20)).decode()
            conn.execute("INSERT INTO ifttt_preferences VALUES (?,'totp-pending',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value", (owner, json.dumps({'secret': secret, 'expires_at': int(time.time()) + 600})))
        return {'secret': secret, 'message': 'Enter this setup key in your authenticator, then enter its six-digit code.'}

    def two_step_enable(self, owner, body):
        with self.backend.lifecycle.connection(transaction=True) as conn:
            row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='totp-pending'", (owner,)).fetchone()
            if not row: raise ValueError('Confirm your password to start setup')
            pending = json.loads(row['value'])
            if pending['expires_at'] <= time.time(): raise ValueError('Setup expired. Confirm your password again.')
            counter = int(time.time()) // 30
            if not secrets.compare_digest(str(body.get('code', '')), self.totp(pending['secret'], counter)):
                raise ValueError('Authenticator code is incorrect')
            backup = [secrets.token_hex(10) for _ in range(10)]
            value = {'secret': pending['secret'], 'last_counter': counter,
                     'backup': [hashlib.sha256(code.encode()).hexdigest() for code in backup]}
            conn.execute("INSERT INTO ifttt_preferences VALUES (?,'totp',?)", (owner, json.dumps(value)))
            conn.execute("DELETE FROM ifttt_preferences WHERE owner=? AND key='totp-pending'", (owner,))
        return {'backup_codes': backup, 'message': 'Two-step verification enabled. Save these single-use backup codes.'}

    def _factor(self, conn, owner, code):
        row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='totp'", (owner,)).fetchone()
        if not row or not isinstance(code, str): return False
        value = json.loads(row['value'])
        digest = hashlib.sha256(code.encode()).hexdigest()
        valid = False
        for saved in list(value['backup']):
            if secrets.compare_digest(saved, digest):
                value['backup'].remove(saved)
                valid = True
                break
        if not valid:
            counter = int(time.time()) // 30
            for attempt in (counter - 1, counter, counter + 1):
                if attempt > value['last_counter'] and secrets.compare_digest(code, self.totp(value['secret'], attempt)):
                    value['last_counter'] = attempt
                    valid = True
                    break
        if valid: conn.execute("UPDATE ifttt_preferences SET value=? WHERE owner=? AND key='totp'", (json.dumps(value), owner))
        return valid

    def two_step_disable(self, owner, body):
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.check_password(conn, owner, body.get('password'))
            if not self._factor(conn, owner, body.get('code')): raise ValueError('Verification code is incorrect or has already been used')
            conn.execute("DELETE FROM ifttt_preferences WHERE owner=? AND key='totp'", (owner,))
        return {'redirect': '/settings'}

    def require_factor(self, login_result, return_to):
        """Never expose a fully authenticated cookie before factor verification."""
        owner = login_result['account']['account_id']
        if not self.public(owner)['two_step_enabled']: return None
        self.auth.sign_out(login_result['session_token'])
        token = self.auth.create_anonymous_session()
        key = 'mfa-login:' + self.auth.session_owner_digest(token)
        with self.backend.lifecycle.connection(transaction=True) as conn:
            conn.execute('INSERT INTO ifttt_preferences VALUES (?,?,?)', (owner, key, json.dumps({'expires_at': int(time.time()) + 300, 'attempts': 0, 'return_to': return_to})))
        return token

    def verify_login(self, token, code):
        key = 'mfa-login:' + self.auth.session_owner_digest(token)
        failure = None
        with self.backend.lifecycle.connection(transaction=True) as conn:
            row = conn.execute('SELECT owner,value FROM ifttt_preferences WHERE key=?', (key,)).fetchone()
            if not row: raise ValueError('Sign in with your password first')
            value = json.loads(row['value'])
            if value['expires_at'] <= time.time() or value['attempts'] >= 5:
                failure = 'Verification expired. Sign in again.'
            elif not self._factor(conn, row['owner'], code):
                value['attempts'] += 1
                conn.execute('UPDATE ifttt_preferences SET value=? WHERE owner=? AND key=?', (json.dumps(value), row['owner'], key))
                failure = 'Verification code is incorrect or has already been used'
            else:
                session = self.auth._session_row(conn, token)
                if not session: raise ValueError('Session expired')
                rotated = self.auth._rotate_session_unlocked(conn, session['session_digest'], row['owner'], int(time.time()), None)
                conn.execute('DELETE FROM ifttt_preferences WHERE owner=? AND key=?', (row['owner'], key))
        if failure: raise ValueError(failure)
        return {'session_token': rotated, 'redirect': value['return_to']}

    def delete(self, owner, body):
        if body.get('confirmation') != 'DELETE': raise ValueError('Type DELETE to confirm')
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.check_password(conn, owner, body.get('password'))
            if conn.execute("SELECT 1 FROM ifttt_preferences WHERE owner=? AND key='totp'", (owner,)).fetchone() and not self._factor(conn, owner, body.get('code')):
                raise ValueError('Enter an authenticator or backup code to delete this account')
            self._delete_account(conn, owner)
        return {'redirect': '/join?deleted=1'}

    def _delete_account(self, conn, owner):
        conn.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=?', (int(time.time()), owner))
        for table in ('effects','runs','events','applets','connections','operations','preferences','profiles'):
            conn.execute(f'DELETE FROM ifttt_{table} WHERE owner=?', (owner,))
        conn.execute('DELETE FROM local_auth_accounts WHERE account_id=?', (owner,))

    def delete_start(self, owner, body):
        code = _verification_code()
        salt, digest = _hash_secret(code)
        now = int(time.time())
        with self.backend.lifecycle.connection(transaction=True) as conn:
            row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='account-deletion'", (owner,)).fetchone()
            if row and json.loads(row['value'])['created_at'] > now-60: raise ValueError('Wait 60 seconds before requesting another email')
            account = conn.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?', (owner,)).fetchone()
            if not account: raise ValueError('Account no longer exists')
            value = {'salt':salt.hex(),'digest':digest.hex(),'created_at':now,'expires_at':now+600,'attempts':0}
            conn.execute("INSERT INTO ifttt_preferences VALUES (?,'account-deletion',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value", (owner,json.dumps(value)))
        return account['email_normalized'], code

    def delete_verify(self, owner, body):
        if body.get('confirmation') != 'DELETE': raise ValueError('Type DELETE to confirm')
        failure = None
        with self.backend.lifecycle.connection(transaction=True) as conn:
            row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='account-deletion'", (owner,)).fetchone()
            if not row: raise ValueError('Request a deletion email first')
            value = json.loads(row['value'])
            if value['expires_at'] <= time.time() or value['attempts'] >= 5: raise ValueError('Verification expired. Request another email.')
            code = body.get('code','')
            if not isinstance(code,str) or not _verify_secret(code,bytes.fromhex(value['salt']),bytes.fromhex(value['digest'])):
                value['attempts']+=1
                conn.execute("UPDATE ifttt_preferences SET value=? WHERE owner=? AND key='account-deletion'",(json.dumps(value),owner))
                failure='Verification code is incorrect'
            elif conn.execute("SELECT 1 FROM ifttt_preferences WHERE owner=? AND key='totp'",(owner,)).fetchone() and not self._factor(conn,owner,body.get('factor')):
                value['attempts']+=1
                conn.execute("UPDATE ifttt_preferences SET value=? WHERE owner=? AND key='account-deletion'",(json.dumps(value),owner))
                failure='Enter an authenticator or backup code to delete this account'
            else:self._delete_account(conn,owner)
        if failure:raise ValueError(failure)
        return {'redirect':'/join?deleted=1'}

    def email_start(self, owner, body):
        address = _normalize_email(body.get('email'))
        code = _verification_code()
        salt, digest = _hash_secret(code)
        now = int(time.time())
        with self.backend.lifecycle.connection(transaction=True) as conn:
            self.check_password(conn, owner, body.get('password'))
            if conn.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=?', (address,)).fetchone():
                raise ValueError('This email already belongs to a local account')
            row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='email-change'", (owner,)).fetchone()
            if row and json.loads(row['value'])['created_at'] > now - 60: raise ValueError('Wait 60 seconds before requesting another email')
            challenge = {'address': address, 'salt': salt.hex(), 'digest': digest.hex(), 'expires_at': now + 600,
                         'created_at': now, 'attempts': 0}
            conn.execute("INSERT INTO ifttt_preferences VALUES (?,'email-change',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value", (owner, json.dumps(challenge)))
        return address, code

    def email_verify(self, owner, body):
        failure = None
        with self.backend.lifecycle.connection(transaction=True) as conn:
            row = conn.execute("SELECT value FROM ifttt_preferences WHERE owner=? AND key='email-change'", (owner,)).fetchone()
            if not row: raise ValueError('Request a verification email first')
            value = json.loads(row['value'])
            if value['expires_at'] <= time.time() or value['attempts'] >= 5: raise ValueError('Verification expired. Request another email.')
            code = body.get('code', '')
            if not isinstance(code, str) or not _verify_secret(code, bytes.fromhex(value['salt']), bytes.fromhex(value['digest'])):
                value['attempts'] += 1
                conn.execute("UPDATE ifttt_preferences SET value=? WHERE owner=? AND key='email-change'", (json.dumps(value), owner))
                failure = 'Verification code is incorrect'
            else:
                if conn.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=? AND account_id<>?', (value['address'], owner)).fetchone():
                    raise ValueError('This email already belongs to another account')
                conn.execute('UPDATE local_auth_accounts SET email_normalized=?,email_verified=1 WHERE account_id=?', (value['address'], owner))
                conn.execute("DELETE FROM ifttt_preferences WHERE owner=? AND key='email-change'", (owner,))
                conn.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL', (int(time.time()), owner))
        if failure: raise ValueError(failure)
        return {'redirect': '/login?email_changed=1'}

    def resend(self, token, purpose, *, retry=False):
        config = {'registration': ('local_auth_registration_flows', 'pending_id'),
                  'password-reset': ('local_auth_password_reset_flows', 'reset_id'),
                  'passwordless-signin': ('local_auth_passwordless_flows', 'signin_id')}
        if purpose not in config: raise ValueError('Invalid email purpose')
        table, id_column = config[purpose]
        code = _verification_code()
        salt, digest = _hash_secret(code)
        now = self.auth._now()
        with self.auth.connect() as conn, self.auth._transaction(conn):
            session = self.auth._session_row(conn, token)
            if not session: raise ValueError('Session expired')
            flow = conn.execute(f'SELECT * FROM {table} WHERE session_digest=?', (session['session_digest'],)).fetchone()
            if not flow or flow['verified_at']: raise ValueError('Start verification again')
            if retry:
                mail = conn.execute('SELECT status,claim_token FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=? ORDER BY mail_id DESC LIMIT 1', (purpose, flow[id_column])).fetchone()
                # LocalAuthStore removes outbox rows at startup; hash-only
                # unfinished flows persist. A retry must reissue their OTP.
                if mail and (mail['status'] not in {'SMTP_FAILED', 'SMTP_PENDING'} or (mail['status'] == 'SMTP_PENDING' and mail['claim_token'])):
                    raise ValueError('No failed delivery is available to retry')
            if purpose == 'password-reset':
                account = conn.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?', (flow['account_id'],)).fetchone()
                if not account: return
                address = account['email_normalized']
            else: address = flow['email_normalized']
            self.auth._rate_limit_unlocked(conn, purpose=purpose, scopes=[('session', session['session_digest']), ('recipient', _recipient_digest(address))], now=now, ignore_cooldown=retry)
            conn.execute(f'UPDATE {table} SET code_salt=?,code_hash=?,expires_at=?,attempts=0,verified_at=NULL,updated_at=? WHERE {id_column}=?', (salt, digest, now + 600, now, flow[id_column]))
            conn.execute('DELETE FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?', (purpose, flow[id_column]))
            self.auth._insert_mail_unlocked(conn, purpose=purpose, flow_id=flow[id_column], session_digest=session['session_digest'], recipient=address, now=now)
        self.auth._remember_mail_code(purpose, flow[id_column], code)
