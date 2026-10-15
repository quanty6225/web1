"""Source-observed trigger filters, evaluated against the actual triggering change."""
import json
from fastapi import HTTPException

CONTENT_TRIGGERS={'Task name changes':'title','Task description changes':'description','Task comment added':'text'}

def validate(rule):
 trigger=rule['trigger']
 if trigger in CONTENT_TRIGGERS:
  phrases=rule.get('contains',[])
  if isinstance(phrases,str):phrases=[p.strip() for p in phrases.splitlines() if p.strip()]
  if not isinstance(phrases,list) or len(phrases)>50 or any(not isinstance(p,str) or not p.strip() or len(p)>500 for p in phrases):raise HTTPException(422,'Enter valid text options.')
  rule['contains']=phrases
 if trigger=='Task priority changes':
  for key in ['from_value','to_value']:
   rule.setdefault(key,'Any')
   if rule[key] not in ['Any','None','Low','Medium','High']:raise HTTPException(422,'Choose a valid priority filter.')
 if trigger=='Task list changes' and not str(rule.get('task_list','')).strip():raise HTTPException(422,'Choose a task list.')
 if trigger=='Task comment added':
  if not isinstance(rule.get('authors',[]),list) or any(not isinstance(v,str) for v in rule.get('authors',[])):raise HTTPException(422,'Choose valid comment authors.')
 if trigger=='Task time logged':
  if not isinstance(rule.get('billable_only',False),bool):raise HTTPException(422,'Choose a valid billable option.')

def validate_scope(c,who,rule):
 if rule['trigger']=='Task comment added':
  for person in rule.get('authors',[]):
   if not c.execute('SELECT 1 FROM local_auth_accounts WHERE account_id=? AND (account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?))',(person,who,who)).fetchone():raise HTTPException(422,'Choose a comment author in this workspace.')
 if rule['trigger']=='Task list changes':
  parent=rule.get('parent','')
  selected=rule.get('task_list_project') or parent
  if selected and parent and selected!=parent:raise HTTPException(422,'Choose a task list in the selected project.')
  tasks=c.execute('SELECT project_id,list_name FROM tw_tasks WHERE owner=?',(who,)).fetchall()
  records=c.execute("SELECT parent,data FROM tw_records WHERE owner=? AND kind='list'",(who,)).fetchall()
  projects={r['project_id'] for r in tasks if r['list_name']==rule['task_list']}|{r['parent'] for r in records if json.loads(r['data']).get('title')==rule['task_list']}
  if selected:
   if selected not in projects:raise HTTPException(422,'Choose a task list in the selected project.')
  elif len(projects)==1:selected=next(iter(projects))
  else:raise HTTPException(422,'Choose a task list and its project.')
  rule['task_list_project']=selected

def matches(rule,task,previous,actor):
 trigger=rule['trigger'];previous=previous or {}
 if trigger in CONTENT_TRIGGERS:
  # Comment payload is supplied directly by its insertion transaction. Looking
  # up the latest comment could accidentally match another automation's output.
  text=previous.get('event_record',{}).get('text','') if trigger=='Task comment added' else task.get(CONTENT_TRIGGERS[trigger],'')
  phrases=rule.get('contains',[])
  if phrases and not any(p.casefold() in str(text).casefold() for p in phrases):return False
 if trigger=='Task priority changes':
  if rule.get('from_value','Any')!='Any' and previous.get('priority')!=rule['from_value']:return False
  if rule.get('to_value','Any')!='Any' and task.get('priority')!=rule['to_value']:return False
 if trigger=='Task list changes' and (task['list_name']!=rule.get('task_list') or rule.get('task_list_project') and task['project_id']!=rule['task_list_project']):return False
 if trigger=='Task comment added' and rule.get('authors') and actor not in rule['authors']:return False
 if trigger=='Task time logged' and rule.get('billable_only') and not previous.get('event_record',{}).get('billable'):return False
 return True
