"""Persistent local scheduling, conflict checks and booking lifecycle for Cal.com."""
from __future__ import annotations
import contextlib,hashlib,json,re,secrets,sqlite3,time,unicodedata
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

class DomainError(ValueError):
 def __init__(self,message,status=422):super().__init__(message);self.status=status

def uid():return secrets.token_urlsafe(18)
RESERVED_USERNAMES={'d','links','api','assets','static','settings','apps','auth','signup','booking','availability','events','bookings','workflow','workflows','routing','insights','teams','help','download','terms','privacy','external','healthz'}
def username_value(value):
 value=unicodedata.normalize('NFKC',str(value or '')).strip().lower()
 if not 2<=len(value)<=60 or not value[0].isalnum() or any(not (c.isalnum() or c=='-') for c in value) or value in RESERVED_USERNAMES:raise DomainError('Choose an available username using letters, numbers and hyphens.')
 return value
def email(value):
 value=str(value or '').strip().lower()
 if len(value)>254 or not re.fullmatch(r'[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+',value):raise DomainError('Enter a valid email address.')
 return value

def text(value,label,limit=200):
 value=str(value or '').strip()
 if not value or len(value)>limit or '\n' in value or '\r' in value:raise DomainError(f'Enter a valid {label}.')
 return value

def zone(value):
 try:return ZoneInfo(str(value))
 except (ValueError,ZoneInfoNotFoundError):raise DomainError('Choose a valid timezone.')

def stamp(value):
 try:
  dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
  if dt.tzinfo is None:raise ValueError()
  return int(dt.timestamp())
 except (ValueError,TypeError,OverflowError):raise DomainError('Choose a valid time with a timezone.')

def iso(value):return datetime.fromtimestamp(value,timezone.utc).isoformat().replace('+00:00','Z')
def minutes(value,label,minimum=0,maximum=1440):
 try:
  n=int(value)
  if isinstance(value,bool) or float(value)!=n or not minimum<=n<=maximum:raise ValueError()
 except (ValueError,TypeError,OverflowError):raise DomainError(f'Enter a valid {label}.')
 return n

def windows(value):
 if not isinstance(value,dict):raise DomainError('Enter weekly availability.')
 result={}
 for key,rows in value.items():
  if str(key) not in [str(x) for x in range(7)] or not isinstance(rows,list):raise DomainError('Invalid weekday.')
  result[str(key)]=[]
  for row in rows:
   if not isinstance(row,list) or len(row)!=2 or any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',str(x)) for x in row):raise DomainError('Enter valid availability times.')
   if row[0]>=row[1]:raise DomainError('End time must be after start time.')
   result[str(key)].append(row)
  result[str(key)].sort()
  if any(a[1]>b[0] for a,b in zip(result[str(key)],result[str(key)][1:])):raise DomainError('Availability intervals must not overlap.')
 return result

