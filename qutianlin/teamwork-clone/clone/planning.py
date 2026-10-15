"""Working hours and resource totals derived from this workspace's actual data."""
import json,re
from datetime import date,datetime,timedelta
from fastapi import Request,HTTPException
DEFAULT=[{'enabled':i<5,'start':'08:00','end':'16:00'} for i in range(7)]
def install(app,db,owner,account,workspace):
 def schedule(c,who):
  row=c.execute("SELECT value FROM tw_preferences WHERE owner=? AND key='working_hours'",(who,)).fetchone();return json.loads(row['value']) if row else DEFAULT
 @app.get('/api/working-hours')
 def working_hours(req:Request):
  with db() as c:return schedule(c,account(req)['account_id'])
 @app.put('/api/working-hours')
 async def save_hours(req:Request):
  data=await req.json()
  if not isinstance(data,list) or len(data)!=7:raise HTTPException(422,'Enter working hours for all seven days.')
  clean=[]
  for day in data:
   if not isinstance(day,dict):raise HTTPException(422,'Enter valid working hours.')
   start,end=day.get('start',''),day.get('end','')
   if not all(isinstance(v,str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v) for v in [start,end]):raise HTTPException(422,'Enter times in HH:MM format.')
   if day.get('enabled') and end<=start:raise HTTPException(422,'End time must be later than start time.')
   clean.append({'enabled':bool(day.get('enabled')),'start':start,'end':end})
  with db() as c:c.execute("INSERT INTO tw_preferences VALUES(?,'working_hours',?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value",(account(req)['account_id'],json.dumps(clean)))
  return {'ok':True,'days':clean}
 @app.get('/api/planning')
 def planning(req:Request):
  ws=workspace(req);today=date.today()
  try:
   start=date.fromisoformat(req.query_params.get('from',today.isoformat()));end=date.fromisoformat(req.query_params.get('to',(today+timedelta(days=6)).isoformat()))
  except (TypeError,ValueError):raise HTTPException(422,'Choose valid dates.')
  if end<start or (end-start).days>366:raise HTTPException(422,'Choose a date range of up to one year.')
  with db() as c:
   people=c.execute('SELECT account_id,display_name,created_at FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(owner(req),owner(req))).fetchall();people=[{**dict(p),'hours':schedule(c,p['account_id'])} for p in people]
  rights=ws.get('permissions');people=[p for p in people if rights is None or rights.get('Project Administrator') or rights.get('View People') or p['account_id']==account(req)['account_id']]
  rows=[]
  for person in people:
   capacity=0;days=[]
   for offset in range((end-start).days+1):
    day=start+timedelta(days=offset);hours=person['hours'][day.weekday()];minutes=lambda value:int(value[:2])*60+int(value[3:]);available=minutes(hours['end'])-minutes(hours['start']) if hours['enabled'] and day>=datetime.fromtimestamp(person['created_at']).date() else 0;capacity+=available;days.append({'date':day.isoformat(),'available':available})
   tasks=[t for t in ws['tasks'] if person['account_id'] in t.get('assignee_ids',[]) and (not t['due_date'] or start.isoformat()<=t['due_date']<=end.isoformat())];logs=[r for r in ws['records'] if r['kind']=='time' and r['data'].get('actor',owner(req))==person['account_id'] and start.isoformat()<=r['data'].get('date','')<=end.isoformat()];estimate=sum(t['estimate'] for t in tasks if not t['completed']);logged=sum(r['data']['minutes'] for r in logs)
   rows.append({'id':person['account_id'],'name':person['display_name'],'capacity':capacity,'estimated':estimate,'logged':logged,'remaining':capacity-estimate,'open_tasks':sum(not t['completed'] for t in tasks),'completed_tasks':sum(bool(t['completed']) for t in tasks),'days':days,'tasks':[{'id':t['id'],'title':t['title'],'due_date':t['due_date'],'estimate':t['estimate'],'completed':bool(t['completed'])} for t in tasks]})
  return {'from':start.isoformat(),'to':end.isoformat(),'people':rows,'unassigned':[t for t in ws['tasks'] if not t.get('assignee_ids')]}
