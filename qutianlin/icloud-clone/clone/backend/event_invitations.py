"""Local event invitations, account-bound replies and notification preferences."""
import json,secrets,time
from backend.reminder_sharing import read
PREFIX='einv:'
ALERT_OPTIONS=('None','At time of event','5 minutes before','15 minutes before','30 minutes before','1 hour before','2 hours before','1 day before','2 days before')
FORMAT_OPTIONS={'date_format':('MM/DD/YYYY','DD/MM/YYYY','YYYY/MM/DD'),
                'date_separator':('/','-','.'),'time_format':('12 Hour','24 Hour'),'time_separator':(':','.')}
DEFAULTS={'delivery':'email','shared_updates':False,'prompt_event_updates':True,'hide_past':False,'hide_days':30,
          'default_calendar':'selected','selected_calendar':'','default_alert':'None','calendar_order':[],'hidden_calendars':[],'show_birthdays':False,'alternate_calendar':'',
          **{key:options[0] for key,options in FORMAT_OPTIONS.items()}}


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_calendar_preferences (
      owner TEXT PRIMARY KEY,payload TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_event_invites (
      token TEXT PRIMARY KEY,owner TEXT NOT NULL,event_id TEXT NOT NULL,email TEXT NOT NULL,
      account_id TEXT,status TEXT NOT NULL,active INTEGER NOT NULL,updated INTEGER NOT NULL)''')
    if 'destination' not in [row[1] for row in db.execute('PRAGMA table_info(icloud_event_invites)')]:
        db.execute('ALTER TABLE icloud_event_invites ADD COLUMN destination TEXT')


def preferences(db,owner):
    row=db.execute('SELECT payload FROM icloud_calendar_preferences WHERE owner=?',(owner,)).fetchone()
    result={**DEFAULTS,**(json.loads(row[0]) if row else {})}
    from backend import calendar_sharing
    actor=recipient_account(db,'',owner)
    calendars=calendar_sharing.visible(db,actor,'calendars') if actor else []
    writable=[c['id'] for c in calendars if not c.get('_sharing') or c['_sharing']['permission']=='write']
    fallback='personal' if 'personal' in writable else next((c['id'] for c in calendars if not c.get('_sharing') or c['_sharing']['owner']),writable[0] if writable else '')
    if result['selected_calendar'] not in [c['id'] for c in calendars]:result['selected_calendar']=fallback
    if result['default_calendar']!='selected' and result['default_calendar'] not in writable:result['default_calendar']=fallback
    result['effective_default_calendar']=result['selected_calendar'] if result['default_calendar']=='selected' and result['selected_calendar'] in writable else fallback if result['default_calendar']=='selected' else result['default_calendar']
    result['calendar_order']=[key for key in result['calendar_order'] if any(c['id']==key for c in calendars)]
    result['hidden_calendars']=[key for key in result['hidden_calendars'] if key=='birthdays' or any(c['id']==key for c in calendars)]
    return result


def save_preferences(db,owner,data):
    previous=preferences(db,owner)
    data={**previous,**data}
    if data.get('delivery') not in ('email','in-app'):raise ValueError('Choose how to receive invitations.')
    if not isinstance(data.get('shared_updates'),bool) or not isinstance(data.get('hide_past'),bool):raise ValueError('Choose your event settings.')
    if not isinstance(data['prompt_event_updates'],bool):raise ValueError('Choose whether to ask before sending event changes.')
    days=data.get('hide_days')
    if type(days) is not int or not 1<=days<=3650:raise ValueError('Enter between 1 and 3650 days.')
    if not isinstance(data['show_birthdays'],bool):raise ValueError('Choose whether to show birthdays.')
    if data['alternate_calendar'] not in ('','chinese','islamic'):raise ValueError('Choose an alternate calendar.')
    if data['default_alert'] not in ALERT_OPTIONS:raise ValueError('Choose a default alert.')
    for key,options in FORMAT_OPTIONS.items():
        if data[key] not in options:raise ValueError('Choose a valid '+key.replace('_',' ')+'.')
    from backend import calendar_sharing
    actor=recipient_account(db,'',owner)
    calendars=calendar_sharing.visible(db,actor,'calendars')
    writable=[c['id'] for c in calendars if not c.get('_sharing') or c['_sharing']['permission']=='write']
    if data['default_calendar']!='selected' and data['default_calendar'] not in writable:raise ValueError('Choose an editable default calendar.')
    if data['selected_calendar'] not in [c['id'] for c in calendars]:raise ValueError('Choose a calendar from your sidebar.')
    order=data['calendar_order']
    if not isinstance(order,list) or any(not isinstance(key,str) or not any(c['id']==key for c in calendars) for key in order) or len(set(order))!=len(order):raise ValueError('Choose calendars from your sidebar.')
    hidden=data['hidden_calendars']
    if not isinstance(hidden,list) or any(not isinstance(key,str) or key!='birthdays' and not any(c['id']==key for c in calendars) for key in hidden) or len(set(hidden))!=len(hidden):raise ValueError('Choose calendars from your sidebar.')
    clean={k:data[k] for k in DEFAULTS}
    # Preserve placement for accepted invitations created before destination persistence.
    db.execute("UPDATE icloud_event_invites SET destination=? WHERE account_id=? AND active=1 AND status IN ('accepted','maybe') AND destination IS NULL",(previous['effective_default_calendar'],owner))
    db.execute('INSERT INTO icloud_calendar_preferences VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET payload=excluded.payload',(owner,json.dumps(clean)))
    return preferences(db,owner)


def recipient_account(db,email,account_id=None):
    return db.execute('SELECT account_id,email_normalized,display_name FROM local_auth_accounts WHERE '+('account_id=?' if account_id else 'email_normalized=?'),(account_id or email,)).fetchone()


def wants_email(db,email,account_id=None):
    person=recipient_account(db,email,account_id)
    return not person or preferences(db,person['account_id'])['delivery']=='email'


def message(db,email,account_id,text):
    db.execute('INSERT INTO icloud_calendar_notifications VALUES (?,?,?,?,?)',(secrets.token_hex(16),account_id,email,text,int(time.time()*1000)))


def rows(db,owner,event):return db.execute('SELECT * FROM icloud_event_invites WHERE owner=? AND event_id=? AND active=1',(owner,event)).fetchall()


def responses(db,owner,event):return [{'email':r['email'],'status':r['status']} for r in rows(db,owner,event) if r['status']!='junk']


def sync(db,owner,event,old,now,cancellation=None):
    """Return mail jobs; caller delivers them before committing the mutation."""
    key=(event or old)['id'];existing={r['email']:r for r in rows(db,owner,key)};jobs=[]
    desired=set((event or {}).get('invitees',[]))
    owner_row=recipient_account(db,'',owner);desired.discard(owner_row['email_normalized'])
    for email,r in existing.items():
        if email not in desired:
            db.execute('UPDATE icloud_event_invites SET active=0,updated=? WHERE token=?',(now,r['token']))
            if r['status']!='junk':
                text=(old or event)['title']+' was cancelled.'
                message(db,email,r['account_id'],text)
                if wants_email(db,email,r['account_id']):jobs.append((email,'Calendar event cancelled',text,''))
    changed=old is not None and event is not None and any(old.get(k)!=event.get(k) for k in ('title','start','end','location','notes','url','repeat','allDay','attachments','timezone','calendar','_excluded','_until'))
    for email in desired:
        r=existing.get(email)
        if not r:
            token=secrets.token_hex(20)
            db.execute("INSERT INTO icloud_event_invites (token,owner,event_id,email,account_id,status,active,updated) VALUES (?,?,?,?,NULL,'pending',1,?)",(token,owner,key,email,now))
        else:token=r['token']
        if r and r['status']=='junk':continue
        if (not r or changed) and wants_email(db,email,r['account_id'] if r else None):
            jobs.append((email,'Calendar event invitation' if not r else 'Calendar event updated',cancellation or (owner_row['display_name']+' invited you to '+event['title']+'.\n'+event['start']+' – '+event['end']),'/calendar/invitation/'+token+'/'))
        if r and changed:
            db.execute('UPDATE icloud_event_invites SET updated=? WHERE token=?',(now,token))
            message(db,email,r['account_id'],cancellation or event['title']+' was updated.')
    return jobs


def shared_update(db,actor,owner,event,deleted=False,cancellation=None):
    share=db.execute('SELECT * FROM icloud_calendar_shares WHERE owner=? AND target=? AND active=1',(owner,event['calendar'])).fetchone()
    if not share:return []
    people=[recipient_account(db,'',owner)]
    people.extend(recipient_account(db,p['email'],p['account_id']) for p in db.execute("SELECT * FROM icloud_calendar_members WHERE share_id=? AND status='accepted'",(share['id'],)))
    jobs=[];seen=set()
    for person in people:
        if not person or person['account_id'] in seen or person['account_id']==actor['account_id']:continue
        seen.add(person['account_id'])
        if preferences(db,person['account_id'])['shared_updates']:
            jobs.append((person['email_normalized'],'Shared calendar updated',cancellation or event['title']+(' was cancelled.' if deleted else ' was updated.'),'/calendar/'))
    return jobs


def access(db,token,actor):
    r=db.execute('SELECT * FROM icloud_event_invites WHERE token=? AND active=1',(token,)).fetchone()
    if not r or r['status']=='junk':raise LookupError('This invitation is no longer available.')
    if not (r['account_id']==actor['account_id'] or r['account_id'] is None and r['email']==actor['email_normalized']):raise PermissionError('Sign in with the invited account.')
    event=read(db,r['owner'],'events',r['event_id'])
    if not event:raise LookupError('This event is no longer available.')
    return r,event


def summary(db,token,actor):
    r,event=access(db,token,actor);organizer=recipient_account(db,'',r['owner'])
    return {'token':token,'status':r['status'],'event':{k:event.get(k) for k in ('title','start','end','location','notes','url','repeat','allDay','attachments','timezone','_excluded','_until')},'organizer':organizer['display_name']}


def reply(db,token,actor,status):
    if status not in ('accepted','declined','maybe','junk'):raise ValueError('Choose Accept, Decline, or Maybe.')
    r,event=access(db,token,actor)
    destination=r['destination']
    if status in ('accepted','maybe') and not destination:destination=preferences(db,actor['account_id'])['effective_default_calendar']
    db.execute('UPDATE icloud_event_invites SET account_id=?,status=?,destination=? WHERE token=?',(actor['account_id'],status,destination,token))
    if status=='junk':return []
    if status==r['status']:return []
    organizer=recipient_account(db,'',r['owner']);text=actor['display_name']+' replied '+status+' to '+event['title']+'.'
    message(db,organizer['email_normalized'],r['owner'],text)
    if wants_email(db,organizer['email_normalized'],r['owner']):return [(organizer['email_normalized'],'Calendar event response',text,'/calendar/')]
    return []


def inbox(db,actor):
    if preferences(db,actor['account_id'])['delivery']!='in-app':return []
    result=[]
    for r in db.execute("SELECT * FROM icloud_event_invites WHERE active=1 AND status='pending' AND (account_id=? OR (account_id IS NULL AND email=?))",(actor['account_id'],actor['email_normalized'])):
        try:result.append(summary(db,r['token'],actor))
        except LookupError:pass
    return result


def visible(db,actor,existing):
    default=preferences(db,actor['account_id'])['effective_default_calendar']
    if not default:return existing
    covered={}
    for value in existing:
        owner=actor['account_id']
        if value.get('_sharing'):
            row=db.execute('SELECT owner FROM icloud_calendar_shares WHERE id=?',(value['_sharing']['id'],)).fetchone()
            if row:owner=row[0]
        covered[(owner,value.get('_original_id',value['id']))]=value
    for r in db.execute("SELECT * FROM icloud_event_invites WHERE active=1 AND status IN ('accepted','maybe') AND (account_id=? OR (account_id IS NULL AND email=?))",(actor['account_id'],actor['email_normalized'])):
        event=read(db,r['owner'],'events',r['event_id'])
        if not event:continue
        if (r['owner'],r['event_id']) in covered:
            covered[(r['owner'],r['event_id'])]['_invitation']={'token':r['token'],'status':r['status']}
            continue
        destination=r['destination'] or default
        from backend import calendar_sharing
        try:calendar_sharing.locate(db,actor,destination,write=True)
        except (ValueError,LookupError,PermissionError):destination=default
        existing.append({**event,'id':PREFIX+r['token'],'calendar':destination,'_invitation':{'token':r['token'],'status':r['status']}})
    return existing


def revoke(db,owner):
    db.execute('UPDATE icloud_event_invites SET active=0 WHERE owner=?',(owner,))
