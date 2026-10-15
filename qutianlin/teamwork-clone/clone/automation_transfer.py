"""Move/copy automation targets to an existing list in an owned project."""
import json,secrets
import task_assignees
from fastapi import HTTPException
EFFECTS={'Move to task list','Copy to task list'}

def lists(c,who,project):
 names={r['list_name'] for r in c.execute('SELECT list_name FROM tw_tasks WHERE owner=? AND project_id=?',(who,project))};inactive=set()
 for row in c.execute("SELECT data FROM tw_records WHERE owner=? AND parent=? AND kind='list'",(who,project)):
  d=json.loads(row['data'])
  if d.get('archived') or d.get('status') in ['Archived','Completed']:inactive.add(d.get('title'))
  else:names.add(d.get('title'))
 return names-inactive-{None,''}

def validate(c,who,action,parent=''):
 if action['effect'] not in EFFECTS:return
 project=action.get('project_id') or parent;name=action.get('list_name') or action.get('value')
 if not isinstance(project,str) or not project or not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,project)).fetchone():raise HTTPException(422,'Choose a destination project in this workspace.')
 if not isinstance(name,str) or name not in lists(c,who,project):raise HTTPException(422,'Choose an active task list in the destination project.')
 action.update(project_id=project,list_name=name,value=name)

def execute(c,who,task,action,rule_id):
 try:validate(c,who,action,task['project_id'])
 except HTTPException:return None
 source=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,task['id'])).fetchone()
 if not source:return None
 source=dict(source);source_id=source['id'];project=action['project_id'];name=action['list_name'];copy=action['effect']=='Copy to task list'
 if not copy and source['project_id']==project and source['list_name']==name:return source['id']
 rows=[];queue=[source];seen=set();privacy={}
 while queue:
  row=queue.pop(0)
  if row['id'] in seen:continue
  seen.add(row['id']);opts=json.loads(row['options'])
  private_actor=opts.get('privacy_actor') if opts.get('privacy')=='Only me' else privacy.get(row.get('parent_id'))
  if private_actor:
   if private_actor!=who:return None
   privacy[row['id']]=private_actor;opts.update(privacy='Only me',privacy_actor=private_actor);row['options']=json.dumps(opts)
  rows.append(row);queue.extend(dict(r) for r in c.execute('SELECT * FROM tw_tasks WHERE owner=? AND project_id=? AND parent_id=?',(who,source['project_id'],row['id'])))
 ids={r['id']:secrets.token_hex(12) if copy else r['id'] for r in rows}
 for row in rows:
  original=row['id'];row.update(id=ids[original],project_id=project,list_name=name,parent_id=ids.get(row['parent_id'],''))
  if copy:
   options=task_assignees.canonical_options(c,who,row);options.pop('repeat_next_id',None);options.update(automation_id=rule_id,created_by=who);options['dependencies']=[ids.get(i,i) for i in options.get('dependencies',[])];row['options']=json.dumps(options);columns=list(row);c.execute('INSERT INTO tw_tasks('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
  else:c.execute('UPDATE tw_tasks SET project_id=?,list_name=?,parent_id=?,options=? WHERE owner=? AND id=?',(project,name,row['parent_id'],row['options'],who,original))
 return ids[source_id]
