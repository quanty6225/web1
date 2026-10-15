"""Linear business state, in the site backend's single SQLite database."""
import json,re,secrets,time,hashlib,hmac
from pathlib import Path
from issue_properties import prepare_issue,synchronize_issues
from documents import prepare_document,detach_documents,deliver_document_reminders
from document_templates import prepare_template
from issue_templates import prepare_issue_template
from project_labels import prepare_project_label,prepare_project_labels,delete_project_label

SCHEMA='''
CREATE TABLE IF NOT EXISTS linear_uploads(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, filename TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at INTEGER NOT NULL, render_type TEXT NOT NULL, content BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS linear_schema(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS linear_workspaces(id TEXT PRIMARY KEY, owner_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, slug TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS linear_records(workspace_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, document TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, PRIMARY KEY(workspace_id,kind,id));
CREATE TABLE IF NOT EXISTS linear_settings(workspace_id TEXT NOT NULL, route TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(workspace_id,route,key));
CREATE TABLE IF NOT EXISTS linear_magic(digest TEXT PRIMARY KEY, signin_id TEXT NOT NULL, expires_at INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0, redirect_to TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS linear_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS linear_forms(id TEXT PRIMARY KEY, kind TEXT NOT NULL, document TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS linear_api_keys(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, account_id TEXT NOT NULL, name TEXT NOT NULL, digest TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL, permissions TEXT NOT NULL, created_at INTEGER NOT NULL, last_used_at INTEGER);
CREATE TABLE IF NOT EXISTS linear_account_actions(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, purpose TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS linear_counters(workspace_id TEXT NOT NULL, kind TEXT NOT NULL, next_number INTEGER NOT NULL, PRIMARY KEY(workspace_id,kind));
CREATE TABLE IF NOT EXISTS linear_webhook_events(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, webhook_id TEXT NOT NULL, event_type TEXT NOT NULL, body TEXT NOT NULL, signature TEXT NOT NULL, created_at INTEGER NOT NULL);
'''
def migrate(c):
 for statement in SCHEMA.split(";"):
  if statement.strip():c.execute(statement)
 c.execute('INSERT OR IGNORE INTO linear_schema VALUES(1,?)',(int(time.time()),))
 c.execute('INSERT OR IGNORE INTO linear_metadata VALUES(?,?)',('csrf_secret',secrets.token_hex(32)))
 from workspaces import migrate_workspaces
 migrate_workspaces(c)

