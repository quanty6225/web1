"""Previewed, transactional local workspace and CSV imports with reversible history."""
import csv,hashlib,io,json,re,secrets,time
from fastapi import Request,HTTPException
from workspaces import admin,teams,validate_team,next_issue_id,account_workspaces

def migrate(c):
 c.execute('CREATE TABLE IF NOT EXISTS linear_imports(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,account_id TEXT NOT NULL,source_workspace TEXT,source_digest TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL,completed_at INTEGER,manifest TEXT NOT NULL)')

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def csv_issues(content):
 if not isinstance(content,str) or len(content.encode())>5*1024*1024:raise HTTPException(413,'Upload a CSV file no larger than 5 MB.')
 try:
  reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')),strict=True)
  if not reader.fieldnames:raise ValueError('The CSV is empty.')
  result=[]
  for number,row in enumerate(reader,2):
   if number>5001:raise ValueError('Import up to 5,000 issues at a time.')
   values={str(k).strip().casefold():str(v or '').strip() for k,v in row.items() if k is not None}
   title=values.get('title') or values.get('name') or values.get('summary') or values.get('issue')
   if not title:raise ValueError('Row '+str(number)+': a title, name or summary is required.')
   priority=values.get('priority','No priority') or 'No priority';priority={'0':'No priority','1':'Urgent','2':'High','3':'Medium','4':'Low'}.get(priority,priority.title())
   if priority=='No Priority':priority='No priority'
   result.append({'id':'row-'+str(number),'title':title,'description':values.get('description',''),'status':values.get('status') or ('Done' if values.get('completed','').lower()=='true' else 'Todo'),'priority':priority,'assignee':values.get('assignee') or None,'labels':[x.strip() for x in re.split('[,;]',values.get('labels',values.get('tags',''))) if x.strip()],'due_date':values.get('due date',values.get('due_date','')) or None,'source_row':number})
 except (csv.Error,ValueError) as error:raise HTTPException(422,str(error))
 if not result:raise HTTPException(422,'The CSV contains no issues.')
 return result

