"""Workspace membership, local invitations and independent team identities."""
import hashlib,json,re,secrets,time
from fastapi import HTTPException,Request
from fastapi.responses import JSONResponse,RedirectResponse,HTMLResponse

WORKSPACE_COOKIE='linear_clone_workspace'

def migrate_workspaces(c):
 # Upgrade the original one-workspace-per-owner schema without losing any data.
 sql=c.execute("SELECT sql FROM sqlite_master WHERE name='linear_workspaces'").fetchone()[0]
 if 'owner_id TEXT UNIQUE' in sql:
  c.execute('CREATE TABLE linear_workspaces_v3(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,name TEXT NOT NULL,slug TEXT NOT NULL)')
  c.execute('INSERT INTO linear_workspaces_v3 SELECT * FROM linear_workspaces')
  c.execute('DROP TABLE linear_workspaces');c.execute('ALTER TABLE linear_workspaces_v3 RENAME TO linear_workspaces')
 c.execute('CREATE TABLE IF NOT EXISTS linear_members(workspace_id TEXT NOT NULL,account_id TEXT NOT NULL,role TEXT NOT NULL,joined_at INTEGER NOT NULL,PRIMARY KEY(workspace_id,account_id))')
 c.execute('CREATE TABLE IF NOT EXISTS linear_team_members(workspace_id TEXT NOT NULL,team_id TEXT NOT NULL,account_id TEXT NOT NULL,PRIMARY KEY(workspace_id,team_id,account_id))')
 c.execute('CREATE TABLE IF NOT EXISTS linear_invitations(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,email TEXT NOT NULL,role TEXT NOT NULL,teams TEXT NOT NULL,digest TEXT UNIQUE NOT NULL,expires_at INTEGER NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL)')
 c.execute("INSERT OR IGNORE INTO linear_members SELECT id,owner_id,'admin',? FROM linear_workspaces",(int(time.time()),))
 if not c.execute('SELECT 1 FROM linear_schema WHERE version=3').fetchone():
  c.execute("INSERT OR IGNORE INTO linear_team_members SELECT id,'QQQ',owner_id FROM linear_workspaces")
  c.execute('INSERT INTO linear_schema VALUES(3,?)',(int(time.time()),))

def admin(w):
 if w.get('role','admin')!='admin':raise HTTPException(403,'Only workspace admins can make this change.')

