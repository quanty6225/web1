import task_assignees
"""Validated automation predicates over records in the rule owner's workspace."""
import json
from datetime import date
from pathlib import Path
from fastapi import HTTPException
CATALOG=json.loads(Path(__file__).with_name('automation-conditions.json').read_text())
MODELS={row['name']:row for row in CATALOG}
NO_VALUE={'is set','is not set','is added','is not added','has passed','has not passed','has any comments','has no comments','has any attachments'}
PEOPLE={'Assignee','Follower','Trigger user','Created by'}
def sequence(value):
 if value is None:return []
 if isinstance(value,list):return [str(x).strip() for x in value if str(x).strip()]
 return [v.strip() for v in str(value).split(',') if v.strip()]
def validate(conditions):
 if not isinstance(conditions,list) or len(conditions)>30:raise HTTPException(422,'Use up to 30 automation conditions.')
 for condition in conditions:
  if not isinstance(condition,dict) or condition.get('field') not in MODELS:raise HTTPException(422,'Choose a condition.')
  model=MODELS[condition['field']];operator=condition.setdefault('operator',model['operators'][0]);value=condition.get('value');kind=model['kind']
  if operator not in model['operators']:raise HTTPException(422,'Choose a valid condition operator.')
  if operator in NO_VALUE:continue
  if kind in ['set','person','text'] or kind=='comments' and operator in ['any contains text','last contains text','has comments from']:
   if not isinstance(value,(str,list)) or not sequence(value) or isinstance(value,list) and any(not isinstance(v,str) or len(v)>4000 for v in value):raise HTTPException(422,'Enter a condition value.')
   if kind=='person' and len(sequence(value))!=1:raise HTTPException(422,'Choose one creator.')
  elif kind=='number' or kind=='comments' and operator in ['has more than','has less than']:
   try:number=float(value)
   except (ValueError,TypeError):raise HTTPException(422,'Enter a numeric condition value.')
   if not 0<=number<=1000000:raise HTTPException(422,'Enter a valid condition value.')
   condition['value']=number
  elif kind=='date':
   try:date.fromisoformat(value)
   except (ValueError,TypeError):raise HTTPException(422,'Choose a valid condition date.')
  elif kind=='boolean':
   if not isinstance(value,bool):raise HTTPException(422,'Choose True or False.')
  elif kind=='custom':
   if not isinstance(condition.get('custom_field'),str) or not condition['custom_field']:raise HTTPException(422,'Choose a custom field.')
   if not isinstance(value,(str,float,int,bool)) or isinstance(value,str) and len(value)>4000:raise HTTPException(422,'Enter a custom field condition value.')
 return conditions
