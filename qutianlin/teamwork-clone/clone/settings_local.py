"""Workspace settings and offline data exchange. No external service calls."""
import csv,io,json,re,secrets,time,zipfile
from urllib.parse import urlsplit
from fastapi import Request,HTTPException
from fastapi.responses import Response

DEFAULTS={'welcome_email':'','default_task_lists':['General tasks'],'message_categories':['Announcements','Communication','Important Updates'],'file_categories':['Documents','Important files','Photos'],'notebook_categories':['Project ideas','Project notes','Useful Information'],'link_categories':['Interesting Articles','Useful Resources'],'email_format':'[firstname] [lastname] ([installationName])','email_forwarded':False,'email_similar':False,'email_logo':True,'webhooks_enabled':False}

def install(app,db,owner,account,workspace,uploads,create_record,permission_defaults):
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS tw_settings(owner TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(owner,key))')
  c.execute('CREATE TABLE IF NOT EXISTS tw_webhook_events(id TEXT PRIMARY KEY,owner TEXT NOT NULL,webhook_id TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL,created INTEGER NOT NULL)')
 def admin(req):
  who=owner(req)
  if account(req)['account_id']!=who:raise HTTPException(403,'Only the workspace owner can change these settings.')
  return who
 def settings(who):
  with db() as c:return {**DEFAULTS,**{r['key']:json.loads(r['value']) for r in c.execute('SELECT key,value FROM tw_settings WHERE owner=?',(who,))}}
 @app.get('/api/settings/permissions')
 def read_permissions(req:Request):
  current=settings(owner(req));return [{**group,'values':{**{p['name']:p['enabled'] for p in group['permissions']},**current.get('permission:'+group['group'],{})}} for group in permission_defaults]
 @app.get('/api/settings')
 def read_settings(req:Request):return settings(owner(req))
 @app.put('/api/settings')
 async def save_settings(req:Request):
  who=admin(req);data=await req.json()
  if not isinstance(data,dict):raise HTTPException(422,'Expected settings.')
  for key,value in data.items():
   if key not in DEFAULTS and not key.startswith(('ai:','beta:','permission:','default_projects:')):raise HTTPException(422,'Unknown setting.')
   if key in DEFAULTS:
    if type(value)!=type(DEFAULTS[key]):raise HTTPException(422,'Invalid setting value.')
    if isinstance(value,list) and (len(value)>100 or any(not isinstance(s,str) or not s.strip() or len(s)>200 for s in value)):raise HTTPException(422,'Enter up to 100 non-empty names.')
    if isinstance(value,str) and len(value)>20000:raise HTTPException(422,'Setting is too long.')
   if key.startswith('permission:'):
    baseline=next((g for g in permission_defaults if key=='permission:'+g['group']),None)
    if not baseline or not isinstance(value,dict) or any(k not in {p['name'] for p in baseline['permissions']} or type(v)!=bool for k,v in value.items()):raise HTTPException(422,'Choose valid project permissions.')
    if any(p['locked'] and value.get(p['name'],p['enabled'])!=p['enabled'] for p in baseline['permissions']):raise HTTPException(422,'This permission is fixed for the selected user type.')
   if key.startswith('default_projects:'):
    valid={p['id'] for p in workspace(req)['projects']}
    if not isinstance(value,list) or any(p not in valid for p in value):raise HTTPException(422,'Choose projects in this workspace.')
  with db() as c:
   for key,value in data.items():c.execute('INSERT INTO tw_settings VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value',(who,key,json.dumps(value)))
  return {'ok':True,'settings':settings(who)}

 @app.get('/api/settings/tags')
 def tags(req:Request):
  data=workspace(req);defined={r['data']['title']:dict(r['data'],id=r['id']) for r in data['records'] if r['kind']=='tag'}
  for task in data['tasks']:
   for name in filter(None,map(str.strip,task['tag'].split(','))):defined.setdefault(name,{'title':name,'color':'#6e65c2','id':''})
  return [dict(tag,count=sum(name in [t.strip() for t in task['tag'].split(',')] for task in data['tasks'])) for name,tag in defined.items()]

 @app.post('/api/settings/tags')
 async def save_tag(req:Request):
  who=admin(req);data=await req.json();title=str(data.get('title','')).strip();previous=str(data.get('previous','')).strip();project=str(data.get('project',''))
  if not title or len(title)>100 or ',' in title:raise HTTPException(422,'Enter a tag name without commas.')
  color=str(data.get('color','#6e65c2'))
  if not re.fullmatch('#[0-9a-fA-F]{6}',color):raise HTTPException(422,'Choose a valid color.')
  if project and project not in {p['id'] for p in workspace(req)['projects']}:raise HTTPException(404,'Project not found.')
  with db() as c:
   rows=c.execute("SELECT id,data FROM tw_records WHERE owner=? AND kind='tag'",(who,)).fetchall()
   target=next((r for r in rows if json.loads(r['data'])['title']==previous),None)
   if any(json.loads(r['data'])['title']==title and (not target or r['id']!=target['id']) for r in rows):raise HTTPException(409,'This tag already exists.')
   tid=target['id'] if target else secrets.token_hex(12);value=json.dumps({'title':title,'color':color,'project':project})
   if target:c.execute('UPDATE tw_records SET data=? WHERE id=?',(value,tid))
   else:c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(tid,who,'tag','',value,int(time.time())))
   if previous and previous!=title:
    for row in c.execute('SELECT id,tag FROM tw_tasks WHERE owner=?',(who,)).fetchall():
     names=list(dict.fromkeys(title if n.strip()==previous else n.strip() for n in row['tag'].split(',') if n.strip()));c.execute('UPDATE tw_tasks SET tag=? WHERE owner=? AND id=?',(', '.join(names),who,row['id']))
  return {'ok':True,'id':tid}

 @app.post('/api/settings/tags/merge')
 async def merge_tags(req:Request):
  who=admin(req);data=await req.json();names=data.get('names',[]);target=str(data.get('target','')).strip()
  if not isinstance(names,list) or not names or any(not isinstance(n,str) for n in names) or ',' in target:raise HTTPException(422,'Select tags to merge or delete.')
  with db() as c:
   for row in c.execute('SELECT id,tag FROM tw_tasks WHERE owner=?',(who,)).fetchall():
    updated=list(dict.fromkeys(target if n.strip() in names else n.strip() for n in row['tag'].split(',')));c.execute('UPDATE tw_tasks SET tag=? WHERE owner=? AND id=?',(', '.join(filter(None,updated)),who,row['id']))
   for row in c.execute("SELECT id,data FROM tw_records WHERE owner=? AND kind='tag'",(who,)).fetchall():
    if json.loads(row['data'])['title'] in names and json.loads(row['data'])['title']!=target:c.execute('DELETE FROM tw_records WHERE id=?',(row['id'],))
  return {'ok':True}

 @app.get('/api/settings/export')
 def export(req:Request):
  admin(req);data=workspace(req);data.pop('account');data.pop('preferences');data.pop('workspace_owner')
  for group in ['projects','tasks','records']:
   for row in data[group]:row.pop('owner',None)
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
   z.writestr('workspace.json',json.dumps(data,ensure_ascii=False,indent=2));z.writestr('settings.json',json.dumps(settings(owner(req)),ensure_ascii=False,indent=2))
   for row in data['records']:
    if row['kind']=='file' and (uploads/row['id']).is_file():z.write(uploads/row['id'],'files/'+row['id']+'/'+row['data']['name'])
  return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="teamwork-backup.zip"'})

 @app.get('/api/settings/import/sample')
 def sample(req:Request):
  admin(req);return Response('First Name,Last Name,Email,Company\r\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="teamwork-import.csv"'})
 @app.post('/api/settings/import/{kind}')
 async def import_people(kind:str,req:Request):
  who=admin(req)
  if kind not in ['contacts','users']:raise HTTPException(422,'Choose users or contacts.')
  form=await req.form();file=form.get('file')
  if not file or not hasattr(file,'read'):raise HTTPException(422,'Choose a CSV or vCard file.')
  raw=await file.read(2*1024*1024+1)
  if len(raw)>2*1024*1024:raise HTTPException(413,'Choose a file smaller than 2 MB.')
  try:text=raw.decode('utf-8-sig')
  except UnicodeDecodeError:raise HTTPException(422,'Use UTF-8 encoding.')
  rows=[]
  if text.lstrip().startswith('BEGIN:VCARD'):
   for block in text.split('BEGIN:VCARD')[1:]:
    fields={line.split(':',1)[0].split(';')[0].upper():line.split(':',1)[1] for line in block.splitlines() if ':' in line};rows.append({'name':fields.get('FN',''),'email':fields.get('EMAIL',''),'company':fields.get('ORG','')})
  else:
   try:
    for row in csv.DictReader(io.StringIO(text)):
     r={re.sub('[^a-z]','',k.lower()):str(v or '').strip() for k,v in row.items() if k};rows.append({'name':r.get('name') or r.get('firstname','')+' '+r.get('lastname',''),'email':r.get('email') or r.get('emailaddress',''),'company':r.get('company','')})
   except csv.Error:raise HTTPException(422,'Invalid CSV.')
  if not rows or len(rows)>200:raise HTTPException(422,'Import 1 to 200 rows at a time.')
  for row in rows:
   row['name']=row['name'].strip();row['email']=row['email'].lower()
   if not row['name'] or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',row['email']):raise HTTPException(422,'Every row requires a name and valid email.')
  result=[]
  for row in rows:
   if kind=='users':
    class PayloadRequest:
     cookies=req.cookies;url=req.url;base_url=req.base_url
     async def json(self):return dict(row,title=row['name'])
    result.append(await create_record('invitation',PayloadRequest()))
   else:
    rid=secrets.token_hex(12)
    with db() as c:c.execute('INSERT INTO tw_records VALUES(?,?,?,?,?,?)',(rid,who,'contact','',json.dumps(dict(row,title=row['name'])),int(time.time())))
    result.append({'id':rid})
  return {'ok':True,'imported':len(result),'records':result,'status':'Invited' if kind=='users' else 'Imported'}

 @app.get('/api/settings/webhook-events')
 def webhook_events(req:Request):
  with db() as c:return [dict(r,payload=json.loads(r['payload'])) for r in c.execute('SELECT * FROM tw_webhook_events WHERE owner=? ORDER BY created DESC LIMIT 100',(admin(req),))]
 @app.middleware('http')
 async def record_webhook_event(req,call_next):
  response=await call_next(req)
  match=re.fullmatch(r'/api/(tasks|projects|records)(?:/([^/]+))?',req.url.path)
  if response.status_code<300 and req.method in ['POST','PATCH','DELETE'] and match:
   try:
    who=owner(req)
    if settings(who)['webhooks_enabled']:
     kind={'tasks':'TASK','projects':'PROJECT','records':(match[2] or '').upper()}.get(match[1]);event=kind+'.'+{'POST':'CREATED','PATCH':'UPDATED','DELETE':'DELETED'}[req.method]
     with db() as c:
      for row in c.execute("SELECT id,data FROM tw_records WHERE owner=? AND kind='webhook'",(who,)).fetchall():
       if json.loads(row['data']).get('event')==event:c.execute('INSERT INTO tw_webhook_events VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),who,row['id'],event,json.dumps({'path':req.url.path,'method':req.method,'status':'Captured locally; no external delivery'}),int(time.time())))
   except HTTPException:pass
  return response
 return settings
