"""Local Chat profile, stable workspace handles and source-sized profile photos."""
import hashlib, hmac, io, json, re, secrets, sqlite3, time, unicodedata, warnings
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
from status_subscriptions import send_mail
from websitebench.local_clone_auth.store import _normalize_email
from websitebench.local_clone_auth import AuthValidationError

CHARS = json.loads((Path(__file__).parent / 'static/chat-profile-validation.json').read_text())['character_class']
HANDLE = re.compile('^[0-9' + CHARS + ']+$')
NAME = re.compile('^[' + CHARS + " '-]+$")
FIELDS = ['email', 'firstName', 'lastName', 'title', 'handle', 'mobilePhoneNumber', 'website', 'twitter', 'linkedin', 'facebook']
SCHEMA = '''
CREATE TABLE IF NOT EXISTS tw_chat_profiles(owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,handle TEXT NOT NULL,handle_key TEXT NOT NULL,profile TEXT NOT NULL DEFAULT '{}',PRIMARY KEY(owner,actor),UNIQUE(owner,handle_key));
CREATE TABLE IF NOT EXISTS tw_chat_profile_photos(owner TEXT NOT NULL,actor TEXT NOT NULL,version TEXT NOT NULL,mime TEXT NOT NULL,bytes BLOB NOT NULL,PRIMARY KEY(owner,actor),FOREIGN KEY(owner,actor) REFERENCES tw_chat_profiles(owner,actor) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_chat_profile_email(actor TEXT PRIMARY KEY REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,owner TEXT NOT NULL,session TEXT NOT NULL,profile TEXT NOT NULL,salt TEXT NOT NULL,code_digest TEXT NOT NULL,sent REAL NOT NULL,expires REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tw_chat_mention_tokens(owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL,label TEXT NOT NULL,PRIMARY KEY(owner,message,actor),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
'''


def handle_key(value):
    return unicodedata.normalize('NFKC', value).casefold()


def identity_for(c, who, actor, name):
    row = c.execute('SELECT handle FROM tw_chat_profiles WHERE owner=? AND actor=?', (who, actor)).fetchone()
    if not row:
        base = ''.join(char for char in name if HANDLE.fullmatch(char))[:240] or 'user'
        handle, suffix = base, 1
        while handle_key(handle) in ['all', 'online'] or c.execute('SELECT 1 FROM tw_chat_profiles WHERE owner=? AND handle_key=?', (who, handle_key(handle))).fetchone():
            suffix += 1
            handle = base + str(suffix)
        c.execute('INSERT INTO tw_chat_profiles(owner,actor,handle,handle_key) VALUES(?,?,?,?)', (who, actor, handle, handle_key(handle)))
    else:
        handle = row['handle']
    photo = c.execute('SELECT version FROM tw_chat_profile_photos WHERE owner=? AND actor=?', (who, actor)).fetchone()
    return {'handle': handle, 'avatar_url': '/api/chat/people/' + actor + '/avatar?v=' + photo['version'] if photo else None}


def profile(c, who, actor):
    a = c.execute('SELECT display_name,email_normalized FROM local_auth_accounts WHERE account_id=?', (actor,)).fetchone()
    identity = identity_for(c, who, actor, a['display_name'])
    data = json.loads(c.execute('SELECT profile FROM tw_chat_profiles WHERE owner=? AND actor=?', (who, actor)).fetchone()['profile'])
    if ' '.join([data.get('firstName', ''), data.get('lastName', '')]).strip() != a['display_name']:
        names = a['display_name'].split(' ', 1)
        data.update(firstName=names[0], lastName=names[1] if len(names) > 1 else '')
    return {**{key: '' for key in FIELDS}, **data, **identity, 'email': a['email_normalized']}


