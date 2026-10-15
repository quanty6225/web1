"""Calculate task/focus counters from owned records using captured response shapes."""
import datetime,time,json
from pathlib import Path

def habit_week(d):
 today=datetime.datetime.now(datetime.timezone.utc).date()
 start=today-datetime.timedelta(days=(today.weekday()+1)%7)
 habits=[h for h in d.get('habits',{}).values() if not h.get('deleted') and not h.get('archived')]
 result={}
 for offset in range(7):
  day=start+datetime.timedelta(days=offset);key=day.strftime('%Y%m%d')
  completed={c.get('habitId') for c in d.get('habitCheckins',{}).values() if str(c.get('checkinStamp'))==key and c.get('status',0)>0}
  result[key]={'totalHabitCount':len(habits),'completedHabitCount':sum(h['id'] in completed for h in habits)}
 return result

def statistics(d,a,ranking=False):
 now=datetime.datetime.now(datetime.timezone.utc);today=now.date();yesterday=today-datetime.timedelta(days=1)
 def date(value):
  try:return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).date()
  except (ValueError,AttributeError):return None
 tasks=[t for t in d['tasks'].values() if not t.get('deleted')];completed=[t for t in tasks if t.get('status',0)>0]
 if ranking:
  # Captured starter tasks/lists do not contribute to the source account's
  # creation counters. Count locally created records independently of them.
  seed=json.loads((Path(__file__).parent/'seed/batch.json').read_text())
  starter_tasks={t['id'] for t in seed['syncTaskBean']['update']}
  starter_projects={p['id'] for p in seed['projectProfiles']}
  return {'ranking':0.0,'taskCount':sum(t['id'] not in starter_tasks for t in tasks),'projectCount':sum(p not in starter_projects for p in d['projects']),'dayCount':max(1,(int(time.time())-a.get('created_at',int(time.time())))//86400+1),'completedCount':len(completed),'score':0,'level':1}
 pomos=list(d.get('pomodoros',{}).values());timings=list(d.get('timings',{}).values());allfocus=pomos+timings
 def duration(t):
  try:
   start=datetime.datetime.fromisoformat(t['startTime'].replace('Z','+00:00'));end=datetime.datetime.fromisoformat(t['endTime'].replace('Z','+00:00'));return max(0,(end-start).total_seconds()-t.get('pauseDuration',0))/60
  except (KeyError,ValueError,TypeError):return 0
 def totals(day):return sum(date(t.get('completedTime'))==day for t in completed)
 out={'score':0,'level':1,'yesterdayCompleted':totals(yesterday),'todayCompleted':totals(today),'totalCompleted':len(completed),'todayPomoCount':sum(date(t.get('endTime'))==today for t in pomos),'yesterdayPomoCount':sum(date(t.get('endTime'))==yesterday for t in pomos),'totalPomoCount':len(pomos),'todayPomoDuration':sum(duration(t) for t in allfocus if date(t.get('endTime'))==today),'yesterdayPomoDuration':sum(duration(t) for t in allfocus if date(t.get('endTime'))==yesterday),'totalPomoDuration':sum(duration(t) for t in allfocus),'pomoGoal':0,'pomoDurationGoal':0,'scoreByDay':{},'taskByDay':{},'taskByWeek':{},'taskByMonth':{},'pomoByDay':{},'pomoByWeek':{},'pomoByMonth':{}}
 def task_bucket(start,end):return {'completeCount':sum(start<=x<end for t in completed if (x:=date(t.get('completedTime'))) is not None),'notCompleteCount':sum(start<=x<end for t in tasks if not t.get('status') and (x:=date(t.get('dueDate') or t.get('startDate'))) is not None)}
 for n in range(6,-1,-1):
  day=today-datetime.timedelta(days=n);key=day.strftime('%Y%m%d');out['scoreByDay'][key]=0;out['taskByDay'][key]=task_bucket(day,day+datetime.timedelta(days=1))
  week=today-datetime.timedelta(days=(today.weekday()+1)%7+7*n);out['taskByWeek'][week.strftime('%Y%m%d')]=task_bucket(week,week+datetime.timedelta(days=7))
  monthnum=today.year*12+today.month-1-n;month=datetime.date(monthnum//12,monthnum%12+1,1);nextnum=monthnum+1;end=datetime.date(nextnum//12,nextnum%12+1,1);out['taskByMonth'][month.strftime('%Y%m%d')]=task_bucket(month,end)
 for kind,taskkey in [('Day','taskByDay'),('Week','taskByWeek'),('Month','taskByMonth')]:
  for key in out[taskkey]:
   start=datetime.datetime.strptime(key,'%Y%m%d').date()
   if kind=='Month':
    monthnum=start.year*12+start.month;end=datetime.date(monthnum//12,monthnum%12+1,1)
   else:end=start+datetime.timedelta(days=7 if kind=='Week' else 1)
   included=[t for t in allfocus if (dt:=date(t.get('endTime'))) is not None and start<=dt<end]
   if included:out['pomoBy'+kind][key]={'count':sum(t in pomos for t in included),'duration':sum(duration(t) for t in included)}
 return out
