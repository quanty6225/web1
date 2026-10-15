"""Local Scheduling Link groups and availability rules derived from the native client."""
import copy,hashlib,re,uuid
from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo
from fastapi import HTTPException

class Scheduling:
 def primary_group(self):
  group=copy.deepcopy(self.fixtures['/api/scheduling-link/group'][0])
  group.update(self.get('settings','primary-group',{}))
  group.update({'main':True,'slug':self.get('settings','user-slug',{'slug':'local-'+hashlib.sha256(self.owner.encode()).hexdigest()[:10]})['slug']})
  if not self.get('settings','primary-group'):group['name']=self.account['display_name']+"'s Booking Page"
  return group
 def decorate_link(self,link):
  main=self.primary_group();gid=link.get('linkGroupId')or main['id'];group=main if gid==main['id']else self.get('group',gid)
  if group is None:group=main;gid=main['id']
  link.update({'linkGroupId':gid,'pageSlug':group['slug'],'linkGroupName':group['name'],'userSlug':main['slug']})
  mode=link.get('brandingMode')or 'INHERIT'
  if mode=='INHERIT':mode=group.get('brandingMode','RECLAIM')
  link['resolvedBrandingMode']=mode;link['branding']={'mode':mode,**(group.get('branding',{})if mode=='CUSTOM'else{})}
  return link
 def groups(self):
  groups=[self.primary_group(),*self.rows('group')];links=self.rows('link')
  for g in groups:g['linkIds']=[l['id']for l in links if l['linkGroupId']==g['id']]
  return groups
 def group_by_slug(self,slug):return next((g for g in self.groups()if g['slug']==slug),None)
 def save_group(self,data,key=None):
  main=self.primary_group();old=next((g for g in self.groups()if g['id']==key),None)if key else None
  if key and old is None:raise HTTPException(404,'Booking page group not found.')
  group=copy.deepcopy(old or {'id':str(uuid.uuid4()),'main':False,'brandingMode':'RECLAIM','branding':{'mode':'RECLAIM'},'linkIds':[]})
  for field in ['name','description','slug','brandingMode','branding']:
   if field in data:group[field]=copy.deepcopy(data[field])
  if not str(group.get('name','')).strip():raise HTTPException(422,'Enter a group name.')
  slug=group.get('slug','')
  if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,78}[a-z0-9]',slug):raise HTTPException(422,'Use 2–80 lowercase letters, numbers or hyphens; end with a letter or number.')
  owner=self.slug_owner(slug)
  if owner and (owner!=self.owner or any(g['slug']==slug and g['id']!=group['id']for g in self.groups())):raise HTTPException(409,'This booking page URL is already in use.')
  links=self.rows('link');ids=data.get('linkIds',group.get('linkIds',[]))
  if not isinstance(ids,list)or any(not isinstance(i,str)for i in ids):raise HTTPException(422,'Invalid link selection.')
  if not set(ids)<={l['id']for l in links}:raise HTTPException(404,'A selected link does not belong to this account.')
  if group['main']:
   # Primary links cannot be removed without assigning a destination group.
   if not set(group['linkIds'])<=set(ids):raise HTTPException(422,'Move links to another group before removing them.')
   self.put('settings','primary-group',group);self.put('settings','user-slug',{'slug':slug})
  else:self.put('group',group['id'],group)
  for link in links:
   if link['id']in ids:link['linkGroupId']=group['id']
   elif link['linkGroupId']==group['id']:link['linkGroupId']=main['id']
   self.put('link',link['id'],self.decorate_link(link))
  return next(g for g in self.groups()if g['id']==group['id'])
 def remove_group(self,key,destination=None):
  groups=self.groups();group=next((g for g in groups if g['id']==key),None)
  if group is None:raise HTTPException(404,'Booking page group not found.')
  if group['main']:raise HTTPException(422,'The primary booking page cannot be deleted.')
  if destination and (destination==key or not any(g['id']==destination for g in groups)):raise HTTPException(404,'Destination group not found.')
  for link in self.rows('link'):
   if link['linkGroupId']!=key:continue
   if destination:link['linkGroupId']=destination;self.put('link',link['id'],self.decorate_link(link))
   else:self.delete('link',link['id'])
  self.delete('group',key)
 def validate_link_rules(self,link):
  group=link.get('linkGroupId')
  if group and group not in [g['id']for g in self.groups()]:raise HTTPException(404,'Booking page group not found.')
  buffers=link.get('bufferSettings')or{}
  if not isinstance(buffers,dict):raise HTTPException(422,'Invalid buffer settings.')
  for key in ['beforeMinutes','afterMinutes']:
   val=buffers.get(key)
   if val is not None and (isinstance(val,bool)or not isinstance(val,(int,float))or not 0<=val<=1440):raise HTTPException(422,'Buffer time must be between 0 and 1440 minutes.')
  limit=link.get('meetingLimit')
  if limit is not None and (not isinstance(limit,dict)or limit.get('period')not in ['DAILY','WEEKLY']or isinstance(limit.get('limit'),bool)or not isinstance(limit.get('limit'),int)or not 1<=limit['limit']<=1000):raise HTTPException(422,'Choose a positive whole-number daily or weekly limit.')
  for field in ['delayStartUnits','daysIntoFuture']:
   val=link.get(field)
   if val is not None and (isinstance(val,bool)or not isinstance(val,(int,float))or not 0<=val<=365*24):raise HTTPException(422,'Invalid scheduling window.')
  reminder=link.get('reminderEmailDurationMins',1440)
  if (link.get('reminderEmailActive')or link.get('reminderEmailDurationMins'))and (isinstance(reminder,bool)or not isinstance(reminder,(int,float))or not 0<reminder<=525600):raise HTTPException(422,'Choose a positive reminder time of at most one year.')
  survey=link.get('survey')or{}
  if not isinstance(survey,dict)or not isinstance(survey.get('questions',[]),list):raise HTTPException(422,'Invalid screening questions.')
  for question in survey.get('questions',[]):
   if not isinstance(question,dict)or question.get('type')not in ['DROPDOWN','RADIO','EMAIL','MULTI_LINE','ONE_LINE','PHONE_NUMBER']or not str(question.get('questionValue','')).strip():raise HTTPException(422,'Enter a valid screening question.')
   if question['type']in ['DROPDOWN','RADIO']and (not isinstance(question.get('options'),list)or not question['options']or any(not isinstance(o,str)or not o.strip()for o in question['options'])):raise HTTPException(422,'Enter answer choices for this question.')
 def survey_response(self,link,data):
  raw=data.get('surveyResponse')or{};responses=raw.get('responses',[])if isinstance(raw,dict)else None
  if not isinstance(responses,list):raise HTTPException(422,'Invalid screening answers.')
  saved=[]
  for question in (link.get('survey')or{}).get('questions',[]):
   response=next((r for r in responses if isinstance(r,dict)and isinstance(r.get('question'),dict)and r['question'].get('questionValue')==question['questionValue']and r['question'].get('type')==question['type']),{})
   answer=response.get('answer')or{};value=answer.get('value','')if isinstance(answer,dict)else None
   if not isinstance(value,str):raise HTTPException(422,'Enter a text answer.')
   value=value.strip()
   if question.get('isRequired')and not value:raise HTTPException(422,'Answer the required question: '+question['questionValue'])
   if value:
    if question['type']in ['DROPDOWN','RADIO']and value not in question['options']:raise HTTPException(422,'Choose an available answer.')
    if question['type']=='EMAIL'and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',value):raise HTTPException(422,'Enter a valid email answer.')
    if len(value)>(256 if question['type']=='MULTI_LINE'else 100):raise HTTPException(422,'Screening answer is too long.')
   saved.append({'question':copy.deepcopy(question),'answer':{'value':value}})
  return {'responses':saved}
 def buffer_minutes(self,link):
  if link.get('disableBuffers')is True:return 0,0
  settings=link.get('bufferSettings')or{}
  return settings.get('beforeMinutes')or 0,settings.get('afterMinutes')or 0
 def booking_limit_reached(self,link,start,ignore_meeting=None):
  limit=link.get('meetingLimit')
  if not limit:return False
  tz=ZoneInfo(self.profile()['timezone']['id']);day=start.astimezone(tz).date()
  if limit['period']=='WEEKLY':
   first=self.profile().get('settings',{}).get('startOfWeek',self.profile().get('startOfWeek','SUNDAY'));day-=timedelta(days=day.weekday()if first in ['MONDAY',1]else(day.weekday()+1)%7)
  end=day+timedelta(days=7 if limit['period']=='WEEKLY'else 1)
  booked=0
  for b in self.rows('booking'):
   if b['meetingId']==ignore_meeting or b.get('status')=='CANCELLED'or b['schedulingLinkId']!=link['id']:continue
   d=datetime.fromisoformat(b['event']['startTime']).astimezone(tz).date()
   if day<=d<end:booked+=1
  return booked>=limit['limit']
 def available_slots(self,link,day,duration,zone_id=None,ignore_meeting=None):
  tz=ZoneInfo(self.profile()['timezone']['id'])
  try:display_tz=ZoneInfo(zone_id)if zone_id else tz;display_date=datetime.fromisoformat(day).date()
  except (ValueError,KeyError):raise HTTPException(422,'Invalid date or timezone.')
  if duration not in link['durations']:return []
  current=datetime.now(tz);units=link.get('delayStartUnits')or 0;latest=current.date()+timedelta(days=min(365,int(link.get('daysIntoFuture')or 60)));slots=[]
  delay=link.get('delayStart')or 'FROM_NOW_HOURS';earliest=current
  if delay=='FROM_NOW_MINUTES':earliest+=timedelta(minutes=units)
  elif delay=='FROM_NOW_HOURS':earliest+=timedelta(hours=units)
  elif delay=='FROM_NOW_DAYS':earliest+=timedelta(days=units)
  elif delay=='FROM_NOW_START_OF_NEXT_DAY':earliest=datetime.combine(current.date()+timedelta(days=1),time.min,tz)
  elif delay=='FROM_NOW_START_OF_NEXT_WEEK':
   first=self.profile().get('settings',{}).get('startOfWeek',self.profile().get('startOfWeek','SUNDAY'));weekday=0 if first in ['MONDAY',1]else 6;earliest=datetime.combine(current.date()+timedelta(days=(weekday-current.weekday())%7 or 7),time.min,tz)
  if not link.get('enabled')or display_date<current.astimezone(display_tz).date():return slots
  schemes=self.get('settings','/api/timeschemes',self.fixtures['/api/timeschemes']);organizer=next(iter(link.get('organizers')or[{}]));scheme=next((s for s in schemes if s['id']==organizer.get('timeSchemeId')),None)
  policy=organizer.get('oneOffPolicy')if organizer.get('timePolicyType')=='ONE_OFF'else None
  policy=policy or (scheme or {}).get('policy',link['effectiveTimePolicy']);intervals=self.profile()['features'].get('availableMeetingTimes',[0,15,30,45]);anchor=datetime.combine(display_date,time.min,display_tz).astimezone(tz).date();before,after=self.buffer_minutes(link)
  ignore=self.get('booking',ignore_meeting)if ignore_meeting else None;ignore_event=ignore.get('eventKey')if ignore and ignore.get('schedulingLinkId')==link['id']else None
  bookings={b['eventKey']:b for b in self.rows('booking')if b.get('status')!='CANCELLED'}
  for offset in [-1,0,1,2]:
   date=anchor+timedelta(days=offset)
   if date>latest:continue
   if link.get('startDate')and date<datetime.fromisoformat(link['startDate'][:10]).date():continue
   if link.get('endDate')and date>datetime.fromisoformat(link['endDate'][:10]).date():continue
   hours=policy.get('dayHours',{}).get(date.strftime('%A').upper(),{}).get('intervals',[])
   if not hours:continue
   events=self.calendar_events({'start':(date-timedelta(days=1)).isoformat(),'end':(date+timedelta(days=1)).isoformat()});busy=[]
   for event in events:
    if event['key']==ignore_event or event['key']in link.get('_ignore_event_keys',[]) or event.get('transparency')=='TRANSPARENT':continue
    low,high=self.event_range(event);booking=bookings.get(event['key']);eb,ea=self.buffer_minutes(booking['schedulingLink'])if booking else event.get('_bookingBuffers',(0,0));busy.append((low-timedelta(minutes=eb),high+timedelta(minutes=ea)))
   for span in hours:
    start=datetime.combine(date,datetime.strptime(span['start'],'%H:%M:%S').time(),tz);end=datetime.combine(date,datetime.strptime(span['end'],'%H:%M:%S').time(),tz)
    if self.booking_limit_reached(link,start,ignore_meeting):continue
    while start+timedelta(minutes=duration)<=end:
     finish=start+timedelta(minutes=duration);low=start-timedelta(minutes=before);high=finish+timedelta(minutes=after)
     if start>=earliest and start.minute in intervals and start.astimezone(display_tz).date()==display_date and not any(a<high and b>low for a,b in busy):slots.append({'startTime':start.astimezone(display_tz).isoformat(),'endTime':finish.astimezone(display_tz).isoformat(),'isSuggested':not slots,'organizerIds':['100001']})
     start+=timedelta(minutes=5)
  return slots