def validate(c, who, actor, data):
    if not isinstance(data, dict) or not data or set(data) - set(FIELDS):
        raise HTTPException(422, 'Choose valid profile fields.')
    if any(not isinstance(value, str) for value in data.values()):
        raise HTTPException(422, 'Enter valid profile values.')
    value = {**{k: v for k, v in profile(c, who, actor).items() if k in FIELDS}, **{k: v.strip() for k, v in data.items()}}
    for key in ['firstName', 'lastName']:
        if not value[key] or not NAME.fullmatch(value[key]):
            raise HTTPException(422, 'Your ' + ('first name' if key == 'firstName' else 'last name') + ' must only contain letters.')
    if len(value['firstName'] + ' ' + value['lastName']) > 120:
        raise HTTPException(422, 'Enter a display name between 1 and 120 characters.')
    handle = value['handle']
    if len(handle) > 255:
        raise HTTPException(422, 'Your handle must be 255 characters or less.')
    if not HANDLE.fullmatch(handle) or handle_key(handle) in ['all', 'online']:
        raise HTTPException(422, 'Your handle may only contain letters and numbers; all and online are reserved mentions.')
    if c.execute('SELECT 1 FROM tw_chat_profiles WHERE owner=? AND handle_key=? AND actor!=?', (who, handle_key(handle), actor)).fetchone():
        raise HTTPException(409, 'That handle is already in use.')
    try:
        value['email'] = _normalize_email(value['email'])
    except AuthValidationError:
        raise HTTPException(422, 'Enter a valid email address.')
    if c.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=? AND account_id!=?', (value['email'], actor)).fetchone():
        raise HTTPException(409, 'That email address is already in use.')
    if value['mobilePhoneNumber']:
        import phonenumbers
        try:
            phone = phonenumbers.parse(value['mobilePhoneNumber'], None)
            valid = value['mobilePhoneNumber'].startswith('+') and phonenumbers.is_valid_number(phone)
        except phonenumbers.NumberParseException:
            valid = False
        if not valid:
            raise HTTPException(422, 'The mobile number should start with your country code & prefix e.g. +1 12 1234567.')
    for key in ['website', 'linkedin', 'facebook']:
        text = value[key]
        if text:
            try:
                url = urlsplit(text if '://' in text else 'https://' + text)
                valid = url.scheme in ['http', 'https'] and bool(url.hostname) and '.' in url.hostname and not url.username and not re.search(r'\s', text)
            except ValueError:
                valid = False
            if not valid:
                raise HTTPException(422, 'Enter a valid ' + key + ' URL.')
    if value['twitter'] and not re.fullmatch(r'(?:https?://twitter\.com/)?[A-Za-z0-9_]{1,15}', value['twitter']):
        raise HTTPException(422, 'Your Twitter must be a URL or handle.')
    if any(len(v) > 2048 for v in value.values()):
        raise HTTPException(422, 'A profile value is too long.')
    return value


def store(c, who, actor, value):
    import task_assignees
    old = c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?', (actor,)).fetchone()['email_normalized']
    task_assignees.migrate(c)
    c.execute('UPDATE local_auth_accounts SET display_name=?,email_normalized=? WHERE account_id=?', (value['firstName'] + ' ' + value['lastName'], value['email'], actor))
    c.execute('UPDATE tw_chat_profiles SET handle=?,handle_key=?,profile=? WHERE owner=? AND actor=?', (value['handle'], handle_key(value['handle']), json.dumps({k: v for k, v in value.items() if k not in ['email', 'handle']}), who, actor))
    for row in c.execute('SELECT id,owner,options FROM tw_tasks').fetchall():
        options = json.loads(row['options'])
        if actor in options.get('assignee_ids', []):
            task_assignees.store(c, row['owner'], row['id'], options['assignee_ids'], options.get('assignee_labels', []))
    if old != value['email']:
        c.execute('DELETE FROM local_auth_password_reset_flows WHERE account_id=?', (actor,))
    c.execute('DELETE FROM tw_chat_profile_email WHERE actor=?', (actor,))
    return profile(c, who, actor)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def resized_photo(path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in ['GIF', 'PNG', 'JPEG']:
                    raise ValueError('Unsupported photo')
                frames, durations = [], []
                for frame in ImageSequence.Iterator(image):
                    frames.append(ImageOps.fit(ImageOps.exif_transpose(frame).convert('RGBA'), (200, 200), method=Image.Resampling.LANCZOS))
                    durations.append(frame.info.get('duration', 100))
                output = io.BytesIO()
                if len(frames) > 1:
                    frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:], duration=durations, loop=image.info.get('loop', 0))
                    mime = 'image/gif'
                else:
                    frames[0].save(output, format='PNG')
                    mime = 'image/png'
                return mime, output.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Your profile picture must be a valid GIF, PNG or JPG image.')


