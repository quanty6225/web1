"""Private Calendar grants and revocable public iCalendar feeds."""
import hashlib,json,re,secrets,time
from datetime import date,datetime,timedelta
from backend import reminders,calendar_archives,event_invitations,event_attachments,event_recurrence,calendar_time,event_editing
from backend.reminder_sharing import read
from websitebench.local_clone_auth.store import _normalize_email,AuthError
PREFIX='cshared:'


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_calendar_shares (
      id TEXT PRIMARY KEY,owner TEXT NOT NULL,target TEXT NOT NULL,
      public_token TEXT,active INTEGER NOT NULL,revision INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_calendar_members (
      share_id TEXT NOT NULL,email TEXT NOT NULL,account_id TEXT,status TEXT NOT NULL,
      permission TEXT NOT NULL,PRIMARY KEY(share_id,email))''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_calendar_notifications (
      id TEXT PRIMARY KEY,account_id TEXT,email TEXT NOT NULL,message TEXT NOT NULL,created_at INTEGER NOT NULL)''')


def get_share(db,key):
    row=db.execute('SELECT * FROM icloud_calendar_shares WHERE id=? AND active=1',(key,)).fetchone()
    if not row or not read(db,row['owner'],'calendars',row['target']):raise LookupError('This shared calendar is no longer available.')
    return row


def owned(db,owner,key):
    return db.execute('SELECT * FROM icloud_calendar_shares WHERE owner=? AND target=? AND active=1',(owner,key)).fetchone()


def member(db,share,actor):
    return db.execute('''SELECT * FROM icloud_calendar_members WHERE share_id=? AND
      (account_id=? OR (account_id IS NULL AND email=?))''',(share['id'],actor['account_id'],actor['email_normalized'])).fetchone()


def access(db,key,actor,pending=False):
    share=get_share(db,key)
    if share['owner']==actor['account_id']:return share,None
    person=member(db,share,actor)
    if not person or person['status']=='declined' or not pending and person['status']!='accepted':raise PermissionError('You do not have access to this calendar.')
    return share,person


def revision(item):return hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()


def decorate(item,share=None,person=None,kind='events'):
    value={k:v for k,v in item.items() if k not in ('_sharing','_original_id','_revision','_responses','_invitation')}
    if kind=='events':value['_revision']=revision(value)
    if share:
        value['_sharing']={'id':share['id'],'owner':person is None,'permission':person['permission'] if person else 'write'}
        if person:
            value['_original_id']=item['id'];value['id']=PREFIX+share['id']+':'+item['id']
            if kind=='events':value['calendar']=PREFIX+share['id']+':'+share['target']
    return value


def visible(db,actor,kind):
    owner=actor['account_id'];values=[]
    for item in reminders.rows(db,owner,kind).values():
        values.append(decorate(item,owned(db,owner,item['id'] if kind=='calendars' else item.get('calendar')),kind=kind))
    for share in db.execute('SELECT * FROM icloud_calendar_shares WHERE active=1 AND owner!=?',(owner,)).fetchall():
        person=member(db,share,actor);target=read(db,share['owner'],'calendars',share['target'])
        if not target or not person or person['status']!='accepted':continue
        if kind=='calendars':values.append(decorate(target,share,person,kind))
        else:values.extend(decorate(v,share,person) for v in reminders.rows(db,share['owner'],'events').values() if v.get('calendar')==share['target'])
    if kind=='events':
        for value in values:
            resource_owner=get_share(db,value['_sharing']['id'])['owner'] if value.get('_sharing') else owner
            value['_responses']=event_invitations.responses(db,resource_owner,value.get('_original_id',value['id']))
        values=event_invitations.visible(db,actor,values)
        for value in values:
            if not value.get('_invitation') or value.get('_sharing'):
                resource_owner=get_share(db,value['_sharing']['id'])['owner'] if value.get('_sharing') else owner
                event_editing.annotate(db,actor,resource_owner,value)
    return values


def summary(db,key,actor):
    share,person=access(db,key,actor,pending=True);calendar=read(db,share['owner'],'calendars',share['target'])
    owner=db.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(share['owner'],)).fetchone()
    result={'id':key,'target':share['target'],'name':calendar['name'],'owner':person is None,'owner_name':owner[0],
            'accepted':person is None or person['status']=='accepted','revision':share['revision']}
    if result['accepted']:
        result['participants']=[{'email':p['email'],'permission':p['permission'],'status':p['status']} for p in db.execute('SELECT * FROM icloud_calendar_members WHERE share_id=? ORDER BY email',(key,))]
    if person is None:result['public_path']='/api/calendar-public/'+share['public_token']+'.ics' if share['public_token'] else None
    return result


def notice(db,person,name):
    db.execute('INSERT INTO icloud_calendar_notifications VALUES (?,?,?,?,?)',(secrets.token_hex(16),person['account_id'],person['email'],name+' is no longer shared with you.',int(time.time()*1000)))


def retire_if_empty(db,key):
    db.execute('UPDATE icloud_calendar_shares SET active=0 WHERE id=? AND public_token IS NULL AND NOT EXISTS (SELECT 1 FROM icloud_calendar_members WHERE share_id=?)',(key,key))


def configure(db,actor,data):
    key=data.get('calendar');owner=actor['account_id']
    if not isinstance(key,str) or key.startswith(PREFIX):raise PermissionError('Only the owner can share a calendar.')
    target=read(db,owner,'calendars',key)
    if not target:raise LookupError('Calendar not found.')
    values=data.get('participants',[]);public=data.get('public',False)
    if not isinstance(values,list) or len(values)>100 or not isinstance(public,bool):raise ValueError('Invalid sharing details.')
    participants={}
    for value in values:
        if not isinstance(value,dict) or value.get('permission') not in ('read','write'):raise ValueError('Choose access privileges.')
        try:email=_normalize_email(value.get('email'))
        except AuthError:raise ValueError('Enter an email address for each participant.')
        if email==actor['email_normalized']:raise ValueError('The owner already has access.')
        participants[email]=value
    share=owned(db,owner,key)
    if share and data.get('revision')!=share['revision']:raise FileExistsError('Sharing changed. Reopen the calendar sharing controls.')
    if not share:
        sid=secrets.token_hex(16);db.execute('INSERT INTO icloud_calendar_shares VALUES (?,?,?,NULL,1,0)',(sid,owner,key));share=get_share(db,sid)
    old={p['email']:p for p in db.execute('SELECT * FROM icloud_calendar_members WHERE share_id=?',(share['id'],))};mail=[]
    for email,p in old.items():
        if email not in participants:
            notice(db,p,target['name']);mail.append((email,'removed',share['id'],target['name']))
            db.execute('DELETE FROM icloud_calendar_members WHERE share_id=? AND email=?',(share['id'],email))
    for email,value in participants.items():
        previous=old.get(email);resend=bool(value.get('resend'))
        if not previous:
            db.execute("INSERT INTO icloud_calendar_members VALUES (?,?,NULL,'invited',?)",(share['id'],email,value['permission']))
        else:
            db.execute('UPDATE icloud_calendar_members SET permission=?,status=? WHERE share_id=? AND email=?',
                       (value['permission'],'invited' if resend and previous['status']=='declined' else previous['status'],share['id'],email))
        if not previous or resend:mail.append((email,'invited',share['id'],target['name']))
    public_token=(share['public_token'] or secrets.token_hex(24)) if public else None
    db.execute('UPDATE icloud_calendar_shares SET public_token=?,revision=revision+1 WHERE id=?',(public_token,share['id']))
    result=summary(db,share['id'],actor);retire_if_empty(db,share['id'])
    return result,mail


def act(db,actor,key,action):
    share,person=access(db,key,actor,pending=action in ('join','decline'))
    if not person:raise ValueError('The owner cannot respond to their own invitation.')
    if action in ('join','decline'):
        db.execute('UPDATE icloud_calendar_members SET account_id=?,status=? WHERE share_id=? AND email=?',(actor['account_id'],'accepted' if action=='join' else 'declined',key,person['email']))
    elif action=='leave':db.execute('DELETE FROM icloud_calendar_members WHERE share_id=? AND email=?',(key,person['email']))
    else:raise ValueError('Choose a calendar invitation action.')
    db.execute('UPDATE icloud_calendar_shares SET revision=revision+1 WHERE id=?',(key,));retire_if_empty(db,key)


def inbox(db,actor):
    invitations=[]
    for share in db.execute('SELECT * FROM icloud_calendar_shares WHERE active=1 AND owner!=?',(actor['account_id'],)):
        p=member(db,share,actor)
        if p and p['status']=='invited' and read(db,share['owner'],'calendars',share['target']):invitations.append(summary(db,share['id'],actor))
    messages=[dict(r) for r in db.execute('SELECT id,message,created_at FROM icloud_calendar_notifications WHERE account_id=? OR (account_id IS NULL AND email=?) ORDER BY created_at DESC',(actor['account_id'],actor['email_normalized']))]
    return {'invitations':invitations,'messages':messages}


def revoke(db,actor,target=None):
    """Revoke owned grants, and on account restore also received grants."""
    owner=actor['account_id']
    shares=db.execute('SELECT * FROM icloud_calendar_shares WHERE owner=? AND active=1'+(' AND target=?' if target else ''),(owner,target) if target else (owner,)).fetchall()
    for share in shares:
        name=(read(db,owner,'calendars',share['target']) or {}).get('name','Calendar')
        for p in db.execute('SELECT * FROM icloud_calendar_members WHERE share_id=?',(share['id'],)):notice(db,p,name)
        db.execute('DELETE FROM icloud_calendar_members WHERE share_id=?',(share['id'],))
        db.execute('UPDATE icloud_calendar_shares SET active=0,public_token=NULL,revision=revision+1 WHERE id=?',(share['id'],))
    if target is None:
        db.execute('DELETE FROM icloud_calendar_members WHERE account_id=? OR (account_id IS NULL AND email=?)',(owner,actor['email_normalized']))
        db.execute('UPDATE icloud_calendar_shares SET active=0 WHERE public_token IS NULL AND NOT EXISTS (SELECT 1 FROM icloud_calendar_members WHERE share_id=icloud_calendar_shares.id)')


def locate(db,actor,key,write=False):
    if not isinstance(key,str):raise ValueError('Choose a calendar.')
    if key.startswith(PREFIX):
        try:_,sid,original=key.split(':',2)
        except ValueError:raise LookupError('Calendar not found.')
        share,p=access(db,sid,actor)
        if original!=share['target']:raise LookupError('Calendar not found.')
        if write and p and p['permission']!='write':raise PermissionError('This calendar is read-only.')
        return share['owner'],original,share,p
    if not read(db,actor['account_id'],'calendars',key):raise ValueError('Choose one of your calendars.')
    return actor['account_id'],key,owned(db,actor['account_id'],key),None


def validate_event(data,previous):
    clean={**previous,**data}
    for field in ('_excluded','_until','_recurrence_parent','_recurrence_date'):
        clean.pop(field,None)
        if field in previous:clean[field]=previous[field]
    for field in ('_sharing','_original_id','_revision','_responses','_invitation','_parent_key','_parent_revision','_series_repeat','scope','occurrence','_edit_occurrence','_prompt_event_updates','_end_timestamp'):clean.pop(field,None)
    for field,limit in [('title',500),('location',2000),('notes',10000),('url',2000)]:
        value=clean.get(field,'')
        if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid event '+field+'.')
        clean[field]=value
    if not clean['title'].strip():raise ValueError('Enter an event title.')
    all_day=clean.get('allDay',False)
    if not isinstance(all_day,bool):raise ValueError('Invalid all-day setting.')
    fmt='%Y-%m-%d' if all_day else '%Y-%m-%dT%H:%M'
    try:
        start=datetime.strptime(clean.get('start',''),fmt);end=datetime.strptime(clean.get('end',''),fmt)
        if start.strftime(fmt)!=clean['start'] or end.strftime(fmt)!=clean['end']:raise ValueError()
    except (ValueError,TypeError):raise ValueError('Enter valid start and end dates.')
    if end<start:raise ValueError('The end date must follow the start date.')
    clean['allDay']=all_day;clean.setdefault('repeat','Never');clean.setdefault('alert','None');clean.setdefault('invitees',[])
    clean.setdefault('second_alert','None')
    for field in ('alert','second_alert'):
        if clean[field] not in event_invitations.ALERT_OPTIONS:raise ValueError('Choose a valid event alert.')
    if clean['repeat'] not in ('Never','Every Day','Every Week','Every Month','Every Year'):raise ValueError('Choose a repeat interval.')
    if not isinstance(clean['invitees'],list) or len(clean['invitees'])>300:raise ValueError('Enter valid invitees.')
    try:clean['invitees']=[_normalize_email(v) for v in clean['invitees']]
    except AuthError:raise ValueError('Enter valid invitee email addresses.')
    return clean


def write_event(db,actor,key,data,now,delete=False,mail=None,attachment_source=None,response_source=None):
    if mail is None:mail=[]
    detach_occurrence=False
    if key.startswith(event_invitations.PREFIX):raise PermissionError('Use the invitation to reply to this event.')
    owner=actor['account_id'];original=key;share=None;person=None
    if key.startswith(PREFIX):
        try:_,sid,original=key.split(':',2)
        except ValueError:raise LookupError('Event not found.')
        share,person=access(db,sid,actor);owner=share['owner']
        if person and person['permission']!='write':raise PermissionError('This calendar is read-only.')
    old=read(db,owner,'events',original)
    if share and (not old or old.get('calendar')!=share['target']):raise LookupError('Event not found.')
    if db.execute("SELECT 1 FROM icloud_entity_tombstones WHERE owner=? AND kind='events' AND id=?",(owner,original)).fetchone():
        if delete:raise LookupError('Event not found.')
        raise FileNotFoundError('This event was deleted.')
    if old and (share or owned(db,owner,old.get('calendar')) or data.get('_revision') is not None):
        if data.get('_revision')!=revision(old):raise FileExistsError('This event changed. Reopen it before saving.')
    if data.get('scope') is not None and data['scope'] not in ('one','future'):raise ValueError('Choose only this event or this and future events.')
    if old and old.get('_recurrence_parent'):
        parent=read(db,owner,'events',old['_recurrence_parent'])
        if data.get('scope')=='future':
            if not parent:raise LookupError('The repeating series is no longer available.')
            parent_key=event_editing.parent_key(db,actor,owner,parent)
            if not parent_key:raise PermissionError('You cannot edit the original repeating series.')
            if data.get('_parent_revision')!=revision(parent):raise FileExistsError('This series changed. Reopen it before saving.')
            return write_event(db,actor,parent_key,{**data,'_revision':revision(parent),'occurrence':old['_recurrence_date']},now,delete,mail,attachment_source=old,response_source=old['id'])
        if not delete:
            if parent and data.get('repeat',parent['repeat']) not in (parent['repeat'],'Never'):raise ValueError('Apply a changed repeat interval to future events.')
            detach_occurrence=data.get('scope')=='one' and data.get('repeat')=='Never'
            data={**data,'repeat':'Never'}
    if delete:
        if not old:raise LookupError('Event not found.')
        if old.get('repeat','Never')!='Never':
            selected=event_editing.selection(db,owner,old,data.get('occurrence'))
            changed=event_recurrence.cancel(selected,data.get('occurrence'),data.get('scope'))
            calendar_archives.snapshot(db,owner,time.time_ns()//1000000)
            event_editing.discard_children(db,actor,owner,old,data.get('occurrence'),data.get('scope'),now,mail)
            if changed is not None:
                reminders.save(db,owner,'events',changed,now)
                notice=old['title']+': '+data['occurrence']+(' and all future occurrences were cancelled.' if data['scope']=='future' else ' was cancelled.')
                mail.extend(event_invitations.sync(db,owner,changed,old,now,cancellation=notice))
                mail.extend(event_invitations.shared_update(db,actor,owner,changed,cancellation=notice))
                return decorate(changed,share or owned(db,owner,old['calendar']),person)
        mail.extend(event_invitations.sync(db,owner,None,old,now));mail.extend(event_invitations.shared_update(db,actor,owner,old,deleted=True))
        if old.get('repeat','Never')=='Never':calendar_archives.snapshot(db,owner,time.time_ns()//1000000)
        reminders.delete(db,owner,'events',original,now);return None
    target=data.get('calendar',decorate(old,share,person).get('calendar') if old else event_invitations.preferences(db,actor['account_id'])['effective_default_calendar'])
    dest_owner,dest,dest_share,dest_person=locate(db,actor,target,write=True)
    if not old and read(db,dest_owner,'events',original):raise FileExistsError('An event already uses this identifier.')
    if db.execute("SELECT 1 FROM icloud_entity_tombstones WHERE owner=? AND kind='events' AND id=?",(dest_owner,original)).fetchone():raise FileNotFoundError('This event was deleted.')
    target_id=secrets.token_hex(16) if old and dest_owner!=owner else original
    defaults={'alert':event_invitations.preferences(db,actor['account_id'])['default_alert']} if not old else old
    clean=validate_event(data,defaults);clean.update(id=target_id,calendar=dest)
    calendar_time.validate_event(db,actor['account_id'],owner,clean,old)
    attachment_previous=attachment_source or old or {}
    if old and data.get('scope') in ('one','future'):
        attachment_previous=next((child for child in event_editing.children(db,owner,old) if child['_recurrence_date']==data.get('occurrence')),attachment_previous)
    clean['attachments']=event_attachments.validate(db,actor,clean.get('attachments',[]),attachment_previous)
    if sum(a['size'] for a in clean['attachments'])+len(json.dumps(clean,ensure_ascii=False).encode())>event_attachments.MAX_BYTES:raise ValueError('The event and its attachments must fit within 20 MB.')
    if old and old.get('repeat','Never')!='Never' and data.get('scope') is not None:
        return event_editing.apply(db,actor,owner,old,clean,data,dest_owner,dest_share,dest_person,now,mail,response_source)
    if old and old.get('repeat','Never')!='Never' and (dest_owner!=owner or dest!=old['calendar']):raise ValueError('Choose whether to move this event or future events.')
    if old and old.get('repeat','Never')!='Never' and any(clean.get(field,default)!=old.get(field,default) for field,default in (('start',None),('end',None),('repeat','Never'),('allDay',False),('timezone','Floating'))):
        raise ValueError('Choose whether to change this event or future events.')
    if clean.get('_recurrence_parent') and (detach_occurrence or owner!=dest_owner or dest!=old['calendar']):
        clean.pop('_recurrence_parent',None);clean.pop('_recurrence_date',None)
    for changed_owner in {owner,dest_owner}:calendar_archives.snapshot(db,changed_owner,time.time_ns()//1000000)
    if old and dest_owner!=owner:
        mail.extend(event_invitations.sync(db,owner,None,old,now))
        reminders.delete(db,owner,'events',original,now)
    reminders.save(db,dest_owner,'events',clean,now)
    mail.extend(event_invitations.sync(db,dest_owner,clean,old if owner==dest_owner else None,now))
    mail.extend(event_invitations.shared_update(db,actor,dest_owner,clean))
    return decorate(clean,dest_share,dest_person)


def public_feed(db,token,origin=None):
    share=db.execute('SELECT * FROM icloud_calendar_shares WHERE public_token=? AND active=1',(token,)).fetchone()
    if not share or not read(db,share['owner'],'calendars',share['target']):raise LookupError('Public calendar not found.')
    def escape(v):return str(v).replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//iCloud Local//Calendar//EN','CALSCALE:GREGORIAN']
    events=[e for e in reminders.rows(db,share['owner'],'events').values() if e.get('calendar')==share['target']]
    names=sorted({e['timezone'] for e in events if not e.get('allDay') and e.get('timezone','Floating')!='Floating'})
    for name in names:lines.extend(calendar_time.timezone_component(name).strip().split('\r\n'))
    by_id={e['id']:e for e in events}
    overridden={e['id']:set() for e in events}
    for e in events:
        if e.get('_recurrence_parent') in overridden:overridden[e['_recurrence_parent']].add(e['_recurrence_date'])
    for e in events:
        if e.get('calendar')!=share['target']:continue
        stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
        parent=by_id.get(e.get('_recurrence_parent'));identity=parent['id'] if parent else e['id']
        uid=hashlib.sha256((share['id']+identity).encode()).hexdigest()+'@icloud.offline.invalid'
        lines+=['BEGIN:VEVENT','UID:'+uid,'DTSTAMP:'+stamp,'SUMMARY:'+escape(e['title'])]
        if parent:
            rid=e['_recurrence_date'].replace('-','')
            if parent.get('allDay'):lines.append('RECURRENCE-ID;VALUE=DATE:'+rid)
            else:lines.append('RECURRENCE-ID'+(';TZID='+parent['timezone'] if parent.get('timezone','Floating')!='Floating' else '')+':'+rid+'T'+parent['start'][11:16].replace(':','')+'00')
        if e.get('allDay'):
            lines+=['DTSTART;VALUE=DATE:'+e['start'].replace('-',''),'DTEND;VALUE=DATE:'+(date.fromisoformat(e['end'])+timedelta(days=1)).strftime('%Y%m%d')]
        else:
            zone=';TZID='+e['timezone'] if e.get('timezone','Floating')!='Floating' else ''
            lines+=['DTSTART'+zone+':'+e['start'].replace('-','').replace(':','')+'00','DTEND'+zone+':'+e['end'].replace('-','').replace(':','')+'00']
        for key,prop in [('notes','DESCRIPTION'),('location','LOCATION')]:
            if e.get(key):lines.append(prop+':'+escape(e[key]))
        if e.get('url') and '\n' not in e['url'] and '\r' not in e['url']:lines.append('URL:'+e['url'])
        freq={'Every Day':'DAILY','Every Week':'WEEKLY','Every Month':'MONTHLY','Every Year':'YEARLY'}.get(e.get('repeat'))
        if freq:
            until=''
            if e.get('_until'):
                until=';UNTIL='+(calendar_time.utc_until(e['_until'],e['timezone']) if not e.get('allDay') and e.get('timezone','Floating')!='Floating' else e['_until'].replace('-','')+('' if e.get('allDay') else 'T235959'))
            lines.append('RRULE:FREQ='+freq+until)
        excluded=[day for day in e.get('_excluded',[]) if day not in overridden[e['id']]]
        if excluded:
            suffix='' if e.get('allDay') else 'T'+e['start'][11:16].replace(':','')+'00'
            lines.append(('EXDATE;VALUE=DATE:' if e.get('allDay') else 'EXDATE'+(';TZID='+e['timezone'] if e.get('timezone','Floating')!='Floating' else '')+':')+','.join(day.replace('-','')+suffix for day in excluded))
        if origin:
            from urllib.parse import quote
            for attachment in e.get('attachments',[]):lines.append('ATTACH:'+origin+'/api/calendar-public/'+token+'/events/'+quote(e['id'],safe='')+'/attachments/'+attachment['id'])
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR');folded=[]
    for line in lines:
        current=''
        for char in line:
            if len((current+char).encode())>75:folded.append(current);current=' '
            current+=char
        folded.append(current)
    return '\r\n'.join(folded)+'\r\n'
