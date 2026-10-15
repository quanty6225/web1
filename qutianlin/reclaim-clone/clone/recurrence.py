"""Native recurrence contracts: calendar intervals, monthly ordinals and series ends."""
import calendar,copy
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import HTTPException

DAYS=['MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY','SATURDAY','SUNDAY']
MONTHS=[calendar.month_name[i].upper() for i in range(1,13)]

def validate(rule):
 if rule is None:return
 if not isinstance(rule,dict) or rule.get('frequency') not in ('DAILY','WEEKLY','MONTHLY','YEARLY'):raise HTTPException(422,'Choose a supported repeat frequency.')
 interval=rule.get('interval',1)
 if interval is None:interval=1;rule['interval']=1
 if type(interval)is not int or not 1<=interval<=1000:raise HTTPException(422,'Repeat interval must be between 1 and 1000.')
 if rule.get('days') is not None and (not isinstance(rule['days'],list) or not rule['days'] or any(x not in DAYS for x in rule['days'])):raise HTTPException(422,'Choose valid weekdays.')
 for key in ['monthlyDay','yearlyDay']:
  if key not in rule:continue
  value=rule[key]
  if not isinstance(value,dict):raise HTTPException(422,'Invalid monthly or yearly recurrence.')
  if key=='yearlyDay':
   month=value.get('month')
   if month not in MONTHS and (type(month)is not int or not 1<=month<=12):raise HTTPException(422,'Select a month.')
   value=value.get('monthlyDay',{})
  if value.get('dayOfMonth') is not None:
   if type(value['dayOfMonth'])is not int or not 1<=value['dayOfMonth']<=31:raise HTTPException(422,'Select a day from 1 to 31.')
  elif value.get('dayOfWeek') not in DAYS or value.get('week') not in (-1,1,2,3,4,5):raise HTTPException(422,'Select a weekday and week of month.')
 end=rule.get('end') or {};count=rule.get('count',end.get('count'));until=rule.get('until',end.get('until'))
 if count is not None and (type(count)is not int or not 1<=count<=10000):raise HTTPException(422,'Repeat count must be between 1 and 10000.')
 if until is not None:
  try:datetime.fromisoformat(until.replace('Z','+00:00'))
  except (ValueError,TypeError,AttributeError):raise HTTPException(422,'Choose a valid recurrence end date.')
 for key in ('excludedDates','additionalDates'):
  if key in rule:
   if not isinstance(rule[key],list) or len(rule[key])>1000:raise HTTPException(422,'Invalid recurrence exception dates.')
   for value in rule[key]:
    try:date.fromisoformat(value)
    except (ValueError,TypeError):raise HTTPException(422,'Use YYYY-MM-DD for recurrence exceptions.')

def monthly_matches(day,spec,origin):
 if not spec:return day.day==origin.day
 if spec.get('dayOfMonth') is not None:return day.day==spec['dayOfMonth']
 if day.strftime('%A').upper()!=spec.get('dayOfWeek'):return False
 week=spec.get('week',1)
 return day.day+7>calendar.monthrange(day.year,day.month)[1] if week==-1 else (day.day-1)//7+1==week

def occurrence_days(rule,origin,first,last):
 validate(rule);interval=rule.get('interval') or 1;freq=rule['frequency'];end=rule.get('end') or {};count=rule.get('count',end.get('count'));until=rule.get('until',end.get('until'));excluded=set(rule.get('excludedDates',[]));additional={date.fromisoformat(x) for x in rule.get('additionalDates',[])}
 until_dt=datetime.fromisoformat(until.replace('Z','+00:00')) if until else None
 # Count from DTSTART rather than the visible calendar window.
 day=origin.date() if count else max(origin.date(),first);seen=0;result=set()
 while day<=last:
  if until_dt:
   candidate=datetime.combine(day,origin.timetz())
   if until_dt.tzinfo is None:
    if day>until_dt.date():break
   elif candidate>until_dt:break
  elapsed=(day-origin.date()).days;months=(day.year-origin.year)*12+day.month-origin.month
  if freq=='DAILY':match=elapsed%interval==0
  elif freq=='WEEKLY':
   week=(day-timedelta(days=day.weekday())-(origin.date()-timedelta(days=origin.weekday()))).days//7
   match=week%interval==0 and day.strftime('%A').upper() in (rule.get('days') or [origin.strftime('%A').upper()])
  elif freq=='MONTHLY':match=months%interval==0 and monthly_matches(day,rule.get('monthlyDay'),origin)
  else:
   yearly=rule.get('yearlyDay') or {};month=yearly.get('month',origin.month);month=MONTHS.index(month)+1 if isinstance(month,str) else month
   match=(day.year-origin.year)%interval==0 and day.month==month and monthly_matches(day,yearly.get('monthlyDay'),origin)
  if match:
   seen+=1
   if count and seen>count:break
   if day>=first and day.isoformat() not in excluded:result.add(day)
  day+=timedelta(days=1)
 return sorted(result|{day for day in additional if first<=day<=last and day>=origin.date() and day.isoformat() not in excluded})

