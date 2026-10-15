"""Creation and explicit-target actions shared by task and daily automations."""
import json,secrets,time
import task_assignees
from datetime import date,timedelta
from fastapi import HTTPException
from settings_local import DEFAULTS

CREATION={'Add task','Add subtask','Add milestone','Create project'}
DAILY=['Add task','Add subtask','Log task time','Add milestone','Create project','Notify people','Send HTTP request','Send Chat message to channel','Send Slack message to channel','Notify team in Channel','Notify in Teams Chat']

def validate(action,daily=False):
 effect=action['effect']
 if effect not in CREATION and effect!='Log task time':return
 if effect in CREATION and (not isinstance(action.get('value'),str) or not action['value'].strip()):raise HTTPException(422,'Enter a name for the new item.')
 for key in ['start_date','due_date']:
  if action.get(key):
   try:date.fromisoformat(action[key])
   except (ValueError,TypeError):raise HTTPException(422,'Choose a valid action date.')
 if effect=='Add milestone' and not action.get('due_date'):raise HTTPException(422,'Choose the milestone due date.')
 if effect=='Add milestone' and not action.get('project_id'):raise HTTPException(422,'Choose the milestone project.')
 if effect in ['Add task','Add subtask']:
  if action.get('priority','None') not in ['None','Low','Medium','High']:raise HTTPException(422,'Choose a valid task priority.')
  try:action['estimate']=int(action.get('estimate',0))
  except (ValueError,TypeError):raise HTTPException(422,'Enter estimated minutes.')
  if action['estimate']<0:raise HTTPException(422,'Estimated time cannot be negative.')
 for key in ['assignees','followers','task_lists']:
  if not isinstance(action.get(key,[]),list) or any(not isinstance(v,str) for v in action.get(key,[])):raise HTTPException(422,'Choose valid '+key+'.')
 for key in ['project_id','parent_task','task_id','project_template','workflow_id','project_owner','tracked_for']:
  if action.get(key) is not None and not isinstance(action[key],str):raise HTTPException(422,'Choose a valid action target.')
 if daily and effect in ['Add task','Add milestone'] and not action.get('project_id'):raise HTTPException(422,'Choose an action project.')
 if daily and effect=='Add task' and not action.get('list_name'):raise HTTPException(422,'Choose the task list.')
 if daily and effect=='Add subtask' and not action.get('parent_task'):raise HTTPException(422,'Choose the parent task.')
 if daily and effect=='Log task time' and not action.get('task_id'):raise HTTPException(422,'Choose a task to log time on.')
 if effect=='Create project' and action.get('project_type','Confirmed') not in ['Confirmed','Tentative']:raise HTTPException(422,'Choose a project type.')

def target_task(c,who,tid):
 row=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone()
 if not row:raise HTTPException(422,'Choose a task in this workspace.')
 row=dict(row);options=json.loads(row['options'])
 if options.get('privacy')=='Only me' and options.get('privacy_actor')!=who:raise HTTPException(422,'Choose an accessible task.')
 return row

def people(c,who):return {r['account_id']:dict(r) for r in c.execute('SELECT account_id,display_name,email_normalized FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(who,who))}

def validate_scope(c,who,action):
 if action['effect'] not in CREATION and action['effect']!='Log task time':return
 if action.get('project_id') and not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,action['project_id'])).fetchone():raise HTTPException(422,'Choose a project in this workspace.')
 for key in ['parent_task','task_id']:
  if action.get(key):target_task(c,who,action[key])
 for key,kind in [('project_template','template'),('workflow_id','workflow')]:
  if action.get(key):
   row=c.execute('SELECT data FROM tw_records WHERE owner=? AND id=? AND kind=?',(who,action[key],kind)).fetchone()
   if not row or json.loads(row['data']).get('private_actor') not in [None,who]:raise HTTPException(422,'Choose an available '+kind+'.')
   if key=='project_template':
    entries=json.loads(row['data']).get('tasks',[])
    if not isinstance(entries,list):raise HTTPException(422,'Choose a valid project template.')
    for task in entries:
     if not isinstance(task,dict):raise HTTPException(422,'Choose a valid project template.')
     validate(dict(task,effect='Add task',value=task.get('title')))
 if action.get('project_id'):
  project=action['project_id'];lists={r['list_name'] for r in c.execute('SELECT list_name FROM tw_tasks WHERE owner=? AND project_id=?',(who,project))}|{json.loads(r['data']).get('title') for r in c.execute("SELECT data FROM tw_records WHERE owner=? AND parent=? AND kind='list'",(who,project))}
  if action.get('list_name') and action['list_name'] not in lists or any(name not in lists for name in action.get('task_lists',[])):raise HTTPException(422,'Choose task lists in the selected project.')
 members=people(c,who)
 ids=action.get('assignees',[])+action.get('followers',[])+[action[k] for k in ['project_owner','tracked_for'] if action.get(k)]
 if any(ident not in members for ident in ids):raise HTTPException(422,'Choose people in this workspace.')

def allowed(c,who,person,project,options=None):
 if options and options.get('privacy')=='Only me' and options.get('privacy_actor')!=person:return False
 if person==who:return True
 policy=c.execute('SELECT permissions,projects FROM tw_member_policies WHERE workspace_owner=? AND account=?',(who,person)).fetchone()
 if not policy:return False
 permissions=json.loads(policy['permissions'])
 return project in json.loads(policy['projects']) and (permissions.get('Project Administrator') or permissions.get('View Tasks & Milestones'))

def insert(c,who,kind,parent,data,rid):
 ident=secrets.token_hex(12);data={**data,'automation_id':rid};c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(ident,who,kind,parent,json.dumps(data),time.time()));return ident

