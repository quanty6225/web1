"""Offline IANA time zones and authorized calendar occurrence projections."""
import sys
from pathlib import Path
from datetime import date,datetime,time,timedelta,timezone
from functools import lru_cache

VENDOR=Path(__file__).resolve().parents[1]/'vendor'
if str(VENDOR) not in sys.path:sys.path.insert(0,str(VENDOR))
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError,available_timezones
from backend import event_recurrence
from backend.reminder_sharing import read

UTC=timezone.utc
DAY=timedelta(days=1)


def validate_zone(value,floating=True):
    if floating and value=='Floating':return value
    if not isinstance(value,str) or len(value)>128:raise ValueError('Choose a valid time zone.')
    try:ZoneInfo(value)
    except (ZoneInfoNotFoundError,ValueError):raise ValueError('Choose a valid time zone.')
    return value


@lru_cache(maxsize=1)
def zones():return sorted(available_timezones())


def account_zone(db,owner):
    value=(read(db,owner,'settings','preferences') or {}).get('timezone','America/Toronto')
    try:return validate_zone(value,False)
    except ValueError:return 'America/Toronto'


def validate_event(db,actor_owner,resource_owner,event,old):
    event['timezone']=validate_zone(event.get('timezone',old.get('timezone','Floating') if old else account_zone(db,actor_owner)))
    if not event['allDay'] and event['timezone']!='Floating':
        zone=ZoneInfo(event['timezone'])
        start=datetime.fromisoformat(event['start']).replace(tzinfo=zone).astimezone(UTC)
        end=datetime.fromisoformat(event['end']).replace(tzinfo=zone).astimezone(UTC)
        if end<start:raise ValueError('The end time must follow the start time in this time zone.')


def candidate_dates(event,first,last):
    base=date.fromisoformat(event['start'][:10]);first=max(first,base)
    if event.get('_until'):last=min(last,date.fromisoformat(event['_until']))
    if event.get('repeat','Never')=='Never':
        if event_recurrence.starts_on(event,base.isoformat()):yield base
        return
    step=DAY
    if event.get('repeat')=='Every Week':
        first+=timedelta(days=(base.weekday()-first.weekday())%7);step=timedelta(days=7)
    current=first
    while current<=last:
        if event_recurrence.starts_on(event,current.isoformat()):yield current
        if (date.max-current)<step:break
        current+=step


def valid_occurrence_time(event,day):
    if event.get('allDay') or event.get('timezone','Floating')=='Floating':return True
    wall=datetime.combine(day,datetime.fromisoformat(event['start']).time())
    zone=ZoneInfo(event['timezone'])
    return wall.replace(tzinfo=zone).astimezone(UTC).astimezone(zone).replace(tzinfo=None)==wall


def instance(event,day):
    """Editable values in the event's own zone, preserving exact DTEND duration."""
    if event.get('_recurrence_parent'):return {**event,'repeat':event.get('_series_repeat',event['repeat'])}
    if not event_recurrence.starts_on(event,day):raise ValueError('Choose an existing occurrence of this event.')
    start=datetime.fromisoformat(event['start']);end=datetime.fromisoformat(event['end'])
    shown=datetime.combine(date.fromisoformat(day),start.time())
    name=event.get('timezone','Floating')
    if not event.get('allDay') and name!='Floating':
        zone=ZoneInfo(name);duration=end.replace(tzinfo=zone).astimezone(UTC)-start.replace(tzinfo=zone).astimezone(UTC)
        finish=(shown.replace(tzinfo=zone).astimezone(UTC)+duration).astimezone(zone).replace(tzinfo=None)
    else:finish=shown+(end-start)
    return {**event,'start':shown.date().isoformat() if event.get('allDay') else shown.isoformat(timespec='minutes'),
            'end':finish.date().isoformat() if event.get('allDay') else finish.isoformat(timespec='minutes')}