def validate_scope(c,who,conditions,project):
 for condition in conditions:
  name=condition['field'];operator=condition['operator'];value=condition.get('value')
  if name in ['Task list','Stage'] and not project:raise HTTPException(422,'Select one project for a task list or stage condition.')
  if name in PEOPLE or name=='Comments' and operator=='has comments from':
   if operator in NO_VALUE:continue
   people={r['account_id'] for r in c.execute('SELECT account_id FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(who,who))}
   if any(v not in people for v in sequence(value)):raise HTTPException(422,'Choose people in this workspace.')
  if name=='Priority' and operator not in NO_VALUE and any(v not in ['None','Low','Medium','High'] for v in sequence(value)):raise HTTPException(422,'Choose valid priorities.')
  if name=='Custom field':
   row=c.execute("SELECT data FROM tw_records WHERE owner=? AND id=? AND kind='customfield'",(who,condition['custom_field'])).fetchone()
   if not row or json.loads(row['data']).get('entity')!='Task':raise HTTPException(422,'Choose a task custom field in this workspace.')
def compare(actual,operator,expected=None):
 present=actual is not None and actual!='' and actual!=[] and actual!=set()
 if operator in ['is set','is added']:return present
 if operator in ['is not set','is not added']:return not present
 if operator in ['has passed','has not passed']:
  if not actual:return False
  passed=actual<date.today().isoformat();return passed if operator=='has passed' else not passed
 if operator=='Contains':return any(v.casefold() in str(actual or '').casefold() for v in sequence(expected))
 if operator in ['is any of','is all of','is not any of','is not all of']:
  have=set(sequence(actual));want=set(sequence(expected));result=bool(have&want) if 'any' in operator else want<=have
  return not result if 'not' in operator else result
 if operator=='is equal to':return actual==expected
 if operator=='is not equal to':return actual!=expected
 if not present:return False
 try:
  if operator=='is less than':return actual<expected
  if operator=='is greater than':return actual>expected
  if operator=='is less than or equal to':return actual<=expected
  if operator=='is greater than or equal to':return actual>=expected
 except TypeError:return False
 return False
def matches(c,who,task,conditions,actor):
 if not conditions:return True
 opts=json.loads(task.get('options','{}')) if isinstance(task.get('options','{}'),str) else task['options']
 people=[dict(r) for r in c.execute('SELECT account_id,display_name FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(who,who))]
 def people_ids(value):
  values=sequence(value);return list({r['account_id'] for r in people if r['account_id'] in values or r['display_name'] in values})
 records=[{**dict(r),'data':json.loads(r['data'])} for r in c.execute('SELECT id,kind,data,created FROM tw_records WHERE owner=? AND parent=? ORDER BY created,rowid',(who,task['id']))]
 for condition in conditions:
  name=condition['field'];operator=condition['operator'];expected=condition.get('value');actual=None
  if name=='Assignee':actual=task_assignees.assigned_ids(c,who,task)
  elif name=='Follower':actual=people_ids(opts.get('followers',[]))
  elif name=='Trigger user':actual=[actor] if actor else []
  elif name=='Created by':actual=opts.get('created_by') or who;expected=sequence(expected)[0]
  elif name=='Priority':actual=(None if task['priority']=='None' else task['priority']) if operator in NO_VALUE else [task['priority']]
  elif name=='Tag':actual=sequence(task['tag'])
  elif name=='Task list':actual=[task['list_name']] if task['list_name'] else []
  elif name=='Stage':actual=[task['stage']] if task['stage'] else []
  elif name=='Progress':actual=opts.get('progress',0)
  elif name=='Time estimate':actual=(task['estimate'] or None) if operator in NO_VALUE else task['estimate']
  elif name=='Logged time':
   logs=[r for r in records if r['kind']=='time'];actual=sum(r['data'].get('minutes',0) for r in logs) if logs or operator not in NO_VALUE else None
  elif name in ['Start date','Due date']:actual=task['start_date' if name=='Start date' else 'due_date'] or None
  elif name in ['Task name','Task description','Task list name']:actual=task[{'Task name':'title','Task description':'description','Task list name':'list_name'}[name]]
  elif name=='Project name':
   project=c.execute('SELECT name FROM tw_projects WHERE owner=? AND id=?',(who,task['project_id'])).fetchone();actual=project['name'] if project else ''
  elif name=='Is blocked':
   dependencies=opts.get('dependencies',[]);actual=any(not row['completed'] for row in c.execute('SELECT id,completed FROM tw_tasks WHERE owner=?',(who,)) if row['id'] in dependencies)
  elif name=='Is completed':actual=bool(task['completed'])
  elif name=='Is subtask':actual=bool(task['parent_id'])
  elif name=='Has Desk tickets':actual=bool(opts.get('desk_tickets',[]))
  elif name=='Has reminders':actual=bool(c.execute('SELECT 1 FROM tw_reminders WHERE workspace_owner=? AND task=? AND sent=0',(who,task['id'])).fetchone())
  elif name=='Comments':
   comments=[r for r in records if r['kind']=='comment']
   if operator in ['any contains text','last contains text']:
    chosen=comments[-1:] if operator=='last contains text' else comments
    if not any(compare(r['data'].get('text',''),'Contains',expected) for r in chosen):return False
   elif operator=='has any comments' and not comments:return False
   elif operator=='has no comments' and comments:return False
   elif operator=='has more than' and not len(comments)>expected:return False
   elif operator=='has less than' and not len(comments)<expected:return False
   elif operator=='has comments from' and not any(set(people_ids(r['data'].get('actor') or r['data'].get('author')))&set(sequence(expected)) for r in comments):return False
   continue
  elif name=='Attachments':
   if not any(r['kind']=='file' for r in records):return False
   continue
  elif name=='Custom field':
   row=c.execute("SELECT data FROM tw_records WHERE owner=? AND id=? AND kind='customfield'",(who,condition['custom_field'])).fetchone()
   if not row:return False
   field=json.loads(row['data']);actual=opts.get('custom_fields',{}).get(field.get('title'))
   if field.get('project_specific') and task['project_id']!=field.get('project_id'):return False
   if field.get('type') in ['Number','Decimal number','Currency']:
    try:actual=float(actual);expected=float(expected)
    except (ValueError,TypeError):return False
  if not compare(actual,operator,expected):return False
 return True
