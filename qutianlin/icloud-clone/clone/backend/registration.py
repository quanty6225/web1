"""Local registration fields and session-bound visual/audio challenges."""
import hashlib,io,json,re,secrets,wave
from datetime import date
from pathlib import Path
from websitebench.local_clone_auth.store import AuthRejected,AuthValidationError
ROOT=Path(__file__).resolve().parents[1]
CHOICES=json.loads((ROOT/'static/auth-choices.json').read_text())

def migrate(auth):
 with auth.connect() as db:
  db.execute('CREATE TABLE IF NOT EXISTS icloud_captchas (owner TEXT PRIMARY KEY,id TEXT UNIQUE,salt TEXT,answer_hash TEXT,image TEXT,audio BLOB,expires INTEGER,attempts INTEGER)')
  db.execute('CREATE TABLE IF NOT EXISTS icloud_registration_profiles (owner TEXT PRIMARY KEY,payload TEXT)')

def issue_challenge(auth,token):
 owner=auth.session_owner_digest(token);code=''.join(secrets.choice('0123456789') for _ in range(6));identifier=secrets.token_hex(16);salt=secrets.token_hex(16)
 image='<svg xmlns="http://www.w3.org/2000/svg" width="230" height="72" viewBox="0 0 230 72"><rect width="230" height="72" fill="#f5f5f7"/>'
 for i,digit in enumerate(code):image+=f'<text x="{18+34*i}" y="48" font-family="monospace" font-size="34" fill="#333" transform="rotate({secrets.randbelow(15)-7} {18+34*i} 48)">{digit}</text>'
 image+='</svg>';pcm=[]
 for digit in code:
  with wave.open(str(ROOT/'static/auth-audio'/f'{digit}.wav'),'rb') as wav:rate=wav.getframerate();pcm.append(wav.readframes(wav.getnframes()));pcm.append(b'\0\0'*(rate//4))
 stream=io.BytesIO()
 with wave.open(stream,'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(b''.join(pcm))
 with auth.connect() as db:
  db.execute('DELETE FROM icloud_captchas WHERE expires<?',(auth._now(),))
  db.execute('INSERT OR REPLACE INTO icloud_captchas VALUES (?,?,?,?,?,?,?,0)',(owner,identifier,salt,hashlib.sha256((salt+code).encode()).hexdigest(),image,stream.getvalue(),auth._now()+600))
 return {'id':identifier,'image':'/api/auth/captcha/'+identifier+'/image','audio':'/api/auth/captcha/'+identifier+'/audio'}

def challenge_asset(auth,token,identifier,kind):
 if kind not in ('image','audio'):raise AuthRejected('Challenge not found')
 owner=auth.session_owner_digest(token)
 with auth.connect() as db:row=db.execute('SELECT image,audio FROM icloud_captchas WHERE owner=? AND id=? AND expires>? AND attempts<5',(owner,identifier,auth._now())).fetchone()
 if not row:raise AuthRejected('Challenge expired. Request a new code.')
 return row[kind]

def consume_challenge(auth,token,data):
 owner=auth.session_owner_digest(token);error=None
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT * FROM icloud_captchas WHERE owner=? AND id=?',(owner,str(data.get('captcha_id','')))).fetchone()
  if not row or row['expires']<=auth._now() or row['attempts']>=5:error='Request a new image code.'
  elif not secrets.compare_digest(row['answer_hash'],hashlib.sha256((row['salt']+str(data.get('captcha','')).strip()).encode()).hexdigest()):
   db.execute('UPDATE icloud_captchas SET attempts=attempts+1 WHERE owner=?',(owner,));error='The characters do not match. Try again.'
  else:db.execute('DELETE FROM icloud_captchas WHERE owner=?',(owner,))
 if error:raise AuthValidationError(error)

def registration_profile(data):
 profile={k:str(data.get(k,'')).strip() for k in ('first','last','country','birthday','phone_code','phone')}
 if any(not profile[k] or len(profile[k])>100 for k in ('first','last')):raise AuthValidationError('Enter your first and last name.')
 if profile['country'] not in {c['value'] for c in CHOICES['countries']}:raise AuthValidationError('Choose your country or region.')
 if profile['phone_code'] not in {c['value'] for c in CHOICES['phone_codes']}:raise AuthValidationError('Choose a phone country code.')
 try:birthday=date.fromisoformat(profile['birthday'])
 except ValueError:raise AuthValidationError('Enter a valid birthday.')
 if birthday>=date.today() or birthday.year<1876:raise AuthValidationError('Enter a valid birthday.')
 if not re.fullmatch(r'[0-9 ()+\-]{4,25}',profile['phone']) or not 4<=len(re.sub(r'\D','',profile['phone']))<=18:raise AuthValidationError('Enter a valid phone number.')
 if data.get('password')!=data.get('confirm'):raise AuthValidationError('Passwords do not match.')
 profile.update({k:data.get(k) in (True,'on','true') for k in ('announcements','media_updates')})
 return profile

def save_profile(auth,token,profile):
 with auth.connect() as db:db.execute('INSERT OR REPLACE INTO icloud_registration_profiles VALUES (?,?)',(auth.session_owner_digest(token),json.dumps(profile)))

def take_profile(auth,token):
 owner=auth.session_owner_digest(token)
 with auth.connect() as db:
  row=db.execute('SELECT payload FROM icloud_registration_profiles WHERE owner=?',(owner,)).fetchone()
 return (owner,json.loads(row[0]) if row else {})

def finish_profile(auth,old_owner,account_id,profile):
 with auth.connect() as db:
  db.execute('DELETE FROM icloud_registration_profiles WHERE owner=?',(old_owner,))
  if profile:db.execute('INSERT OR REPLACE INTO icloud_entities VALUES (?,?,?,?,?)',(account_id,'settings','profile',json.dumps({'id':'profile',**profile}),auth._now()))

def update_profile(auth,owner,data):
 first=str(data.get('first','')).strip();last=str(data.get('last','')).strip()
 if not first or len(first)>100 or len(last)>100:raise AuthValidationError('Enter your name.')
 birthday=str(data.get('birthday','')).strip();country=str(data.get('country','')).strip()
 if birthday:
  try:born=date.fromisoformat(birthday)
  except ValueError:raise AuthValidationError('Enter a valid birthday.')
  if born>=date.today() or born.year<1876:raise AuthValidationError('Enter a valid birthday.')
 if country and country not in {c['value'] for c in CHOICES['countries']}:raise AuthValidationError('Choose your country or region.')
 with auth.connect() as db:
  row=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='settings' AND id='profile'",(owner,)).fetchone()
  profile=json.loads(row[0]) if row else {'id':'profile'}
  profile.update({'first':first,'last':last,'birthday':birthday,'country':country})
  profile.update({key:data.get(key) in (True,'on','true') for key in ('announcements','media_updates')})
  db.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',((' '.join([first,last])).strip(),owner))
  db.execute('INSERT OR REPLACE INTO icloud_entities VALUES (?,?,?,?,?)',(owner,'settings','profile',json.dumps(profile),auth._now()))
 return profile