class Store:
 def __init__(self,path):
  self.path=str(path)
  with self.db() as c:c.executescript('''
   CREATE TABLE IF NOT EXISTS cal_profiles(owner TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai');
   CREATE TABLE IF NOT EXISTS cal_schedules(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,timezone TEXT NOT NULL,weekly TEXT NOT NULL,overrides TEXT NOT NULL DEFAULT '{}',is_default INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS cal_events(id TEXT PRIMARY KEY,owner TEXT NOT NULL,title TEXT NOT NULL,slug TEXT NOT NULL,length INTEGER NOT NULL,description TEXT NOT NULL DEFAULT '',hidden INTEGER NOT NULL DEFAULT 0,schedule_id TEXT NOT NULL,options TEXT NOT NULL DEFAULT '{}',created INTEGER NOT NULL,UNIQUE(owner,slug),FOREIGN KEY(schedule_id) REFERENCES cal_schedules(id));
   CREATE TABLE IF NOT EXISTS cal_bookings(id TEXT PRIMARY KEY,owner TEXT NOT NULL,event_id TEXT NOT NULL,title TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,busy_start INTEGER NOT NULL,busy_end INTEGER NOT NULL,attendee_name TEXT NOT NULL,attendee_email TEXT NOT NULL,timezone TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,manage_hash TEXT NOT NULL,idempotency_key TEXT,request_hash TEXT,created INTEGER NOT NULL,updated INTEGER NOT NULL,UNIQUE(owner,idempotency_key));
   CREATE INDEX IF NOT EXISTS cal_booking_conflicts ON cal_bookings(owner,start,end,status);
   CREATE TABLE IF NOT EXISTS cal_mail(id TEXT PRIMARY KEY,owner TEXT NOT NULL,booking_id TEXT NOT NULL,recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,error TEXT,created INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS cal_event_order(owner TEXT NOT NULL,event_id TEXT PRIMARY KEY,position INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS cal_private_links(digest TEXT PRIMARY KEY,owner TEXT NOT NULL,event_id TEXT NOT NULL,used_booking_id TEXT,created INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS cal_time_off(id TEXT PRIMARY KEY,owner TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,timezone TEXT NOT NULL,reason TEXT NOT NULL,notes TEXT NOT NULL,show_note INTEGER NOT NULL DEFAULT 0);
  ''')
  with self.db(True) as c:
   columns={r['name'] for r in c.execute('PRAGMA table_info(cal_profiles)')}
   for name in ['display_name','about','location']:
    if name not in columns:c.execute('ALTER TABLE cal_profiles ADD COLUMN '+name+" TEXT NOT NULL DEFAULT ''")
   mail_columns={r['name'] for r in c.execute('PRAGMA table_info(cal_mail)')}
   for name,kind in [('claim_token','TEXT'),('claimed_at','INTEGER')]:
    if name not in mail_columns:c.execute('ALTER TABLE cal_mail ADD COLUMN '+name+' '+kind)
   booking_columns={r['name'] for r in c.execute('PRAGMA table_info(cal_bookings)')}
   for name,default in [('topic',''),('phone',''),('guests','[]'),('location','')]:
    if name not in booking_columns:c.execute('ALTER TABLE cal_bookings ADD COLUMN '+name+" TEXT NOT NULL DEFAULT '"+default+"'")
 @contextlib.contextmanager
 def db(self,write=False):
  c=sqlite3.connect(self.path,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL')
  try:
   if write:c.execute('BEGIN IMMEDIATE')
   yield c;c.commit()
  except Exception:c.rollback();raise
  finally:c.close()
 def profile(self,owner,username=None):
  with self.db(True) as c:
   r=c.execute('SELECT * FROM cal_profiles WHERE owner=?',(owner,)).fetchone()
   if r:return dict(r)
   username=username_value(username or ('user-'+secrets.token_hex(6)))
   try:c.execute('INSERT INTO cal_profiles(owner,username) VALUES(?,?)',(owner,username))
   except sqlite3.IntegrityError:raise DomainError('This username is already in use.',409)
   return dict(c.execute('SELECT * FROM cal_profiles WHERE owner=?',(owner,)).fetchone())
 def update_profile(self,owner,data):
  self.profile(owner)
  with self.db(True) as c:
   before=dict(c.execute('SELECT * FROM cal_profiles WHERE owner=?',(owner,)).fetchone());name=text(data.get('display_name',before['display_name']),'full name');username=username_value(data.get('username',before['username']));tz=str(data.get('timezone',before['timezone']));zone(tz);about=str(data.get('about',before['about']))[:10000];location=str(data.get('location',before['location']))[:200]
   try:c.execute('UPDATE cal_profiles SET username=?,display_name=?,about=?,location=?,timezone=? WHERE owner=?',(username,name,about,location,tz,owner))
   except sqlite3.IntegrityError:raise DomainError('This username is already in use.',409)
   return dict(c.execute('SELECT * FROM cal_profiles WHERE owner=?',(owner,)).fetchone())
 def time_off(self,owner,data,ident=None):
  profile=self.profile(owner)
  try:
   start=date.fromisoformat(data.get('start_date',''));end=date.fromisoformat(data.get('end_date',''))
  except (ValueError,TypeError):raise DomainError('Choose a valid date range.')
  if end<start or end.year>=9999:raise DomainError('Choose a valid date range.')
  reason=data.get('reason','Unspecified')
  if reason not in ['Unspecified','Vacation','Travel','Sick leave','Public holiday']:raise DomainError('Choose a valid reason.')
  notes=data.get('notes','')
  if not isinstance(notes,str) or len(notes)>2000:raise DomainError('Notes must be at most 2000 characters.')
  if not isinstance(data.get('show_note',False),bool):raise DomainError('Invalid note visibility.')
  with self.db(True) as c:
   previous=c.execute('SELECT * FROM cal_time_off WHERE id=? AND owner=?',(ident,owner)).fetchone() if ident else None
   if ident and not previous:raise DomainError('Out of office entry not found.',404)
   tz=previous['timezone'] if previous else profile['timezone'];zone(tz);ident=ident or uid()
   c.execute('INSERT INTO cal_time_off VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET start_date=excluded.start_date,end_date=excluded.end_date,reason=excluded.reason,notes=excluded.notes,show_note=excluded.show_note',(ident,owner,str(start),str(end),tz,reason,notes,int(data.get('show_note',False))))
   return dict(c.execute('SELECT * FROM cal_time_off WHERE id=?',(ident,)).fetchone())
 def list_time_off(self,owner,public=False):
  with self.db() as c:
   rows=[dict(r) for r in c.execute('SELECT * FROM cal_time_off WHERE owner=? ORDER BY start_date,id',(owner,))]
  if public:return [{k:r[k] for k in ['start_date','end_date','timezone','notes']} for r in rows if r['show_note'] and r['notes']]
  return rows
 def delete_time_off(self,owner,ident):
  with self.db(True) as c:
   if not c.execute('DELETE FROM cal_time_off WHERE id=? AND owner=?',(ident,owner)).rowcount:raise DomainError('Out of office entry not found.',404)
  return {'ok':True}
 def reorder_events(self,owner,identifiers):
  if not isinstance(identifiers,list) or any(not isinstance(x,str) for x in identifiers):raise DomainError('Invalid link order.')
  with self.db(True) as c:
   ids={r['id'] for r in c.execute('SELECT id FROM cal_events WHERE owner=?',(owner,))}
   if len(identifiers)!=len(ids) or set(identifiers)!=ids:raise DomainError('Link order must include exactly your own links.',409)
   c.execute('DELETE FROM cal_event_order WHERE owner=?',(owner,))
   c.executemany('INSERT INTO cal_event_order VALUES(?,?,?)',[(owner,ident,i) for i,ident in enumerate(identifiers)])
  return {'ok':True,'order':identifiers}
 def schedule(self,owner,data,ident=None):
  with self.db(True) as c:
   old=c.execute('SELECT * FROM cal_schedules WHERE id=? AND owner=?',(ident,owner)).fetchone() if ident else None
   if ident and not old:raise DomainError('Schedule not found.',404)
   before=dict(old) if old else {};name=text(data.get('name',before.get('name')),'schedule name');tz=str(data.get('timezone',before.get('timezone','Asia/Shanghai')));zone(tz)
   weekly=windows(data.get('weekly',json.loads(before['weekly']) if old else {str(i):[['09:00','17:00']] for i in range(5)}));overrides=data.get('overrides',json.loads(before.get('overrides','{}')))
   if not isinstance(overrides,dict):raise DomainError('Invalid date overrides.')
   for day,rows in overrides.items():
    try:date.fromisoformat(day)
    except (ValueError,TypeError):raise DomainError('Invalid override date.')
    windows({'0':rows})
   default=bool(data.get('is_default',before.get('is_default',not c.execute('SELECT 1 FROM cal_schedules WHERE owner=?',(owner,)).fetchone())))
   if default:c.execute('UPDATE cal_schedules SET is_default=0 WHERE owner=?',(owner,))
   ident=ident or uid();c.execute('INSERT INTO cal_schedules VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,timezone=excluded.timezone,weekly=excluded.weekly,overrides=excluded.overrides,is_default=excluded.is_default',(ident,owner,name,tz,json.dumps(weekly),json.dumps(overrides),int(default)))
   return self.schedule_dict(c.execute('SELECT * FROM cal_schedules WHERE id=?',(ident,)).fetchone())
 @staticmethod
 def schedule_dict(row):
  d=dict(row);d['weekly']=json.loads(d['weekly']);d['overrides']=json.loads(d['overrides']);d['is_default']=bool(d['is_default']);return d
 @staticmethod
 def event_dict(row):
  d=dict(row);d['options']=json.loads(d['options']);d['hidden']=bool(d['hidden']);return d
 def event(self,owner,data,ident=None):
  with self.db(True) as c:
   old=c.execute('SELECT * FROM cal_events WHERE id=? AND owner=?',(ident,owner)).fetchone() if ident else None
   if ident and not old:raise DomainError('Link not found.',404)
   before=self.event_dict(old) if old else {};title=text(data.get('title',before.get('title')),'title');slug=str(data.get('slug',before.get('slug',''))).strip().lower()
   if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,119}',slug):raise DomainError('Enter a valid URL slug.')
   length=minutes(data.get('length',before.get('length',30)),'duration',1);sid=data.get('schedule_id',before.get('schedule_id'))
   if not sid:
    default=c.execute('SELECT id FROM cal_schedules WHERE owner=? ORDER BY is_default DESC,rowid LIMIT 1',(owner,)).fetchone();sid=default['id'] if default else None
   if not c.execute('SELECT 1 FROM cal_schedules WHERE id=? AND owner=?',(sid,owner)).fetchone():raise DomainError('Choose one of your availability schedules.')
   options=dict(before.get('options',{}));incoming=data.get('options',{})
   if not isinstance(incoming,dict):raise DomainError('Invalid link settings.')
   options.update(incoming)
   for key in ['minimum_notice','buffer_before','buffer_after','slot_interval']:
    if key in options:options[key]=minutes(options[key],key,1 if key=='slot_interval' else 0,525600 if key=='minimum_notice' else 1440)
   ident=ident or uid()
   try:c.execute('INSERT INTO cal_events VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,slug=excluded.slug,length=excluded.length,description=excluded.description,hidden=excluded.hidden,schedule_id=excluded.schedule_id,options=excluded.options',(ident,owner,title,slug,length,str(data.get('description',before.get('description','')))[:20000],int(bool(data.get('hidden',before.get('hidden',False)))),sid,json.dumps(options),before.get('created',int(time.time()))))
   except sqlite3.IntegrityError:raise DomainError('This URL is already in use.',409)
   return self.event_dict(c.execute('SELECT * FROM cal_events WHERE id=?',(ident,)).fetchone())
 def workspace(self,owner):
  profile=self.profile(owner)
  with self.db() as c:return {'profile':profile,'events':[self.event_dict(r) for r in c.execute('SELECT e.* FROM cal_events e LEFT JOIN cal_event_order o ON o.event_id=e.id AND o.owner=e.owner WHERE e.owner=? ORDER BY o.position IS NULL,o.position,e.created,e.rowid',(owner,))],'schedules':[self.schedule_dict(r) for r in c.execute('SELECT * FROM cal_schedules WHERE owner=? ORDER BY rowid',(owner,))],'bookings':[self.booking_dict(r) for r in c.execute('SELECT * FROM cal_bookings WHERE owner=? ORDER BY start DESC',(owner,))]}
 def public_event(self,username,slug):
  with self.db() as c:
   row=c.execute('SELECT e.* FROM cal_events e JOIN cal_profiles p ON p.owner=e.owner WHERE p.username=? AND e.slug=?',(username,slug)).fetchone()
   if not row:raise DomainError('This booking link could not be found.',404)
   return self.event_dict(row)
 def create_private_link(self,owner,event_id):
  token=uid()
  with self.db(True) as c:
   if not c.execute('SELECT 1 FROM cal_events WHERE id=? AND owner=?',(event_id,owner)).fetchone():raise DomainError('Link not found.',404)
   c.execute('INSERT INTO cal_private_links VALUES(?,?,?,NULL,?)',(hashlib.sha256(token.encode()).hexdigest(),owner,event_id,int(time.time())))
  return {'path':'/d/'+token,'single_use':True}
 def private_event(self,token,connection=None):
  if connection is None:
   with self.db() as c:return self.private_event(token,c)
  row=connection.execute('SELECT e.* FROM cal_private_links p JOIN cal_events e ON e.id=p.event_id AND e.owner=p.owner WHERE p.digest=? AND p.used_booking_id IS NULL',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
  if not row:raise DomainError('This private link is unavailable or has already been used.',404)
  return self.event_dict(row)
 def slots(self,event_id,day,display_timezone='UTC',now=None,ignore_booking=None,connection=None):
  try:wanted=date.fromisoformat(day)
  except (ValueError,TypeError):raise DomainError('Choose a valid date.')
  display=zone(display_timezone);now=int(time.time()) if now is None else now
  if connection is None:
   with self.db() as c:return self.slots(event_id,day,display_timezone,now,ignore_booking,c)
  c=connection;row=c.execute('SELECT * FROM cal_events WHERE id=?',(event_id,)).fetchone()
  if not row:raise DomainError('Link not found.',404)
  event=self.event_dict(row);schedule=self.schedule_dict(c.execute('SELECT * FROM cal_schedules WHERE id=?',(event['schedule_id'],)).fetchone());tz=zone(schedule['timezone']);opts=event['options'];start_day=datetime.combine(wanted,datetime.min.time(),display);end_day=datetime.combine(wanted+timedelta(days=1),datetime.min.time(),display);first=start_day.astimezone(tz).date()-timedelta(days=1);last=end_day.astimezone(tz).date()+timedelta(days=1);busy=c.execute("SELECT busy_start AS start,busy_end AS end FROM cal_bookings WHERE owner=? AND status IN ('confirmed','pending') AND (? IS NULL OR id!=?)",(event['owner'],ignore_booking,ignore_booking)).fetchall();result=set();current=first
  # Inclusive calendar dates are converted in the timezone saved with the entry.
  # Test absolute overlap so a guest's display timezone cannot bypass an absence.
  absences=[]
  for absence in c.execute('SELECT * FROM cal_time_off WHERE owner=?',(event['owner'],)):
   away_zone=zone(absence['timezone']);away_start=datetime.combine(date.fromisoformat(absence['start_date']),datetime.min.time(),away_zone);away_end=datetime.combine(date.fromisoformat(absence['end_date'])+timedelta(days=1),datetime.min.time(),away_zone)
   absences.append((int(away_start.timestamp()),int(away_end.timestamp())))
  while current<=last:
   intervals=schedule['overrides'].get(str(current),schedule['weekly'].get(str(current.weekday()),[]))
   for begin,end in intervals:
    wall=datetime.fromisoformat(str(current)+'T'+begin);limit=datetime.fromisoformat(str(current)+'T'+end);end_stamp=max(int(limit.replace(tzinfo=tz,fold=f).timestamp()) for f in [0,1])
    while wall<limit:
     for fold in [0,1]:
      candidate=wall.replace(tzinfo=tz,fold=fold);ts=int(candidate.timestamp());finish=ts+event['length']*60
      if datetime.fromtimestamp(ts,tz).replace(tzinfo=None)!=wall:continue
      if ts<now+opts.get('minimum_notice',0)*60 or finish>end_stamp or not int(start_day.timestamp())<=ts<int(end_day.timestamp()):continue
      lo=ts-opts.get('buffer_before',0)*60;hi=finish+opts.get('buffer_after',0)*60
      if any(lo<r['end'] and hi>r['start'] for r in busy):continue
      if any(ts<end and finish>start for start,end in absences):continue
      result.add(ts)
     wall+=timedelta(minutes=opts.get('slot_interval',event['length']))
   current+=timedelta(days=1)
  return [{'start':iso(ts),'end':iso(ts+event['length']*60),'local':datetime.fromtimestamp(ts,display).isoformat()} for ts in sorted(result)]
 @staticmethod
 def booking_dict(row):
  d={k:row[k] for k in row.keys() if k not in ['manage_hash','idempotency_key','request_hash','busy_start','busy_end']}
  if 'guests' in d:d['guests']=json.loads(d['guests'])
  return d
 def _queue_mail(self,c,booking,token,base,action):
  if not re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):1821[0-9]',base.rstrip('/')):raise DomainError('Invalid local booking origin.')
  summary=f"{booking['title']}\n{iso(booking['start'])} – {iso(booking['end'])}\nStatus: {booking['status']}\n"
  if booking.get('topic'):summary+='Topic: '+booking['topic']+'\n'
  if booking.get('location'):summary+='Location: '+booking['location']+'\n'
  body=summary+f"Manage this booking: {base.rstrip('/')}/booking/{booking['id']}?token={token}\n"
  deliveries={booking['attendee_email']:body}
  for guest in json.loads(booking.get('guests','[]')):deliveries.setdefault(guest,summary)
  if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_auth_accounts'").fetchone():
   organizer=c.execute('SELECT email_normalized FROM local_auth_accounts WHERE account_id=?',(booking['owner'],)).fetchone()
   if organizer:deliveries[organizer['email_normalized']]=summary+f"Attendee: {booking['attendee_name']} <{booking['attendee_email']}>\nPhone: {booking.get('phone','')}\nNotes: {booking.get('notes','')}\nManage this booking: {base.rstrip('/')}/booking/{booking['id']}\n"
  for recipient,content in deliveries.items():c.execute('INSERT INTO cal_mail(id,owner,booking_id,recipient,subject,body,created) VALUES(?,?,?,?,?,?,?)',(uid(),booking['owner'],booking['id'],recipient,action+': '+booking['title'],content,int(time.time())))
 def book(self,event_id,data,base,idempotency_key=None,now=None,private_token=None):
  start=stamp(data.get('start'));name=text(data.get('name'),'name');recipient=email(data.get('email'));tz=str(data.get('timezone','UTC'));zone(tz);now=int(time.time()) if now is None else now
  phone=str(data.get('attendeePhoneNumber','')).strip()
  if phone and (len(phone)>40 or not re.fullmatch(r'[+0-9() .-]+',phone)):raise DomainError('Enter a valid phone number.')
  guests=data.get('guests',[])
  if not isinstance(guests,list) or len(guests)>20:raise DomainError('Enter up to 20 guest email addresses.')
  guests=list(dict.fromkeys(email(x) for x in guests if email(x)!=recipient));topic=str(data.get('title','')).strip()
  if len(topic)>200 or '\n' in topic or '\r' in topic:raise DomainError('Enter a valid meeting topic.')
  digest=hashlib.sha256(json.dumps({'event':event_id,'start':start,'name':name,'email':recipient,'timezone':tz,'notes':data.get('notes',''),'phone':phone,'guests':guests,'topic':topic},sort_keys=True).encode()).hexdigest();token=uid()
  with self.db(True) as c:
   if private_token and self.private_event(private_token,c)['id']!=event_id:raise DomainError('Private link not found.',404)
   row=c.execute('SELECT * FROM cal_events WHERE id=?',(event_id,)).fetchone()
   if not row:raise DomainError('Link not found.',404)
   event=self.event_dict(row)
   if event['options'].get('requires_topic') and not topic:raise DomainError('Tell us what this meeting is about.')
   if idempotency_key:
    old=c.execute('SELECT * FROM cal_bookings WHERE owner=? AND idempotency_key=?',(event['owner'],idempotency_key)).fetchone()
    if old:
     if old['request_hash']!=digest:raise DomainError('This request key was used for another booking.',409)
     return {**self.booking_dict(old),'replayed':True}
   day=str(datetime.fromtimestamp(start,zone(tz)).date());allowed=self.slots(event_id,day,tz,now,connection=c)
   if iso(start) not in {s['start'] for s in allowed}:raise DomainError('This time is no longer available. Choose another time.',409)
   ident=uid();status='pending' if event['options'].get('requires_confirmation') else 'confirmed';end=start+event['length']*60
   c.execute('INSERT INTO cal_bookings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,event['owner'],event_id,event['title'],start,end,start-event['options'].get('buffer_before',0)*60,end+event['options'].get('buffer_after',0)*60,name,recipient,tz,str(data.get('notes',''))[:10000],status,hashlib.sha256(token.encode()).hexdigest(),idempotency_key,digest,now,now,topic,phone,json.dumps(guests),str(event['options'].get('location',''))))
   booking=dict(c.execute('SELECT * FROM cal_bookings WHERE id=?',(ident,)).fetchone());self._queue_mail(c,booking,token,base,'Booking received' if status=='pending' else 'Booking confirmed')
   if private_token:c.execute('UPDATE cal_private_links SET used_booking_id=? WHERE digest=?',(ident,hashlib.sha256(private_token.encode()).hexdigest()))
   return {**self.booking_dict(booking),'manage_token':token}
 def _authorized_booking(self,c,ident,owner=None,token=None):
  row=c.execute('SELECT * FROM cal_bookings WHERE id=?',(ident,)).fetchone()
  if not row or not (owner==row['owner'] or token and secrets.compare_digest(row['manage_hash'],hashlib.sha256(token.encode()).hexdigest())):raise DomainError('Booking not found.',404)
  return dict(row)
 def change_booking(self,ident,action,data,base,owner=None,token=None,now=None):
  now=int(time.time()) if now is None else now
  with self.db(True) as c:
   booking=self._authorized_booking(c,ident,owner,token);mail_token=token or uid()
   if action=='cancel':
    if booking['status']=='cancelled':return self.booking_dict(booking)
    c.execute("UPDATE cal_bookings SET status='cancelled',updated=? WHERE id=?",(now,ident));subject='Booking cancelled'
   elif action=='reschedule':
    if booking['status']=='cancelled':raise DomainError('This booking has been cancelled.',409)
    start=stamp(data.get('start'));day=str(datetime.fromtimestamp(start,zone(booking['timezone'])).date());allowed=self.slots(booking['event_id'],day,booking['timezone'],now,ident,c)
    if iso(start) not in {s['start'] for s in allowed}:raise DomainError('This time is no longer available.',409)
    event=self.event_dict(c.execute('SELECT * FROM cal_events WHERE id=?',(booking['event_id'],)).fetchone());end=start+event['length']*60
    c.execute('UPDATE cal_bookings SET start=?,end=?,busy_start=?,busy_end=?,updated=? WHERE id=?',(start,end,start-event['options'].get('buffer_before',0)*60,end+event['options'].get('buffer_after',0)*60,now,ident));subject='Booking rescheduled'
   elif action=='confirm' and owner==booking['owner']:
    if booking['status']!='pending':raise DomainError('Only pending bookings can be confirmed.',409)
    c.execute("UPDATE cal_bookings SET status='confirmed',updated=? WHERE id=?",(now,ident));subject='Booking confirmed'
   else:raise DomainError('Unknown booking action.')
   if token is None:c.execute('UPDATE cal_bookings SET manage_hash=? WHERE id=?',(hashlib.sha256(mail_token.encode()).hexdigest(),ident))
   result=dict(c.execute('SELECT * FROM cal_bookings WHERE id=?',(ident,)).fetchone());self._queue_mail(c,result,mail_token,base,subject);return self.booking_dict(result)
