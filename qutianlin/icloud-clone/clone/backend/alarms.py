"""Account-authorized alarm scheduling and durable delivery/acknowledgement."""
import base64,hashlib,json,time,re
from datetime import datetime,timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from backend import calendar_time,calendar_sharing,calendar_archives,reminder_sharing

OFFSETS={'At time of event':0,'5 minutes before':300,'15 minutes before':900,
         '30 minutes before':1800,'1 hour before':3600,'2 hours before':7200,
         '1 day before':86400,'2 days before':172800}
DAY_MS=86400000


def now_ms():return int(time.time()*1000)


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS icloud_alarm_states (
      owner TEXT NOT NULL,id TEXT NOT NULL,state TEXT NOT NULL,updated INTEGER NOT NULL,
      PRIMARY KEY(owner,id))''')

    db.execute('CREATE TABLE IF NOT EXISTS icloud_alarm_snoozes (owner TEXT NOT NULL,id TEXT NOT NULL,until INTEGER NOT NULL,PRIMARY KEY(owner,id))')
    db.execute('CREATE TABLE IF NOT EXISTS icloud_reminder_preferences (owner TEXT PRIMARY KEY,all_day_time TEXT NOT NULL)')


def preferences(db,owner):
    row=db.execute('SELECT all_day_time FROM icloud_reminder_preferences WHERE owner=?',(owner,)).fetchone()
    return {'all_day_time':row[0] if row else '', 'timezone':calendar_time.account_zone(db,owner)}


def save_preferences(db,owner,data):
    if not isinstance(data,dict) or not isinstance(data.get('all_day_time'),str):raise ValueError('Choose a notification time.')
    value=data['all_day_time']
    if value and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',value):raise ValueError('Choose a valid notification time.')
    db.execute('INSERT INTO icloud_reminder_preferences VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET all_day_time=excluded.all_day_time',(owner,value))
    return preferences(db,owner)


def resources(db,actor):
    return {'calendar':{e['id']:e for e in calendar_sharing.visible(db,actor,'events')},
            'reminders':{e['id']:e for e in reminder_sharing.visible(db,actor,'reminders')}}


def build(db,actor,kind,key,day,slot,available=None):
    available=available or resources(db,actor)
    original=available.get(kind,{}).get(key)
    if not original:return None
    zone_name=calendar_time.account_zone(db,actor['account_id'])
    if kind=='calendar':
        if slot not in ('alert','second_alert') or original.get(slot,'None') not in OFFSETS:return None
        if day!=original['start'][:10] and not calendar_time.valid_occurrence_time(original,calendar_time.date.fromisoformat(day)):return None
        try:event=calendar_time.instance(original,day)
        except ValueError:return None
        if original.get('_recurrence_parent') and day!=original['start'][:10]:return None
        start=datetime.fromisoformat(event['start'])
        zone=ZoneInfo(zone_name if event.get('allDay') or event.get('timezone','Floating')=='Floating' else event['timezone'])
        start_at=int(start.replace(tzinfo=zone).timestamp()*1000)
        trigger=start_at-OFFSETS[original[slot]]*1000
        end_at=calendar_time.end_timestamp(event,zone_name)
        title=event['title'];location=event.get('location','')
        path='/calendar/?'+urlencode({'item':key,'occurrence':day})
    elif kind=='reminders':
        due_time=original.get('due_time') or preferences(db,actor['account_id'])['all_day_time']
        if slot!='due' or original.get('completed') or not due_time or day!=original.get('due'):return None
        start=datetime.fromisoformat(day+'T'+due_time)
        start_at=int(start.replace(tzinfo=ZoneInfo(zone_name)).timestamp()*1000)
        trigger=start_at;end_at=start_at;title=original['title'];location=''
        path='/reminders/?'+urlencode({'list':original['list'],'item':key})
    else:return None
    descriptor=[kind,key,day,slot,calendar_archives.generation(db,actor['account_id'])]
    encoded=base64.urlsafe_b64encode(json.dumps(descriptor,separators=(',',':')).encode()).decode().rstrip('=')
    digest=hashlib.sha256(json.dumps([trigger,start_at,end_at,title,location],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()[:32]
    return {'id':encoded+'.'+digest,'application':kind,'item':key,'occurrence':day,'slot':slot,
            'trigger_at':trigger,'start_at':start_at,'end_at':end_at,'title':title,'location':location,'path':path}


def resolve(db,actor,key,available=None):
    try:
        if not isinstance(key,str) or len(key)>1600:raise ValueError()
        encoded,digest=key.split('.')
        descriptor=json.loads(base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)))
        if not isinstance(descriptor,list) or len(descriptor)!=5:raise ValueError()
        kind,item,day,slot,generation=descriptor
        if not all(isinstance(v,str) for v in (kind,item,day,slot)):raise ValueError()
        result=build(db,actor,kind,item,day,slot,available)
        if not result or result['id']!=key:raise ValueError()
        return result
    except (ValueError,TypeError,KeyError,OverflowError):raise LookupError('This reminder is no longer available.')


def state(db,owner,key):
    row=db.execute('SELECT state FROM icloud_alarm_states WHERE owner=? AND id=?',(owner,key)).fetchone()
    return row[0] if row else 'scheduled'


def schedule(db,actor,now=None):
    now=now_ms() if now is None else now;owner=actor['account_id'];available=resources(db,actor)
    first=datetime.fromtimestamp(now/1000,calendar_time.UTC).date()-timedelta(days=2)
    last=datetime.fromtimestamp((now+DAY_MS)/1000,calendar_time.UTC).date()+timedelta(days=3)
    alarms={}
    for kind,items in available.items():
        for key,event in items.items():
            if kind=='calendar':
                slots=[s for s in ('alert','second_alert') if event.get(s) in OFFSETS]
                if not slots:continue
                days=calendar_time.candidate_dates(event,first,last)
            else:
                if event.get('completed') or not event.get('due'):continue
                slots=['due'];days=[calendar_time.date.fromisoformat(event['due'])]
            for day in days:
                for slot in slots:
                    value=build(db,actor,kind,key,day.isoformat(),slot,available)
                    if value and now<value['trigger_at']<=now+DAY_MS and (value['end_at'] is None or value['end_at']+30000>=now) and state(db,owner,value['id'])=='scheduled':
                        alarms[value['id']]={**value,'state':'scheduled'}
    # A shown banner survives refresh, but every read rechecks current visibility.
    for row in db.execute("SELECT id FROM icloud_alarm_states WHERE owner=? AND state='delivered'",(owner,)):
        try:value=resolve(db,actor,row['id'],available)
        except LookupError:continue
        alarms[value['id']]={**value,'state':'delivered'}
    for row in db.execute("SELECT s.id,z.until FROM icloud_alarm_states s JOIN icloud_alarm_snoozes z ON s.owner=z.owner AND s.id=z.id WHERE s.owner=? AND s.state='snoozed'",(owner,)):
        try:value=resolve(db,actor,row['id'],available)
        except LookupError:continue
        alarms[value['id']]={**value,'trigger_at':row['until'],'state':'scheduled','snoozed':True}
    return {'owner':owner,'now':now,'through':now+DAY_MS,'alarms':sorted(alarms.values(),key=lambda a:(a['trigger_at'],a['id']))}


def act(db,actor,key,action,now=None,minutes=None):
    if action not in ('deliver','dismiss','snooze'):raise ValueError('Choose a valid reminder action.')
    if action=='snooze' and (type(minutes) is not int or minutes not in (5,10,15,30,60)):raise ValueError('Choose 5, 10, 15, 30 or 60 minutes.')
    now=now_ms() if now is None else now;owner=actor['account_id'];value=resolve(db,actor,key)
    current=state(db,owner,key)
    if action=='deliver':
        if current=='dismissed':raise FileNotFoundError('This reminder was dismissed.')
        if current=='delivered':return {**value,'state':current}
        snoozed=db.execute('SELECT until FROM icloud_alarm_snoozes WHERE owner=? AND id=?',(owner,key)).fetchone() if current=='snoozed' else None
        trigger=snoozed[0] if snoozed else value['trigger_at']
        if trigger>now:raise FileExistsError('This reminder is not due yet.')
        if not snoozed and value['end_at'] is not None and value['end_at']+30000<now:raise FileNotFoundError('This reminder has ended.')
        next_state='delivered'
    elif action=='snooze':
        if current!='delivered':raise FileExistsError('Only a shown reminder can be delayed.')
        until=now+minutes*60000
        db.execute('INSERT INTO icloud_alarm_snoozes VALUES (?,?,?) ON CONFLICT(owner,id) DO UPDATE SET until=excluded.until',(owner,key,until))
        value={**value,'trigger_at':until};next_state='snoozed'
    else:
        if current=='scheduled':raise FileExistsError('This reminder has not been shown yet.')
        next_state='dismissed'
    db.execute('INSERT INTO icloud_alarm_states VALUES (?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET state=excluded.state,updated=excluded.updated',
               (owner,key,next_state,now))
    return {**value,'state':next_state}