def notify(c,who,person,parent,title,message,rid):
 member=people(c,who).get(person)
 if not member:return
 insert(c,who,'notification',parent,{'title':title,'text':message,'private_actor':person},rid)
 c.execute('INSERT INTO tw_automation_mail(id,owner,recipient,title,message) VALUES(?,?,?,?,?)',(secrets.token_hex(12),who,member['email_normalized'],title,message))

def execute(c,who,trigger_task,action,rid,actor=None):
 effect=action['effect'];value=action.get('value');members=people(c,who)
 try:validate_scope(c,who,action)
 except HTTPException:return None
 if effect=='Create project':
  pid=secrets.token_hex(12);c.execute('INSERT INTO tw_projects(id,owner,name,description) VALUES(?,?,?,?)',(pid,who,value,action.get('description','')))
  settings={**DEFAULTS,**{r['key']:json.loads(r['value']) for r in c.execute('SELECT key,value FROM tw_settings WHERE owner=?',(who,))}}
  for title in settings['default_task_lists']:insert(c,who,'list',pid,{'title':title},rid)
  insert(c,who,'preference',pid,{'title':'Project category defaults',**{k:v for k,v in settings.items() if k.endswith('_categories')}},rid)
  insert(c,who,'project_configuration',pid,{k:action.get(k) for k in ['project_type','project_owner','workflow_id','project_template','tags','skip_weekends','billable']},rid)
  selected_owner=action.get('project_owner')
  if selected_owner and selected_owner!=who:
   policy=c.execute('SELECT projects FROM tw_member_policies WHERE workspace_owner=? AND account=?',(who,selected_owner)).fetchone()
   if policy:c.execute('UPDATE tw_member_policies SET projects=? WHERE workspace_owner=? AND account=?',(json.dumps(list(dict.fromkeys([*json.loads(policy['projects']),pid]))),who,selected_owner))
  if action.get('workflow_id'):
   workflow=json.loads(c.execute('SELECT data FROM tw_records WHERE owner=? AND id=?',(who,action['workflow_id'])).fetchone()['data'])
   for stage in workflow.get('stages',[]):insert(c,who,'stage',pid,{'title':stage},rid)
  if action.get('project_template'):
   template=json.loads(c.execute('SELECT data FROM tw_records WHERE owner=? AND id=?',(who,action['project_template'])).fetchone()['data'])
   for task in template.get('tasks',[]):
    task=dict(task)
    if action.get('skip_weekends'):
     for key in ['start_date','due_date']:
      if task.get(key):
       value_date=date.fromisoformat(task[key])
       while value_date.weekday()>=5:value_date+=timedelta(days=1)
       task[key]=value_date.isoformat()
    list_name=task.get('list_name') or (settings['default_task_lists'][0] if settings['default_task_lists'] else 'My List')
    if not c.execute("SELECT 1 FROM tw_records WHERE owner=? AND parent=? AND kind='list' AND json_extract(data,'$.title')=?",(who,pid,list_name)).fetchone():insert(c,who,'list',pid,{'title':list_name},rid)
    execute(c,who,{},dict(task,effect='Add task',value=task.get('title',''),project_id=pid,list_name=list_name),rid,actor)
  return pid
 target=trigger_task or {}
 if effect=='Add subtask' and action.get('parent_task'):target=target_task(c,who,action['parent_task'])
 if effect=='Log task time' and action.get('task_id'):target=target_task(c,who,action['task_id'])
 project=target.get('project_id','') if effect in ['Add subtask','Log task time'] else action.get('project_id') or target.get('project_id','')
 if not project or not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,project)).fetchone():return None
 options=json.loads(target.get('options','{}'))
 recipients=list(dict.fromkeys(action.get('assignees',[])+action.get('followers',[])))
 if any(not allowed(c,who,p,project,options if effect=='Add subtask' else None) for p in recipients):return None
 if effect=='Log task time':
  person=action.get('tracked_for') or actor or who
  if not target.get('id') or not allowed(c,who,person,project,options):return None
  return insert(c,who,'time',target['id'],{'minutes':int(value),'billable':bool(action.get('billable',False)),'date':date.today().isoformat(),'actor':person,'description':action.get('description',''),'tags':action.get('tags','')},rid)
 if effect=='Add milestone':
  ident=insert(c,who,'milestone',project,{'title':value,'due_date':action['due_date'],'description':action.get('description',''),'task_lists':action.get('task_lists',[]),'tags':action.get('tags',''),'assignees':action.get('assignees',[]),'followers':action.get('followers',[])},rid)
 else:
  if effect=='Add subtask' and not target.get('id'):return None
  ident=secrets.token_hex(12);new_options={'created_by':who,'automation_id':rid,'followers':action.get('followers',[]),'assignee_ids':action.get('assignees',[]),'assignee_labels':[]}
  if effect=='Add subtask' and options.get('privacy')=='Only me':new_options.update(privacy='Only me',privacy_actor=options['privacy_actor'])
  c.execute('INSERT INTO tw_tasks(id,owner,project_id,title,description,priority,tag,start_date,due_date,list_name,assignee,estimate,options,parent_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,who,project,value,action.get('description',''),action.get('priority','None'),action.get('tags',''),action.get('start_date') or None,action.get('due_date') or None,action.get('list_name') or target.get('list_name') or 'My List',', '.join(members[p]['display_name'] for p in action.get('assignees',[])),action.get('estimate',0),json.dumps(new_options),target.get('id','') if effect=='Add subtask' else ''))
 if action.get('notify'):
  for person in recipients:notify(c,who,person,ident if effect!='Add milestone' else project,'New '+('milestone' if effect=='Add milestone' else 'task')+': '+value,action.get('description') or value,rid)
 return ident
