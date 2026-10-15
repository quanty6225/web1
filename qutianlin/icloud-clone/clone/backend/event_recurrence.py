"""Recurring event start dates and precise instance/future cancellation."""
from datetime import date,timedelta


def starts_on(event,value,include_excluded=False):
    try:day=date.fromisoformat(value);first=date.fromisoformat(event['start'][:10])
    except (TypeError,ValueError,KeyError):return False
    if day.isoformat()!=value or day<first:return False
    if event.get('_until') and value>event['_until']:return False
    if not include_excluded and value in event.get('_excluded',[]):return False
    repeat=event.get('repeat','Never')
    if repeat!='Never' and day!=first:
        from backend.calendar_time import valid_occurrence_time
        if not valid_occurrence_time(event,day):return False
    if repeat=='Never':return day==first
    if repeat=='Every Day':return True
    if repeat=='Every Week':return day.weekday()==first.weekday()
    if repeat=='Every Month':return day.day==first.day
    if repeat=='Every Year':return (day.month,day.day)==(first.month,first.day)
    return False


def cancel(event,value,scope):
    if scope not in ('one','future'):raise ValueError('Choose only this event or this and future events.')
    if not isinstance(value,str) or not starts_on(event,value):raise ValueError('Choose an existing occurrence of this event.')
    if event.get('repeat','Never')=='Never':return None
    if scope=='future' and value==event['start'][:10]:return None
    changed={**event}
    if scope=='one':changed['_excluded']=sorted(set(event.get('_excluded',[]))|{value})
    else:
        changed['_until']=(date.fromisoformat(value)-timedelta(days=1)).isoformat()
        changed['_excluded']=[day for day in event.get('_excluded',[]) if day<=changed['_until']]
    return changed
