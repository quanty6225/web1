"""Workspace-scoped task automations, scheduled triggers and local notification mail."""
import json,logging,os,re,secrets,smtplib,threading,time
import task_assignees
import automation_connections as connections
import automation_http as http_actions
import chat_local as chat_actions
from datetime import date,datetime,timedelta,timezone
from email.message import EmailMessage
from fastapi import HTTPException,Request
from automation_conditions import CATALOG as CONDITIONS,validate as validate_conditions,validate_scope as validate_condition_scope,matches as conditions_match
from automation_events import validate as validate_event,validate_scope as validate_event_scope,matches as event_matches
from automation_fields import validate as validate_custom_field,apply as apply_custom_field,TYPES as FIELD_TYPES,CURRENCIES
from automation_collections import MODES as COLLECTION_MODES,PEOPLE_SOURCES,validate as validate_collection,validate_scope as validate_collection_scope,execute as execute_collection,tag_names
from automation_transfer import EFFECTS as TRANSFER_EFFECTS,validate as validate_transfer,execute as execute_transfer
from automation_targets import TARGETS,CREATORS as TASK_CREATORS,EFFECTS as TARGET_EFFECTS,validate as validate_target,resolve as resolve_targets
from automation_creation import CREATION,DAILY,validate as validate_creation,validate_scope as validate_creation_scope,execute as execute_creation
TRIGGERS=['Task added','Task completed','Task stage changes','Task tag added','Task tag removed','Task custom field changes','Task estimated time exceeds','Task logged time exceeds estimated','Task time logged','Task assignee added','Task assignee removed','Task due date changes','Task due date arrives','Task start date arrives','Task start date changes','Task progress exceeds','Task priority changes','Task comment added']
EFFECTS=['Notify people','Change task assignees','Move to task list','Copy to task list','Add task','Add subtask','Change task priority','Log task time','Change task tags','Change task estimated time','Change task followers','Change task start date','Change task due date','Change task progress','Add tasks from template','Move task to stage','Complete task','Add task comment']
TRIGGER_ALIASES={'Priority changed':'Task priority changes'}
TRIGGERS += ['Task list changes','Task name changes','Task updated','Task description changes','Task unblocked','Task inactive','Every day']
EFFECTS += ['Update task name','Update task description','Uncomplete task','Set task custom field','Add milestone','Create project']
TRIGGERS += list(connections.TRIGGERS)
EFFECTS += list(connections.EFFECTS)+[http_actions.EFFECT,chat_actions.EFFECT]
EFFECT_ALIASES={'Add a comment':'Add task comment','Assign task':'Change task assignees','Move to Done':'Move task to stage'}

def integer(value,label,minimum=0,maximum=1000000):
 try:n=int(value)
 except (ValueError,TypeError):raise HTTPException(422,'Enter valid '+label+'.')
 if not minimum<=n<=maximum:raise HTTPException(422,'Enter valid '+label+'.')
 return n

