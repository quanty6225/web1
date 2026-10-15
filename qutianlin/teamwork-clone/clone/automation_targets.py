"""Related-task targets observed in the source automation action menu."""
import json
from fastapi import HTTPException
PREVIOUS='Previous created task'
CREATORS=['Add task','Add subtask','Copy to task list']
TARGETS=['Trigger task','Parent task','Subtasks',PREVIOUS]
EFFECTS=['Add task comment','Change task followers','Change task assignees','Move task to stage','Move to task list','Change task start date','Change task due date','Change task tags','Complete task','Change task estimated time','Change task priority','Update task name','Update task description','Change task progress','Set task custom field','Uncomplete task']

def validate(action,earlier=()):
 target=action.get('target','Trigger task')
 if target not in TARGETS:raise HTTPException(422,'Choose a valid action target.')
 if action['effect'] not in EFFECTS and target!='Trigger task':raise HTTPException(422,'This action uses its own target selection.')
 if target==PREVIOUS and not any(a.get('effect') in CREATORS for a in earlier):raise HTTPException(422,'Add a task-creation action before choosing Previous created task.')
 action['target']=target

def resolve(c,who,trigger,action,previous_created=None):
 if action.get('target')==PREVIOUS:
  if not previous_created:return []
  row=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,previous_created)).fetchone()
  if not row:return []
  row=dict(row);options=json.loads(row['options'])
  if options.get('privacy')=='Only me' and options.get('privacy_actor')!=who:return []
  return [row]
 # Earlier actions may have moved the trigger and its subtree to another project.
 if trigger.get('id'):
  current=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,trigger['id'])).fetchone()
  if not current:return []
  trigger=dict(current)
 if action['effect'] not in EFFECTS:return [trigger]
 project=trigger.get('project_id');target=action.get('target','Trigger task')
 def accessible(ident):
  row=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=? AND project_id=?',(who,ident,project)).fetchone()
  if not row:return None
  row=dict(row);options=json.loads(row['options'])
  if options.get('privacy')=='Only me' and options.get('privacy_actor')!=who:return None
  return row
 if target!='Subtasks':
  row=accessible(trigger.get('parent_id') if target=='Parent task' else trigger['id'])
  return [row] if row else []
 # A visited set also makes imported malformed parent cycles harmless.
 result=[];pending=[trigger['id']];seen=set(pending)
 while pending:
  parent=pending.pop(0)
  for row in c.execute('SELECT id FROM tw_tasks WHERE owner=? AND project_id=? AND parent_id=? ORDER BY rowid',(who,project,parent)).fetchall():
   ident=row['id']
   if ident in seen:continue
   seen.add(ident);task=accessible(ident)
   if task:result.append(task);pending.append(ident)
 return result
