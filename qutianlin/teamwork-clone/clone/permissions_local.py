"""Project permissions copied from the captured default user settings."""
import json,re
from fastapi import HTTPException
VIEW={'risk':'View Risk Register','message':'View Messages & Files','file':'View Messages & Files','time':'View Time Log','notebook':'View Notebooks','link':'View Links','form':'View Forms','person':'View People','team':'View People','budget':'View Project Budget','invoice':'Can Access Billing','expense':'Can Access Billing','quote':'Can Access Billing','list':'View Tasks & Milestones','milestone':'View Tasks & Milestones','stage':'View Tasks & Milestones','comment':'View Tasks & Milestones'}
ADD={'risk':'Add Risks','message':'Add Messages','file':'Add Files','time':'Can log time','notebook':'Add Notebooks','link':'Add Links','form':'Add Forms','budget':'Manage Project Budget','invoice':'Can Access Billing','expense':'Can Access Billing','quote':'Can Access Billing','list':'Add Task Lists','milestone':'Add Milestones','stage':'Can Manage Board','workflow':'Can Manage Board'}

def install(db,owner,account,defaults):
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS tw_member_policies(account TEXT NOT NULL,workspace_owner TEXT NOT NULL,permissions TEXT NOT NULL,projects TEXT NOT NULL,PRIMARY KEY(account,workspace_owner))')
  c.execute('CREATE TABLE IF NOT EXISTS tw_invite_groups(digest TEXT PRIMARY KEY,permission_group TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS tw_invite_projects(digest TEXT PRIMARY KEY REFERENCES tw_invites(digest) ON DELETE CASCADE,projects TEXT NOT NULL)')
 def policy(req):
  actor=account(req)['account_id'];who=owner(req)
  if actor==who:return None
  with db() as c:row=c.execute('SELECT permissions,projects FROM tw_member_policies WHERE account=? AND workspace_owner=?',(actor,who)).fetchone()
  # Existing memberships predate configurable defaults and retain their access.
  if not row:return None
  return {'permissions':json.loads(row['permissions']),'projects':json.loads(row['projects'])}
 def allowed(req,name,project=None):
  p=policy(req)
  if p is None:return True
  if project is not None and project not in p['projects']:return False
  return bool(p['permissions'].get('Project Administrator') or p['permissions'].get(name))
 def require(req,name,project=None):
  if not allowed(req,name,project):raise HTTPException(403,'Your project permissions do not allow this action.')
 def require_project(req,pid):
  p=policy(req)
  if p is not None and pid not in p['projects']:raise HTTPException(404,'Project not found.')
 def permission_defaults(who,group):
  baseline=next((g['permissions'] for g in defaults if g['group']==group),None)
  if baseline is None:raise HTTPException(422,'Select a valid user type.')
  perms={p['name']:p['enabled'] for p in baseline};projects=[]
  with db() as c:
   for row in c.execute('SELECT key,value FROM tw_settings WHERE owner=?',(who,)):
    if row['key']=='permission:'+group:perms.update(json.loads(row['value']))
    if row['key']=='default_projects:'+('owner_company' if group=='owner_company' else 'other_company'):projects=json.loads(row['value'])
  return perms,projects
 def accept(who,actor,digest,c):
  row=c.execute('SELECT permission_group FROM tw_invite_groups WHERE digest=?',(digest,)).fetchone()
  if not row:return
  permissions,projects=permission_defaults(who,row['permission_group'])
  selected=c.execute('SELECT projects FROM tw_invite_projects WHERE digest=?',(digest,)).fetchone()
  if selected:
   existing={r['id'] for r in c.execute('SELECT id FROM tw_projects WHERE owner=?',(who,))}
   projects=[pid for pid in json.loads(selected['projects']) if pid in existing]
  c.execute('INSERT INTO tw_member_policies VALUES(?,?,?,?) ON CONFLICT(account,workspace_owner) DO UPDATE SET permissions=excluded.permissions,projects=excluded.projects',(actor,who,json.dumps(permissions),json.dumps(projects)))
 def filter_workspace(req,ws):
  p=policy(req)
  if p is None:return ws
  ws['projects']=[r for r in ws['projects'] if r['id'] in p['projects']]
  tasks=[r for r in ws['tasks'] if r['project_id'] in p['projects']];task_ids={r['id'] for r in tasks}
  ws['tasks']=tasks if allowed(req,'View Tasks & Milestones') else []
  if not allowed(req,'View Estimated Time'):
   for task in ws['tasks']:task['estimate']=0
  ws['records']=[r for r in ws['records'] if (not r['parent'] or r['parent'] in p['projects'] or r['parent'] in task_ids) and (r['kind'] not in VIEW or allowed(req,VIEW[r['kind']]))]
  if not allowed(req,'Can View Other Peoples Time'):ws['records']=[r for r in ws['records'] if r['kind']!='time' or r['data'].get('actor')==account(req)['account_id']]
  ws['permissions']=p['permissions'];return ws
 def record_check(req,kind,parent,write=False):
  project=parent
  if parent:
   with db() as c:task=c.execute('SELECT project_id FROM tw_tasks WHERE owner=? AND id=?',(owner(req),parent)).fetchone()
   if task:project=task['project_id']
   require_project(req,project)
  name=(ADD if write else VIEW).get(kind)
  if name:require(req,name,project or None)
  elif write and kind in ['client','person','role','skill','team','invitation','automation','customfield','webhook'] and policy(req) is not None:raise HTTPException(403,'Only the workspace owner can manage this item.')
 return {'policy':policy,'allowed':allowed,'require':require,'project':require_project,'accept':accept,'filter':filter_workspace,'record':record_check,'defaults':permission_defaults}