def validate(rule):
 rule['conditions']=validate_conditions(rule.get('conditions',[]))
 rule['trigger']=TRIGGER_ALIASES.get(rule.get('trigger'),rule.get('trigger'))
 if rule['trigger'] not in TRIGGERS:raise HTTPException(422,'Select an automation trigger.')
 validate_event(rule)
 if rule['trigger'] in ['Task comment added','Every day','Deal stage changes'] and rule['conditions']:raise HTTPException(422,'This trigger does not support additional conditions.')
 actions=rule.get('actions')
 if actions is None:actions=[{'effect':rule.get('effect'),'value':rule.get('value','')}]
 if not isinstance(actions,list) or not 1<=len(actions)<=5:raise HTTPException(422,'Add between one and five actions.')
 for action_index,action in enumerate(actions):
  if not isinstance(action,dict):raise HTTPException(422,'Choose an action.')
  original=action.get('effect');action['effect']=EFFECT_ALIASES.get(original,original)
  if original=='Move to Done':action['value']='Done'
  effect=action['effect'];value=action.get('value','')
  if effect not in EFFECTS:raise HTTPException(422,'Select an automation action.')
  if rule['trigger'] in connections.COMPATIBLE and effect not in connections.COMPATIBLE[rule['trigger']]:raise HTTPException(422,'Choose an action compatible with this trigger.')
  if rule['trigger']=='Every day' and effect not in DAILY:raise HTTPException(422,'Choose an action compatible with Every day.')
  validate_creation(action,rule['trigger']=='Every day')
  validate_target(action,actions[:action_index])
  validate_collection(action)
  http_actions.validate(action)
  chat_actions.validate_action(action)
  if effect in COLLECTION_MODES or effect in connections.EFFECTS or effect in [http_actions.EFFECT,chat_actions.EFFECT]:pass
  elif effect in ['Log task time','Change task estimated time','Change task progress']:action['value']=integer(value,'minutes' if effect!='Change task progress' else 'progress',1 if effect=='Log task time' else 0,100 if effect=='Change task progress' else 1000000)
  elif effect=='Change task priority' and value not in ['None','Low','Medium','High']:raise HTTPException(422,'Choose None, Low, Medium or High.')
  elif effect in ['Change task due date','Change task start date']:
   try:date.fromisoformat(value)
   except (ValueError,TypeError):raise HTTPException(422,'Choose a valid date.')
  elif effect=='Notify people':
   if not str(action.get('title','')).strip() or not str(action.get('message','')).strip():raise HTTPException(422,'Enter a notification title and message.')
   if not isinstance(action.get('people'),list) or not action['people']:raise HTTPException(422,'Choose people to notify.')
  elif effect in ['Change task followers','Change task assignees']:
   if not isinstance(value,(str,list)):raise HTTPException(422,'Choose people.')
  elif effect=='Set task custom field':
   if not isinstance(action.get('custom_field'),str) or not action['custom_field']:raise HTTPException(422,'Choose a task custom field.')
  elif effect not in ['Complete task','Uncomplete task'] and not str(value).strip():raise HTTPException(422,'Enter the action value.')
 rule['actions']=actions;rule['effect']=actions[0]['effect'];rule['value']=actions[0].get('value','')
 rule['title']=str(rule.get('title') or 'When '+rule['trigger']+', '+rule['effect']).strip()
 if not isinstance(rule.get('enabled',True),bool):raise HTTPException(422,'Choose a valid active state.')
 if rule['trigger']=='Every day':
  days=rule.get('weekdays',[date.today().weekday()])
  if not isinstance(days,list) or not days or any(type(n) is not int or not 0<=n<=6 for n in days):raise HTTPException(422,'Choose at least one day of the week.')
  rule['weekdays']=sorted(set(days))
 if rule['trigger'] in ['Task estimated time exceeds','Task progress exceeds']:rule['threshold']=integer(rule.get('threshold',0),'trigger threshold')
 if rule['trigger']=='Task inactive':
  rule['inactive_count']=integer(rule.get('inactive_count',1),'inactivity period',1)
  rule.setdefault('inactive_unit','Day')
  if rule['inactive_unit'] not in ['Day','Week']:raise HTTPException(422,'Choose days or weeks.')
 if rule['trigger'] in ['Task due date arrives','Task start date arrives','Every day']:
  rule.setdefault('run_at','09:00')
  if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',str(rule['run_at'])):raise HTTPException(422,'Choose a valid trigger time.')
  rule['offset_days']=integer(rule.get('offset_days',0),'day offset',-365,365)
 return rule

