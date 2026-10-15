import task_assignees
"""Workspace-owned task options, recurrence, dependency checks and local SMTP reminders."""
import calendar,json,secrets,time,threading,os,smtplib,logging
from datetime import date,datetime,timedelta,timezone
from email.message import EmailMessage
from fastapi import HTTPException,Request

def install(app,db,owner,account,get_task,ACL,automations=None):
 with db() as c:
  if 'options' not in [r['name'] for r in c.execute('PRAGMA table_info(tw_tasks)')]:c.execute("ALTER TABLE tw_tasks ADD COLUMN options TEXT NOT NULL DEFAULT '{}'")
  c.execute('CREATE TABLE IF NOT EXISTS tw_reminders(id TEXT PRIMARY KEY,account TEXT NOT NULL,workspace_owner TEXT NOT NULL,task TEXT NOT NULL,due INTEGER NOT NULL,sent INTEGER NOT NULL DEFAULT 0,origin TEXT NOT NULL,error TEXT)')
 def deliver_reminders():
  with db() as c:
   # An immediate transaction prevents overlapping workers from sending the same reminder.
   c.execute('BEGIN IMMEDIATE')
   rows=c.execute('SELECT r.*,a.email_normalized,t.title,t.options FROM tw_reminders r JOIN local_auth_accounts a ON a.account_id=r.account JOIN tw_tasks t ON t.owner=r.workspace_owner AND t.id=r.task WHERE r.sent=0 AND r.due<=?',(int(time.time()),)).fetchall()
   for r in rows:
    options=json.loads(r['options'])
    if options.get('privacy')=='Only me' and options.get('privacy_actor')!=r['account']:
     c.execute('DELETE FROM tw_reminders WHERE id=?',(r['id'],));continue
    message=EmailMessage();message['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@teamwork.clone.test');message['To']=r['email_normalized'];message['Subject']='Task reminder: '+r['title'];message.set_content(r['title']+'\n'+r['origin']+'/app/tasks/'+r['task'])
    try:
     with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(message)
     c.execute('UPDATE tw_reminders SET sent=?,error=NULL WHERE id=?',(int(time.time()),r['id']))
    except (OSError,smtplib.SMTPException):c.execute("UPDATE tw_reminders SET error='Email could not be sent; retry pending' WHERE id=?",(r['id'],))
 stop=threading.Event()
 @app.on_event('startup')
 def start_reminders():
  def loop():
   while not stop.wait(10):
    try:deliver_reminders()
    except Exception:logging.getLogger(__name__).exception('Reminder delivery failed')
  stop.clear();threading.Thread(target=loop,daemon=True,name='teamwork-local-reminders').start()
 @app.on_event('shutdown')
 def stop_reminders():stop.set()
 @app.get('/api/reminders')
 def reminders(req:Request):
  with db() as c:return [dict(r) for r in c.execute('SELECT id,task,due,sent,error FROM tw_reminders WHERE account=? AND workspace_owner=?',(account(req)['account_id'],owner(req)))]
 @app.post('/api/tasks/{tid}/reminders')
 async def add_reminder(tid:str,req:Request):
  get_task(tid,req);d=await req.json()
  try:
   parsed=datetime.fromisoformat(d['due'].replace('Z','+00:00'));due=int((parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp())
  except (KeyError,ValueError,TypeError):raise HTTPException(422,'Enter a valid reminder date and time.')
  if due<int(time.time())-60:raise HTTPException(422,'Choose a future reminder time.')
  rid=secrets.token_hex(12)
  with db() as c:c.execute('INSERT INTO tw_reminders(id,account,workspace_owner,task,due,origin) VALUES(?,?,?,?,?,?)',(rid,account(req)['account_id'],owner(req),tid,due,str(req.base_url).rstrip('/')))
  return {'ok':True,'id':rid}
 @app.delete('/api/reminders/{rid}')
 def delete_reminder(rid:str,req:Request):
  with db() as c:changed=c.execute('DELETE FROM tw_reminders WHERE id=? AND account=?',(rid,account(req)['account_id'])).rowcount
  if not changed:raise HTTPException(404,'Reminder not found.')
  return {'ok':True}
 @app.put('/api/tasks/{tid}/options')
 async def options(tid:str,req:Request):
  before=get_task(tid,req);d=await req.json();who=owner(req);allowed={'dependencies','repeat','progress','privacy','custom_fields','followers'}
  if set(d)-allowed:raise HTTPException(422,'Unknown task option.')
  if 'progress' in d:
   try:d['progress']=int(d['progress'])
   except (ValueError,TypeError):raise HTTPException(422,'Progress must be a number.')
   if not 0<=d['progress']<=100:raise HTTPException(422,'Progress must be between 0 and 100.')
  if 'repeat' in d and d['repeat'] not in ['Does not repeat','Daily','Weekly','Monthly','Yearly']:raise HTTPException(422,'Choose a repeat interval.')
  if 'privacy' in d:ACL['require'](req,'Can Set Privacy on Items',get_task(tid,req)['project_id'])
  if 'privacy' in d and d['privacy'] not in ['Everyone on project','Only me']:raise HTTPException(422,'Choose task privacy.')
  if 'custom_fields' in d and (not isinstance(d['custom_fields'],dict) or any(not isinstance(v,(str,int,float,bool)) for v in d['custom_fields'].values())):raise HTTPException(422,'Enter valid custom fields.')
  if 'followers' in d and (not isinstance(d['followers'],list) or any(not isinstance(v,str) for v in d['followers'])):raise HTTPException(422,'Choose valid followers.')
  with db() as c:
   blocked_before=automations['blocked'](c,who) if automations and 'dependencies' in d else set()
   if 'dependencies' in d:
    if not isinstance(d['dependencies'],list):raise HTTPException(422,'Choose dependency tasks.')
    for dependency in d['dependencies']:get_task(dependency,req)
    rows={r['id']:json.loads(r['options']) for r in c.execute('SELECT id,options FROM tw_tasks WHERE owner=?',(who,))}
    if any(i not in rows or i==tid for i in d['dependencies']):raise HTTPException(422,'Choose existing tasks other than this task.')
    def reaches(current,seen):
     if current==tid:return True
     if current in seen:return False
     seen.add(current);return any(reaches(i,seen) for i in rows.get(current,{}).get('dependencies',[]))
    if any(reaches(i,set()) for i in d['dependencies']):raise HTTPException(422,'Dependencies cannot form a cycle.')
   previous=json.loads(c.execute('SELECT options FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone()['options']);previous.update(d)
   if 'privacy' in d:previous['privacy_actor']=account(req)['account_id']
   c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(previous),who,tid))
   if blocked_before:automations['unblocked'](c,who,blocked_before,account(req)['account_id'])
   if automations:
    after={**before,'options':json.dumps(previous)};prior={**before,'options':json.dumps(before['options'])}
    for event in automations['events'](prior,after):automations['run'](c,who,tid,event,actor=account(req)['account_id'],previous=prior)
  return {'ok':True,'options':previous}
 @app.post('/api/tasks/{tid}/transfer')
 async def transfer(tid:str,req:Request):
  source=get_task(tid,req);who=owner(req);d=await req.json();project=d.get('project_id');copy=d.get('action')=='Copy'
  ACL['require'](req,'Add Tasks',project)
  if d.get('action') not in ['Move','Copy']:raise HTTPException(422,'Choose Move or Copy.')
  with db() as c:
   if not c.execute('SELECT 1 FROM tw_projects WHERE owner=? AND id=?',(who,project)).fetchone():raise HTTPException(404,'Project not found.')
   rows=[dict(r) for r in c.execute('WITH RECURSIVE children AS (SELECT * FROM tw_tasks WHERE owner=? AND id=? UNION ALL SELECT t.* FROM tw_tasks t JOIN children p ON t.parent_id=p.id AND t.owner=p.owner) SELECT * FROM children',(who,tid))];ids={r['id']:secrets.token_hex(12) if copy else r['id'] for r in rows}
   for row in rows:get_task(row['id'],req)
   for row in rows:
    prior=dict(row);oldid=row['id'];row.update(id=ids[oldid],project_id=project,parent_id=ids.get(row['parent_id'],''),list_name=d.get('list_name') or row['list_name'])
    if copy:
     opts=task_assignees.canonical_options(c,who,row);opts.pop('repeat_next_id',None);opts['dependencies']=[ids.get(i,i) for i in opts.get('dependencies',[])];row['options']=json.dumps(opts);columns=list(row);c.execute('INSERT INTO tw_tasks('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns])
    else:c.execute('UPDATE tw_tasks SET project_id=?,parent_id=?,list_name=? WHERE owner=? AND id=?',(project,row['parent_id'],row['list_name'],who,oldid))
    if automations:
     for event in ['Task added'] if copy else automations['events'](prior,row):automations['run'](c,who,row['id'],event,actor=account(req)['account_id'],previous=prior)
  return {'ok':True,'id':ids[tid],'redirect':'/app/tasks/'+ids[tid]}
 return deliver_reminders

def complete_recurring(c,who,tid):
 row=dict(c.execute('SELECT * FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone());opts=json.loads(row['options']);repeat=opts.get('repeat','Does not repeat')
 if repeat=='Does not repeat' or opts.get('repeat_next_id'):return
 def advance(value):
  current=date.fromisoformat(value or date.today().isoformat())
  if repeat in ['Daily','Weekly']:return (current+timedelta(days=1 if repeat=='Daily' else 7)).isoformat()
  month=current.month+(1 if repeat=='Monthly' else 12);year=current.year+(month-1)//12;month=(month-1)%12+1
  return current.replace(year=year,month=month,day=min(current.day,calendar.monthrange(year,month)[1])).isoformat()
 nextid=secrets.token_hex(12);newopts=task_assignees.canonical_options(c,who,row);newopts.pop('repeat_next_id',None);newopts['progress']=0;row.update(id=nextid,completed=0,stage='Backlog',options=json.dumps(newopts),due_date=advance(row['due_date']))
 if row['start_date']:row['start_date']=advance(row['start_date'])
 columns=list(row);c.execute('INSERT INTO tw_tasks('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[k] for k in columns]);opts['repeat_next_id']=nextid;c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(opts),who,tid))
