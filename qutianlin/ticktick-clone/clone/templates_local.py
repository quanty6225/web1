"""Apply captured public template blueprints to independently owned local lists."""
import copy,json,secrets,re
from pathlib import Path
from fastapi import HTTPException
TEMPLATES=json.loads((Path(__file__).parent/'seed/public-templates.json').read_text())
def apply(ident,d,uid):
 source=TEMPLATES.get(ident)
 if source is None:raise HTTPException(404,'Template is not included in the captured selection')
 new_id=lambda:secrets.token_hex(12)
 project_id=new_id();meta=source['metaData'];project={'id':project_id,'name':source['name'],'color':'#4772FA','sortOrder':len(d['projects'])*1099511627776,'closed':False,'muted':False,'inAll':True,'kind':'TASK','viewMode':meta.get('viewMode') or 'list','sortType':meta.get('sortType') or 'sortOrder','permission':'write','userCount':1,'etag':new_id()}
 d['projects'][project_id]=project
 cols={x['id']:new_id() for x in meta.get('columns',[])};ids={x['id']:new_id() for x in meta['tasks']}
 for col in meta.get('columns',[]):
  cid=cols[col['id']];d['columns'][cid]={'id':cid,'projectId':project_id,'name':col['name'],'sortOrder':col.get('sortOrder',0),'etag':new_id()}
 for i,raw in enumerate(meta['tasks']):
  task={k:copy.deepcopy(raw[k]) for k in ['title','content','desc','items','startDate','dueDate','reminders','repeatFlag','repeatFrom','priority','tags','timeZone','floating','allDay'] if raw.get(k) is not None}
  task.update(id=ids[raw['id']],projectId=project_id,creator=uid,status=0,kind='TEXT',sortOrder=i*1099511627776,etag=new_id(),tags=[tag for tag in raw.get('tags',[]) if tag],columnId=cols.get(raw.get('columnId')),parentId=ids.get(raw.get('parentId')))
  if task.get('items'):
   for item in task['items']:item['id']=new_id();item['status']=0
  d['tasks'][task['id']]=task
 return {'projectId':project_id}
