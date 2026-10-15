"""Date-driven calendars and local iCalendar exports, independent of captured months."""
import calendar,copy,json,re
from datetime import date,datetime,timedelta,timezone
from urllib.parse import urlencode,urlsplit,parse_qsl
from lxml import html,etree
from fastapi import HTTPException,Request,APIRouter
from fastapi.responses import Response
from record_operations import metadata,fields_for,DATA

def timestamp(value):
    try:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError):raise HTTPException(422,'Choose a valid start and end date.')

def validate(fields):
    start=fields.get('schedule_entry[starts_at]');end=fields.get('schedule_entry[ends_at]')
    if not start or not end:raise HTTPException(422,'Choose a start and end date.')
    if timestamp(end)<timestamp(start):raise HTTPException(422,'The event cannot end before it starts.')
    for key in ['week_interval','month_interval']:
        value=fields.get('schedule_entry[recurrence_schedule]['+key+']')
        if value and (not str(value).isdigit() or not 1<=int(value)<=999):raise HTTPException(422,'Choose a valid repeat interval.')
    if fields.get('schedule_entry[recurs_until]'):timestamp(fields['schedule_entry[recurs_until]'])

def records(connection,owner):
    result={r['id']:r for r in DATA['records'].values() if r['kind']=='schedule_entries'}
    for row in connection.execute('SELECT id FROM bc_records WHERE owner=? AND kind="schedule_entries"',(owner,)):
        record=metadata(connection,owner,row['id'])
        if record:result[record['id']]=record
    return [(r,fields_for(connection,owner,r)) for r in result.values()]

