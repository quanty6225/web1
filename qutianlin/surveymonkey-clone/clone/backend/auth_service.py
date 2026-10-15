"""Site-owned challenge resend adapter; shared authentication stays unchanged."""
from websitebench.local_clone_auth.store import (
    LocalAuthStore, AuthRejected, AuthConflict, CHALLENGE_TTL_SECONDS,
    _hash_secret, _verification_code, _recipient_digest, _token,
)


class SurveyAuthStore(LocalAuthStore):
    def resend_challenge(self, session_token, *, purpose):
        tables = {
            'registration': ('local_auth_registration_flows', 'pending_id'),
            'password-reset': ('local_auth_password_reset_flows', 'reset_id'),
        }
        if purpose not in tables:
            raise AuthRejected('Invalid email purpose.')
        table, id_column = tables[purpose]
        now = self._now()
        code = _verification_code()
        salt, digest = _hash_secret(code)
        new_id = _token('challenge')
        with self.connect() as connection, self._transaction(connection):
            session = self._session_row(connection, session_token)
            if session is None:
                raise AuthRejected('This session has expired. Start again.')
            flow = connection.execute(
                f'SELECT * FROM {table} WHERE session_digest=?',
                (session['session_digest'],),
            ).fetchone()
            if flow is None:
                raise AuthRejected('No verification is pending. Start again.')
            if flow['verified_at'] is not None:
                raise AuthConflict('This code has already been verified.')
            recipient = None
            if purpose == 'registration':
                recipient = flow['email_normalized']
            elif flow['account_id']:
                row = connection.execute(
                    'SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',
                    (flow['account_id'],),
                ).fetchone()
                recipient = row['email_normalized'] if row else None
            scopes = [('session', session['session_digest'])]
            if recipient:
                scopes.append(('recipient', _recipient_digest(recipient)))
            if purpose == 'password-reset' and flow['account_id']:
                scopes.append(('account', flow['account_id']))
            self._rate_limit_unlocked(connection, purpose=purpose, scopes=scopes, now=now)
            old_id = str(flow[id_column])
            in_flight = connection.execute(
                'SELECT 1 FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=? AND claim_token IS NOT NULL',
                (purpose, old_id),
            ).fetchone()
            if in_flight:
                raise AuthConflict('Email delivery is still in progress. Try again shortly.')
            connection.execute('DELETE FROM local_auth_mail_outbox WHERE purpose=? AND flow_id=?', (purpose, old_id))
            connection.execute(
                f'UPDATE {table} SET {id_column}=?,code_salt=?,code_hash=?,expires_at=?,attempts=0,verified_at=NULL,updated_at=? WHERE session_digest=?',
                (new_id, salt, digest, now + CHALLENGE_TTL_SECONDS, now, session['session_digest']),
            )
            if recipient:
                self._insert_mail_unlocked(connection, purpose=purpose, flow_id=new_id,
                    session_digest=session['session_digest'], recipient=recipient, now=now)
        with self._mail_secrets_lock:
            self._mail_secrets.pop((purpose, old_id), None)
        if recipient:
            self._remember_mail_code(purpose, new_id, code)

