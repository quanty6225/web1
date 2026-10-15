"""Offline status archive with calendar-only empty periods before source creation."""
import calendar,json,copy,re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from fastapi import HTTPException,Query,Request
from fastapi.responses import FileResponse,Response
ROOT=Path(__file__).parent;DATA=ROOT/'static/status-data'
def data_for(kind,page,component='mq77zy384hvj'):
 index=json.loads((DATA/'index.json').read_text());key='history-'+str(page) if kind=='history' else 'uptime-'+component+'-'+str(page);path=DATA/(key+'.json')
 if path.exists():return json.loads(path.read_text())
 if kind=='uptime' and component+':37' not in index['uptime_states']:raise HTTPException(404,'Component not found.')
 if page<=37:raise HTTPException(503,'The local status archive is incomplete for this period.')
 # Source page was created in January 2018. Source page 37 demonstrates
 # empty incident lists and each component's own unavailable/no-downtime default.
 # Only dates are computed; no incident, downtime or uptime observation is added.
 end=2026*12+9-(page-1)*3
 if end-2<12:raise HTTPException(422,'Date is outside the supported calendar.')
 months=[]
 template=json.loads((DATA/('uptime-'+component+'-37.json')).read_text()) if kind=='uptime' else None
 if template:
  day_template={k:v for k,v in template['months'][0]['days'][0].items() if k!='date'}
  assert all(m['uptime_percentage']==template['months'][0]['uptime_percentage'] and all({k:v for k,v in d.items() if k!='date'}==day_template for d in m['days']) for m in template['months'])
 for offset in [-2,-1,0]:
  year,zero_month=divmod(end+offset,12);month=zero_month+1;weekday,days=calendar.monthrange(year,month);name=calendar.month_name[month]
  if kind=='history':months.append({'name':name,'year':year,'starts_on':(weekday+1)%7,'days':days,'incidents':[]})
  else:months.append({'name':name,'year':year,'start_offset':(weekday+1)%7,'uptime_percentage':template['months'][0]['uptime_percentage'],'days':[{**copy.deepcopy(day_template),'date':date(year,month,n).isoformat()+'T00:00:00.000Z'} for n in range(1,days+1)]})
 return {**(template or {}),'months':months if kind=='uptime' else list(reversed(months))}
def install(app):
 @app.get('/status/history.atom')
 @app.get('/status/history.rss')
 def feed(req:Request):
  name=req.url.path.rsplit('/',1)[-1];tree=ET.fromstring((ROOT/'backend/status-feeds'/name).read_bytes());base=str(req.base_url).rstrip('/')
  for node in tree.iter():
   for key,value in list(node.attrib.items()):
    if value.startswith('/') and not value.startswith('//'):node.set(key,base+value)
   if node.text:
    if node.text.startswith('/') and not node.text.startswith('//'):node.text=base+node.text
    node.text=re.sub(r'(href=[\"\'])/(?!/)',lambda m:m.group(1)+base+'/',node.text)
  return Response(ET.tostring(tree,encoding='utf-8',xml_declaration=True),media_type='application/atom+xml' if name.endswith('.atom') else 'application/rss+xml')
 @app.get('/api/status/history')
 def history(page:int=Query(1,ge=1)):return data_for('history',page)
 @app.get('/api/status/uptime/{component}')
 def uptime(component:str,page:int=Query(1,ge=1)):
  if not component.isalnum():raise HTTPException(404,'Component not found.')
  return data_for('uptime',page,component)
 @app.get('/status/uptime/{component}')
 def component_page(component:str):
  data_for('uptime',1,component)
  return FileResponse(ROOT/'status/uptime/index.html',media_type='text/html')