def install(app,db,owner,account):
 deliver_http=http_actions.install(app,db,owner,account)
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS tw_automation_fired(rule TEXT NOT NULL,task TEXT NOT NULL,slot TEXT NOT NULL,PRIMARY KEY(rule,task,slot));CREATE TABLE IF NOT EXISTS tw_automation_mail(id TEXT PRIMARY KEY,owner TEXT NOT NULL,recipient TEXT NOT NULL,title TEXT NOT NULL,message TEXT NOT NULL,sent INTEGER NOT NULL DEFAULT 0,error TEXT);''')
  c.execute('CREATE TABLE IF NOT EXISTS tw_automation_activity(owner TEXT NOT NULL,task TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(owner,task))')
 @app.get('/api/automations/connections/{provider}')
 def connection_status(provider:str,req:Request):
  if account(req)['account_id']!=owner(req):raise HTTPException(403,'Only the workspace owner can manage automations.')
  return connections.status(provider)
 @app.get('/api/automations/catalog')
 def catalog(req:Request):
  who=owner(req)
  if account(req)['account_id']!=who:raise HTTPException(403,'Only the workspace owner can manage automations.')
  with db() as c:
   people=[{'id':r['account_id'],'name':r['display_name']} for r in c.execute('SELECT account_id,display_name FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(who,who))]
   templates=[{'id':r['id'],'title':json.loads(r['data']).get('title','')} for r in c.execute("SELECT id,data FROM tw_records WHERE owner=? AND kind='template'",(who,))]
   chat_channels=[{'id':x['id'],'name':x['name']} for x in chat_actions.channels(c,who,who) if x['joined']]
  return {'chat_channels':chat_channels,'triggers':TRIGGERS,'effects':EFFECTS,'people':people,'templates':templates,'conditions':CONDITIONS,'field_types':FIELD_TYPES,'currencies':CURRENCIES,'daily_actions':DAILY,'targets':TARGETS,'target_effects':TARGET_EFFECTS,'task_creators':TASK_CREATORS,'http_methods':http_actions.METHODS,'collection_modes':COLLECTION_MODES,'people_sources':PEOPLE_SOURCES,'compatible_actions':{**connections.COMPATIBLE,'Every day':DAILY},'connection_effects':connections.EFFECTS,'connection_triggers':connections.TRIGGERS,'connections':{p:connections.status(p) for p in connections.PROVIDERS}}
 def validate_scope(c,who,rule):
  connections.require(rule)
  if rule['trigger']=='Every day' and rule.get('parent'):raise HTTPException(422,'Choose projects in the daily actions rather than the trigger.')
  validate_event_scope(c,who,rule)
  validate_condition_scope(c,who,rule.get('conditions',[]),rule.get('parent',''))
  for action in rule['actions']:
   chat_actions.validate_action_scope(c,who,action)
   validate_creation_scope(c,who,action)
   validate_transfer(c,who,action,rule.get('parent',''))
   validate_collection_scope(c,who,action)
   if action['effect']=='Set task custom field':validate_custom_field(c,who,action)
   if action['effect']=='Notify people':
    for person in action['people']:
     if not c.execute('SELECT account_id FROM local_auth_accounts WHERE account_id=? AND (account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?))',(person,who,who)).fetchone():raise HTTPException(422,'Choose a person in this workspace.')
   if action['effect']=='Add tasks from template' and not c.execute("SELECT 1 FROM tw_records WHERE owner=? AND id=? AND kind='template'",(who,action['value'])).fetchone():raise HTTPException(422,'Choose a task template in this workspace.')
 def insert_record(c,who,kind,tid,data,rule_id):
  data['automation_id']=rule_id;c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),who,kind,tid,json.dumps(data),int(time.time())))
 def touch(c,who,tid):
  if c.execute('SELECT 1 FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone():c.execute('INSERT INTO tw_automation_activity VALUES(?,?,?) ON CONFLICT(owner,task) DO UPDATE SET updated=excluded.updated',(who,tid,time.time()))
 def blocked(c,who):
  tasks=[dict(r) for r in c.execute('SELECT id,completed,options FROM tw_tasks WHERE owner=?',(who,))];incomplete={r['id'] for r in tasks if not r['completed']}
  return {r['id'] for r in tasks if incomplete.intersection(json.loads(r['options']).get('dependencies',[]))}
 def unblocked(c,who,previous,actor):
  # Only user mutations call this hook; action side effects do not recursively
  # produce a new chain of automation events.
  for tid in sorted(previous-blocked(c,who)):run(c,who,tid,'Task unblocked',actor=actor)
 def task_events(before,after):
  events=[]
  for column,event in [('priority','Task priority changes'),('stage','Task stage changes'),('due_date','Task due date changes'),('start_date','Task start date changes'),('list_name','Task list changes'),('title','Task name changes'),('description','Task description changes')]:
   if before.get(column)!=after.get(column):events.append(event)
  if not before.get('completed') and after.get('completed'):events.append('Task completed')
  before_options=before.get('options',{});after_options=after.get('options',{})
  if isinstance(before_options,str):before_options=json.loads(before_options)
  if isinstance(after_options,str):after_options=json.loads(after_options)
  for column,added,removed in [('tag','Task tag added','Task tag removed'),('assignee','Task assignee added','Task assignee removed')]:
   old=set(before_options.get('assignee_ids',[])) if column=='assignee' and 'assignee_ids' in before_options else {x.strip() for x in str(before.get(column,'')).split(',') if x.strip()}
   new=set(after_options.get('assignee_ids',[])) if column=='assignee' and 'assignee_ids' in after_options else {x.strip() for x in str(after.get(column,'')).split(',') if x.strip()}
   if new-old:events.append(added)
   if old-new:events.append(removed)
  old=before.get('options',{});new=after.get('options',{})
  if isinstance(old,str):old=json.loads(old)
  if isinstance(new,str):new=json.loads(new)
  if old.get('custom_fields')!=new.get('custom_fields'):events.append('Task custom field changes')
  if old.get('progress',0)<new.get('progress',0):events.append('Task progress exceeds')
  if before.get('estimate',0)<after.get('estimate',0):events.append('Task estimated time exceeds')
  if old!=new or any(before.get(k)!=after.get(k) for k in ['title','description','priority','stage','tag','start_date','due_date','completed','list_name','assignee','estimate','parent_id','project_id']):events.append('Task updated')
  return events
 def execute_action(c,who,task,action,rule_id,actor,trigger_task):
  tid=task['id'];opts=json.loads(task.get('options','{}'))
  effect=EFFECT_ALIASES.get(action['effect'],action['effect']);value=action.get('value','')
  if action['effect']=='Move to Done':value='Done'
  columns={'Change task assignees':'assignee','Change task priority':'priority','Change task tags':'tag','Change task estimated time':'estimate','Change task due date':'due_date','Change task start date':'start_date','Move task to stage':'stage','Move to task list':'list_name','Update task name':'title','Update task description':'description'}
  if effect==http_actions.EFFECT:http_actions.enqueue(c,who,rule_id,tid,action)
  elif effect==chat_actions.EFFECT:chat_actions.execute(c,who,action,rule_id)
  elif effect in COLLECTION_MODES:execute_collection(c,who,task,action,trigger_task)
  elif effect in TRANSFER_EFFECTS:return execute_transfer(c,who,task,action,rule_id)
  elif effect in CREATION or effect=='Log task time':return execute_creation(c,who,task,action,rule_id,actor)
  elif effect in columns:
   if isinstance(value,list):value=', '.join(value)
   c.execute('UPDATE tw_tasks SET '+columns[effect]+'=? WHERE owner=? AND id=?',(value,who,tid))
  elif effect=='Set task custom field':apply_custom_field(c,who,tid,action)
  elif effect in ['Change task progress','Change task followers']:
   current=json.loads(c.execute('SELECT options FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone()['options']);current['progress' if effect=='Change task progress' else 'followers']=value if effect=='Change task progress' or isinstance(value,list) else [x.strip() for x in value.split(',') if x.strip()];c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(current),who,tid))
  elif effect in ['Complete task','Uncomplete task']:c.execute('UPDATE tw_tasks SET completed=? WHERE owner=? AND id=?',(int(effect=='Complete task'),who,tid))
  elif effect in ['Add task comment','Log task time']:
   kind='comment' if effect=='Add task comment' else 'time';data={'text':str(value),'author':'Automation'} if kind=='comment' else {'minutes':int(value),'billable':False,'date':date.today().isoformat(),'actor':actor or who};insert_record(c,who,kind,tid,data,rule_id)
  elif effect=='Notify people':
   for person in action['people']:
    if person==actor and action.get('skip_triggering_person'):continue
    if opts.get('privacy')=='Only me' and opts.get('privacy_actor')!=person:continue
    member=c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=? AND (account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?))',(person,who,who)).fetchone()
    if not member:continue
    policy=c.execute('SELECT permissions,projects FROM tw_member_policies WHERE account=? AND workspace_owner=?',(person,who)).fetchone()
    if policy and task['project_id'] and (task['project_id'] not in json.loads(policy['projects']) or not (json.loads(policy['permissions']).get('Project Administrator') or json.loads(policy['permissions']).get('View Tasks & Milestones'))):continue
    insert_record(c,who,'notification',tid,{'title':action['title'],'text':action['message'],'private_actor':person},rule_id);c.execute('INSERT INTO tw_automation_mail(id,owner,recipient,title,message) VALUES(?,?,?,?,?)',(secrets.token_hex(12),who,member['email_normalized'],action['title'],action['message']))
  elif effect in ['Add task','Add subtask','Copy to task list','Add tasks from template']:
   entries=[{'title':str(value)}]
   if effect=='Add tasks from template':
    template=c.execute("SELECT data FROM tw_records WHERE owner=? AND id=? AND kind='template'",(who,value)).fetchone()
    if not template:return
    entries=json.loads(template['data']).get('tasks',[])
   for entry in entries:
    new={**task} if effect=='Copy to task list' else {**task,'title':str(entry.get('title','')),'description':str(entry.get('description','')),'completed':0,'priority':entry.get('priority','None'),'tag':'','assignee':entry.get('assignee',''),'start_date':None,'due_date':None,'stage':'Backlog','estimate':entry.get('estimate',0),'options':json.dumps({'created_by':who,'automation_id':rule_id})}
    if effect=='Add subtask' and opts.get('privacy')=='Only me':
     private_options=json.loads(new['options']);private_options.update(privacy='Only me',privacy_actor=opts['privacy_actor']);new['options']=json.dumps(private_options)
    if not new['title']:continue
    new['options']=json.dumps(task_assignees.canonical_options(c,who,new))
    new.update(id=secrets.token_hex(6),parent_id=tid if effect=='Add subtask' else '',list_name=str(value) if effect=='Copy to task list' else action.get('list_name',task['list_name']));cols=list(new);c.execute('INSERT INTO tw_tasks('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[new[k] for k in cols])
 def run(c,who,tid,trigger,actor=None,only_rule=None,previous=None):
  trigger=TRIGGER_ALIASES.get(trigger,trigger);task=c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone()
  if trigger=='Every day':task={'id':'','project_id':'','options':'{}','estimate':0,'list_name':''}
  if not task:return
  if not only_rule:touch(c,who,tid)
  task=dict(task);opts=json.loads(task.get('options','{}'))
  rows=c.execute("SELECT id,parent,data FROM tw_records WHERE owner=? AND kind='automation'",(who,)).fetchall()
  for row in rows:
   if only_rule and row['id']!=only_rule:continue
   rule=json.loads(row['data']);rule_trigger=TRIGGER_ALIASES.get(rule.get('trigger'),rule.get('trigger'))
   if rule_trigger!=trigger or rule.get('enabled') is False or row['parent'] and row['parent']!=task['project_id']:continue
   if not event_matches(rule,task,previous,actor):continue
   if not conditions_match(c,who,task,rule.get('conditions',[]),actor):continue
   threshold=rule.get('threshold',0)
   if trigger=='Task progress exceeds' and (opts.get('progress',0)<=threshold or previous and json.loads(previous.get('options','{}')).get('progress',0)>threshold):continue
   if trigger=='Task estimated time exceeds' and (task['estimate']<=threshold or previous and previous.get('estimate',0)>threshold):continue
   if trigger=='Task logged time exceeds estimated':
    total=sum(json.loads(r['data']).get('minutes',0) for r in c.execute("SELECT data FROM tw_records WHERE owner=? AND parent=? AND kind='time'",(who,tid)))
    if not task['estimate'] or total<=task['estimate']:continue
    # Trigger only the log that crosses the estimate.
    if previous and previous.get('logged_total',0)>task['estimate']:continue
   actions=rule.get('actions') or [{'effect':rule.get('effect'),'value':rule.get('value','')}]
   previous_created=None
   for action in actions:
    creates_task=action['effect'] in TASK_CREATORS
    if creates_task:previous_created=None
    for target in resolve_targets(c,who,task,action,previous_created):
     result=execute_action(c,who,target,action,row['id'],actor,task)
     if creates_task:previous_created=result
   # Persist actual executions independently of action records (e.g. priority only).
   insert_record(c,who,'automation_run',tid,{'trigger':trigger,'title':rule.get('title',''),'actions':len(actions)},row['id'])
 def scheduled(now=None):
  now=now or datetime.now(timezone.utc)
  with db() as c:
   c.execute('BEGIN IMMEDIATE')
   for row in c.execute("SELECT id,owner,parent,data,created FROM tw_records WHERE kind='automation'").fetchall():
    rule=json.loads(row['data']);trigger=rule.get('trigger')
    if trigger not in ['Task due date arrives','Task start date arrives','Task inactive','Every day'] or rule.get('enabled') is False:continue
    if trigger=='Every day':
     if now.weekday() not in rule['weekdays']:continue
     when=datetime.fromisoformat(now.date().isoformat()+'T'+rule['run_at']).replace(tzinfo=timezone.utc)
     if when>now or row['created']>when.timestamp():continue
     slot='daily:'+when.isoformat();changed=c.execute('INSERT OR IGNORE INTO tw_automation_fired VALUES(?,?,?)',(row['id'],'',slot)).rowcount
     if changed:run(c,row['owner'],'',trigger,only_rule=row['id'])
     continue
    if trigger=='Task inactive':
     duration=int(rule.get('inactive_count',1))*(7 if rule.get('inactive_unit')=='Week' else 1)*86400
     for activity in c.execute('SELECT a.task,a.updated,t.project_id FROM tw_automation_activity a JOIN tw_tasks t ON t.owner=a.owner AND t.id=a.task WHERE a.owner=? AND a.updated>=?',(row['owner'],row['created'])).fetchall():
      if row['parent'] and row['parent']!=activity['project_id']:continue
      when=datetime.fromtimestamp(activity['updated'],timezone.utc)+timedelta(seconds=duration)
      if when>now:continue
      slot='inactive:'+repr(activity['updated']);changed=c.execute('INSERT OR IGNORE INTO tw_automation_fired VALUES(?,?,?)',(row['id'],activity['task'],slot)).rowcount
      if changed:run(c,row['owner'],activity['task'],trigger,only_rule=row['id'])
     continue
    column='due_date' if trigger=='Task due date arrives' else 'start_date'
    for task in c.execute('SELECT * FROM tw_tasks WHERE owner=? AND '+column+' IS NOT NULL',(row['owner'],)).fetchall():
     if row['parent'] and row['parent']!=task['project_id']:continue
     try:when=datetime.fromisoformat(task[column]+'T'+rule.get('run_at','09:00')).replace(tzinfo=timezone.utc)+timedelta(days=int(rule.get('offset_days',0)))
     except (ValueError,TypeError):continue
     if when.date()!=now.date() or when>now:continue
     slot=when.isoformat();changed=c.execute('INSERT OR IGNORE INTO tw_automation_fired VALUES(?,?,?)',(row['id'],task['id'],slot)).rowcount
     if changed:run(c,row['owner'],task['id'],trigger,only_rule=row['id'])
 def deliver_mail():
  with db() as c:
   c.execute('BEGIN IMMEDIATE')
   for row in c.execute('SELECT * FROM tw_automation_mail WHERE sent=0').fetchall():
    msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@teamwork.clone.test');msg['To']=row['recipient'];msg['Subject']=row['title'];msg.set_content(row['message'])
    try:
     with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(msg)
     c.execute('UPDATE tw_automation_mail SET sent=?,error=NULL WHERE id=?',(int(time.time()),row['id']))
    except (OSError,smtplib.SMTPException):c.execute("UPDATE tw_automation_mail SET error='Email could not be sent; retry pending' WHERE id=?",(row['id'],))
 stop=threading.Event()
 @app.on_event('startup')
 def start():
  def loop():
   while not stop.wait(10):
    try:scheduled();deliver_mail();deliver_http()
    except Exception:logging.getLogger(__name__).exception('Automation worker failed')
  stop.clear();threading.Thread(target=loop,daemon=True,name='teamwork-local-automations').start()
 @app.on_event('shutdown')
 def shutdown():stop.set()
 return {'deliver_http':deliver_http,'validate_scope':validate_scope,'run':run,'events':task_events,'scheduled':scheduled,'deliver_mail':deliver_mail,'touch':touch,'blocked':blocked,'unblocked':unblocked}
