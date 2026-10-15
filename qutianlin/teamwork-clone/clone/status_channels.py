"""Isolated SMS and webhook subscriptions backed by local delivery adapters."""
import hashlib,hmac,json,re,secrets,time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import HTTPException,Request
from fastapi.responses import HTMLResponse
import phonenumbers
from automation_http import validate as validate_http,local_destination
ROOT=Path(__file__).parent

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def origin(req):
 value=str(req.base_url).rstrip('/');p=urlsplit(value)
 if p.hostname not in ['127.0.0.1','localhost','::1'] or p.port not in range(18150,18160):raise HTTPException(400,'Use the local status site to subscribe.')
 return value

def install(app,db,auth,response,send_mail):
 with db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS tw_status_channels(id TEXT PRIMARY KEY,session TEXT NOT NULL,kind TEXT NOT NULL,address TEXT NOT NULL,email TEXT NOT NULL,country TEXT NOT NULL DEFAULT '',origin TEXT NOT NULL,created REAL NOT NULL,active INTEGER NOT NULL DEFAULT 0,token TEXT NOT NULL UNIQUE,confirm_digest TEXT NOT NULL,expires REAL NOT NULL,UNIQUE(session,kind,address));
 CREATE TABLE IF NOT EXISTS tw_status_sms_flows(session TEXT PRIMARY KEY,country TEXT NOT NULL,number TEXT NOT NULL,origin TEXT NOT NULL,salt TEXT NOT NULL,code_digest TEXT NOT NULL,sent REAL NOT NULL,expires REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,consumed INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS tw_status_sms_messages(id TEXT PRIMARY KEY,session TEXT NOT NULL,number TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
 ''')
 countries={r['code'] for r in json.loads((ROOT/'static/status-data/sms-countries.json').read_text())}
 def session(req):
  token,state=auth.ensure_session(req.cookies.get('teamwork_session'));return token,auth.session_owner_digest(token)
 async def data(req):
  try:d=await req.json()
  except ValueError:raise HTTPException(422,'Enter valid subscription details.')
  if not isinstance(d,dict):raise HTTPException(422,'Enter valid subscription details.')
  return d
 def send_sms(c,sid,number,body):
  # SMTP is the real local transport; this separate inbox represents the local phone.
  recipient='sms-'+sid[:16]+'-'+number.lstrip('+')+'@teamwork.sms.invalid'
  send_mail(recipient,'Teamwork.com local SMS to '+number,body)
  c.execute('INSERT INTO tw_status_sms_messages VALUES(?,?,?,?,?)',(secrets.token_hex(16),sid,number,body,time.time()))
 @app.post('/api/status/subscriptions/sms')
 async def sms_start(req:Request):
  d=await data(req);country=str(d.get('phone_country','')).lower();raw=str(d.get('phone_number','')).strip()
  try:
   if country not in countries or len(raw)>40 or not re.fullmatch(r'[+0-9(). -]+',raw):raise ValueError()
   phone=phonenumbers.parse(raw,country.upper())
   if not phonenumbers.is_valid_number_for_region(phone,country.upper()):raise ValueError()
   number=phonenumbers.format_number(phone,phonenumbers.PhoneNumberFormat.E164)
  except (ValueError,phonenumbers.NumberParseException):raise HTTPException(422,'Enter a valid phone number for the selected country.')
  token,sid=session(req);base=origin(req);now=time.time();code=f'{secrets.randbelow(1000000):06d}';salt=secrets.token_hex(16)
  with db() as c:
   c.execute('BEGIN IMMEDIATE');previous=c.execute('SELECT sent FROM tw_status_sms_flows WHERE session=?',(sid,)).fetchone()
   if previous and now-previous['sent']<30:raise HTTPException(429,'Please wait before requesting another code.')
   send_sms(c,sid,number,'Your Teamwork.com status verification code is '+code+'. It expires in 10 minutes.')
   c.execute('INSERT INTO tw_status_sms_flows VALUES(?,?,?,?,?,?,?,?,0,0) ON CONFLICT(session) DO UPDATE SET country=excluded.country,number=excluded.number,origin=excluded.origin,salt=excluded.salt,code_digest=excluded.code_digest,sent=excluded.sent,expires=excluded.expires,attempts=0,consumed=0',(sid,country,number,base,salt,digest(salt+code),now,now+600))
  return response({'state':'verification','phone_number':number,'phone_country':country,'retry_after':30},token)
 @app.get('/api/status/subscriptions/sms')
 def sms_state(req:Request):
  token,sid=session(req)
  with db() as c:r=c.execute('SELECT * FROM tw_status_sms_flows WHERE session=?',(sid,)).fetchone();active=c.execute("SELECT * FROM tw_status_channels WHERE session=? AND kind='sms' AND active=1 ORDER BY created DESC LIMIT 1",(sid,)).fetchone()
  value={'state':'idle'}
  if r and not r['consumed'] and r['expires']>time.time():value={'state':'verification','phone_number':r['number'],'phone_country':r['country'],'retry_after':max(0,int(r['sent']+30-time.time()))}
  elif active:value={'state':'subscribed','phone_number':active['address'],'phone_country':active['country']}
  return response(value,token)
 @app.post('/api/status/subscriptions/sms/change-number')
 def change_number(req:Request):
  token,sid=session(req)
  with db() as c:c.execute('DELETE FROM tw_status_sms_flows WHERE session=?',(sid,))
  return response({'state':'idle'},token)
 @app.post('/api/status/subscriptions/sms/verify')
 async def sms_verify(req:Request):
  d=await data(req);token,sid=session(req);now=time.time()
  with db() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM tw_status_sms_flows WHERE session=?',(sid,)).fetchone()
   if not r or r['consumed'] or r['expires']<=now:raise HTTPException(400,'This verification code has expired or has already been used.')
   if r['attempts']>=5:raise HTTPException(429,'Too many attempts. Request another verification code.')
   if not hmac.compare_digest(digest(r['salt']+str(d.get('code',''))),r['code_digest']):
    c.execute('UPDATE tw_status_sms_flows SET attempts=attempts+1 WHERE session=?',(sid,));c.commit();raise HTTPException(400,'The verification code is incorrect.')
   cancel=secrets.token_urlsafe(32);send_sms(c,sid,r['number'],'You are subscribed to Teamwork.com status updates.\nTo unsubscribe: '+r['origin']+'/status/unsubscribe?token='+cancel)
   c.execute("INSERT INTO tw_status_channels(id,session,kind,address,email,country,origin,created,active,token,confirm_digest,expires) VALUES(?,?,'sms',?,'',?,?,?,1,?,'',0) ON CONFLICT(session,kind,address) DO UPDATE SET active=1,created=excluded.created,token=excluded.token,origin=excluded.origin",(secrets.token_hex(16),sid,r['number'],r['country'],r['origin'],now,cancel));c.execute('UPDATE tw_status_sms_flows SET consumed=1 WHERE session=?',(sid,))
  return response({'state':'subscribed'},token)
 @app.get('/api/status/sms-inbox')
 def inbox(req:Request):
  token,sid=session(req)
  with db() as c:messages=[dict(r) for r in c.execute('SELECT id,number,body,created FROM tw_status_sms_messages WHERE session=? ORDER BY created DESC LIMIT 100',(sid,))]
  return response({'messages':messages,'adapter':'local-smtp-sms-capture'},token)
 @app.post('/api/status/subscriptions/webhook')
 async def hook_start(req:Request):
  d=await data(req);endpoint=str(d.get('endpoint','')).strip();email=str(d.get('email','')).strip().lower();action={'effect':'Send HTTP request','url':endpoint};validate_http(action)
  if local_destination(endpoint) is None:raise HTTPException(422,'Use a local webhook endpoint on ports 18150–18159.')
  if len(email)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):raise HTTPException(422,'Enter a valid email address.')
  token,sid=session(req);base=origin(req);now=time.time();confirm=secrets.token_urlsafe(32);cancel=secrets.token_urlsafe(32)
  with db() as c:
   c.execute('BEGIN IMMEDIATE');previous=c.execute("SELECT created FROM tw_status_channels WHERE session=? AND kind='webhook' ORDER BY created DESC LIMIT 1",(sid,)).fetchone()
   if previous and now-previous['created']<30:raise HTTPException(429,'Please wait before subscribing again.')
   send_mail(email,'Confirm your Teamwork.com status webhook',f'Confirm status notifications for {endpoint}\n\nOpen {base}/status/confirm?token={confirm}\n\nThis link expires in 24 hours.\n')
   c.execute("INSERT INTO tw_status_channels(id,session,kind,address,email,origin,created,active,token,confirm_digest,expires) VALUES(?,?,'webhook',?,?,?,?,0,?,?,?) ON CONFLICT(session,kind,address) DO UPDATE SET email=excluded.email,origin=excluded.origin,created=excluded.created,active=0,token=excluded.token,confirm_digest=excluded.confirm_digest,expires=excluded.expires",(secrets.token_hex(16),sid,endpoint,email,base,now,cancel,digest(confirm),now+86400))
  return response({'state':'confirmation'},token)
 @app.get('/api/status/subscriptions/webhook')
 def hook_state(req:Request):
  token,sid=session(req)
  with db() as c:r=c.execute("SELECT active,address,email,expires,confirm_digest FROM tw_status_channels WHERE session=? AND kind='webhook' ORDER BY created DESC LIMIT 1",(sid,)).fetchone()
  return response({'state':'subscribed' if r['active'] else 'confirmation','endpoint':r['address'],'email':r['email']} if r and (r['active'] or r['confirm_digest'] and r['expires']>time.time()) else {'state':'idle'},token)
 @app.post('/api/status/subscriptions/confirm')
 async def confirm(req:Request):
  d=await data(req);value=str(d.get('token',''))
  with db() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute("SELECT * FROM tw_status_channels WHERE confirm_digest=? AND kind='webhook'",(digest(value),)).fetchone()
   if not r or r['active'] or r['expires']<=time.time():raise HTTPException(400,'This confirmation link has expired or has already been used.')
   send_mail(r['email'],'Teamwork.com status webhook confirmed','Your webhook subscription is active.\n\nTo unsubscribe, open '+r['origin']+'/status/unsubscribe?token='+r['token']+'\n')
   c.execute("UPDATE tw_status_channels SET active=1,created=?,confirm_digest='' WHERE id=?",(time.time(),r['id']))
  return {'state':'subscribed'}
 @app.get('/status/sms-inbox')
 def inbox_page():return HTMLResponse(page('Local SMS inbox','<p>Messages delivered to this browser’s local phone adapter. No mobile network is contacted.</p><section id="local-sms-inbox" aria-live="polite"></section><button data-refresh-sms>Refresh</button>'))
 @app.get('/status/confirm')
 def confirm_page():return HTMLResponse(page('Confirm status subscription','<form id="status-confirm"><p>Confirm to start receiving status notifications.</p><button type="submit">Confirm subscription</button><p role="status"></p></form>'))
 def page(title,body):return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><link rel="stylesheet" href="/static/clone.css"><script defer src="/static/status-channels.js"></script></head><body><header><a href="/status">Teamwork.com Status</a></header><main><h1>'+title+'</h1>'+body+'</main><footer><a href="/status">Back to status</a></footer></body></html>'
 import status_channel_delivery
 return status_channel_delivery.install(db,send_mail,send_sms)