def install(app, db, identity, uploads):
    from chat_local import people
    with db() as c:
        c.executescript(SCHEMA)

    @app.get('/api/chat/profile')
    def get(req: Request):
        with db() as c:
            who, actor = identity(req, c)
            return profile(c, who, actor)

    @app.patch('/api/chat/profile')
    async def save(req: Request):
        try:
            data = await req.json()
        except ValueError:
            raise HTTPException(422, 'Enter valid profile values.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            who, actor = identity(req, c)
            people(c, who)  # Reserve handles for all existing workspace members first.
            value = validate(c, who, actor, data)
            current = profile(c, who, actor)
            if value['email'] == current['email']:
                return {'profile': store(c, who, actor, value)}
            prior = c.execute('SELECT sent FROM tw_chat_profile_email WHERE actor=?', (actor,)).fetchone()
            now = time.time()
            if prior and now - prior['sent'] < 30:
                raise HTTPException(429, 'Please wait 30 seconds before requesting another email.')
            code, salt = f'{secrets.randbelow(1000000):06d}', secrets.token_hex(16)
            send_mail(value['email'], 'Verify your Teamwork Chat email change', f'Your verification code is {code}.\n\nThis code expires in 10 minutes. Your profile and login email will change only after you confirm this code in the same signed-in browser.')
            c.execute('INSERT INTO tw_chat_profile_email VALUES(?,?,?,?,?,?,?,?,0) ON CONFLICT(actor) DO UPDATE SET owner=excluded.owner,session=excluded.session,profile=excluded.profile,salt=excluded.salt,code_digest=excluded.code_digest,sent=excluded.sent,expires=excluded.expires,attempts=0',
                      (actor, who, digest(req.cookies.get('teamwork_session', '')), json.dumps(value), salt, digest(salt + code), now, now + 600))
            return {'pending_email': value['email']}

    @app.post('/api/chat/profile/email/verify')
    async def verify(req: Request):
        try:
            data = await req.json()
        except ValueError:
            raise HTTPException(422, 'Enter a verification code.')
        if not isinstance(data, dict) or not isinstance(data.get('code'), str):
            raise HTTPException(422, 'Enter a verification code.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            who, actor = identity(req, c)
            flow = c.execute('SELECT * FROM tw_chat_profile_email WHERE actor=?', (actor,)).fetchone()
            if not flow or flow['owner'] != who or flow['session'] != digest(req.cookies.get('teamwork_session', '')) or flow['expires'] <= time.time():
                raise HTTPException(400, 'This verification code has expired or has already been used.')
            if flow['attempts'] >= 5:
                raise HTTPException(429, 'Too many attempts. Request another verification code.')
            if not hmac.compare_digest(flow['code_digest'], digest(flow['salt'] + str(data.get('code', '')))):
                c.execute('UPDATE tw_chat_profile_email SET attempts=attempts+1 WHERE actor=?', (actor,))
                c.commit()
                raise HTTPException(400, 'The verification code is incorrect.')
            value = validate(c, who, actor, json.loads(flow['profile']))
            return {'profile': store(c, who, actor, value)}

    @app.post('/api/chat/profile/avatar')
    async def avatar(req: Request):
        from upload_stream import save
        with db() as c:
            who, actor = identity(req, c)
        form = await req.form()
        file = form.get('file')
        if not file or not hasattr(file, 'read'):
            raise HTTPException(422, 'Choose an image.')
        path = uploads / ('chat-avatar-' + secrets.token_hex(16))
        try:
            await save(file, path)
            mime, raw = resized_photo(path)
            with db() as c:
                if identity(req, c) != (who, actor):
                    raise HTTPException(403, 'The active workspace changed during upload.')
                profile(c, who, actor)
                c.execute('INSERT INTO tw_chat_profile_photos VALUES(?,?,?,?,?) ON CONFLICT(owner,actor) DO UPDATE SET version=excluded.version,mime=excluded.mime,bytes=excluded.bytes', (who, actor, secrets.token_hex(12), mime, raw))
                return profile(c, who, actor)
        finally:
            path.unlink(missing_ok=True)

    @app.get('/api/chat/people/{person}/avatar')
    def photo(person: str, req: Request):
        with db() as c:
            who, actor = identity(req, c)
            if not any(p['id'] == person for p in people(c, who)):
                raise HTTPException(404, 'Photo not found.')
            row = c.execute('SELECT mime,bytes FROM tw_chat_profile_photos WHERE owner=? AND actor=?', (who, person)).fetchone()
            if not row:
                raise HTTPException(404, 'Photo not found.')
            return Response(bytes(row['bytes']), media_type=row['mime'], headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
