"""Local invitations, explicit workspace membership, and server-side role checks."""
import hashlib,html,json,re,secrets,smtplib,time
from copy import deepcopy
from urllib.parse import urlencode,urlsplit
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import RedirectResponse
from lxml import etree

OWNER_ACCOUNT_PATHS=tuple('/6302022/account/'+suffix for suffix in ('plans','files','owners','ownerships','name','trash','todos/mass_reassignments','accesses/overrides','exports','cancellation'))
def owner_action(path):
 path=urlsplit(path).path
 return any(path==prefix or path.startswith(prefix+'/') for prefix in OWNER_ACCOUNT_PATHS)

def initialize(db):
 with db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS bc_members(workspace TEXT,account TEXT,role TEXT NOT NULL,created INTEGER,PRIMARY KEY(workspace,account));
 CREATE TABLE IF NOT EXISTS bc_invites(token_hash TEXT PRIMARY KEY,workspace TEXT,email TEXT,name TEXT,role TEXT,project TEXT,expires INTEGER,accepted INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS bc_project_members(workspace TEXT,project TEXT,account TEXT,PRIMARY KEY(workspace,project,account));
 ''')
 with db() as c:
  if 'access' not in {r['name'] for r in c.execute('PRAGMA table_info(bc_members)')}:c.execute("ALTER TABLE bc_members ADD COLUMN access TEXT NOT NULL DEFAULT 'all'")
def context(db,account):
 with db() as c:
  if not c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"',(account['account_id'],)).fetchone():
   c.execute('INSERT OR IGNORE INTO bc_members(workspace,account,role,created) VALUES(?,?,"owner",?)',(account['account_id'],account['account_id'],int(time.time())))
  row=c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="selected_workspace"',(account['account_id'],)).fetchone();selected=json.loads(row['value']) if row else account['account_id']
  member=c.execute('SELECT * FROM bc_members WHERE workspace=? AND account=?',(selected,account['account_id'])).fetchone()
  if not member:selected=account['account_id'];role='owner'
  else:role=member['role']
  projects=None if not member or role=='owner' or member['access']=='all' else [r['project'] for r in c.execute('SELECT project FROM bc_project_members WHERE workspace=? AND account=?',(selected,account['account_id']))]
  closed=bool(c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"',(selected,)).fetchone())
 return {**account,'workspace_id':selected,'role':role,'projects':projects,'closed':closed}
def manager(account,owner_only=False):
 if account['role'] not in (['owner'] if owner_only else ['owner','admin']):raise HTTPException(403,'Only an account '+('owner' if owner_only else 'administrator')+' can do this.')
def writable(account):
 if account['role']=='viewer':raise HTTPException(403,'You have read-only access to this account.')
def members(c,workspace):
 return [dict(r) for r in c.execute('SELECT m.account,m.role,a.display_name AS name,a.email_normalized AS email FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.account WHERE m.workspace=? ORDER BY m.created',(workspace,))]
def role_candidates(c,account,kind):
 manager(account,kind=='new_owners')
 from task_fields import people
 catalog=people(c,account)
 excluded=('owner','admin') if kind=='new_administrators' else ('owner',)
 return [catalog[member['account']] for member in members(c,account['workspace_id']) if member['role'] not in excluded]
def enroll(db,account,people,send_mail,origin,project=''):
 manager(account);prepared=[]
 for person in people:
  email=str(person.get('email','')).strip().lower();name=str(person.get('name','')).strip();role=person.get('role','member')
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(422,'Enter a valid email address for each person.')
  if role not in ['member','admin','viewer']:raise HTTPException(422,'Choose a valid role.')
  token=secrets.token_urlsafe(32);prepared.append((email,name,role,token))
 if not prepared:raise HTTPException(422,'Choose someone to invite.')
 for email,name,role,token in prepared:
  try:send_mail(email,"You've been invited to Basecamp",account['display_name']+' invited you to their local Basecamp account.\n\n'+origin+'/invitations/'+token+'\n\nSign in using '+email+' to accept. This invitation expires in 7 days.')
  except (OSError,smtplib.SMTPException):raise HTTPException(503,'The invitation email could not be sent. Please try again.')
  with db() as c:c.execute('INSERT INTO bc_invites VALUES(?,?,?,?,?,?,?,0)',(hashlib.sha256(token.encode()).hexdigest(),account['workspace_id'],email,name,role,project,int(time.time())+7*86400))
 return len(prepared)
def allows(account,path):
 match=re.search(r'/6302022/(?:buckets|projects)/(\d+)(?:/|$)',path)
 return not match or account.get('projects') is None or match[1] in account['projects']

def filter_tree(tree,account):
 overview=bool(tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," superpowers ")]'))
 for node in list(tree.xpath('//a[@href]')):
  target=urlsplit(node.get('href')).path
  forbidden=(account['role']!='owner' and owner_action(target)) or (account['role'] not in ['owner','admin'] and target.startswith('/6302022/account/') and target.rstrip('/')!='/6302022/account')
  if forbidden and node.getparent() is not None:
   if overview and any('superpower-item' in parent.get('class','').split() for parent in node.iterancestors()):
    style=node.get('class');node.attrib.clear()
    if style:node.set('class',style)
    node.set('aria-disabled','true');node.set('tabindex','-1')
   else:node.getparent().remove(node)
 for section in tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," superpowers ")]'):
  allowed=account['role']=='owner' if 'superpowers--owner' in section.get('class','').split() else account['role'] in ('owner','admin')
  if not allowed:
   for heading in section.xpath('./h4'):section.remove(heading)
 if account.get('projects') is None:return
 for node in list(tree.xpath('//*[@href or @src or @data-url]')):
  target=node.get('href',node.get('src',node.get('data-url','')))
  if allows(account,target):continue
  container=next((ancestor for ancestor in node.iterancestors() if ancestor.tag in ['article','li'] or 'recording-preview' in ancestor.get('class','')),node)
  if container.getparent() is not None:container.getparent().remove(container)
 if account['role'] not in ['owner','admin']:
  for node in tree.xpath('//a[starts-with(@href,"/6302022/account/")]'):
   if node.getparent() is not None:node.getparent().remove(node)

def render(tree,path,account,c):
 filter_tree(tree,account)
 for action,kind in [('administratorships','new_administrators'),('ownerships','new_owners')]:
  for picker in tree.xpath('//form[@action="/6302022/account/'+action+'"]//bc-autocomplete'):
   picker.set('url','/6302022/autocompletables/people/'+kind)
   picker.set('preload',json.dumps(role_candidates(c,account,kind)))
   # Captured DOM has already been hydrated. Rebuild the native input so the
   # component creates its own hidden value and suggestions for this session.
   for child in list(picker):picker.remove(child)
   for key in ('id','ready','value','selected-count','unselected-count','aria-expanded'):picker.attrib.pop(key,None)
   etree.SubElement(picker,'input',{'type':'text','name':'person_id','id':'person_id','autocomplete':'off','placeholder':'Type a person’s name…','required':'required','class':'new-administrator-field','dir':'auto','aria-label':'Type a person’s name…'})
 if path in ('/6302022/account/administrators','/6302022/account/owners'):
  containers=tree.xpath('//main//div[contains(concat(" ",normalize-space(@class)," ")," list-picker--with-button ")]')
  if containers:
   container=containers[0];prototype=deepcopy(container[0])
   for node in list(container):container.remove(node)
   for member in members(c,account['workspace_id']):
    if member['role'] not in (('owner',) if path.endswith('/owners') else ('owner','admin')):continue
    row=deepcopy(prototype);row.set('id','person_'+member['account']);row.set('data-member-id',member['account'])
    for name in row.xpath('.//strong'):name.text=member['name']
    for avatar in row.xpath('.//img'):
     avatar.set('src','/api/avatar.svg?person='+member['account']);avatar.set('alt',member['name']);avatar.set('title',member['name']);avatar.set('data-avatar-for-person-id',member['account'])
    if member['role']!='owner':
     for label in row.xpath('.//*[contains(@class,"list-picker-item--owner")]'):label.getparent().remove(label)
     form=etree.SubElement(row,'form',{'action':'/6302022/account/administratorships','method':'post','data-remote':'true','class':'list-picker-item__label'})
     etree.SubElement(form,'input',{'type':'hidden','name':'_method','value':'DELETE'})
     etree.SubElement(form,'input',{'type':'hidden','name':'person_id','value':member['account']})
     etree.SubElement(form,'button',{'type':'submit','class':'btn btn--small btn--negative','aria-label':'Revoke administrator '+member['name']}).text='Revoke'
    container.append(row)
  return
 if path not in ['/6302022/account/people','/6302022/people','/6302022/account/administrators'] and not re.search(r'/projects/\d+/people/',path):return
 targets=tree.xpath('//main')
 if not targets:return
 section=etree.SubElement(targets[0],'section',{'class':'settings-list margin-block-24','data-local-members':'true'})
 for member in members(c,account['workspace_id']):
  if path.endswith('/administrators') and member['role'] not in ['owner','admin']:continue
  row=etree.SubElement(section,'div',{'class':'settings-list__item','data-member-id':member['account']});etree.SubElement(row,'strong').text=member['name'];etree.SubElement(row,'span',{'class':'text-subtle'}).text=' · '+member['email']+' · '+member['role']
 for invite in c.execute('SELECT email FROM bc_invites WHERE workspace=? AND accepted=0 AND expires>?',(account['workspace_id'],time.time())):etree.SubElement(section,'p',{'class':'text-subtle'}).text=invite['email']+' — Invitation pending'
def install(app,db,require_user,user,csrf_check,send_mail,origin,auth_page,form):
 router=APIRouter()
 @router.get('/workspaces/{workspace}/open')
 def open_link(workspace:str,request:Request):
  account=user(request);target=request.query_params.get('path','/6302022/')
  if not account:return RedirectResponse('/signin?'+urlencode({'return_to':request.url.path+'?'+request.url.query}),303)
  if not target.startswith('/6302022/') or '\\' in target or any(ord(ch)<32 for ch in target):raise HTTPException(422,'Invalid workspace link.')
  with db() as c:
   member=c.execute('SELECT * FROM bc_members WHERE workspace=? AND account=?',(workspace,account['account_id'])).fetchone()
   if not member:raise HTTPException(403,'You do not belong to this account.')
   if c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"',(workspace,)).fetchone():raise HTTPException(403,'This account has closed.')
   projects=None if member['role']=='owner' or member['access']=='all' else [row['project'] for row in c.execute('SELECT project FROM bc_project_members WHERE workspace=? AND account=?',(workspace,account['account_id']))]
   if not allows({'projects':projects},target):raise HTTPException(403,'You do not have access to this project.')
   c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"selected_workspace",?)',(account['account_id'],json.dumps(workspace)))
  return RedirectResponse(target,303)
 @router.get('/api/workspaces')
 def listing(request:Request):
  account=require_user(request)
  with db() as c:
   rows=c.execute('SELECT m.workspace,m.role,a.display_name FROM bc_members m JOIN local_auth_accounts a ON a.account_id=m.workspace WHERE m.account=?',(account['account_id'],)).fetchall()
   return {'current':account['workspace_id'],'workspaces':[dict(r) for r in rows]}
 @router.post('/api/workspaces/{workspace}/switch')
 async def switch(workspace:str,request:Request):
  account=require_user(request);csrf_check(request,await request.json())
  with db() as c:
   if not c.execute('SELECT 1 FROM bc_members WHERE workspace=? AND account=?',(workspace,account['account_id'])).fetchone():raise HTTPException(403,'You do not belong to this account.')
   c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"selected_workspace",?)',(account['account_id'],json.dumps(workspace)))
  return {'redirect':'/6302022/'}
 @router.get('/api/members')
 def listing_members(request:Request):
  account=require_user(request)
  with db() as c:return members(c,account['workspace_id'])
 @router.post('/api/invitations')
 async def invite(request:Request):
  account=require_user(request);data=await request.json();csrf_check(request,data)
  return {'sent':enroll(db,account,data.get('people',[]),send_mail,origin)}
 @router.api_route('/api/members/{identifier}',methods=['PATCH','DELETE'])
 async def member(identifier:str,request:Request):
  account=require_user(request);manager(account);data=await request.json() if request.method=='PATCH' else {};csrf_check(request,data)
  with db() as c:
   c.execute('BEGIN IMMEDIATE')
   actor=c.execute('SELECT role FROM bc_members WHERE workspace=? AND account=?',(account['workspace_id'],account['account_id'])).fetchone()
   manager({**account,'role':actor['role'] if actor else 'member'})
   target=c.execute('SELECT * FROM bc_members WHERE workspace=? AND account=?',(account['workspace_id'],identifier)).fetchone()
   if not target:raise HTTPException(404,'Person not found')
   if target['role']=='owner':raise HTTPException(409,'The account owner cannot be removed or demoted.')
   if request.method=='DELETE' and target['role']=='admin':raise HTTPException(409,'Revoke administrator powers before removing this person from the account.')
   if request.method=='DELETE':c.execute('DELETE FROM bc_members WHERE workspace=? AND account=?',(account['workspace_id'],identifier));c.execute('DELETE FROM bc_project_members WHERE workspace=? AND account=?',(account['workspace_id'],identifier))
   else:
    if data.get('role') not in ['member','admin','viewer']:raise HTTPException(422,'Choose a valid role.')
    c.execute('UPDATE bc_members SET role=? WHERE workspace=? AND account=?',(data['role'],account['workspace_id'],identifier))
  return {'saved':True}
 def invitation(token):
  with db() as c:
   row=c.execute('SELECT * FROM bc_invites WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
   if row and c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"',(row['workspace'],)).fetchone():raise HTTPException(410,'This account has closed.')
  if not row or row['expires']<time.time() or row['accepted']:raise HTTPException(410,'This invitation has expired or has already been accepted.')
  return row
 @router.get('/invitations/{token}')
 def invitation_page(token:str,request:Request):
  row=invitation(token);account=user(request)
  if not account:return RedirectResponse('/signin?'+urlencode({'return_to':'/invitations/'+token}),303)
  if account['email_normalized']!=row['email']:raise HTTPException(403,'Sign in with the email address that received this invitation.')
  return auth_page('Join Basecamp','<p>You have been invited to collaborate in this Basecamp account.</p>'+form('/invitations/'+token,'','Accept invitation'),request.cookies.get('basecamp_local_session'))
 @router.post('/invitations/{token}')
 async def accept(token:str,request:Request):
  account=require_user(request);csrf_check(request,await request.form());key=hashlib.sha256(token.encode()).hexdigest()
  with db() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM bc_invites WHERE token_hash=?',(key,)).fetchone()
   if not row or row['expires']<time.time() or row['accepted']:raise HTTPException(410,'This invitation has expired or has already been accepted.')
   if c.execute('SELECT 1 FROM bc_settings WHERE owner=? AND name="cancelled_at"',(row['workspace'],)).fetchone():raise HTTPException(410,'This account has closed.')
   if account['email_normalized']!=row['email']:raise HTTPException(403,'Sign in with the email address that received this invitation.')
   c.execute('INSERT OR IGNORE INTO bc_members(workspace,account,role,created,access) VALUES(?,?,?,?,?)',(row['workspace'],account['account_id'],row['role'],int(time.time()),'projects' if row['project'] else 'all'))
   if not row['project']:c.execute("UPDATE bc_members SET access='all' WHERE workspace=? AND account=?",(row['workspace'],account['account_id']))
   if row['project']:c.execute('INSERT OR IGNORE INTO bc_project_members VALUES(?,?,?)',(row['workspace'],row['project'],account['account_id']))
   c.execute('UPDATE bc_invites SET accepted=1 WHERE token_hash=?',(key,));c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"selected_workspace",?)',(account['account_id'],json.dumps(row['workspace'])))
  return RedirectResponse('/6302022/',303)
 app.include_router(router)
