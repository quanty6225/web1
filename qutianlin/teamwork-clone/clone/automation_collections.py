"""Source-observed collection operations for assignees, followers and tags."""
import json
import task_assignees
from fastapi import HTTPException
from automation_creation import people,allowed
MODES={'Change task assignees':['Add','Remove','Reassign'],'Change task followers':['Add','Remove','Replace with'],'Change task tags':['Add','Remove','Replace']}
PEOPLE_SOURCES=['Select people','Project owner','Task creator']

def values(value):
 if isinstance(value,str):return list(dict.fromkeys(x.strip() for x in value.split(',') if x.strip()))
 if not isinstance(value,list) or any(not isinstance(x,str) or not x.strip() for x in value):raise HTTPException(422,'Choose valid values.')
 return list(dict.fromkeys(value))

def validate(action):
 effect=action['effect']
 if effect not in MODES:return
 action.setdefault('mode','Add');action.setdefault('value_source','Choose tags' if effect=='Change task tags' else 'Select people');action.setdefault('remove_all',False)
 if action['mode'] not in MODES[effect]:raise HTTPException(422,'Choose a valid collection option.')
 if not isinstance(action['remove_all'],bool) or action['remove_all'] and action['mode']!='Remove':raise HTTPException(422,'Remove all is available only with Remove.')
 sources=['Choose tags'] if effect=='Change task tags' else PEOPLE_SOURCES
 if action['value_source'] not in sources:raise HTTPException(422,'Choose a valid value source.')
 action['value']=values(action.get('value',[]))
 if not action['remove_all'] and action['value_source'] in ['Select people','Choose tags'] and not action['value']:raise HTTPException(422,'Choose at least one value.')

def tag_names(c,who):
 result=set()
 for row in c.execute('SELECT tag FROM tw_tasks WHERE owner=?',(who,)):result.update(values(row['tag']))
 for row in c.execute("SELECT data FROM tw_records WHERE owner=? AND kind='tag'",(who,)):
  title=json.loads(row['data']).get('title')
  if title:result.add(title)
 return result

def validate_scope(c,who,action):
 effect=action['effect']
 if effect not in MODES or action.get('remove_all'):return
 if effect=='Change task tags':
  if any(v not in tag_names(c,who) for v in action['value']):raise HTTPException(422,'Choose tags in this workspace.')
 elif action['value_source']=='Select people':
  members=people(c,who);selected=[]
  for value in action['value']:
   matches=[p for p,d in members.items() if d['display_name']==value]
   ident=value if value in members else matches[0] if len(matches)==1 else None
   if ident is None:raise HTTPException(422,'Choose people in this workspace.')
   selected.append(ident)
  action['value']=list(dict.fromkeys(selected))

def combine(existing,selected,mode,remove_all):
 if remove_all:return []
 if mode=='Add':return list(dict.fromkeys(existing+selected))
 if mode=='Remove':return [v for v in existing if v not in selected]
 return list(selected)

def execute(c,who,target,action,trigger):
 action=dict(action)
 try:validate(action);validate_scope(c,who,action)
 except HTTPException:return False
 effect=action['effect'];mode=action.get('mode','Add');remove_all=action.get('remove_all',False);options=json.loads(target['options']);selected=[] if remove_all else values(action.get('value',[]))
 if effect=='Change task tags':
  if any(v not in tag_names(c,who) for v in selected):return False
  tags=combine(values(target['tag']),selected,mode,remove_all);c.execute('UPDATE tw_tasks SET tag=? WHERE owner=? AND id=?',(', '.join(tags),who,target['id']));return True
 members=people(c,who);source=action.get('value_source','Select people')
 if source=='Task creator':selected=[json.loads(trigger.get('options','{}')).get('created_by')]
 elif source=='Project owner':
  config=c.execute("SELECT data FROM tw_records WHERE owner=? AND parent=? AND kind='project_configuration' ORDER BY created DESC LIMIT 1",(who,trigger['project_id'])).fetchone();selected=[json.loads(config['data']).get('project_owner')] if config else []
 if not remove_all:
  if not selected or any(p not in members or not allowed(c,who,p,target['project_id'],options) for p in selected):return False
 if effect=='Change task assignees':
  current,labels=task_assignees.identity(target,members);updated=combine(current,selected,mode,remove_all);task_assignees.store(c,who,target['id'],updated,labels if mode in ['Add','Remove'] and not remove_all else [])
 else:
  # Normalize uniquely-resolvable legacy display-name followers to account IDs.
  current=[]
  for value in options.get('followers',[]):
   matches=[p for p,d in members.items() if d['display_name']==value];current.append(matches[0] if value not in members and len(matches)==1 else value)
  options['followers']=combine(current,selected,mode,remove_all);c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(options),who,target['id']))
 return True