def source_snapshot(c,wid,selected):
 issues=[json.loads(r[0]) for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,)) if json.loads(r[0]).get('team','QQQ') in selected]
 projects={x.get('project') for x in issues if x.get('project')}
 return {'issues':issues,'projects':[json.loads(r[0]) for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='projects'",(wid,)) if json.loads(r[0])['id'] in projects]}

def install(app,auth,store,actor):
 with auth.connect() as c:migrate(c);c.commit()

 @app.get('/api/imports/sources')
 def sources(request:Request):
  a,w=actor(request);admin(w);result=[]
  with auth.connect() as c:
   for item in account_workspaces(auth,a):
    if item['id']==w['id'] or item['owner_id']!=a['account_id']:continue
    result.append({**item,'teams':teams(c,item['id'])})
  return result

 @app.get('/api/imports')
 def history(request:Request):
  a,w=actor(request);admin(w)
  with auth.connect() as c:return [dict(r) for r in c.execute('SELECT id,status,created_at,completed_at FROM linear_imports WHERE workspace_id=? ORDER BY created_at DESC',(w['id'],))]

 @app.post('/api/imports/preview')
 async def preview(request:Request):
  a,w=actor(request);admin(w);d=await request.json();source=d.get('source_workspace');mapping=d.get('teams',{});target=d.get('team','QQQ');users=d.get('users',{})
  if not isinstance(users,dict) or not isinstance(mapping,dict):raise HTTPException(422,'Choose teams and map users.')
  with auth.connect() as c:
   if source:
    src=c.execute('SELECT * FROM linear_workspaces WHERE id=? AND owner_id=?',(source,a['account_id'])).fetchone()
    if not src or source==w['id']:raise HTTPException(403,'Only the owner of a different source workspace can start this import.')
    if not mapping:raise HTTPException(422,'Select teams to import.')
    for old,new in mapping.items():validate_team(c,source,old);validate_team(c,w['id'],new)
    snapshot=source_snapshot(c,source,mapping)
   else:
    validate_team(c,w['id'],target);snapshot={'issues':csv_issues(d.get('csv')),'projects':[]}
   if len(snapshot['issues'])>5000:raise HTTPException(422,'Import up to 5,000 issues at a time.')
   valid_users={r[0] for r in c.execute('SELECT a.email_normalized FROM linear_members m JOIN local_auth_accounts a ON m.account_id=a.account_id WHERE m.workspace_id=?',(w['id'],))}
   if any(value is not None and value not in valid_users for value in users.values()):raise HTTPException(422,'Map users to members of the destination workspace.')
   warnings=[];normalized=[]
   for issue in snapshot['issues']:
    team=mapping[issue.get('team','QQQ')] if source else target
    states={x['title'] for x in store.list(w['id'],'workflow-states') if x.get('team','QQQ')==team}
    value={k:issue.get(k) for k in ('title','description','priority','due_date')};value['description']=value['description'] or '';value['priority']=value['priority'] or 'No priority';value.update(team=team,source_id=issue['id'],status=issue.get('status') or 'Todo',labels=issue.get('labels',[]))
    if value['status'] not in states:raise HTTPException(422,'Issue '+issue['id']+': status '+str(value['status'])+' does not exist in team '+team+'. Create or map the status before importing.')
    if value['priority'] not in ('No priority','Urgent','High','Medium','Low'):raise HTTPException(422,'Issue '+issue['id']+': invalid priority.')
    if value['due_date']:
     from datetime import date
     try:date.fromisoformat(value['due_date'])
     except (TypeError,ValueError):raise HTTPException(422,'Issue '+issue['id']+': use YYYY-MM-DD for due dates.')
    assignee=issue.get('assignee');value['assignee']=users.get(assignee,assignee if assignee in valid_users else None)
    if assignee and not value['assignee']:warnings.append({'issue':issue['id'],'message':'Assignee is not mapped; the imported issue will be unassigned.'})
    normalized.append(value)
   plan={'source':snapshot,'issues':normalized,'teams':mapping,'users':users,'target':target,'warnings':warnings};id='import_'+secrets.token_hex(12)
   c.execute('INSERT INTO linear_imports VALUES(?,?,?,?,?,?,?, ?,NULL,?)',(id,w['id'],a['account_id'],source,digest(snapshot),json.dumps(plan),'preview',int(time.time()),'[]'));c.commit()
  return {'id':id,'issues':normalized,'projects':len(snapshot['projects']),'source_users':{i['assignee']:users.get(i['assignee']) for i in snapshot['issues'] if i.get('assignee')},'warnings':warnings,'status':'preview'}

 @app.post('/api/imports/{id}/commit')
 def commit(id:str,request:Request):
  from issue_properties import prepare_issue,synchronize_issues
  a,w=actor(request);admin(w);now=int(time.time())
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM linear_imports WHERE id=? AND workspace_id=? AND account_id=?',(id,w['id'],a['account_id'])).fetchone()
   if not row:raise HTTPException(404,'Import preview not found.')
   if row['status']=='completed':return {'id':id,'status':'completed','records':len(json.loads(row['manifest']))}
   if row['status']!='preview' or now-row['created_at']>3600:raise HTTPException(409,'Create a new import preview before continuing.')
   plan=json.loads(row['plan']);source=row['source_workspace'];manifest=[]
   if source:
    src=c.execute('SELECT owner_id FROM linear_workspaces WHERE id=?',(source,)).fetchone()
    if not src or src['owner_id']!=a['account_id']:raise HTTPException(403,'You no longer own the source workspace.')
    if digest(source_snapshot(c,source,plan['teams']))!=row['source_digest']:raise HTTPException(409,'The source data changed. Create a new import preview.')
   def insert(kind,key,value):
    value['id']=key;value['import_id']=id;c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(w['id'],kind,key,json.dumps(value),now,now));manifest.append({'kind':kind,'id':key});return key
   # Copy project relationships using new local identities; never reuse source IDs.
   projects={p['id']:'project_'+secrets.token_hex(8) for p in plan['source']['projects']}
   for project in plan['source']['projects']:
    value={k:project.get(k) for k in ('title','description','summary','status','priority','start_date','target_date')};value.update(teams=list(dict.fromkeys(plan['teams'].values())),lead_team=next(iter(plan['teams'].values())),creator=a['email_normalized'],members=[],labels=[],dependencies=[projects[x] for x in project.get('dependencies',[]) if x in projects],milestones=[],activity=[])
    insert('projects',projects[project['id']],value)
   labels={json.loads(r[0])['title'] for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='labels'",(w['id'],))}
   ids={value['source_id']:next_issue_id(c,w['id'],value['team']) for value in plan['issues']};source_issues={i['id']:i for i in plan['source']['issues']}
   uploads={}
   def copy_upload(item):
    old=item.get('id')
    if old in uploads:return uploads[old]
    row=c.execute('SELECT * FROM linear_uploads WHERE id=? AND workspace_id=?',(old,source)).fetchone()
    if not row:raise HTTPException(409,'A source attachment is no longer available. Refresh the import preview.')
    key='upload_'+secrets.token_hex(16);c.execute('INSERT INTO linear_uploads VALUES(?,?,?,?,?,?,?,?,?)',(key,w['id'],row['filename'],row['mime'],row['size'],row['sha256'],now,row['render_type'],row['content']));manifest.append({'kind':'uploads','id':key})
    from uploads import metadata
    result=metadata({**dict(row),'id':key});uploads[old]=result;return result
   # Insert the entire issue set first so parent and blocker references resolve atomically.
   for value in plan['issues']:
    old=source_issues[value['source_id']];data={k:v for k,v in value.items() if k!='source_id'};data.update(creator=a['email_normalized'],comments=[],subissues=[],project=projects.get(old.get('project')),parent=ids.get(old.get('parent')),duplicate_of=ids.get(old.get('duplicate_of')),attachments=[copy_upload(x) for x in old.get('attachments',[])] if source else [])
    for field in ('blocked_by','blocks','related'):data[field]=[ids[x] for x in old.get(field,[]) if x in ids]
    for label in data['labels']:
     if label not in labels:insert('labels','label_'+secrets.token_hex(8),{'title':label,'description':''});labels.add(label)
    if source:
     for comment in old.get('comments',[]):
      data['comments'].append({**comment,'id':secrets.token_hex(12),'attachments':[copy_upload(x) for x in comment.get('attachments',[])]})
    insert('issues',ids[value['source_id']],data)
   for key in ids.values():
    value=json.loads(c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='issues' AND id=?",(w['id'],key)).fetchone()[0]);prepare_issue(c,w['id'],value,None,value,now);c.execute("UPDATE linear_records SET document=? WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(value),w['id'],key));store.collect_record_event(c,w['id'],'issues','create',value)
   synchronize_issues(store,c,w['id'],now)
   # Preserve the exact imported revision for safe undo after relationship normalization.
   for item in manifest:
    if item['kind']!='uploads':item['revision']=c.execute('SELECT revision FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(w['id'],item['kind'],item['id'])).fetchone()[0]
   c.execute("UPDATE linear_imports SET status='completed',completed_at=?,manifest=? WHERE id=?",(now,json.dumps(manifest),id));c.commit()
  return {'id':id,'status':'completed','issues':len(ids),'projects':len(projects),'records':len(manifest)}

 @app.delete('/api/imports/{id}')
 def undo(id:str,request:Request):
  a,w=actor(request);admin(w)
  with auth.connect() as c:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM linear_imports WHERE workspace_id=? AND id=?',(w['id'],id)).fetchone()
   if not row:raise HTTPException(404,'Import not found.')
   if row['status']=='undone':return {'status':'undone'}
   if row['status']!='completed' or time.time()-row['completed_at']>14*86400:raise HTTPException(409,'Only imports completed within 14 days can be deleted.')
   manifest=json.loads(row['manifest']);imported={(x['kind'],x['id']) for x in manifest}
   for item in manifest:
    if item['kind']=='uploads':continue
    record=c.execute('SELECT revision FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(w['id'],item['kind'],item['id'])).fetchone()
    if record and record[0]!=item['revision']:raise HTTPException(409,'Imported records have been edited. Remove or revert those changes before deleting this import.')
   # Refuse to erase objects which have since been attached to unrelated local work.
   ids={x['id'] for x in manifest};labels={json.loads(r[0])['title'] for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='labels'",(w['id'],)) if ('labels',json.loads(r[0])['id']) in imported}
   for record in c.execute('SELECT kind,id,document FROM linear_records WHERE workspace_id=?',(w['id'],)):
    if (record['kind'],record['id']) in imported:continue
    value=json.loads(record['document']);encoded=json.dumps(value)
    if any('"'+key+'"' in encoded or '/api/uploads/'+key in encoded for key in ids) or record['kind'] in ('issues','issue-templates','recurring-issues','drafts') and labels.intersection(value.get('labels',[])):raise HTTPException(409,'Other records now reference this import. Remove those references before deleting it.')
   for item in manifest:
    if item['kind']=='uploads':c.execute('DELETE FROM linear_uploads WHERE workspace_id=? AND id=?',(w['id'],item['id']))
    else:c.execute('DELETE FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(w['id'],item['kind'],item['id']))
   c.execute("UPDATE linear_imports SET status='undone' WHERE id=?",(id,));c.commit()
  return {'status':'undone'}