class WorkspaceStore:
 def __init__(self,auth):self.auth=auth
 def collect_event(self,c,wid,event_type,action,data):
  body=json.dumps({'type':event_type,'action':action,'data':data},sort_keys=True,separators=(',',':'));now=int(time.time())
  for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='webhooks'",(wid,)).fetchall():
   hook=json.loads(row['document'])
   if hook.get('enabled',True) and event_type in hook.get('resourceTypes',[]):
    signature=hmac.new(hook['secret'].encode(),body.encode(),hashlib.sha256).hexdigest()
    c.execute('INSERT INTO linear_webhook_events VALUES(?,?,?,?,?,?,?)',('event_'+secrets.token_hex(12),wid,hook['id'],event_type,body,signature,now))
 def collect_record_event(self,c,wid,kind,action,data,previous=None):
  resource={'issues':'Issue','projects':'Project','documents':'Document','labels':'IssueLabel','project-labels':'ProjectLabel','initiatives':'Initiative','comments':'Comment'}.get(kind)
  if resource:self.collect_event(c,wid,resource,action,data)
  if kind=='issues' and action!='remove':
   before={x['id']:x for x in (previous or {}).get('comments',[])};after={x['id']:x for x in data.get('comments',[])}
   for id,item in after.items():
    if item!=before.get(id):self.collect_event(c,wid,'Comment','update' if id in before else 'create',{**item,'issueId':data['id']})
   for id,item in before.items():
    if id not in after:self.collect_event(c,wid,'Comment','remove',{**item,'issueId':data['id']})
 def seed_configuration(self,c,wid):
  if c.execute("SELECT 1 FROM linear_settings WHERE workspace_id=? AND route='internal' AND key='configuration-seeded'",(wid,)).fetchone():return
  now=int(time.time())
  fixtures={'labels':[('Bug','bug'),('Feature','feature'),('Improvement','improvement')], 'workflow-states':[('Backlog','Backlog'),('Todo','Unstarted'),('In Progress','Started'),('Done','Completed'),('Canceled','Canceled'),('Duplicate','Duplicate')], 'project-statuses':[('Backlog','Backlog'),('Planned','Planned'),('In Progress','In Progress'),('Completed','Completed'),('Canceled','Canceled')]}
  for kind,items in fixtures.items():
   for index,(title,category) in enumerate(items):
    id=kind+'-default-'+str(index);d={'id':id,'title':title,'category':category,'description':'','default':title=='Backlog'}
    c.execute('INSERT OR IGNORE INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,kind,id,json.dumps(d),now,now))
  c.execute("INSERT INTO linear_settings VALUES(?,'internal','configuration-seeded','true')",(wid,))
 def workspace(self,account,workspace_id=None):
  owner=account['account_id']
  with self.auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if workspace_id:
    row=c.execute('SELECT w.*,m.role FROM linear_workspaces w JOIN linear_members m ON m.workspace_id=w.id WHERE w.id=? AND m.account_id=?',(workspace_id,owner)).fetchone()
    if not row:
     from fastapi import HTTPException
     raise HTTPException(403,'You are not a member of this workspace.')
    return dict(row)
   row=c.execute('SELECT * FROM linear_workspaces WHERE owner_id=?',(owner,)).fetchone()
   if row:
    self.seed_configuration(c,row['id']);c.execute("INSERT OR IGNORE INTO linear_members VALUES(?,?,'admin',?)",(row['id'],owner,int(time.time())));c.commit();return {**dict(row),'role':'admin'}
   wid='ws_'+secrets.token_hex(12)
   c.execute('INSERT INTO linear_workspaces VALUES(?,?,?,?)',(wid,owner,'qqq153','qqq153'))
   c.execute("INSERT INTO linear_members VALUES(?,?,'admin',?)",(wid,owner,int(time.time())))
   c.execute('INSERT OR IGNORE INTO linear_team_members VALUES(?,?,?)',(wid,'QQQ',owner))
   seedfile=Path(__file__).resolve().parent/'frontend/seed.json'
   seeds=json.loads(seedfile.read_text()) if seedfile.exists() else []
   now=int(time.time())
   for d in seeds:c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,'issues',d['id'],json.dumps(d),now,now))
   c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,'notifications','welcome',json.dumps({'id':'welcome','title':'Welcome to Linear','description':'Watch an introductory video and access a list of resources below.','read':False,'snoozed':False}),now,now))
   self.seed_configuration(c,wid);c.commit();return {'id':wid,'owner_id':owner,'name':'qqq153','slug':'qqq153','role':'admin'}
 def list(self,wid,kind):
  if kind=='notifications':deliver_document_reminders(self,wid)
  if kind=='drafts':
   from issue_drafts import prune_drafts
   prune_drafts(self,wid)
  if kind=='issues':
   from recurring_issues import deliver_recurring_issues
   deliver_recurring_issues(self,wid)
  with self.auth.connect() as c:
   return [{**json.loads(r['document']),'revision':r['revision'],'created_at':r['created_at'],'updated_at':r['updated_at']} for r in c.execute('SELECT * FROM linear_records WHERE workspace_id=? AND kind=? ORDER BY created_at,rowid',(wid,kind))]
 def get(self,wid,kind,id):
  with self.auth.connect() as c:
   r=c.execute('SELECT * FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(wid,kind,id)).fetchone()
   return {**json.loads(r['document']),'revision':r['revision'],'created_at':r['created_at'],'updated_at':r['updated_at']} if r else None
 def save(self,wid,kind,data,id=None):
  now=int(time.time());creating=id is None;previous=None
  with self.auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   draft_id=data.get('draft_id')if kind=='issues'and creating else None
   if draft_id:
    draft=c.execute("SELECT revision FROM linear_records WHERE workspace_id=? AND kind='drafts' AND id=?",(wid,draft_id)).fetchone()
    if not draft:raise ValueError('This draft has already been published or deleted.')
    if data.get('draft_revision')is not None and data['draft_revision']!=draft['revision']:raise ValueError('This draft was updated. Reload and try again.')
   if id:
    r=c.execute('SELECT * FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(wid,kind,id)).fetchone()
    if not r:raise KeyError(id)
    if data.get('revision') is not None and data['revision']!=r['revision']:raise ValueError('This item was updated. Reload and try again.')
    d={**json.loads(r['document']),**{k:v for k,v in data.items() if k not in ['id','owner_id','workspace_id','revision']},'id':id}
    previous=json.loads(r['document'])
    if kind in ('labels','workflow-states') and d.get('title')!=previous.get('title'):
     for issue in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)).fetchall():
      item=json.loads(issue['document']);changed=False
      if kind=='labels' and previous['title'] in item.get('labels',[]):item['labels']=[d['title'] if v==previous['title'] else v for v in item['labels']];changed=True
      if kind=='workflow-states' and item.get('team','QQQ')==previous.get('team','QQQ') and item.get('status')==previous['title']:item['status']=d['title'];changed=True
      if changed:c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(item),now,wid,issue['id']))
    if kind=='project-statuses' and d.get('title')!=previous.get('title'):
     for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='projects'",(wid,)).fetchall():
      item=json.loads(row['document'])
      if item.get('status')==previous['title']:
       item['status']=d['title'];c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='projects' AND id=?",(json.dumps(item),now,wid,row['id']))
    if kind=='issues':prepare_issue(c,wid,d,previous,data,now)
    if kind=='documents':prepare_document(c,wid,d,previous,data,now)
    if kind=='document-templates':prepare_template(c,wid,d,previous,data,now)
    if kind=='issue-templates':prepare_issue_template(c,wid,d,previous,data,now)
    if kind=='recurring-issues':
     from recurring_issues import prepare_recurring
     prepare_recurring(c,wid,d,previous,data,now)
    if kind=='drafts':
     from issue_drafts import prepare_draft
     prepare_draft(c,wid,d,previous,data,now)
    if kind=='project-labels':prepare_project_label(c,wid,d,previous,data,now)
    if kind=='projects':prepare_project_labels(c,wid,d,previous,data,now)
    c.execute('UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind=? AND id=?',(json.dumps(d),now,wid,kind,id))
   else:
    if kind=='issues':
     from workspaces import next_issue_id
     id=next_issue_id(c,wid,data.get('team','QQQ'))
    else:id=kind.rstrip('s')+'_'+secrets.token_hex(8)
    d={k:v for k,v in data.items() if k not in ['id','owner_id','workspace_id','revision']};d['id']=id
    if kind=='projects':d={'status':'Backlog','priority':'No priority','summary':'','description':'','lead':None,'members':[],'labels':[],'dependencies':[],'milestones':[],'start_date':None,'target_date':None,'start_date_precision':'day','target_date_precision':'day','icon':'Project',**d}
    if kind=='issues':d={'status':'Todo','priority':'No priority','assignee':None,'labels':[],'project':None,'comments':[],'subissues':[],**d}
    if kind=='issues':
     prepare_issue(c,wid,d,None,data,now);d.pop('draft_id',None);d.pop('draft_revision',None)
    if kind=='documents':prepare_document(c,wid,d,None,data,now)
    if kind=='document-templates':prepare_template(c,wid,d,None,data,now)
    if kind=='issue-templates':prepare_issue_template(c,wid,d,None,data,now)
    if kind=='recurring-issues':
     from recurring_issues import prepare_recurring
     prepare_recurring(c,wid,d,None,data,now)
    if kind=='drafts':
     from issue_drafts import prepare_draft
     prepare_draft(c,wid,d,None,data,now)
    if kind=='project-labels':prepare_project_label(c,wid,d,None,data,now)
    if kind=='projects':prepare_project_labels(c,wid,d,None,data,now)
    c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,kind,id,json.dumps(d),now,now))
   if draft_id:c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='drafts' AND id=?",(wid,draft_id))
   if creating and kind=='recurring-issues':
    from recurring_issues import create_instance
    create_instance(self,c,wid,d,d['first_due_date'],now,d.get('source_issue_id'))
   self.collect_record_event(c,wid,kind,'create' if creating else 'update',d,previous)
   if previous and kind in ('labels','workflow-states')and previous.get('title')!=d.get('title'):
    from subissue_templates import maintain_references
    maintain_references(c,wid,kind,previous,d)
   if creating and kind=='issues'and data.get('subissue_templates'):
    from subissue_templates import insert_children
    insert_children(self,c,wid,d,data['subissue_templates'],now)
   if kind=='issues':synchronize_issues(self,c,wid,now)
   c.commit()
  return self.get(wid,kind,id)
 def delete(self,wid,kind,id):
  with self.auth.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   existing=c.execute('SELECT document FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(wid,kind,id)).fetchone()
   if kind in ('labels','workflow-states'):
    row=c.execute('SELECT document FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(wid,kind,id)).fetchone()
    if row:
     record=json.loads(row['document'])
     if kind=='workflow-states' and record.get('category')=='Duplicate':raise ValueError('The Duplicate status is reserved and cannot be deleted.')
     for issue in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)).fetchall():
      item=json.loads(issue['document'])
      if kind=='workflow-states' and item.get('team','QQQ')==record.get('team','QQQ') and item.get('status')==record['title']:raise ValueError('Move issues to another status before deleting this status.')
      if kind=='labels' and record['title'] in item.get('labels',[]):
       item['labels']=[v for v in item['labels'] if v!=record['title']];c.execute("UPDATE linear_records SET document=?,revision=revision+1 WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(item),wid,issue['id']))
   if existing and kind=='project-labels':delete_project_label(self,c,wid,json.loads(existing['document']),int(time.time()))
   if existing and kind in ('project-statuses','projects'):
    record=json.loads(existing['document'])
    for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='projects'",(wid,)).fetchall():
     item=json.loads(row['document']);field='labels' if kind=='project-labels' else 'dependencies'
     if kind=='project-statuses' and item.get('status')==record['title']:raise ValueError('Move projects to another status before deleting this status.')
     if kind!='project-statuses' and id in item.get(field,[]):
      item[field]=[ref for ref in item[field] if ref!=id];c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='projects' AND id=?",(json.dumps(item),int(time.time()),wid,row['id']))
    if kind=='projects':
     for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)).fetchall():
      item=json.loads(row['document'])
      if item.get('project')==id:
       item['project']=None;c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(item),int(time.time()),wid,row['id']))
   changed=c.execute('DELETE FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(wid,kind,id)).rowcount
   if changed and kind in ('labels','workflow-states','projects','issue-templates','issues'):
    from subissue_templates import maintain_references
    maintain_references(c,wid,kind,json.loads(existing['document']))
   if changed:self.collect_record_event(c,wid,kind,'remove',json.loads(existing['document']))
   if changed and kind=='issues':
    synchronize_issues(self,c,wid,int(time.time()),deleted=id)
    for reminder in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='notifications'",(wid,)).fetchall():
     if json.loads(reminder['document']).get('issue_id')==id:c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='notifications' AND id=?",(wid,reminder['id']))
   if changed:detach_documents(self,c,wid,kind,id,int(time.time()))
   if changed and kind=='recurring-issues':
    for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)).fetchall():
     value=json.loads(row['document'])
     if value.get('recurring_issue_id')==id:value['recurring_issue_id']=None;c.execute("UPDATE linear_records SET document=?,revision=revision+1 WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(value),wid,row['id']))
   if changed and kind=='issue-templates':
    for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)).fetchall():
     value=json.loads(row['document'])
     if value.get('template')==id:value['template']=None;c.execute("UPDATE linear_records SET document=?,revision=revision+1 WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(value),wid,row['id']))
    c.execute("DELETE FROM linear_settings WHERE workspace_id=? AND key='default-issue-template' AND value=?",(wid,json.dumps(id)))
   if kind=='webhooks':c.execute('DELETE FROM linear_webhook_events WHERE workspace_id=? AND webhook_id=?',(wid,id))
   c.commit();return bool(changed)
 def settings(self,wid,route):
  with self.auth.connect() as c:return {r['key']:json.loads(r['value']) for r in c.execute('SELECT key,value FROM linear_settings WHERE workspace_id=? AND route=?',(wid,route))}
 def setting(self,wid,route,key,value):
  with self.auth.connect() as c:
   c.execute('INSERT INTO linear_settings VALUES(?,?,?,?) ON CONFLICT(workspace_id,route,key) DO UPDATE SET value=excluded.value',(wid,route,key,json.dumps(value)));c.commit()