def starts_on(fields,day):
    start=timestamp(fields['schedule_entry[starts_at]']).date()
    if day<start:return False
    until=fields.get('schedule_entry[recurs_until]')
    if until and day>timestamp(until).date():return False
    frequency=fields.get('schedule_entry[recurrence_schedule][frequency]','')
    if not frequency:return day==start
    delta=(day-start).days;months=(day.year-start.year)*12+day.month-start.month
    if frequency=='every_day':return True
    if frequency=='every_weekday':return day.weekday()<5
    if frequency in ['every_week','every_other_week']:return delta%(14 if frequency=='every_other_week' else 7)==0
    if frequency=='every_year':return (day.month,day.day)==(start.month,start.day)
    if frequency=='every_day_of_month':return day.day==start.day
    if frequency=='every_month':return day.weekday()==start.weekday() and (day.day-1)//7==(start.day-1)//7
    if frequency=='custom_week':
        interval=max(1,int(fields.get('schedule_entry[recurrence_schedule][week_interval]') or 1));days=fields.get('schedule_entry[recurrence_schedule][days][]',[(start.weekday()+1)%7]);days=days if isinstance(days,list) else [days]
        return ((delta+start.weekday())//7)%interval==0 and str((day.weekday()+1)%7) in map(str,days)
    if frequency=='custom_month':
        interval=max(1,int(fields.get('schedule_entry[recurrence_schedule][month_interval]') or 1));return months%interval==0 and day.day==start.day
    return day==start

def on_day(fields,day):
    if fields.get('_record_status','active')!='active' or not fields.get('schedule_entry[starts_at]'):return False
    duration=(timestamp(fields['schedule_entry[ends_at]']).date()-timestamp(fields['schedule_entry[starts_at]']).date()).days
    return any(starts_on(fields,day-timedelta(days=offset)) for offset in range(min(3660,duration)+1))

def event_node(record,fields):
    node=etree.Element('div',{'class':'scheduled-event','data-local-calendar-event':record['id']});link=etree.SubElement(node,'a',{'href':record['url'],'class':'scheduled-event__link','data-turbo-frame':'_top'});link.text=fields.get('schedule_entry[summary]',record['title']);return node

def render(tree,path,owner,connection,query):
    all_events=records(connection,owner)
    all_tasks={r['id']:r for r in DATA['records'].values() if r['kind']=='todos'}
    for row in connection.execute('SELECT id FROM bc_records WHERE owner=? AND kind="todos"',(owner,)):
        task=metadata(connection,owner,row['id'])
        if task:all_tasks[task['id']]=task
    task_fields={identifier:fields_for(connection,owner,task) for identifier,task in all_tasks.items()}
    query=dict(query or {})
    if path.endswith('/entries/new') and query.get('starts_on'):
        day=timestamp(query['starts_on']).date().isoformat()
        from record_operations import apply_fields
        for form in tree.xpath('//form[@action]'):
            if form.get('action').endswith('/entries'):apply_fields(tree,form.get('action'),{'schedule_entry[starts_at]':day+'T09:00:00.000Z','schedule_entry[ends_at]':day+'T10:00:00.000Z','starts_at_date_picker':day,'ends_at_date_picker':day})
    for record,fields in all_events:
        if path!=record['url']:continue
        if not fields.get('schedule_entry[starts_at]'):continue
        start=timestamp(fields['schedule_entry[starts_at]']);end=timestamp(fields['schedule_entry[ends_at]']);all_day=str(fields.get('schedule_entry[all_day]')).lower() in ['true','1']
        for dates in tree.xpath('//*[@data-schedule-entry-date-starts-at-value]'):
            dates.set('data-schedule-entry-date-starts-at-value',fields['schedule_entry[starts_at]']);dates.set('data-schedule-entry-date-ends-at-value',fields['schedule_entry[ends_at]'])
            for key,value in [('startMonth',start.strftime('%b')),('startDay',str(start.day)),('endMonth',end.strftime('%b')),('endDay',str(end.day))]:
                for node in dates.xpath('.//*[@data-schedule-entry-date-target="'+key+'"]'):node.text=value
        for text in tree.xpath('//*[contains(@class,"event-form__dates-wrapper")]//*[@data-twelve-hour-time-format or @data-twenty-four-hour-time-format]'):
            for child in list(text):text.remove(child)
            text.text=start.strftime('%a, %b %d, %Y')+(' – '+end.strftime('%b %d, %Y') if all_day and start.date()!=end.date() else '' if all_day else ' '+start.strftime('%H:%M')+' – '+end.strftime('%H:%M UTC'))
        for link in tree.xpath('//a[contains(@href,".ics")]'):link.set('href','/api/calendar/events/'+record['id']+'.ics')
    bodies=tree.xpath('//*[@id="calendar_weeks-pagination-list"]')
    if not bodies:return tree
    body=bodies[0]
    # Preserve captured to-do markers; event nodes are rebuilt from current records.
    todo_markers={}
    for cell in body.xpath('.//*[@id and starts-with(@id,"day-items-")]'):
        for node in cell:
            if node.xpath('.//a[contains(@href,"/todos/")]') and not any(link.get('href','').split('?')[0].rsplit('/',1)[-1] in all_tasks for link in node.xpath('.//a')):todo_markers.setdefault(cell.get('id'),[]).append(copy.deepcopy(node))
    sample=next(iter(body.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," calendar-grid__week ")]')),None)
    if sample is None:return tree
    query=dict(query or {});anchor=query.get('window_starts_on') or query.get('date') or body.get('data-slide-key') or date.today().isoformat()
    start=timestamp(anchor).date();month=start.replace(day=1);start-=timedelta(days=(start.weekday()+1)%7)
    for child in list(body):body.remove(child)
    for key in ['data-controller','data-turbo-frame-pagination-paginate-on-intersection-value','data-turbo-frame-pagination-discard-frame-value']:body.attrib.pop(key,None)
    body.set('data-slide-key',start.isoformat());base=path.split('/display')[0];new_event=base+'/entries/new' if '/schedules/' in base else '/6302022/calendar/entries/new'
    for week in range(6):
        node=copy.deepcopy(sample);first=start+timedelta(days=week*7);node.set('aria-label','Week from '+first.strftime('%b %d')+' to '+(first+timedelta(days=6)).strftime('%b %d'))
        for sr in node.xpath('.//*[@aria-owns]'):sr.set('aria-owns',' '.join('date-'+(first+timedelta(days=i)).isoformat()+' day-items-'+(first+timedelta(days=i)).isoformat() for i in range(7)))
        for index,day_node in enumerate(node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," calendar-grid__day ")]')):day_node.set('data-day',(first+timedelta(days=index)).isoformat())
        for index,date_node in enumerate(node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," calendar-grid__day-of-month-container ")]')):
            day=first+timedelta(days=index);iso=day.isoformat();date_node.set('id','date-'+iso);date_node.set('data-day',iso)
            for link in date_node.xpath('.//a'):
                link.set('href',new_event+'?starts_on='+iso);link.set('data-day',iso);link.set('aria-label',day.strftime('%A, %B %d, %Y'))
                for child in list(link):link.remove(child)
                span=etree.SubElement(link,'span',{'class':'calendar-grid__date-name'});span.text=day.strftime('%b ')+str(day.day)
        for index,container in enumerate(node.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," calendar-grid__items ")]')):
            day=first+timedelta(days=index);iso=day.isoformat();container.set('id','day-items-'+iso);container.set('data-day',iso)
            for child in list(container):container.remove(child)
            hits=[(r,f) for r,f in all_events if ('/schedules/' not in base or r['parent']==base) and on_day(f,day)]
            for marker in todo_markers.get('day-items-'+iso,[]):container.append(copy.deepcopy(marker))
            for record,fields in hits:container.append(event_node(record,fields))
            include=connection.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="settings"',(owner,base)).fetchone()
            show_tasks=not include or json.loads(include['payload']).get('schedule[include_due_assignments]','1') not in ['0','false']
            if show_tasks:
                for identifier,task in all_tasks.items():
                    fields=task_fields[identifier]
                    if fields.get('_record_status','active')!='active' or fields.get('todo[due_on]')!=iso or ('/buckets/' in base and task['bucket']!=base.split('/')[3]):continue
                    marker=etree.SubElement(container,'div',{'class':'scheduled-todo','data-local-calendar-todo':identifier});link=etree.SubElement(marker,'a',{'href':task['url'],'data-turbo-frame':'_top'});link.text=fields.get('todo[content]',task['title'])
            container.set('aria-label',str(len(container))+' items' if len(container) else 'No events')
        body.append(node)
    for nav in tree.xpath('//*[@data-calendar-navigation-selected-month-value]'):nav.set('data-calendar-navigation-selected-month-value',month.strftime('%Y-%m'))
    for link in tree.xpath('//a[contains(@class,"month-picker__nav-link")]'):
        previous=month-timedelta(days=1);following=(month+timedelta(days=32)).replace(day=1);target=previous.replace(day=1) if 'backward' in link.get('class','') else following;link.set('href',path+'?'+urlencode({'window_starts_on':target.isoformat()}));link.set('data-calendar-navigation-month-param',target.strftime('%B %Y'))
    return tree

