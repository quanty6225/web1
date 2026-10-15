"""Chat-only roles, revocable access and actual local SMTP invitations."""
import hashlib,html,json,secrets,time
from urllib.parse import quote
from fastapi import HTTPException,Request
from fastapi.responses import HTMLResponse
from websitebench.local_clone_auth.store import _normalize_email
from websitebench.local_clone_auth import AuthValidationError
from status_subscriptions import send_mail
import chat_conversations,chat_profile
SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_disabled(owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,PRIMARY KEY(owner,actor));
CREATE TABLE IF NOT EXISTS tw_chat_invitations(owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,id TEXT NOT NULL,email TEXT NOT NULL,role TEXT NOT NULL,digest TEXT NOT NULL UNIQUE,expires REAL NOT NULL,sent REAL NOT NULL,accepted INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,id),UNIQUE(owner,email));
'''
ROLES=['admin','user','guest']
def enabled(c,who,actor):return not c.execute('SELECT 1 FROM tw_chat_disabled WHERE owner=? AND actor=?',(who,actor)).fetchone()
def admin(c,who,actor):
 if not enabled(c,who,actor) or chat_conversations.role(c,who,actor)!='admin':raise HTTPException(403,'Only Chat administrators can manage users.')
def email(value):
 try:return _normalize_email(value)
 except (AuthValidationError,TypeError,AttributeError):raise HTTPException(422,'Enter a valid email address.')
def invitation(c,who,ident):
 row=c.execute('SELECT * FROM tw_chat_invitations WHERE owner=? AND id=? AND accepted=0',(who,ident)).fetchone()
 if not row:raise HTTPException(404,'Invitation not found.')
 return dict(row)
def send(c,who,address,role,origin,resend=False):
 from chat_local import people
 if any(c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(p['id'],)).fetchone()[0]==address for p in people(c,who)):raise HTTPException(409,'This user already exists in Teamwork Chat.')
 row=c.execute('SELECT * FROM tw_chat_invitations WHERE owner=? AND email=?',(who,address)).fetchone()
 if row and not row['accepted'] and not resend:raise HTTPException(409,'This user has already been invited.')
 token=secrets.token_urlsafe(32);ident=row['id'] if row else secrets.token_hex(12);now=time.time()
 c.execute('INSERT INTO tw_chat_invitations VALUES(?,?,?,?,?,?,?,0) ON CONFLICT(owner,email) DO UPDATE SET role=excluded.role,digest=excluded.digest,expires=excluded.expires,sent=excluded.sent,accepted=0',(who,ident,address,role,hashlib.sha256(token.encode()).hexdigest(),now+7*86400,now))
 send_mail(address,'You are invited to Teamwork Chat',f'You have been invited to Teamwork Chat. Sign in with {address} to accept:\n{origin}/chat-invite/{token}\nThis local invitation expires in 7 days.')
 return {'id':ident,'email':address,'role':role,'result':'invite-sent'}

def install(app,db,identity,account,shell,uploads):
 from chat_local import people
 with db() as c:c.executescript(SCHEMA)
 @app.get('/api/chat/users')
 def users(req:Request):
  with db() as c:
   who,actor=identity(req,c);admin(c,who,actor);rows=[]
   for person in people(c,who):
    if person['id']==actor:continue
    profile=chat_profile.profile(c,who,person['id']);rows.append({**person,'email':profile['email'],'title':profile['title'],'role':chat_conversations.role(c,who,person['id']),'pending':False,'manageable':person['id']!=who})
   rows.sort(key=lambda r:r['name'].casefold())
   pending=[{'id':r['id'],'name':r['email'],'email':r['email'],'role':r['role'],'handle':'','pending':True,'manageable':True} for r in c.execute('SELECT * FROM tw_chat_invitations WHERE owner=? AND accepted=0 ORDER BY email',(who,))]
   return pending+rows
 @app.get('/api/chat/users/importable')
 def importable(req:Request):
  with db() as c:
   who,actor=identity(req,c);admin(c,who,actor)
   return [dict(r) for r in c.execute('SELECT account_id AS id,display_name AS name,email_normalized AS email FROM local_auth_accounts WHERE account_id IN (SELECT actor FROM tw_chat_disabled WHERE owner=?) AND account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?) ORDER BY display_name',(who,who))]
 @app.post('/api/chat/users/invite')
 async def invite(req:Request):
  try:data=await req.json()
  except ValueError:raise HTTPException(422,'Choose people to invite.')
  if not isinstance(data,dict) or not isinstance(data.get('users'),list) or not 1<=len(data['users'])<=100:raise HTTPException(422,'Choose between 1 and 100 people.')
  chosen=[]
  for row in data['users']:
   if not isinstance(row,dict) or row.get('role') not in ROLES:raise HTTPException(422,'Choose a valid user role.')
   address=email(row.get('email'));chosen.append((address,row['role']))
  if len({x[0] for x in chosen})!=len(chosen):raise HTTPException(422,'You are already inviting this user')
  results=[]
  for address,role in chosen:
   try:
    with db() as c:
     who,actor=identity(req,c);admin(c,who,actor);result=send(c,who,address,role,str(req.base_url).rstrip('/'))
    results.append(result)
   except HTTPException as e:
    if e.status_code in [401,403]:raise
    results.append({'email':address,'role':role,'result':'already-exists' if e.status_code==409 else 'failed','error':e.detail})
  return {'results':results}
 @app.post('/api/chat/users/invitations/{ident}/resend')
 def resend(ident:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);admin(c,who,actor);row=invitation(c,who,ident)
   return send(c,who,row['email'],row['role'],str(req.base_url).rstrip('/'),True)
 @app.patch('/api/chat/users/{ident}')
 async def update(ident:str,req:Request):
  data=await req.json();value=data.get('role') if isinstance(data,dict) else None
  if value not in ROLES:raise HTTPException(422,'Choose a valid user role.')
  with db() as c:
   who,actor=identity(req,c);admin(c,who,actor)
   if ident in [actor,who]:raise HTTPException(403,'This administrator cannot be changed here.')
   pending=c.execute('SELECT id FROM tw_chat_invitations WHERE owner=? AND id=? AND accepted=0',(who,ident)).fetchone()
   if pending:c.execute('UPDATE tw_chat_invitations SET role=? WHERE owner=? AND id=?',(value,who,ident))
   else:
    if ident not in [p['id'] for p in people(c,who)]:raise HTTPException(404,'User not found.')
    c.execute('INSERT INTO tw_chat_roles VALUES(?,?,?) ON CONFLICT(owner,actor) DO UPDATE SET role=excluded.role',(who,ident,value))
   return {'ok':True,'role':value}
 @app.delete('/api/chat/users/{ident}')
 def remove(ident:str,req:Request):
  paths=[]
  with db() as c:
   who,actor=identity(req,c);admin(c,who,actor)
   if ident in [actor,who]:raise HTTPException(403,'This administrator cannot be deleted here.')
   pending=c.execute('DELETE FROM tw_chat_invitations WHERE owner=? AND id=? AND accepted=0',(who,ident)).rowcount
   if not pending:
    if ident not in [p['id'] for p in people(c,who)]:raise HTTPException(404,'User not found.')
    c.execute('INSERT OR IGNORE INTO tw_chat_disabled VALUES(?,?)',(who,ident))
    # Keep messages and identity snapshots; deny all future Chat reads/writes and delivery.
    c.execute('DELETE FROM tw_chat_clients WHERE owner=? AND actor=?',(who,ident))
    paths=[uploads/'chat'/r['id'] for r in c.execute('SELECT id FROM tw_chat_draft_files WHERE owner=? AND actor=?',(who,ident))]
    c.execute('DELETE FROM tw_chat_draft_files WHERE owner=? AND actor=?',(who,ident))
   result={'ok':True}
  for p in paths:p.unlink(missing_ok=True)
  return result
 @app.get('/chat-invite/{token}')
 def landing(token:str,req:Request):
  digest=hashlib.sha256(token.encode()).hexdigest()
  with db() as c:row=c.execute('SELECT * FROM tw_chat_invitations WHERE digest=?',(digest,)).fetchone()
  if not row or row['accepted'] or row['expires']<time.time():return HTMLResponse(shell('Invitation unavailable','<h1>Invitation expired or already accepted.</h1><a href="/launchpad/login">Log in</a>'),status_code=410)
  try:actor=account(req)
  except HTTPException:
   target=quote('/chat-invite/'+token,safe='');return HTMLResponse(shell('Teamwork Chat invitation','<section class=local-auth><h1>You have been invited to Teamwork Chat</h1><p>Sign in with the email address that received this invitation.</p><a href="/launchpad/login?next='+target+'">Log in</a><a href="/signup?next='+target+'">Create an account</a></section>'))
  if actor['email_normalized']!=row['email']:raise HTTPException(403,'Sign in with the invited email address.')
  return HTMLResponse(shell('Teamwork Chat invitation','<section class=local-auth><h1>Join Teamwork Chat</h1><form data-chat-invitation><input type=hidden name=token value="'+html.escape(token,quote=True)+'"><button type=submit>Accept invitation</button><p role=alert></p></form></section><script src="/static/chat-invite-accept.js" defer></script>'))
 @app.post('/api/chat/invitations/accept')
 async def accept(req:Request):
  actor=account(req);data=await req.json();token=data.get('token') if isinstance(data,dict) else None
  if not isinstance(token,str):raise HTTPException(422,'Choose a valid invitation.')
  with db() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM tw_chat_invitations WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
   if not row or row['accepted'] or row['expires']<time.time():raise HTTPException(410,'Invitation expired or already accepted.')
   if actor['email_normalized']!=row['email']:raise HTTPException(403,'Sign in with the invited email address.')
   who=row['owner'];aid=actor['account_id']
   added=c.execute('INSERT OR IGNORE INTO tw_memberships VALUES(?,?)',(aid,who)).rowcount
   if added:c.execute('INSERT OR IGNORE INTO tw_member_policies VALUES(?,?,?,?)',(aid,who,'{}','[]'))
   c.execute('DELETE FROM tw_chat_disabled WHERE owner=? AND actor=?',(who,aid))
   c.execute('INSERT INTO tw_chat_roles VALUES(?,?,?) ON CONFLICT(owner,actor) DO UPDATE SET role=excluded.role',(who,aid,row['role']))
   c.execute('UPDATE tw_chat_invitations SET accepted=1 WHERE digest=?',(row['digest'],))
   c.execute("INSERT INTO tw_preferences VALUES(?,'active_workspace',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value",(aid,json.dumps(who)))
  return {'ok':True,'redirect':'/workspace/chat/channels/joined'}
