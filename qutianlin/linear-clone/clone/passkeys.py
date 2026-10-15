"""WebAuthn ceremonies backed by the clone's own account/session database."""
import json
import time
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from webauthn import (
    generate_authentication_options, generate_registration_options,
    verify_authentication_response, verify_registration_response,
    options_to_json, base64url_to_bytes,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, ResidentKeyRequirement,
    UserVerificationRequirement, PublicKeyCredentialDescriptor,
)


def install(app, auth, actor, session, set_cookie):
    with auth.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS linear_passkeys(
          id TEXT PRIMARY KEY, account_id TEXT NOT NULL, public_key BLOB NOT NULL,
          sign_count INTEGER NOT NULL, name TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS linear_passkey_challenges(
          session_digest TEXT NOT NULL, purpose TEXT NOT NULL, challenge BLOB NOT NULL,
          rp_id TEXT NOT NULL, origin TEXT NOT NULL, expires_at INTEGER NOT NULL,
          PRIMARY KEY(session_digest,purpose));
        ''')

    def save_challenge(request, purpose, options):
        token, _ = session(request)
        owner = auth.session_owner_digest(token)
        with auth.connect() as c:
            c.execute('INSERT OR REPLACE INTO linear_passkey_challenges VALUES(?,?,?,?,?,?)',
                      (owner, purpose, options.challenge, request.url.hostname,
                       str(request.base_url).rstrip('/'), int(time.time()) + 300))
            c.commit()
        return json.loads(options_to_json(options))

    def take_challenge(request, purpose, c):
        token, _ = session(request)
        owner = auth.session_owner_digest(token)
        row = c.execute('SELECT * FROM linear_passkey_challenges WHERE session_digest=? AND purpose=?',
                        (owner, purpose)).fetchone()
        c.execute('DELETE FROM linear_passkey_challenges WHERE session_digest=? AND purpose=?', (owner, purpose))
        if not row or row['expires_at'] <= int(time.time()):
            raise HTTPException(400, 'Passkey request expired. Please try again.')
        return row

    @app.get('/api/passkeys')
    def list_passkeys(request: Request):
        account, _ = actor(request)
        with auth.connect() as c:
            return [dict(r) for r in c.execute('SELECT id,name,created_at FROM linear_passkeys WHERE account_id=?', (account['account_id'],))]

    @app.post('/api/passkeys/register/options')
    def register_options(request: Request):
        account, _ = actor(request)
        with auth.connect() as c:
            ids = [r['id'] for r in c.execute('SELECT id FROM linear_passkeys WHERE account_id=?', (account['account_id'],))]
        options = generate_registration_options(
            rp_id=request.url.hostname, rp_name='Linear local workspace',
            user_id=account['account_id'].encode(), user_name=account['email_normalized'],
            user_display_name=account['display_name'],
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(i)) for i in ids],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED),
        )
        return save_challenge(request, 'register', options)

    @app.post('/api/passkeys/register/verify')
    async def register_verify(request: Request):
        account, _ = actor(request)
        data = await request.json()
        with auth.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            challenge = take_challenge(request, 'register', c)
            try:
                verification = verify_registration_response(
                    credential=data, expected_challenge=challenge['challenge'],
                    expected_rp_id=challenge['rp_id'], expected_origin=challenge['origin'],
                    require_user_verification=True,
                )
            except Exception:
                c.commit()
                raise HTTPException(400, 'Unable to register passkey. Please try again.')
            if c.execute('SELECT 1 FROM linear_passkeys WHERE id=?', (data['id'],)).fetchone():
                raise HTTPException(409, 'This passkey is already registered.')
            c.execute('INSERT INTO linear_passkeys VALUES(?,?,?,?,?,?)',
                      (data['id'], account['account_id'], verification.credential_public_key,
                       verification.sign_count, 'Passkey', int(time.time())))
            c.commit()
        return {'registered': True}

    @app.delete('/api/passkeys/{id}')
    def delete_passkey(id: str, request: Request):
        account, _ = actor(request)
        with auth.connect() as c:
            changed = c.execute('DELETE FROM linear_passkeys WHERE id=? AND account_id=?', (id, account['account_id'])).rowcount
            c.commit()
        if not changed:
            raise HTTPException(404, 'Passkey not found.')
        return {'deleted': True}

    @app.post('/api/passkeys/login/options')
    def login_options(request: Request):
        _, current = session(request)
        if not current:
            raise HTTPException(401, 'Refresh the login page.')
        options = generate_authentication_options(
            rp_id=request.url.hostname, user_verification=UserVerificationRequirement.REQUIRED)
        return save_challenge(request, 'login', options)

    @app.post('/api/passkeys/login/verify')
    async def login_verify(request: Request):
        token, _ = session(request)
        data = await request.json()
        with auth.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            challenge = take_challenge(request, 'login', c)
            credential = c.execute('SELECT * FROM linear_passkeys WHERE id=?', (data.get('id', ''),)).fetchone()
            if not credential:
                c.commit()
                raise HTTPException(400, 'This passkey is not registered with this local workspace.')
            try:
                verified = verify_authentication_response(
                    credential=data, expected_challenge=challenge['challenge'],
                    expected_rp_id=challenge['rp_id'], expected_origin=challenge['origin'],
                    credential_public_key=credential['public_key'],
                    credential_current_sign_count=credential['sign_count'],
                    require_user_verification=True,
                )
                user_handle = data.get('response', {}).get('userHandle')
                if user_handle and base64url_to_bytes(user_handle) != credential['account_id'].encode():
                    raise ValueError('wrong account')
            except Exception:
                c.commit()
                raise HTTPException(400, 'Unable to verify passkey. Please try again.')
            c.execute('UPDATE linear_passkeys SET sign_count=? WHERE id=?', (verified.new_sign_count, credential['id']))
            new_token = auth._rotate_session_unlocked(c, auth.session_owner_digest(token), credential['account_id'], int(time.time()))
            c.commit()
        response = JSONResponse({'authenticated': True, 'redirect': '/qqq153/team/QQQ/active'})
        set_cookie(response, new_token)
        return response