def ical_escape(value):return str(value).replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
def ical_recurrence(fields,start):
    frequency=fields.get('schedule_entry[recurrence_schedule][frequency]','');weekday=['MO','TU','WE','TH','FR','SA','SU'][start.weekday()]
    rules={'every_day':'FREQ=DAILY','every_weekday':'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR','every_week':'FREQ=WEEKLY','every_other_week':'FREQ=WEEKLY;INTERVAL=2','every_year':'FREQ=YEARLY','every_day_of_month':'FREQ=MONTHLY;BYMONTHDAY='+str(start.day),'every_month':'FREQ=MONTHLY;BYDAY='+str((start.day-1)//7+1)+weekday}
    rule=rules.get(frequency,'')
    if frequency=='custom_week':
        days=fields.get('schedule_entry[recurrence_schedule][days][]',[(start.weekday()+1)%7]);days=days if isinstance(days,list) else [days];codes=['SU','MO','TU','WE','TH','FR','SA'];chosen=[codes[int(day)] for day in days if str(day).isdigit() and 0<=int(day)<=6]
        rule='FREQ=WEEKLY;INTERVAL='+str(fields.get('schedule_entry[recurrence_schedule][week_interval]') or 1)+';BYDAY='+','.join(chosen or [weekday])
    if frequency=='custom_month':rule='FREQ=MONTHLY;INTERVAL='+str(fields.get('schedule_entry[recurrence_schedule][month_interval]') or 1)+';BYMONTHDAY='+str(start.day)
    until=fields.get('schedule_entry[recurs_until]')
    if rule and until:rule+=';UNTIL='+timestamp(until).strftime('%Y%m%dT235959Z')
    return rule

def ical_event(record,fields):
    start=timestamp(fields['schedule_entry[starts_at]']);end=timestamp(fields['schedule_entry[ends_at]']);all_day=str(fields.get('schedule_entry[all_day]')).lower() in ['true','1']
    start_line='DTSTART;VALUE=DATE:'+start.strftime('%Y%m%d') if all_day else 'DTSTART:'+start.strftime('%Y%m%dT%H%M%SZ')
    end_line='DTEND;VALUE=DATE:'+(end+timedelta(days=1)).strftime('%Y%m%d') if all_day else 'DTEND:'+end.strftime('%Y%m%dT%H%M%SZ')
    recurrence=ical_recurrence(fields,start)
    return '\r\n'.join(['BEGIN:VEVENT','UID:'+record['id']+'@basecamp.clone.test','DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),start_line,end_line,'SUMMARY:'+ical_escape(fields.get('schedule_entry[summary]',record['title']))]+(['RRULE:'+recurrence] if recurrence else [])+['END:VEVENT'])
def install(app,db,require_user):
    router=APIRouter()
    @router.get('/api/calendar/events/{identifier}.ics')
    def download(identifier:str,request:Request):
        account=require_user(request)
        with db() as c:
            record=metadata(c,account['workspace_id'],identifier)
            from workspaces import allows
            if not record or not allows(account,record['url']) or record['kind']!='schedule_entries':raise HTTPException(404,'Event not found')
            fields=fields_for(c,account['workspace_id'],record)
        return Response('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Basecamp Local//EN\r\n'+ical_event(record,fields)+'\r\nEND:VCALENDAR\r\n',media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="basecamp-event.ics"'})
    @router.get('/6302022/calendar/feed/{token}.ics')
    @router.get('/6302022/buckets/{bucket}/schedules/{schedule}/feed/{token}.ics')
    def feed(request:Request,token:str,bucket:str='',schedule:str=''):
        account=require_user(request)
        from workspaces import allows
        with db() as c:events=[ical_event(record,fields) for record,fields in records(c,account['workspace_id']) if fields.get('_record_status','active')=='active' and allows(account,record['url']) and (not bucket or record['bucket']==bucket)]
        return Response('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Basecamp Local//EN\r\n'+'\r\n'.join(events)+'\r\nEND:VCALENDAR\r\n',media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="basecamp-calendar.ics"'})
    app.include_router(router)
