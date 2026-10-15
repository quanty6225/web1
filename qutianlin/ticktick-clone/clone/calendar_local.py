"""Owned calendar feed tokens and calendar event serialization."""
import secrets,datetime
from fastapi import HTTPException

def ics(tasks):
 def escape(value):return str(value or '').replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,').replace('\r','')
 def date(value):
  try:return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).strftime('%Y%m%dT%H%M%S')
  except (ValueError,AttributeError):return None
 rows=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//TickTick Local//Calendar//EN','CALSCALE:GREGORIAN']
 for task in tasks:
  start=date(task.get('startDate') or task.get('dueDate'))
  if not start or task.get('deleted'):continue
  rows+=['BEGIN:VEVENT','UID:'+escape(task['id'])+'@ticktick.local','DTSTAMP:'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),'DTSTART:'+start,'SUMMARY:'+escape(task.get('title')),'DESCRIPTION:'+escape(task.get('content'))]
  end=date(task.get('dueDate'))
  if end and end!=start:rows.append('DTEND:'+end)
  rows+=['STATUS:'+('COMPLETED' if task.get('status') else 'CONFIRMED'),'END:VEVENT']
 return '\r\n'.join(rows+['END:VCALENDAR',''])

def handle(path,method,body,req,a,d,db,save,uid):
 feeds=d.setdefault('calendarFeeds',{})
 if path=='calendar/feeds/code':return list(feeds.values())
 if path.startswith('calendar/feeds/code/new/'):
  pid=path.rsplit('/',1)[-1]
  if pid not in ['all','inbox'+str(uid),*d['projects']]:raise HTTPException(404,'List not found')
  feeds[pid]={'projectId':pid,'code':secrets.token_urlsafe(32),'includeDone':req.query_params.get('includeDone')=='true'};save(db,a,d);return feeds[pid]
 if path.startswith('calendar/feeds/cancel/'):
  ident=path.rsplit('/',1)[-1];pid=next((k for k,v in feeds.items() if ident in [k,v['code']]),None)
  if pid is None:raise HTTPException(404,'Feed not found')
  del feeds[pid];save(db,a,d);return {}
 if path=='countdown/list':return list(d.setdefault('countdowns',{}).values())
 if path=='countdown/batch':
  records=d.setdefault('countdowns',{});result={'id2etag':{},'id2error':{}}
  for action in ['add','update','delete']:
   for item in body.get(action,[]):
    ident=item if isinstance(item,str) else item.get('id') or secrets.token_hex(12)
    if action!='add' and ident not in records:raise HTTPException(404,'Countdown not found')
    if action=='delete':del records[ident]
    else:records[ident]={**records.get(ident,{}),**item,'id':ident,'etag':secrets.token_hex(8)};result['id2etag'][ident]=records[ident]['etag']
  save(db,a,d);return result
 return None
