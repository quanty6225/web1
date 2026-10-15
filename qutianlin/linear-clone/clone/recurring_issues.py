"""Durable recurring issues. Generation and counters share one SQLite transaction."""
import calendar,json,secrets,time
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import HTTPException
from issue_properties import prepare_issue,synchronize_issues
from issue_templates import prepare_issue_template

def advance_day(value,interval,unit,anchor_day=None):
 day=date.fromisoformat(value)
 if unit in ('day','week'):return (day+timedelta(days=interval*(7 if unit=='week'else 1))).isoformat()
 months=interval*(12 if unit=='year'else 1);index=day.year*12+day.month-1+months;year,month=divmod(index,12);month+=1
 return date(year,month,min(anchor_day or day.day,calendar.monthrange(year,month)[1])).isoformat()

def run_at(due,zone):return int(datetime.combine(date.fromisoformat(due)+timedelta(days=1),datetime.min.time(),ZoneInfo(zone)).replace(minute=1).timestamp())

def prepare_recurring(c,wid,value,previous,provided,now):
 def bad(message):raise HTTPException(422,message)
 # Validate the same task properties as a team-scoped standard template.
 template={**value,'scope_team':value.get('team','QQQ'),'team':value.get('team','QQQ'),'issue_title':value.get('title',''),'issue_description':value.get('description',''),'issue_content_html':value.get('content_html','')}
 if 'content_html'in provided:template['issue_content_html']=provided['content_html']
 prepare_issue_template(c,wid,template,None,{'issue_content_html':template['issue_content_html']}if 'content_html'in provided else {},now)
 value['title']=template['title'];value['description']=template['issue_description'];value['content_html']=template['issue_content_html'];value['team']=template['team']
 for field in ['priority','labels','assignee','project','icon']:value[field]=template.get(field)
 value['status']=template.get('status')or 'Backlog'
 value['subissue_templates']=template.get('subissue_templates',[])
 interval=value.get('interval',1);unit=value.get('unit','week');zone=value.get('timezone','UTC')
 if type(interval)is not int or not 1<=interval<=100:bad('Choose a repeat interval between 1 and 100.')
 if unit not in ('day','week','month','year'):bad('Choose a repeat period.')
 try:tz=ZoneInfo(zone)
 except (ValueError,TypeError,ZoneInfoNotFoundError):bad('Choose a valid timezone.')
 try:due=date.fromisoformat(value.get('first_due_date',''))
 except (TypeError,ValueError):bad('Choose the first due date.')
 if due.year>2099 or (previous is None and due<datetime.fromtimestamp(now,tz).date()):bad('Choose a due date from today through 2099.')
 if type(value.get('enabled',True))is not bool:bad('Invalid recurring issue state.')
 source=value.get('source_issue_id')if previous is None else previous.get('source_issue_id')
 if source:
  if not isinstance(source,str):bad('Select an issue from this workspace.')
  row=c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='issues' AND id=?",(wid,source)).fetchone()
  if not row:bad('Select an issue from this workspace.')
  if previous is None and json.loads(row['document']).get('recurring_issue_id'):bad('This issue already belongs to a recurring schedule.')
 value.update(interval=interval,unit=unit,timezone=zone,enabled=value.get('enabled',True),first_due_date=due.isoformat(),source_issue_id=source)
 for key in ['last_issue_id','last_due_date','next_run_at','occurrence_count']:
  if previous and key in previous:value[key]=previous[key]
  else:value.pop(key,None)
 value['anchor_day']=(previous or {}).get('anchor_day',due.day)
 if previous:
  value['first_due_date']=previous['first_due_date']
  try:value['next_due_date']=advance_day(previous['last_due_date'],interval,unit,value['anchor_day']);value['next_run_at']=run_at(previous['last_due_date'],zone)
  except (ValueError,OverflowError):bad('The next recurrence is outside the supported date range.')
  if not previous.get('enabled',True)and value['enabled']:
   # On resume, retain cadence but skip missed runs while it was paused.
   while run_at(value['next_due_date'],zone)<=now:value['next_due_date']=advance_day(value['next_due_date'],interval,unit,value['anchor_day'])
   value['next_run_at']=max(now,run_at(previous['last_due_date'],zone))


def create_instance(store,c,wid,record,due,now,source=None):
 owner=c.execute('SELECT a.email_normalized FROM local_auth_accounts a JOIN linear_workspaces w ON w.owner_id=a.account_id WHERE w.id=?',(wid,)).fetchone()
 data={k:record.get(k)for k in ['title','description','status','priority','assignee','labels','project']};data.update(due_date=due,creator=owner['email_normalized'],team=record.get('team','QQQ'),recurring_issue_id=record['id'],comments=[],subissues=[],description_edited=True)
 states=[json.loads(r[0])['title']for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states'",(wid,))]
 if data['status']not in states:data['status']='Todo'if 'Todo'in states else states[0]
 labels={json.loads(r[0])['title']for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='labels'",(wid,))};data['labels']=[x for x in data.get('labels')or[]if x in labels]
 if data.get('project')and not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='projects' AND id=?",(wid,data['project'])).fetchone():data['project']=None
 previous=None
 if source:
  row=c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='issues' AND id=?",(wid,source)).fetchone();previous=json.loads(row[0]);data={**previous,**data,'comments':previous.get('comments',[]),'id':source}
 else:
  from workspaces import next_issue_id
  data['id']=next_issue_id(c,wid,record.get('team','QQQ'))
 prepare_issue(c,wid,data,previous,data,now)
 if source:c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(data),now,wid,source))
 else:c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,'issues',data['id'],json.dumps(data),now,now))
 store.collect_record_event(c,wid,'issues','update'if source else'create',data,previous)
 if record.get('subissue_templates'):
  from subissue_templates import insert_children
  insert_children(store,c,wid,data,record['subissue_templates'],now)
 synchronize_issues(store,c,wid,now)
 record.update(last_issue_id=data['id'],last_due_date=due,next_due_date=advance_day(due,record['interval'],record['unit'],record['anchor_day']),next_run_at=run_at(due,record['timezone']),occurrence_count=record.get('occurrence_count',0)+1)
 c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='recurring-issues' AND id=?",(json.dumps(record),now,wid,record['id']))
 return data

def deliver_recurring_issues(store,wid,at=None):
 now=int(time.time())if at is None else int(at)
 with store.auth.connect()as c:
  c.execute('BEGIN IMMEDIATE')
  for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='recurring-issues'",(wid,)).fetchall():
   record=json.loads(row[0]);count=0
   while record.get('enabled',True)and record.get('next_run_at',now+1)<=now and count<100:
    if date.fromisoformat(record['next_due_date']).year>2099:record['enabled']=False;c.execute("UPDATE linear_records SET document=? WHERE workspace_id=? AND kind='recurring-issues' AND id=?",(json.dumps(record),wid,record['id']));break
    create_instance(store,c,wid,record,record['next_due_date'],now);count+=1
  c.commit()
