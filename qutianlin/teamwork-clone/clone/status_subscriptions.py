"""Local email verification for source status subscriptions; SMTP stays on this host."""
import hashlib,hmac,os,re,secrets,smtplib,time
from email.message import EmailMessage
from fastapi import HTTPException,Request
from fastapi.responses import HTMLResponse
from urllib.parse import urlsplit

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def send_mail(email,subject,body,reply_to=None):
 host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1');port=int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025'))
 if host not in ['127.0.0.1','localhost','::1'] or port!=1025:raise HTTPException(503,'The local email service is unavailable.')
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@teamwork.clone.test');msg['To']=email;msg['Subject']=subject;msg.set_content(body)
 if reply_to:msg['Reply-To']=reply_to
 try:
  with smtplib.SMTP(host,port,timeout=5) as smtp:smtp.send_message(msg)
 except (OSError,smtplib.SMTPException):raise HTTPException(503,'Email could not be sent. Please retry.')

def install(app,db,auth,response):
 with db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS tw_status_email_flows(session TEXT PRIMARY KEY,email TEXT NOT NULL,salt TEXT NOT NULL,code_digest TEXT NOT NULL,expires REAL NOT NULL,sent REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,consumed INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS tw_status_subscriptions(email TEXT PRIMARY KEY,unsubscribe_digest TEXT NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL);
 ''')
 with db() as c:
  if 'origin' not in [r['name'] for r in c.execute('PRAGMA table_info(tw_status_subscriptions)')]:c.execute("ALTER TABLE tw_status_subscriptions ADD COLUMN origin TEXT NOT NULL DEFAULT 'http://127.0.0.1:18150'")
 def session(req):
  token,state=auth.ensure_session(req.cookies.get('teamwork_session'));return token,auth.session_owner_digest(token)
 @app.post('/api/status/subscriptions/email')
 async def start(req:Request):
  d=await req.json();email=str(d.get('email','')).strip().lower()
  if len(email)>254 or not re.fullmatch(r'[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+',email):raise HTTPException(422,'Enter a valid email address.')
  token,sid=session(req);now=time.time();code=f'{secrets.randbelow(1000000):06d}';salt=secrets.token_hex(16)
  with db() as c:
   c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM tw_status_email_flows WHERE session=?',(sid,)).fetchone()
   if old and now-old['sent']<60:raise HTTPException(429,'Please wait before requesting another code.')
   send_mail(email,'Verify your Teamwork.com status subscription',f'Your Teamwork.com status subscription verification code is {code}.\n\nEnter it in the status subscription form. It expires in 10 minutes and can only be used once.\n')
   c.execute('INSERT INTO tw_status_email_flows VALUES(?,?,?,?,?,?,0,0) ON CONFLICT(session) DO UPDATE SET email=excluded.email,salt=excluded.salt,code_digest=excluded.code_digest,expires=excluded.expires,sent=excluded.sent,attempts=0,consumed=0',(sid,email,salt,digest(salt+code),now+600,now))
  return response({'ok':True,'state':'verification','retry_after':60},token)
 @app.get('/api/status/subscriptions/email')
 def state(req:Request):
  token,sid=session(req)
  with db() as c:r=c.execute('SELECT * FROM tw_status_email_flows WHERE session=?',(sid,)).fetchone()
  result={'state':'idle'}
  if r and r['expires']>time.time() and not r['consumed']:result={'state':'verification','email':r['email'],'retry_after':max(0,int(r['sent']+60-time.time()))}
  elif r and r['consumed']:
   with db() as c:sub=c.execute('SELECT active FROM tw_status_subscriptions WHERE email=?',(r['email'],)).fetchone()
   if sub and sub['active']:result={'state':'subscribed','email':r['email']}
  return response(result,token)
 @app.post('/api/status/subscriptions/email/verify')
 async def verify(req:Request):
  d=await req.json();token,sid=session(req);now=time.time();code=str(d.get('code',''))
  with db() as c:
   c.execute('BEGIN IMMEDIATE');flow=c.execute('SELECT * FROM tw_status_email_flows WHERE session=?',(sid,)).fetchone()
   if not flow or flow['consumed'] or flow['expires']<=now:raise HTTPException(400,'This verification code has expired or has already been used.')
   if flow['attempts']>=5:raise HTTPException(429,'Too many attempts. Request another verification code.')
   if not hmac.compare_digest(digest(flow['salt']+code),flow['code_digest']):
    c.execute('UPDATE tw_status_email_flows SET attempts=attempts+1 WHERE session=?',(sid,));c.commit();raise HTTPException(400,'The verification code is incorrect.')
   origin=str(req.base_url).rstrip('/');parts=urlsplit(origin)
   if parts.hostname not in ['127.0.0.1','localhost','::1'] or parts.port not in range(18150,18160):raise HTTPException(400,'Use the local status site to confirm this subscription.')
   unsubscribe=secrets.token_urlsafe(32);url=origin+'/status/unsubscribe?token='+unsubscribe
   send_mail(flow['email'],'Teamwork.com status subscription confirmed',f'You are subscribed to Teamwork.com status updates.\n\nTo unsubscribe, open {url}\n')
   c.execute('INSERT INTO tw_status_subscriptions(email,unsubscribe_digest,active,created,origin) VALUES(?,?,1,?,?) ON CONFLICT(email) DO UPDATE SET unsubscribe_digest=excluded.unsubscribe_digest,active=1,created=excluded.created,origin=excluded.origin',(flow['email'],digest(unsubscribe),now,origin));c.execute('UPDATE tw_status_email_flows SET consumed=1 WHERE session=?',(sid,))
  return response({'ok':True,'state':'subscribed'},token)
 @app.get('/status/unsubscribe')
 def unsubscribe_page():
  return HTMLResponse('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Teamwork.com status subscription</title><link rel="stylesheet" href="/static/clone.css"><script defer src="/static/status-subscriptions.js"></script></head><body><header><a href="/status">Teamwork.com Status</a></header><main><h1>Unsubscribe from status updates</h1><form id="status-unsubscribe"><p>Confirm to stop receiving status updates.</p><button type="submit">Unsubscribe</button><p role="status"></p></form></main><footer><a href="/status">Back to status</a></footer></body></html>')
 @app.post('/api/status/subscriptions/unsubscribe')
 async def unsubscribe(req:Request):
  d=await req.json();value=str(d.get('token',''))
  with db() as c:
   row=c.execute('SELECT email FROM tw_status_subscriptions WHERE unsubscribe_digest=?',(digest(value),)).fetchone()
   if row:c.execute('UPDATE tw_status_subscriptions SET active=0 WHERE email=?',(row['email'],))
   else:
    channel=c.execute('SELECT id FROM tw_status_channels WHERE token=?',(value,)).fetchone()
    if not channel:raise HTTPException(400,'This unsubscribe link is invalid.')
    c.execute('UPDATE tw_status_channels SET active=0 WHERE id=?',(channel['id'],))
  return {'ok':True}
 import status_delivery
 import status_channels
 channels=status_channels.install(app,db,auth,response,send_mail)
 return {**status_delivery.install(app,db,send_mail,channels['tick']),'channels':channels}
