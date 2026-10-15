"""Account-scoped local implementation of Reclaim's observed task/calendar contracts."""
import copy,json,uuid,time,hashlib,re,os,smtplib
from email.message import EmailMessage
from contextlib import nullcontext
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from scheduling import Scheduling
from team_scheduling import TeamScheduling
from recurrence import validate as validate_recurrence,occurrence_days,wall_start,series_action

def now():return datetime.now(timezone.utc).isoformat()
def parse(value):
 try:return datetime.fromisoformat(value.replace('Z','+00:00'))
 except (ValueError,AttributeError):raise HTTPException(422,'Invalid date.')
def merge(a,b):
 for k,v in b.items():
  if isinstance(v,dict)and isinstance(a.get(k),dict):merge(a[k],v)
  else:a[k]=copy.deepcopy(v)
 return a
class Business(Scheduling,TeamScheduling):
 def __init__(self,connection,fixtures,account):self.connect=lambda:nullcontext(connection);self.fixtures=fixtures;self.account=account;self.owner=account['account_id'];self._profile_cache=None;self.seed()
 def normalize(self,kind,value):
  if isinstance(value,dict):
   link=value if kind=='link'else value.get('schedulingLink')if kind=='booking'else None
   if isinstance(link,dict):
    if kind=='booking':
     value['organizers']=[entry if 'organizer' in entry else {'organizer':{**entry,'attendanceType':entry.get('attendanceType','REQUIRED')},'isHost':index==0} for index,entry in enumerate(value.get('organizers',[]))]
     saved=self.get('settings','user-slug')
     if saved:link['userSlug']=saved['slug'];value['userSlug']={'slug':saved['slug']}
     current_link=self.get('link',value.get('schedulingLinkId'))
     if current_link:link['linkGroupId']=current_link['linkGroupId']
    link['linkOwnerTeamId']=int(__import__('team_scheduling').public_id(self.team_owner()))
    link['permissions']={'canEnable':True,'canEdit':True,'canUpdate':True,'canDelete':True}
    self.decorate_link(link)
  return value
 def slug_owner(self,slug):
  with self.connect()as c:
   for row in c.execute("SELECT a.account_id,r.data FROM local_auth_accounts a LEFT JOIN reclaim_records r ON r.account_id=a.account_id AND r.kind='settings' AND r.id='user-slug'"):
    candidate=json.loads(row['data'])['slug']if row['data']else'local-'+hashlib.sha256(row['account_id'].encode()).hexdigest()[:10]
    if candidate==slug:return row['account_id']
   for row in c.execute("SELECT account_id,data FROM reclaim_records WHERE kind='group'"):
    if json.loads(row['data']).get('slug')==slug:return row['account_id']
  return None
 def rows(self,kind):
  with self.connect()as c:return [self.normalize(kind,json.loads(x[0]))for x in c.execute('SELECT data FROM reclaim_records WHERE account_id=? AND kind=? ORDER BY id',(self.owner,kind))]
 def get(self,kind,key,default=None):
  with self.connect()as c:r=c.execute('SELECT data FROM reclaim_records WHERE account_id=? AND kind=? AND id=?',(self.owner,kind,str(key))).fetchone()
  return self.normalize(kind,json.loads(r[0])if r else copy.deepcopy(default))
 def put(self,kind,key,value):
  if kind=='settings'and key=='profile':self._profile_cache=None
  with self.connect()as c:c.execute('INSERT INTO reclaim_records(account_id,kind,id,data) VALUES(?,?,?,?) ON CONFLICT(account_id,kind,id) DO UPDATE SET data=excluded.data,revision=revision+1',(self.owner,kind,str(key),json.dumps(value)))
  return value
 def delete(self,kind,key):
  with self.connect()as c:r=c.execute('DELETE FROM reclaim_records WHERE account_id=? AND kind=? AND id=?',(self.owner,kind,str(key)))
  if not r.rowcount:raise HTTPException(404,'Not found.')
 def seed(self):
  with self.connect()as c:
   if not c.execute("SELECT 1 FROM reclaim_records WHERE account_id=? AND kind='meta' AND id='seed'",(self.owner,)).fetchone():
    for t in self.fixtures['/api/gtd-tasks/search/plan']['tasks']:c.execute('INSERT INTO reclaim_records(account_id,kind,id,data) VALUES(?,?,?,?)',(self.owner,'task',t['id'],json.dumps(t)))
    c.execute('INSERT INTO reclaim_records(account_id,kind,id,data) VALUES(?,?,?,?)',(self.owner,'meta','seed','true'))
 def profile(self):
  if self._profile_cache is None:self._profile_cache=merge(copy.deepcopy(self.fixtures['/api/users/current']),self.get('settings','profile',{}))
  return self._profile_cache
 def task(self,data,key=None):
  old=self.get('task',key)if key else None
  if key and old is None:raise HTTPException(404,'Task not found.')
  t=old or {'id':'RECLAIM:'+str(time.time_ns()//1000),'type':'ReclaimTask','completed':False,'status':'open','extendedProperties':{},'sortOrder':time.time()*1000}
  for field in ['title','description','estimateMinutes','priority','completed']:
   if field in data:t[field]=data[field]
  if not str(t.get('title','')).strip():raise HTTPException(422,'Enter a task title.')
  if t.get('estimateMinutes')is not None and (not isinstance(t['estimateMinutes'],(int,float))or not 0<t['estimateMinutes']<=43200):raise HTTPException(422,'Duration must be between 1 minute and 30 days.')
  if t.get('priority')not in [None,'P1','P2','P3','P4']:raise HTTPException(422,'Invalid priority.')
  tz=ZoneInfo(self.profile().get('timezone',{}).get('id','Asia/Shanghai'))
  for field,out in [('startDate','start'),('dueDate','due')]:
   if field in data:
    value=data[field]
    if value and len(value)==10:value=value+('T23:59:59'if out=='due'else'T00:00:00')
    d=parse(value)if value else None
    t[out]=(d.replace(tzinfo=tz)if d and d.tzinfo is None else d).isoformat()if d else None
  if t.get('start')and t.get('due')and parse(t['start'])>parse(t['due']):raise HTTPException(422,'Due date must follow start date.')
  t['status']='completed'if t['completed']else'open';t['updatedAt']=now();return self.put('task',t['id'],t)
 def tasks(self,query):
  rows=self.rows('task');q=query.get('query','').casefold()
  if q:rows=[t for t in rows if q in t['title'].casefold()or q in (t.get('description')or'').casefold()]
  if query.get('completed')in ['true','false']:rows=[t for t in rows if t['completed']==(query['completed']=='true')]
  priority=query.get('priority')or query.get('priorities')
  if priority:rows=[t for t in rows if t.get('priority','P2')in priority.split(',')]
  if query.get('dueBefore'):rows=[t for t in rows if t.get('due')and parse(t['due'])<=parse(query['dueBefore'])]
  if query.get('dueAfter'):rows=[t for t in rows if t.get('due')and parse(t['due'])>=parse(query['dueAfter'])]
  relative=query.get('relativeDue');today=datetime.now(ZoneInfo(self.profile()['timezone']['id'])).date()
  if relative:
   def matches(t):
    due=parse(t['due']).date()if t.get('due')else None
    return {'OVERDUE':bool(due and due<today),'TODAY':due==today,'TOMORROW':due==today+timedelta(days=1),'THIS_WEEK':bool(due and today<=due<=today+timedelta(days=6-today.weekday())),'NO_DUE_DATE':due is None,'NONE':due is None}.get(relative,True)
   rows=[t for t in rows if matches(t)]
  sort=query.get('sort','SORT_ORDER');key={'TITLE':'title','PRIORITY':'priority','DUE':'due','DUE_DATE':'due'}.get(sort,'sortOrder');rows.sort(key=lambda t:(t.get(key)is None,t.get(key)or''),reverse=query.get('order')=='DESC');return rows
 def event(self,action):
  kind=action['type'];key=action.get('eventKey')or str(action.get('calendarId',200002))+'/'+str(action.get('eventId',''))
  if kind=='AddEventAction':key=str(action.get('calendarId',200002))+'/'+(action.get('eventId')or uuid.uuid4().hex)
  old=self.get('event',key)
  if not old and re.search(r'_\d{4}-\d{2}-\d{2}$',key):
   day=key[-10:];old=next((e for e in self.calendar_events({'start':day,'end':day})if e['key']==key),None)
  if kind!='AddEventAction'and old is None:raise HTTPException(404,'Event not found.')
  if old and old.get('recurringEventId') and action.get('recurrenceEditType','THIS')!='THIS':
   result=series_action(self,action,old)
   if result is not None:return result
  if kind=='CancelEventAction':
   if old.get('recurringEventId'):
    self.put('event-cancel',key,{'cancelled':True,'key':key})
    if self.get('event',key):self.delete('event',key)
   else:self.delete('event',key)
   return old
  if kind in ['RsvpEventAction','EventLockAction','PatchAssistantDataAction']:
   if kind=='RsvpEventAction':old['rsvpStatus']=action['responseStatus']
   if kind=='EventLockAction':old['reclaimData']['associations']['locked']=action.get('lockMode')not in ['UNLOCKED','UNLOCK','OFF']
   if kind=='PatchAssistantDataAction':old['reclaimData']['associations']['snoozeUntil']=action.get('snoozeUntil')
   return self.put('event',key,old)
  event=old or {'key':key,'calendarId':200002,'id':key.split('/')[-1],'eventId':key.split('/')[-1],'title':'','status':'CONFIRMED','entryType':'USER','rsvpStatus':'ACCEPTED','color':'NONE','visibility':'DEFAULT','transparency':'OPAQUE','attendeesAndResources':[],'platformData':{'type':'OutlookEventData'},'reclaimData':{'reclaimEventType':'USER','priority':'P1','associations':{'locked':False,'canLock':True,'canUnlock':False,'canSnooze':False,'canRescheduleForward':True,'policyAssociations':[]}},'allowedEditTypes':{'types':['THIS'],'reason':'ORGANIZER'}}
  if int(action.get('calendarId',200002))!=200002:raise HTTPException(403,'Calendar is not writable.')
  for field in ['title','description','location','color','visibility','transparency','reminders','guestsCanModify','guestsCanInviteOthers','guestsCanSeeOtherGuests','recurrence','eventCategory']:
   if field in action:event[field]=action[field]
  dates=action.get('dateRange')or({'type':'FixedDateTimeRange','start':action['start'],'end':action['end']}if 'start'in action and'end'in action else event.get('eventDate'))
  if not dates or dates.get('type')not in ['AllDayDateRange','FixedDateTimeRange']:raise HTTPException(422,'Invalid event date range.')
  if parse(dates['start'])>=parse(dates['end']):raise HTTPException(422,'Event end must follow its start.')
  if dates['type']=='FixedDateTimeRange'and (parse(dates['start']).tzinfo is None or parse(dates['end']).tzinfo is None):raise HTTPException(422,'Specify a timezone for the event.')
  if not event['title'].strip():raise HTTPException(422,'Enter an event title.')
  validate_recurrence(event.get('recurrence'))
  if event.get('recurrence'):
   event.setdefault('recurrenceTimezone',action.get('recurrenceTimezone') or self.profile()['timezone']['id'])
   try:ZoneInfo(event['recurrenceTimezone'])
   except (KeyError,ValueError,TypeError):raise HTTPException(422,'Choose a valid recurrence timezone.')
  event['canModify']=True;event['canDelete']=True;event['freeBusy']='FREE'if event.get('transparency')=='TRANSPARENT'else'BUSY';event['isOrganizer']=True;event['eventDate']=dates;event['originalStart']=old.get('originalStart',dates['start']) if old and old.get('recurringEventId') else dates['start'];event['reclaimData']['priority']=action.get('priority',event['reclaimData']['priority']);event['versionData']={'syncStatus':'SYNCED','updated':now()}
  if 'attendees'in action:event['attendeesAndResources']=[{'type':'EventAttendeeParticipant','responseStatus':'NEEDS_ACTION',**a}for a in action['attendees']]
  return self.put('event',key,event)
 def updates(self,data):
  req=data.get('request',data);interactions=req.get('interactions',[])
  for i in interactions:
   kind=i['type']
   if kind in ['StartTaskRequest','StopTaskRequest']:
    task=self.get('task',i['task']['id'])
    if not task:raise HTTPException(404,'Task not found.')
    running=self.get('running',task['id'])
    if kind=='StartTaskRequest'and not running:
     start=datetime.now(timezone.utc);end=start+timedelta(minutes=task.get('estimateMinutes')or 30);event=self.event({'type':'AddEventAction','title':task['title'],'dateRange':{'type':'FixedDateTimeRange','start':start.isoformat(),'end':end.isoformat()},'calendarId':200002,'priority':task.get('priority')or'P2'});event['localTaskId']=task['id'];self.put('event',event['key'],event);self.put('running',task['id'],{'eventKey':event['key'],'start':start.isoformat()})
    elif kind=='StopTaskRequest'and running:
     event=self.get('event',running['eventKey']);event['eventDate']['end']=now();self.put('event',event['key'],event);self.delete('running',task['id'])
    continue
   if kind in ['ChangeScheduleWindowRequest','ChangeMeetingHubViewRequest','PreviewModeChangedRequest']:continue
   if kind!='TakeScheduleActionRequest':raise HTTPException(501,'This interaction is not available locally.')
   action=i['actionTaken'];rid=i.get('requestId');prior=self.get('requests',rid)if rid else None
   if prior:continue
   if action['type']in ['AddEventAction','UpdateEventAction','RescheduleEventAction','CancelEventAction','RsvpEventAction','EventLockAction','PatchAssistantDataAction']:result=self.event(action)
   elif action['type']=='MutatePolicyAction':result=self.policy(action)
   elif action['type']in ['CompleteGtdTaskAction','UncompleteGtdTaskAction']:result=self.task({'completed':action['type']=='CompleteGtdTaskAction'},action['task']['id'])
   else:raise HTTPException(501,'This action is not available locally.')
   if rid:self.put('requests',rid,{'result':result})
  updates=copy.deepcopy(self.fixtures['/api/interactions/update']['updates']);window=req.get('scheduleWindow');events=self.calendar_events(window)
  if window:events=[e for e in events if e['eventDate']['start'][:10]<=window['end']and e['eventDate']['end'][:10]>=window['start']]
  meeting=any(i['type']=='ChangeMeetingHubViewRequest'for i in interactions)
  for u in updates:
   d=u['data']
   if d['type']=='SessionUpdate':
    d['session']['sessionScope']=req.get('sessionScope',d['session']['sessionScope']);d['session']['sessionId']={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,self.owner+json.dumps(req.get('sessionScope',{}),sort_keys=True)))};d['session']['updatedAt']=now()
    if window:d['session']['scheduleWindow']=window
   elif d['type']=='SchedulePoliciesUpdate'and u['part']=='CURRENT':
    base={p['commonData']['id']:p for p in d['policies']};base.update({p['commonData']['id']:p for p in self.rows('policy')});d['policies']=[p for p in base.values()if not p['commonData'].get('deleted')]
   elif d['type']=='CalendarEventsUpdate':
    d['events']=events if u['part']=='CURRENT'else[]
    if meeting:u['data']={'type':'CalendarEventsPageUpdate','page':{'items':events,'totalCount':len(events),'hasNextPage':False}}
  return {'updates':updates}
 def policy(self,action):
  pid=action.get('policyId')or str(uuid.uuid4());mutation=copy.deepcopy(action['mutation']);mtype=mutation.pop('type');old=self.get('policy',pid)
  if not old:
   for u in self.fixtures['/api/interactions/update']['updates']:
    if u['data']['type']=='SchedulePoliciesUpdate':old=next((p for p in u['data']['policies']if p['commonData']['id']==pid),None)or old
  if 'CreateRequestFields'in mtype:policy={'type':mtype.replace('CreateRequestFields','Policy'),'commonData':{'id':pid,'index':len(self.rows('policy'))+20,'deleted':False,'policyScope':'USER','status':'ENABLED'}}
  else:
   if old is None:raise HTTPException(404,'Agent not found.')
   policy=old
  if mtype=='PolicyDeleteRequestFields':policy['commonData']['deleted']=bool(mutation.get('deleted',True))
  else:merge(policy,mutation)
  return self.put('policy',pid,policy)
 def event_range(self,event):
  dates=event['eventDate'];tz=ZoneInfo(self.profile()['timezone']['id']);start=parse(dates['start']);end=parse(dates['end'])
  return (start.replace(tzinfo=tz)if start.tzinfo is None else start,end.replace(tzinfo=tz)if end.tzinfo is None else end)
 def calendar_events(self,window=None):
  tz=ZoneInfo(self.profile()['timezone']['id']);today=datetime.now(tz).date();first=datetime.fromisoformat(window['start']).date()if window else today-timedelta(days=7);last=datetime.fromisoformat(window['end']).date()if window else today+timedelta(days=21)
  if (last-first).days>370:raise HTTPException(422,'Choose a calendar range of one year or less.')
  all_events=self.rows('event')
  for event in all_events:event.update({'canModify':True,'canDelete':True,'isOrganizer':True,'freeBusy':'FREE'if event.get('transparency')=='TRANSPARENT'else'BUSY'})
  events=[e for e in all_events if not e.get('recurrence')];schemes=self.get('settings','/api/timeschemes',self.fixtures['/api/timeschemes'])
  for master in all_events:
   rule=master.get('recurrence')
   if not rule:continue
   recurrence_tz=ZoneInfo(master.get('recurrenceTimezone') or tz.key);origin=parse(master['eventDate']['start']);origin=origin.replace(tzinfo=recurrence_tz) if origin.tzinfo is None else origin.astimezone(recurrence_tz);duration=parse(master['eventDate']['end'])-parse(master['eventDate']['start']);day=max(first,origin.date());policy=next((p for p in self.rows('policy')if master['id']in json.dumps(p.get('eventMatcher',{}))),None)
   if policy and (policy['commonData'].get('status')=='DISABLED'or policy['commonData'].get('deleted')):continue
   for day in occurrence_days(rule,origin,first,last):
    start=wall_start(day,origin)
    if start is None:continue
    if True:
     end=(start.astimezone(timezone.utc)+duration).astimezone(recurrence_tz);original_start=start
     if policy:
      scheme=next((t for t in schemes if t['id']==policy.get('timePolicy',{}).get('timeSchemeId')),None)
      hours=(scheme or {}).get('policy',{}).get('dayHours',{}).get(day.strftime('%A').upper(),{}).get('intervals',[])
      chosen=None
      for span in hours:
       low=datetime.combine(day,datetime.strptime(span['start'],'%H:%M:%S').time(),tz);high=datetime.combine(day,datetime.strptime(span['end'],'%H:%M:%S').time(),tz)
       if day==today:low=max(low,datetime.now(tz))
       candidates=[max(low,start)]+[low+timedelta(minutes=15*i)for i in range(max(0,int((high-low).total_seconds()/900)))]
       for candidate in candidates:
        finish=candidate+duration
        if finish<=high and not any(self.event_range(e)[0]<finish and self.event_range(e)[1]>candidate for e in events if e.get('transparency')!='TRANSPARENT'or e.get('recurringEventId')):
         chosen=candidate;break
       if chosen:break
      if chosen:start=chosen;end=start+duration
      else:continue
     e=copy.deepcopy(master);e.pop('recurrence',None);e['recurringEventId']=master['id'];e['id']=master['id']+'_'+day.isoformat();e['key']='200002/'+e['id'];e['eventId']=e['id'];e['eventDate']={'type':'FixedDateTimeRange','start':start.isoformat(),'end':end.isoformat()};e['originalStart']=original_start.isoformat();e['allowedEditTypes']={'types':['THIS','THIS_AND_FOLLOWING','ALL'],'reason':'ORGANIZER'}
     if not self.get('event-cancel',e['key'])and not any(x['key']==e['key']for x in events):events.append(e)
  return events
 def plan(self):
  tz=ZoneInfo(self.profile()['timezone']['id']);current=datetime.now(tz);today=current.date();tasks=[t for t in self.rows('task')if not t['completed']];tasks.sort(key=lambda t:(t.get('priority')or'P2',t.get('due')or'9999',t.get('sortOrder',0)));ids=[t['id']for t in tasks]
  schemes=self.get('settings','/api/timeschemes',self.fixtures['/api/timeschemes']);work=next(t for t in schemes if t['policyType']=='WORK');hours=work['policy']['dayHours'].get(today.strftime('%A').upper(),{}).get('intervals',[]);events=self.calendar_events({'start':today.isoformat(),'end':today.isoformat()});blocks=[]
  for span in hours:
   start=max(current,datetime.combine(today,datetime.strptime(span['start'],'%H:%M:%S').time(),tz));end=datetime.combine(today,datetime.strptime(span['end'],'%H:%M:%S').time(),tz)
   for event in sorted(events,key=lambda e:self.event_range(e)[0]):
    if event.get('transparency')=='TRANSPARENT':continue
    low,high=self.event_range(event)
    if high<=start or low>=end:continue
    if low>start:blocks.append({'start':start.isoformat(),'end':low.isoformat(),'recommendations':ids,'takeoverEventKeys':[]})
    start=max(start,high)
   if start<end:blocks.append({'start':start.isoformat(),'end':end.isoformat(),'recommendations':ids,'takeoverEventKeys':[]})
  at_risk=[t['id']for t in tasks if t.get('due')and parse(t['due'])<current]
  return {'window':{'start':today.isoformat(),'end':today.isoformat()},'tasks':tasks,'atRisk':[],'searches':[{'blocks':blocks,'atRisk':[]}],'timeline':[{**b,'recommendations':[{'taskId':i}for i in b['recommendations']]}for b in blocks]}
 def link(self,data,key=None):
  old=self.get('link',key)if key else None
  if key and old is None:raise HTTPException(404,'Scheduling Link not found.')
  link=merge(old or {'id':str(uuid.uuid4()),'created':now(),'fourOhFourAlerts':[],'resolvedBrandingMode':'RECLAIM','branding':{'mode':'RECLAIM'},'locationOptions':[],'enabled':True,'hidden':False,'iconType':'LIGHT'},data)
  if not str(link.get('title','')).strip():raise HTTPException(422,'Enter a Scheduling Link name.')
  if not link.get('durations')or any(not isinstance(d,(int,float))or d<=0 or d>1440 for d in link['durations']):raise HTTPException(422,'Choose a valid duration.')
  slug=link.get('slug','')
  if not slug or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-'for c in slug):raise HTTPException(422,'Use letters, numbers and hyphens for the link URL.')
  if any(l['slug']==slug and l['id']!=link['id']for l in self.rows('link')):raise HTTPException(409,'This link URL is already in use.')
  self.validate_link_rules(link)
  profile=self.profile();owner={'userId':'100001','email':self.account['email_normalized'],'name':self.account['display_name'],'firstName':self.account['display_name'],'lastName':'','avatarUrl':'','reclaimUser':True};link['owner']=owner;link['hostId']='100001';link['userSlug']=self.get('settings','user-slug',{'slug':'local-'+hashlib.sha256(self.owner.encode()).hexdigest()[:10]})['slug'];link['pageSlug']=link['userSlug'];link['linkGroupName']=self.account['display_name']+"'s Booking Page"
  schemes=self.get('settings','/api/timeschemes',self.fixtures['/api/timeschemes']);policy=next(t['policy']for t in schemes if t['policyType']=='MEETING');link['effectiveTimePolicy']=policy
  organizers=[]
  for item,peer,account in self.resolve_organizers(link,strict=True):
   schemes=peer.get('settings','/api/timeschemes',peer.fixtures['/api/timeschemes']);resolved=next(t['policy']for t in schemes if t['policyType']=='MEETING')
   person={'userId':item['userId'],'email':account['email_normalized'],'name':account['display_name'],'firstName':account['display_name'],'lastName':'','avatarUrl':'','reclaimUser':True}
   organizers.append({**item,'organizer':person,'timezone':peer.profile()['timezone'],'resolvedTimePolicy':resolved,'validConferenceTypes':[],'status':'ACTIVE','role':'HOST'})
  link['organizers']=organizers
  return self.normalize('link',self.put('link',link['id'],link))
 def availability(self,link,day,duration,zone_id=None,ignore_meeting=None):return self.group_availability(link,day,duration,zone_id,ignore_meeting)
 def booking(self,link,data,ignore_meeting=None):
  name=str(data.get('inviteeName')or data.get('name')or'').strip();email=str(data.get('inviteeEmail')or data.get('email')or'').strip();start=parse(data.get('start'));end=parse(data.get('end'))
  if start.tzinfo is None or end.tzinfo is None:raise HTTPException(422,'Specify a timezone for the meeting.')
  duration=int((end-start).total_seconds()/60);survey=self.survey_response(link,data)
  if not name or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise HTTPException(422,'Enter your name and email.')
  if duration not in link['durations']:raise HTTPException(422,'This duration is not offered.')
  day=start.astimezone(ZoneInfo(self.profile()['timezone']['id'])).date().isoformat()
  slot=next((slot for slot in self.availability(link,day,duration,ignore_meeting=ignore_meeting) if parse(slot['startTime'])==start and parse(slot['endTime'])==end),None)
  if not slot:raise HTTPException(409,'This time is no longer available. Choose another time.')
  chosen=self.choose_organizers(link,slot,ignore_meeting)
  event=self.event({'type':'AddEventAction','title':link.get('meetingTitle','{host} and {attendee}').replace('{host}',self.account['display_name']).replace('{attendee}',name),'description':str(data.get('message')or'')+'\n'+'\n'.join(r['question']['questionValue']+': '+r['answer']['value']for r in survey['responses']),'dateRange':{'type':'FixedDateTimeRange','start':start.isoformat(),'end':end.isoformat()},'calendarId':200002,'priority':link.get('priority','P2'),'attendees':[{'email':email,'displayName':name}]});mid=str(uuid.uuid4());attendee={'email':email,'name':name,'firstName':name,'lastName':'','avatarUrl':'','reclaimUser':False};legacy={'eventId':event['id'],'title':event['title'],'startTime':start.isoformat(),'endTime':end.isoformat(),'calendarId':200002,'status':'PUBLISHED'}
  meeting={'meetingId':mid,'event':legacy,'eventKey':event['key'],'schedulingLink':link,'schedulingLinkId':link['id'],'organizer':link['owner'],'organizers':[],'attendee':attendee,'userSlug':{'slug':link['userSlug']},'meetingLocation':data.get('meetingLocation'),'status':'CONFIRMED','surveyResponse':survey,'ccEmails':data.get('ccEmails',[])}
  participants=[]
  for item,peer,account in chosen:
   if peer.owner==self.owner:entry=event
   else:entry=peer.event({'type':'AddEventAction','title':event['title'],'description':event.get('description',''),'dateRange':event['eventDate'],'attendees':[{'email':email,'displayName':name}]})
   entry['_bookingBuffers']=list(self.buffer_minutes(link));peer.put('event',entry['key'],entry);participants.append({'accountId':account['account_id'],'eventKey':entry['key'],'userId':item['userId']})
  if not any(peer.owner==self.owner for _,peer,_ in chosen):self.delete('event',event['key'])
  meeting.update(participantEvents=participants,assignedOrganizerIds=[i['userId']for i,_,_ in chosen],organizers=[{'organizer':{**i['organizer'],'attendanceType':i['attendanceType']},'isHost':index==0} for index,(i,_,_) in enumerate(chosen)],bookedAt=now())
  if chosen:meeting['organizer']=chosen[0][0]['organizer']
  return self.put('booking',mid,meeting)
 def notify_meeting(self,meeting,origin,purpose="confirmation"):
  recipients=sorted(set([meeting['attendee']['email'],self.account['email_normalized']]+[(o.get('organizer') or o)['email']for o in meeting.get('organizers',[])]+meeting.get('ccEmails',[])));state=meeting.get('status','CONFIRMED');key=('reminder:'if purpose=='reminder'else'')+meeting['meetingId']+':'+state+':'+meeting['event']['startTime']
  if self.get('mail',key):return
  host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
  if host not in ['127.0.0.1','localhost','::1','mailpit']:raise HTTPException(503,'Local email service is not configured.')
  msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@reclaim.clone.test');msg['To']=', '.join(recipients);msg['Subject']=('Meeting reminder: 'if purpose=='reminder'else'Meeting cancelled: 'if state=='CANCELLED'else'Meeting confirmed: ')+meeting['event']['title'];message=meeting['event']['title']+'\n'+meeting['event']['startTime']+' – '+meeting['event']['endTime'];message+='\n\n'+str(meeting['schedulingLink'].get('reminderEmailMessage',''))if purpose=='reminder'else'';msg.set_content(message+'\n\nManage your meeting: '+origin.rstrip('/')+'/meeting/'+meeting['meetingId'])
  try:
   with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT',1025)),timeout=5)as smtp:
    refused=smtp.send_message(msg)
    if refused:raise RuntimeError('Recipient refused')
  except Exception:raise HTTPException(503,'Could not send meeting email. Please try again.')
  self.put('mail',key,{'status':'SMTP_SENT','recipients':recipients,'sentAt':now()})
 def handle(self,key,method,data,query):
  handled,result=self.team_handle(key,method,data,query)
  if handled:return handled,result
  meeting_match=re.fullmatch(r'/api/scheduling-link/meeting/([^/]+)(?:/(V2|cancel))?',key)
  if meeting_match:
   mid,action=meeting_match.groups();meeting=self.get('booking',mid)
   if meeting is None:raise HTTPException(404,'Meeting not found.')
   if method=='GET':return True,meeting
   if method=='DELETE'or action=='cancel':
    if meeting.get('status')!='CANCELLED':
     self.clear_participant_events(meeting)
     if self.get('event',meeting['eventKey']):self.delete('event',meeting['eventKey'])
    meeting['status']='CANCELLED';meeting['event']['status']='CANCELLED';return True,self.put('booking',mid,meeting)
   if method in ['PATCH','PUT']:
    link=self.get('link',meeting['schedulingLinkId'])
    if meeting.get('status')=='CANCELLED'or not link or not link['enabled']:raise HTTPException(409,'This meeting cannot be rescheduled.')
    updated=self.booking(link,{'surveyResponse':meeting.get('surveyResponse'),**data,'inviteeName':meeting['attendee']['name'],'inviteeEmail':meeting['attendee']['email']},ignore_meeting=mid);self.clear_participant_events(meeting);
    if self.get('event',meeting['eventKey']):self.delete('event',meeting['eventKey'])
    self.delete('booking',updated['meetingId']);updated['meetingId']=mid;return True,{'data':self.put('booking',mid,updated)}
  if key.startswith(('/api/scheduling-link/for-user-slug/','/api/scheduling-link/group-by-slug/'))and method=='GET':
   group=self.group_by_slug(key.rsplit('/',1)[-1])
   if not group:raise HTTPException(404,'Booking page not found.')
   if '/group-by-slug/'in key:return True,group
   return True,[l for l in self.rows('link')if l['id']in group['linkIds']and l['enabled']and not l.get('hidden')]
  if key.startswith('/api/scheduling-link/for-user-link-slug/')and method=='GET':
   group_slug,slug=key.split('/')[-2:];found=next((l for l in self.rows('link')if l['slug']==slug and l['pageSlug']==group_slug and l['enabled']),None)
   if not found:raise HTTPException(404,'Scheduling Link not found.')
   return True,found
  match=re.fullmatch(r'/api/scheduling-link/([^/]+)/(availability/V[23]|meeting/availability/V2|meeting/V2|meetings)',key)
  if match:
   lid,action=match.groups();link=self.get('link',lid)
   if not link:raise HTTPException(404,'Scheduling Link not found.')
   if action=='meetings'and method=='GET':return True,[b for b in self.rows('booking')if b['schedulingLinkId']==lid]
   if action=='meeting/V2'and method=='POST':return True,{'data':self.booking(link,data)}
   if action.startswith('availability')and method=='GET':
    zone=query.get('zoneId',self.profile()['timezone']['id']);today=datetime.now(ZoneInfo(zone)).date();duration=int(query.get('durationMinutes',link.get('defaultDuration',30)));days={}
    for offset in range(min(90,int(link.get('daysIntoFuture')or 60))+1):
     day=(today+timedelta(days=offset)).isoformat();days[day]=bool(self.availability(link,day,duration,zone,query.get('meetingId')or query.get('rescheduleMeetingId')))
    return True,{'days':days,'tz':{'id':zone,'displayName':zone,'abbreviation':zone}}
   if action=='meeting/availability/V2'and method=='GET':
    day=query.get('date',datetime.now().date().isoformat());return True,{'availableTimes':{str(d):self.availability(link,day,d,query.get('zoneId'),query.get('meetingId')or query.get('rescheduleMeetingId'))for d in link['durations']},'inviteeEvents':[]}
  if key.startswith('/api/schedule-policy/templates/instantiated/')and method=='GET'and key in self.fixtures:
   value=copy.deepcopy(self.fixtures[key]);sequence=value.get('instantiated',{}).get('fallbackPolicyCreationSequence',[]);ids={}
   for action in sequence:
    if action.get('policyId'):ids[action['policyId']]=str(uuid.uuid4())
    if action.get('eventId'):ids[action['eventId']]=uuid.uuid4().hex
   for action in sequence:
    if action.get('dateRange'):
     dates=action['dateRange'];tz=ZoneInfo(self.profile()['timezone']['id']);original=parse(dates['start']).astimezone(tz);duration=parse(dates['end'])-parse(dates['start']);current=datetime.now(tz);start=original.replace(year=current.year,month=current.month,day=current.day)
     if start<current:start=current+timedelta(minutes=15)
     dates['start']=start.isoformat();dates['end']=(start+duration).isoformat()
   serialized=json.dumps(value)
   for old,new in ids.items():serialized=serialized.replace(old,new)
   return True,json.loads(serialized)
  if key.startswith('/api/users/trait/')and method=='POST':
   self.put('trait',key,query)
   if key.endswith('/ONBOARD_SCHEDULING_LINKS'):self.put('settings','profile',merge(self.get('settings','profile',{}),{'features':{'onboard':{'schedulingLinks':True}}}))
   return True,self.profile()
  if key in ['/api/scheduling-link','/api/scheduling-link/recent']and method=='GET':return True,self.rows('link')
  if key=='/api/scheduling-link/user-slug':
   existing=self.get('settings','user-slug',{'slug':'local-'+hashlib.sha256(self.owner.encode()).hexdigest()[:10]})
   if method=='POST':
    slug=data.get('slug','')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,79}',slug):raise HTTPException(422,'Use 2–80 lowercase letters, numbers or hyphens.')
    owner=self.slug_owner(slug)
    if owner and (owner!=self.owner or any(g['slug']==slug for g in self.rows('group'))):raise HTTPException(409,'This booking page URL is already in use.')
    for link in self.rows('link'):
     link['userSlug']=slug;link['pageSlug']=slug;self.put('link',link['id'],link)
    return True,self.put('settings','user-slug',{'slug':slug})
   return True,existing
  if key=='/api/scheduling-link/user-slug/exists'and method=='GET':
   if self.slug_owner(query.get('slug')):return True,True
   raise HTTPException(404,'URL available.')
  if key=='/api/scheduling-link/slug-exists'and method=='GET':
   if any(x['slug']==query.get('slug')for x in self.rows('link')):return True,True
   raise HTTPException(404,'URL available.')
  if key=='/api/scheduling-link/group':
   if method=='GET':return True,self.groups()
   if method=='POST':return True,self.save_group(data)
  group_match=re.fullmatch(r'/api/scheduling-link/group/([^/]+)(/moveLinks)?',key)
  if group_match:
   gid,moving=group_match.groups()
   if method=='PATCH':return True,self.save_group(data,gid)
   if method=='DELETE':self.remove_group(gid,query.get('moveLinksToGroupId')if moving else None);return True,None
  if key=='/api/scheduling-link'and method=='POST':return True,self.link(data)
  if key.startswith('/api/scheduling-link/')and len(key.split('/'))==4:
   lid=key.split('/')[-1];found=self.get('link',lid)
   if found:
    if method=='GET':return True,found
    if method in ['PATCH','PUT']:return True,self.link(data,lid)
    if method=='DELETE':self.delete('link',lid);return True,None
   elif re.fullmatch(r'[0-9a-f-]{36}',lid):raise HTTPException(404,'Scheduling Link not found.')
  if key.startswith('/api/reclaim-tasks'):

   suffix=key.removeprefix('/api/reclaim-tasks').strip('/')
   if method=='GET'and suffix in ['','page']:
    rows=self.tasks(query)
    if suffix=='page':
     offset=int(query.get('offset',0));size=max(1,min(200,int(query.get('count',query.get('limit',query.get('pageSize',50))))));after=query.get('after')or query.get('cursor')
     if after:offset=next((i+1 for i,t in enumerate(rows)if t['id']==after),offset)
     page=rows[offset:offset+size];return True,{'items':page,'totalCount':len(rows),'hasNextPage':offset+size<len(rows),'first':page[0]['id']if page else None,'last':page[-1]['id']if page else None,'count':size}
    return True,rows
   if method=='POST'and not suffix:return True,self.task(data)
   taskkey='RECLAIM:'+suffix.split('/')[0]
   if method=='GET':
    t=self.get('task',taskkey)
    if t is None:raise HTTPException(404,'Task not found.')
    return True,t
   if method=='PATCH'and suffix.endswith('/reindex'):
    rows=sorted(self.rows('task'),key=lambda t:t.get('sortOrder',0));moving=next((t for t in rows if t['id']==taskkey),None);relative='RECLAIM:'+str(data.get('relativeTaskId','')).removeprefix('RECLAIM:');direction=data.get('reindexDirection')
    if moving is None or not any(t['id']==relative for t in rows):raise HTTPException(404,'Task not found.')
    if direction not in ['BEFORE','AFTER']:raise HTTPException(422,'Invalid reorder direction.')
    if taskkey==relative:return True,moving
    rows.remove(moving);position=next(i for i,t in enumerate(rows)if t['id']==relative)+(direction=='AFTER');rows.insert(position,moving)
    for i,t in enumerate(rows):t['sortOrder']=(i+1)*1000;self.put('task',t['id'],t)
    return True,moving
   if method in ['PATCH','PUT']:return True,self.task(data,taskkey)
   if method=='DELETE':self.delete('task',taskkey);return True,None
  if key=='/api/gtd-tasks/search/plan'and method=='POST':return True,self.plan()
  if key in ['/api/interactions/update','/api/interactions']and method=='POST':
   result=self.updates(data)
   if key.endswith('/update'):return True,result
   current={u['data']['type']:u['data']for u in result['updates']if u['part']=='CURRENT'};events=current['CalendarEventsUpdate']['events'];empty={'mutatedEvents':[],'mutatedPolicies':[],'problems':[],'groupedProblems':[],'actionsTaken':[],'backgroundActions':[],'llmProblemCount':0}
   return True,{'session':current['SessionUpdate']['session'],'currentEvents':events,'currentPolicies':current['SchedulePoliciesUpdate']['policies'],'preview':empty,'expected':empty,'recommendations':[]}

  if key=='/api/users/current'and method=='GET':return True,self.profile()
  policy_events=re.fullmatch(r'/api/schedule-policy/([^/]+)/events',key)
  if policy_events and method=='GET':
   policy=self.get('policy',policy_events[1])
   if policy is None:raise HTTPException(404,'Agent not found.')
   events=[e for e in self.calendar_events()if e.get('recurringEventId')and e['recurringEventId']in json.dumps(policy.get('eventMatcher',{}))];return True,{'events':events}
  if key=='/api/recommended-tasks/groups'and method=='GET':return True,[]
  if key=='/api/gtd-tasks/providers'and method=='GET':return True,[{'sourceType':'RECLAIM','displayName':'Reclaim Tasks','openTaskCount':sum(not t['completed']for t in self.rows('task')),'listSupported':True}]
  if key=='/api/events/v2'and method=='GET':return True,self.rows('event')
  if key=='/api/events/utils/to-v2'and method=='POST':return True,[e for e in self.rows('event')if e['key']in data]
  if key=='/api/notification-settings':
   existing=self.get('settings',key,self.fixtures[key])
   if method=='GET':return True,existing
   if method in ['PUT','PATCH']:return True,self.put('settings',key,merge(existing,data))
  if key.startswith('/api/timeschemes'):
   if isinstance(data,dict)and data.get('features')is None:data.pop('features',None)
   rows=self.get('settings','/api/timeschemes',self.fixtures['/api/timeschemes']);suffix=key.removeprefix('/api/timeschemes').strip('/')
   for row in rows:
    if row.get('features')is None:row['features']=next((f['features']for f in self.fixtures['/api/timeschemes']if f['id']==row['id']),['TASK_ASSIGNMENT','SMART_HABIT','SMART_MEETING','SCHEDULING_LINK_MEETING'])
   if method=='GET':
    if not suffix or suffix.startswith('filter-by-feature'):return True,rows
    found=next((t for t in rows if t['id']==suffix),None)
    if not found:raise HTTPException(404,'Hours not found.')
    return True,found
   if method=='POST'and not suffix:
    value={**data,'id':str(uuid.uuid4()),'userId':'100001','status':'ACTIVE'};rows.append(value)
   elif method in ['PUT','PATCH','DELETE']and suffix:
    value=next((t for t in rows if t['id']==suffix),None)
    if not value:raise HTTPException(404,'Hours not found.')
    if method=='DELETE':rows.remove(value)
    else:merge(value,data)
   else:return False,None
   for row in rows:
    for day,hours in row.get('policy',{}).get('dayHours',{}).items():
     for interval in hours.get('intervals',[]):
      if interval['start']>=interval['end']:raise HTTPException(422,'Hours must end after they start.')
   self.put('settings','/api/timeschemes',rows);return True,value
  if key=='/api/users/current'and method=='PATCH':
   safe={k:v for k,v in data.items()if k in ['name','locale','settings','features','startOfWeek']}
   self.put('settings','profile',merge(self.get('settings','profile',{}),safe));return True,self.profile()
  if key=='/api/users/current/timezone-settings'and method=='PUT':
   tz=data.get('homeTimezone')or data.get('timezone')or data.get('tz')
   if tz:
    if isinstance(tz,dict):tz=tz['id']
    try:ZoneInfo(tz)
    except Exception:raise HTTPException(422,'Unknown timezone.')
    self.put('settings','profile',merge(self.get('settings','profile',{}),{'timezone':{'id':tz,'displayName':tz,'abbreviation':tz},'features':{'timezoneSettings':data}}))
   return True,self.profile()
  if key=='/api/users/current/features/app-notifications'and method=='PUT':
   self.put('settings','profile',merge(self.get('settings','profile',{}),{'features':{'appNotifications':data}}));return True,self.profile()

  return False,None