def end_timestamp(event,display_zone):
    """Occurrence end in milliseconds; all-day local end dates are inclusive."""
    end=datetime.fromisoformat(event['end'])
    if event.get('allDay'):
        if end.date()==date.max:return None
        end+=DAY
    name=event.get('timezone','Floating')
    zone=ZoneInfo(display_zone if event.get('allDay') or name=='Floating' else name)
    return int(end.replace(tzinfo=zone).timestamp()*1000)


def time_label(value,formats=None):
    formats=formats or {}
    separator=formats.get('time_separator',':')
    clock=value.strftime('%H'+separator+'%M') if formats.get('time_format')=='24 Hour' else value.strftime('%I'+separator+'%M %p').lstrip('0')
    return clock+(' '+value.tzname() if value.tzinfo else '')


def project(events,first,last,display_zone,support,formats=None):
    """Dates in output are display dates; occurrence identifies the original series date."""
    try:
        begin=date.fromisoformat(first);finish=date.fromisoformat(last)
        if begin.isoformat()!=first or finish.isoformat()!=last or not 0<=(finish-begin).days<=41:raise ValueError()
    except (TypeError,ValueError):raise ValueError('Choose a calendar range of at most 42 days.')
    target=ZoneInfo(validate_zone(display_zone,False))
    result={(begin+timedelta(days=i)).isoformat():[] for i in range((finish-begin).days+1)}
    for event in events:
        all_day=event.get('allDay',False)
        start=datetime.fromisoformat(event['start']);end=datetime.fromisoformat(event['end'])+(DAY if all_day else timedelta())
        name=event.get('timezone','Floating')
        origin=None if all_day or name=='Floating' else ZoneInfo(validate_zone(name))
        duration=end-start if origin is None else end.replace(tzinfo=origin).astimezone(UTC)-start.replace(tzinfo=origin).astimezone(UTC)
        extra=max(0,duration.days)+3
        lower=max(date.min,begin-timedelta(days=min((begin-date.min).days,extra)))
        upper=finish+timedelta(days=min((date.max-finish).days,2))
        for occurrence in candidate_dates(event,lower,upper):
            wall=datetime.combine(occurrence,start.time())
            if origin:
                instant=wall.replace(tzinfo=origin).astimezone(UTC)
                normalized=instant.astimezone(origin).replace(tzinfo=None)
                # Explicit DTSTART uses the pre-gap offset; generated invalid times are omitted.
                if occurrence!=start.date() and normalized!=wall:continue
                zone=target if support else origin
                shown_start=instant.astimezone(zone);shown_end=(instant+duration).astimezone(zone)
                view_start=shown_start.replace(tzinfo=None);view_end=shown_end.replace(tzinfo=None)
                start_label=time_label(shown_start,formats);end_label=time_label(shown_end,formats)
            else:
                view_start=wall;view_end=wall+duration
                start_label=time_label(wall,formats);end_label=time_label(view_end,formats)
            start_day=max(begin,view_start.date());end_day=min(finish,view_end.date())
            day=start_day
            while day<=end_day:
                lo=datetime.combine(day,time.min);hi=lo+DAY
                if view_start<hi and (view_end>lo or duration==timedelta() and view_start>=lo):
                    minute_start=max(0,(view_start-lo).total_seconds()/60)
                    minute_end=min(1440,(view_end-lo).total_seconds()/60)
                    result[day.isoformat()].append({'id':event['id'],'_occurrence':occurrence.isoformat(),
                        '_view_start':view_start.isoformat(timespec='minutes'),'_view_end':view_end.isoformat(timespec='minutes'),
                        '_start_label':start_label,'_end_label':end_label,'_minute_start':minute_start,'_minute_end':max(minute_start,minute_end)})
                if day==date.max:break
                day+=DAY
    return result


@lru_cache(maxsize=32)
def timezone_component(name):
    from icalendar import Timezone
    # Include a long explicit transition range, rather than a 2038 cutoff.
    return Timezone.from_tzinfo(ZoneInfo(name),first_date=date(1,1,1),last_date=date(9998,1,1)).to_ical().decode()


def utc_until(value,name):
    return datetime.combine(date.fromisoformat(value),time(23,59,59)).replace(tzinfo=ZoneInfo(name)).astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')