def wall_start(day,origin):
 value=datetime.combine(day,origin.timetz())
 # An hour skipped by a timezone transition does not denote a real instant.
 if value.astimezone(timezone.utc).astimezone(value.tzinfo).replace(tzinfo=None)!=value.replace(tzinfo=None):return None
 return value

def series_action(business,action,old):
 from business import parse
 scope=action.get('recurrenceEditType','THIS')
 if scope not in ('THIS','ALL','THIS_AND_FOLLOWING','THISANDFOLLOWING'):raise HTTPException(422,'Choose an event recurrence scope.')
 if not old.get('recurringEventId') or scope=='THIS':return None
 prefix=old['key'].split('/')[0]+'/';master_key=prefix+old['recurringEventId'];master=business.get('event',master_key)
 if not master:raise HTTPException(404,'Recurring series not found.')
 zone=ZoneInfo(master.get('recurrenceTimezone') or business.profile()['timezone']['id']);original=parse(master['eventDate']['start']);original=original.replace(tzinfo=zone) if original.tzinfo is None else original.astimezone(zone)
 cutoff=parse(old.get('originalStart',old['eventDate']['start']));cutoff=cutoff.replace(tzinfo=zone) if cutoff.tzinfo is None else cutoff.astimezone(zone)
 following=scope in ('THIS_AND_FOLLOWING','THISANDFOLLOWING');cancel=action['type']=='CancelEventAction'
 with business.connect() as c:
  exceptions=[r for r in business.rows('event') if r.get('recurringEventId')==master['id'] and (not following or parse(r.get('originalStart',r['eventDate']['start'])).date()>=cutoff.date())]
  for value in exceptions:business.delete('event',value['key'])
  for value in business.rows('event-cancel'):
   key=value.get('key')
   if key and key.startswith(master_key+'_') and (not following or key[-10:]>=cutoff.date().isoformat()):business.delete('event-cancel',key)
  if cancel and not following:business.delete('event',master_key);return old
  if following:
   before=len(occurrence_days(master['recurrence'],original,original.date(),cutoff.date()-timedelta(days=1)))
   remaining=(master['recurrence'].get('count') or (master['recurrence'].get('end') or {}).get('count'))
   truncated=copy.deepcopy(master);truncated['recurrence'].pop('count',None);truncated['recurrence'].pop('end',None);truncated['recurrence']['until']=(cutoff-timedelta(microseconds=1)).isoformat();business.put('event',master_key,truncated)
   if cancel:return old
   next_action={**copy.deepcopy(master),**action,'type':'AddEventAction','recurrence':copy.deepcopy(action.get('recurrence',master['recurrence'])),'dateRange':copy.deepcopy(action.get('dateRange',old['eventDate']))}
   if remaining and 'recurrence' not in action:next_action['recurrence'].pop('end',None);next_action['recurrence']['count']=max(1,remaining-before)
   for key in ('eventKey','eventId','recurrenceEditType'):next_action.pop(key,None)
   result=business.event(next_action)
   for policy in business.rows('policy'):
    if master['id'] in str(policy.get('eventMatcher',{})):
     import json,uuid
     new=json.loads(json.dumps(policy).replace(master['id'],result['id']));new['commonData']['id']=str(uuid.uuid4());business.put('policy',new['commonData']['id'],new)
   return result
  update={**action,'eventKey':master_key};update.pop('recurrenceEditType',None)
  if action.get('dateRange'):
   changed=parse(action['dateRange']['start']);current=parse(old['eventDate']['start']);start=parse(master['eventDate']['start'])+(changed-current);finish=start+(parse(action['dateRange']['end'])-changed)
   update['dateRange']={**action['dateRange'],'start':start.isoformat(),'end':finish.isoformat()}
  return business.event(update)