def teams(c,wid):
 rows=[json.loads(r[0]) for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='teams'",(wid,))]
 if not any(x['id']=='QQQ' for x in rows) and not c.execute("SELECT 1 FROM linear_settings WHERE workspace_id=? AND route='internal' AND key='default-team'",(wid,)).fetchone():rows.insert(0,{'id':'QQQ','title':'Qqq153','description':''})
 return rows

def validate_team(c,wid,team):
 if not isinstance(team,str) or not any(t['id']==team and not t.get('archived') for t in teams(c,wid)):raise HTTPException(422,'Select an active team from this workspace.')
 return team

def next_issue_id(c,wid,team):
 validate_team(c,wid,team)
 key='issues' if team=='QQQ' else 'issues:'+team
 row=c.execute('SELECT next_number FROM linear_counters WHERE workspace_id=? AND kind=?',(wid,key)).fetchone()
 number=row[0] if row else max([int(r[0].rsplit('-',1)[1]) for r in c.execute("SELECT id FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)) if re.fullmatch(re.escape(team)+r'-\d+',r[0])],default=0)+1
 c.execute('INSERT INTO linear_counters VALUES(?,?,?) ON CONFLICT(workspace_id,kind) DO UPDATE SET next_number=excluded.next_number',(wid,key,number+1))
 return team+'-'+str(number)

def account_workspaces(auth,a):
 with auth.connect() as c:return [dict(r) for r in c.execute('SELECT w.*,m.role FROM linear_workspaces w JOIN linear_members m ON m.workspace_id=w.id WHERE m.account_id=? ORDER BY m.joined_at,w.rowid',(a['account_id'],))]

def set_workspace(response,w):
 response.set_cookie(WORKSPACE_COOKIE,w['id'],httponly=True,samesite='lax',max_age=30*86400,path='/')
 return response

def team_state(auth,w,a):
 with auth.connect() as c:
  return [{**t,'joined':bool(c.execute('SELECT 1 FROM linear_team_members WHERE workspace_id=? AND team_id=? AND account_id=?',(w['id'],t['id'],a['account_id'])).fetchone()),'member_count':c.execute('SELECT count(*) FROM linear_team_members WHERE workspace_id=? AND team_id=?',(w['id'],t['id'])).fetchone()[0]} for t in teams(c,w['id'])]

def workflow_states(store,wid,team='QQQ'):
 return [x for x in store.list(wid,'workflow-states') if x.get('team','QQQ')==team]

def seed_team_states(c,wid,team,now):
 if team=='QQQ':return
 for index,(title,category) in enumerate([('Backlog','Backlog'),('Todo','Unstarted'),('In Progress','Started'),('Done','Completed'),('Canceled','Canceled'),('Duplicate','Duplicate')]):
  id='workflow-'+team+'-'+str(index);value={'id':id,'title':title,'category':category,'team':team,'default':title=='Backlog'}
  c.execute("INSERT INTO linear_records VALUES(?,'workflow-states',?,?,1,?,?)",(wid,id,json.dumps(value),now,now))

def install(app,auth,store,actor,session,smtp_send):
 @app.middleware('http')
 async def workspace_routes(request,call_next):
  from starlette.responses import Response
  path=request.scope['path'];original=path;slug=path.split('/')[1] if '/' in path else '';_,s=session(request);w=None
  dynamic_static=path.startswith('/static/') and path.endswith(('.js','.json','.html'))
  if dynamic_static:request.scope['headers']=[(key,value) for key,value in request.scope['headers'] if key.lower() not in (b'if-none-match',b'if-modified-since')]
  with auth.connect() as c:exists=c.execute('SELECT 1 FROM linear_workspaces WHERE slug=?',(slug,)).fetchone() if slug!='qqq153' else None
  if exists:
   if not s or not s['authenticated']:return RedirectResponse('/login?redirectTo='+original,303)
   with auth.connect() as c:row=c.execute('SELECT w.*,m.role FROM linear_workspaces w JOIN linear_members m ON w.id=m.workspace_id WHERE w.slug=? AND m.account_id=?',(slug,s['account']['account_id'])).fetchone()
   if not row:return HTMLResponse('<h1>You do not have access to this workspace.</h1><a href="/">Back to Linear</a>',403)
   w=dict(row);request.state.workspace_id=w['id'];request.scope['path']=path='/qqq153'+path[len(slug)+1:];request.scope['raw_path']=path.encode()
  elif s and s['authenticated'] and request.cookies.get(WORKSPACE_COOKIE):
   with auth.connect() as c:row=c.execute('SELECT w.*,m.role FROM linear_workspaces w JOIN linear_members m ON w.id=m.workspace_id WHERE w.id=? AND m.account_id=?',(request.cookies[WORKSPACE_COOKIE],s['account']['account_id'])).fetchone()
   if row:w=dict(row)
  if s and s['authenticated'] and path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
   try:selected=store.workspace(s['account'],getattr(request.state,'workspace_id',None) or request.headers.get('x-linear-workspace') or request.cookies.get(WORKSPACE_COOKIE))
   except HTTPException as error:return JSONResponse({'detail':error.detail},error.status_code)
   restricted=path.startswith(('/api/workspace/delete','/api/workspace/deletion-code','/api/webhooks/')) or bool(re.match(r'/api/entities/(?:workflow-states|project-statuses|webhooks|integrations|label-groups)(?:/|$)',path))
   if restricted and selected.get('role')!='admin':return JSONResponse({'detail':'Only workspace admins can make this change.'},403)
  team=None
  match=re.match(r'^/qqq153/(?:team|settings/teams)/([^/]+)(?:/|$)',path)
  if match and s and s['authenticated']:
   w=w or store.workspace(s['account']);id=match[1]
   with auth.connect() as c:team=next((t for t in teams(c,w['id']) if t['id']==id),None)
   if not team:return HTMLResponse('<h1>Team not found</h1><a href="/'+w['slug']+'/teams">Back to teams</a>',404)
   request.state.team_id=id
   request.scope['path']=path[:match.start(1)]+'QQQ'+path[match.end(1):];request.scope['raw_path']=request.scope['path'].encode()
  response=await call_next(request)
  if dynamic_static:
   response.headers['Cache-Control']='private, no-store';response.headers['Vary']='Cookie'
   if 'etag' in response.headers:del response.headers['etag']
  if w:
   target='/'+w['slug'];kind=response.headers.get('content-type','')
   if 'location' in response.headers and response.headers['location'].startswith('/qqq153'):response.headers['location']=response.headers['location'].replace('/qqq153',target,1)
   if (w['slug']!='qqq153' or team) and ('text/html' in kind or path.startswith('/static/') and (path.endswith('.js') or path.endswith('.json'))):
    body=b''.join([part async for part in response.body_iterator]);body=body.replace(b'qqq153',w['slug'].encode())
    if team and 'text/html' in kind:
     import html
     body=body.replace(b'/QQQ/',('/'+team['id']+'/').encode()).replace(b'Qqq153',html.escape(team['title']).encode())
     body=body.replace(b'<body',('<body data-active-team="'+team['id']+'"').encode(),1)
    headers=dict(response.headers);headers.pop('content-length',None);headers['Cache-Control']='private, no-store';headers['Vary']='Cookie'
    response=Response(body,status_code=response.status_code,headers=headers,background=response.background)
   if exists:set_workspace(response,w)
  return response

 @app.get('/api/workspaces')
 def list_workspaces(request:Request):
  _,s=session(request,True);return account_workspaces(auth,s['account'])

 @app.post('/api/workspaces')
 async def create_workspace(request:Request):
  _,s=session(request,True);a=s['account'];d=await request.json()
  name=str(d.get('name','')).strip();slug=str(d.get('slug','')).strip().lower();team=str(d.get('identifier','QQQ')).upper().strip();title=str(d.get('team_name',name)).strip()
  if not name or len(name)>100 or not re.fullmatch(r'[a-z][a-z0-9-]{2,48}',slug) or slug in {'api','static','login','signup','auth','settings','qqq153','homepage','docs','features','new','team','external','join'}:raise HTTPException(422,'Enter a workspace name and a valid, available workspace URL.')
  if not title or not re.fullmatch(r'[A-Z][A-Z0-9]{0,9}',team):raise HTTPException(422,'Enter a team name and an identifier of 1–10 letters or numbers.')
  wid='ws_'+secrets.token_hex(12);now=int(time.time())
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT 1 FROM linear_workspaces WHERE slug=?',(slug,)).fetchone():raise HTTPException(409,'This workspace URL is already in use.')
   c.execute('INSERT INTO linear_workspaces VALUES(?,?,?,?)',(wid,a['account_id'],name,slug));c.execute("INSERT INTO linear_members VALUES(?,?,'admin',?)",(wid,a['account_id'],now))
   # QQQ remains the default team identifier for captured routes; a chosen team is independent.
   record={'id':team,'title':title,'description':'','archived':False}
   c.execute("INSERT INTO linear_records VALUES(?,'teams',?,?,1,?,?)",(wid,team,json.dumps(record),now,now));c.execute('INSERT INTO linear_team_members VALUES(?,?,?)',(wid,team,a['account_id']))
   c.execute("INSERT INTO linear_settings VALUES(?,'internal','default-team',?)",(wid,json.dumps(team)))
   store.seed_configuration(c,wid);seed_team_states(c,wid,team,now);c.commit()
  w={'id':wid,'owner_id':a['account_id'],'name':name,'slug':slug,'role':'admin'}
  return set_workspace(JSONResponse({**w,'redirect':'/'+slug+'/team/'+team+'/active'},201),w)

 @app.post('/api/workspaces/{id}/switch')
 def switch_workspace(id:str,request:Request):
  _,s=session(request,True);w=store.workspace(s['account'],id)
  with auth.connect() as c:team=teams(c,id)[0]['id']
  return set_workspace(JSONResponse({'workspace':w,'redirect':'/'+w['slug']+'/team/'+team+'/active'}),w)

 @app.get('/api/members')
 def members(request:Request):
  a,w=actor(request)
  with auth.connect() as c:
   result=[dict(r) for r in c.execute('SELECT a.account_id,a.email_normalized,a.display_name,m.role,m.joined_at FROM linear_members m JOIN local_auth_accounts a ON a.account_id=m.account_id WHERE m.workspace_id=? ORDER BY m.joined_at',(w['id'],))]
   for r in result:r['teams']=[x[0] for x in c.execute('SELECT team_id FROM linear_team_members WHERE workspace_id=? AND account_id=?',(w['id'],r['account_id']))];r['owner']=r['account_id']==w['owner_id']
   return result

 @app.patch('/api/members/{id}')
 async def member_role(id:str,request:Request):
  a,w=actor(request);admin(w);d=await request.json();role=d.get('role')
  if role not in ('admin','member'):raise HTTPException(422,'Choose Admin or Member.')
  if id==w['owner_id'] and role!='admin':raise HTTPException(409,'Transfer workspace ownership before changing the owner’s role.')
  with auth.connect() as c:
   if not c.execute('UPDATE linear_members SET role=? WHERE workspace_id=? AND account_id=?',(role,w['id'],id)).rowcount:raise HTTPException(404,'Member not found.')
   c.commit()
  return {'saved':True}

 @app.post('/api/workspace/transfer')
 async def transfer(request:Request):
  a,w=actor(request);d=await request.json()
  if a['account_id']!=w['owner_id']:raise HTTPException(403,'Only the workspace owner can transfer ownership.')
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if not c.execute('SELECT 1 FROM linear_members WHERE workspace_id=? AND account_id=?',(w['id'],d.get('account_id'))).fetchone():raise HTTPException(404,'Member not found.')
   c.execute("UPDATE linear_members SET role='admin' WHERE workspace_id=? AND account_id=?",(w['id'],d['account_id']));c.execute('UPDATE linear_workspaces SET owner_id=? WHERE id=?',(d['account_id'],w['id']));c.commit()
  return {'saved':True}

 def remove_member(w,id):
  if id==w['owner_id']:raise HTTPException(409,'Transfer workspace ownership before leaving or removing the owner.')
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if not c.execute('DELETE FROM linear_members WHERE workspace_id=? AND account_id=?',(w['id'],id)).rowcount:raise HTTPException(404,'Member not found.')
   c.execute('DELETE FROM linear_team_members WHERE workspace_id=? AND account_id=?',(w['id'],id));c.execute('DELETE FROM linear_api_keys WHERE workspace_id=? AND account_id=?',(w['id'],id));c.commit()

 @app.delete('/api/members/{id}')
 def remove(id:str,request:Request):
  a,w=actor(request);admin(w);remove_member(w,id);return {'removed':True}

 @app.post('/api/workspace/leave')
 def leave(request:Request):
  a,w=actor(request);remove_member(w,a['account_id']);remaining=account_workspaces(auth,a)
  if not remaining:remaining=[store.workspace(a)]
  return set_workspace(JSONResponse({'redirect':'/'+remaining[0]['slug']+'/team/QQQ/active'}),remaining[0])

 @app.get('/api/invitations')
 def invitations(request:Request):
  a,w=actor(request);admin(w)
  with auth.connect() as c:return [{**dict(r),'status':'expired' if r['status']=='pending' and r['expires_at']<time.time() else r['status']} for r in c.execute('SELECT id,email,role,teams,expires_at,status,created_at FROM linear_invitations WHERE workspace_id=? ORDER BY created_at DESC',(w['id'],))]

 @app.post('/api/invitations')
 async def invite(request:Request):
  a,w=actor(request);admin(w);d=await request.json();emails=d.get('emails',[]);role=d.get('role','member');selected=d.get('teams',[])
  if not isinstance(emails,list) or not 1<=len(emails)<=50 or any(not isinstance(x,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',x) for x in emails):raise HTTPException(422,'Enter valid email addresses.')
  if role not in ('member','admin') or not isinstance(selected,list):raise HTTPException(422,'Select a valid role and teams.')
  now=int(time.time());result=[]
  with auth.connect() as c:
   for team in selected:validate_team(c,w['id'],team)
  for email in dict.fromkeys(x.strip().lower() for x in emails):
   token=secrets.token_urlsafe(32);id='invite_'+secrets.token_hex(12)
   with auth.connect() as c:
    if c.execute('SELECT 1 FROM linear_members m JOIN local_auth_accounts a ON a.account_id=m.account_id WHERE m.workspace_id=? AND a.email_normalized=?',(w['id'],email)).fetchone():raise HTTPException(409,email+' is already a member.')
    c.execute('INSERT INTO linear_invitations VALUES(?,?,?,?,?,?,?, ?,?)',(id,w['id'],email,role,json.dumps(selected),hashlib.sha256(token.encode()).hexdigest(),now+7*86400,'sending',now));c.commit()
   link=str(request.base_url).rstrip('/')+'/invite/'+token
   try:smtp_send(email,'Join your Linear workspace','You have been invited to '+w['name']+'\n\n'+link+'\n\nThis invitation expires in 7 days. Sign in with '+email+' to accept.')
   except Exception:
    with auth.connect() as c:c.execute("UPDATE linear_invitations SET status='failed' WHERE id=?",(id,));c.commit()
    raise HTTPException(503,'Unable to send this invitation. Please try again.')
   with auth.connect() as c:
    c.execute("UPDATE linear_invitations SET status='revoked' WHERE workspace_id=? AND email=? AND status='pending'",(w['id'],email));c.execute("UPDATE linear_invitations SET status='pending' WHERE id=?",(id,));c.commit()
   result.append({'id':id,'email':email,'status':'pending'})
  return {'invitations':result}

 @app.delete('/api/invitations/{id}')
 def revoke(id:str,request:Request):
  a,w=actor(request);admin(w)
  with auth.connect() as c:
   if not c.execute("UPDATE linear_invitations SET status='revoked' WHERE id=? AND workspace_id=? AND status='pending'",(id,w['id'])).rowcount:raise HTTPException(404,'Pending invitation not found.')
   c.commit()
  return {'revoked':True}

 @app.get('/invite/{token}')
 def invitation_page(token:str,request:Request):
  import html
  _,s=session(request)
  if not s or not s['authenticated']:return RedirectResponse('/login?redirectTo=/invite/'+token,303)
  with auth.connect() as c:r=c.execute('SELECT i.*,w.name FROM linear_invitations i JOIN linear_workspaces w ON w.id=i.workspace_id WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
  valid=r and r['status']=='pending' and r['expires_at']>time.time()
  if not valid:return HTMLResponse('<h1>This invitation has expired or been revoked.</h1><a href="/">Back to Linear</a>',410)
  return HTMLResponse('<!doctype html><html><head><title>Join workspace – Linear</title><link rel="stylesheet" href="/static/local.css"></head><body class="local-auth"><main class="auth-box"><h1>Join '+html.escape(r['name'])+'</h1><p>Sign in as '+html.escape(r['email'])+' to accept this invitation.</p><button data-accept-invitation="'+html.escape(token,quote=True)+'">Accept invitation</button><p role="alert"></p><a href="/">Back to Linear</a></main><script src="/static/workspace-invite.js"></script></body></html>')

 @app.post('/api/invitations/accept/{token}')
 def accept(token:str,request:Request):
  _,s=session(request,True);a=s['account'];now=int(time.time())
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM linear_invitations WHERE digest=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
   if not r or r['status']!='pending' or r['expires_at']<=now:raise HTTPException(410,'This invitation has expired or been revoked.')
   if a['email_normalized']!=r['email']:raise HTTPException(403,'Sign in with the email address that received this invitation.')
   w=c.execute('SELECT * FROM linear_workspaces WHERE id=?',(r['workspace_id'],)).fetchone()
   if not w:raise HTTPException(410,'This workspace no longer exists.')
   c.execute('INSERT OR IGNORE INTO linear_members VALUES(?,?,?,?)',(w['id'],a['account_id'],r['role'],now))
   for team in json.loads(r['teams']):
    if any(t['id']==team and not t.get('archived') for t in teams(c,w['id'])):c.execute('INSERT OR IGNORE INTO linear_team_members VALUES(?,?,?)',(w['id'],team,a['account_id']))
   c.execute("UPDATE linear_invitations SET status='accepted' WHERE id=?",(r['id'],));c.commit()
  return set_workspace(JSONResponse({'redirect':'/'+w['slug']+'/team/QQQ/active'}),dict(w))

 @app.post('/api/teams')
 async def create_team(request:Request):
  a,w=actor(request);d=await request.json();title=str(d.get('title','')).strip();id=str(d.get('identifier') or re.sub('[^A-Za-z0-9]','',title)[:5]).strip().upper();now=int(time.time())
  from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
  try:ZoneInfo(d.get('timezone','UTC'))
  except (ZoneInfoNotFoundError,TypeError):raise HTTPException(422,'Choose a valid timezone.')
  if not title or len(title)>100 or not re.fullmatch(r'[A-Z][A-Z0-9]{0,9}',id):raise HTTPException(422,'Enter a team name and an identifier of 1–10 letters or numbers.')
  if d.get('private'):raise HTTPException(422,'Private team access is not available in this local workspace.')
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if any(x['id']==id or x['title'].casefold()==title.casefold() for x in teams(c,w['id'])):raise HTTPException(409,'A team with this name or identifier already exists.')
   value={'id':id,'title':title,'description':str(d.get('description',''))[:5000],'archived':False,'timezone':d.get('timezone','UTC')}
   copy_from=d.get('copy_from')
   if copy_from:validate_team(c,w['id'],copy_from)
   c.execute("INSERT INTO linear_records VALUES(?,'teams',?,?,1,?,?)",(w['id'],id,json.dumps(value),now,now));c.execute('INSERT INTO linear_team_members VALUES(?,?,?)',(w['id'],id,a['account_id']));seed_team_states(c,w['id'],id,now)
   if copy_from:
    c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='workflow-states' AND json_extract(document,'$.team')=?",(w['id'],id))
    for source in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states' AND COALESCE(json_extract(document,'$.team'),'QQQ')=?",(w['id'],copy_from)).fetchall():
     item=json.loads(source[0]);item['id']='workflow-'+id+'-'+secrets.token_hex(6);item['team']=id;c.execute("INSERT INTO linear_records VALUES(?,'workflow-states',?,?,1,?,?)",(w['id'],item['id'],json.dumps(item),now,now))
    prefix='/qqq153/settings/teams/'+copy_from
    for setting in c.execute('SELECT route,key,value FROM linear_settings WHERE workspace_id=? AND (route=? OR route LIKE ?)',(w['id'],prefix,prefix+'/%')).fetchall():
     if setting['key']!='default-issue-template':c.execute('INSERT OR REPLACE INTO linear_settings VALUES(?,?,?,?)',(w['id'],setting['route'].replace(prefix,'/qqq153/settings/teams/'+id,1),setting['key'],setting['value']))
   c.commit()
  return {**value,'redirect':'/'+w['slug']+'/team/'+id+'/active'}

 @app.post('/api/teams/{id}/membership')
 async def team_membership(id:str,request:Request):
  a,w=actor(request);d=await request.json();target=d.get('account_id',a['account_id'])
  if target!=a['account_id']:admin(w)
  if type(d.get('joined')) is not bool:raise HTTPException(422,'Choose whether to join this team.')
  with auth.connect() as c:
   validate_team(c,w['id'],id)
   if not c.execute('SELECT 1 FROM linear_members WHERE workspace_id=? AND account_id=?',(w['id'],target)).fetchone():raise HTTPException(404,'Workspace member not found.')
   if d['joined']:c.execute('INSERT OR IGNORE INTO linear_team_members VALUES(?,?,?)',(w['id'],id,target))
   else:c.execute('DELETE FROM linear_team_members WHERE workspace_id=? AND team_id=? AND account_id=?',(w['id'],id,target))
   c.commit()
  return {'joined':d['joined']}
