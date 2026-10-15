"""Task comments, moves, backup import, and calendar feeds for owned data."""
import copy,secrets,json,time,re,csv,io
from fastapi import HTTPException
from fastapi.responses import Response

def handle(path,method,body,req,a,d,db,save,uid,seed):
 def persist():save(db,a,d)
 parts=path.split('/')
 if len(parts)==3 and parts[0]=='project' and parts[2]=='join':
  if parts[1] not in d['projects']:raise HTTPException(404,'List not found')
  return {'joined':True}
 if path in ['batch/taskProject','batch/taskParent']:
  rows=body if isinstance(body,list) else body.get('update',body.get('move',[]));result={'id2etag':{},'id2error':{}}
  for item in rows:
   ident=item.get('taskId',item.get('id'));task=d['tasks'].get(ident)
   if task is None:raise HTTPException(404,'Task not found')
   if path.endswith('taskProject'):
    pid=item.get('toProjectId',item.get('projectId'))
    if pid not in d['projects'] and pid!='inbox'+str(uid):raise HTTPException(404,'List not found')
    task['projectId']=pid
   else:
    parent=item.get('parentId')
    if parent and parent not in d['tasks']:raise HTTPException(404,'Parent task not found')
    task['parentId']=parent
   task['etag']=secrets.token_hex(8);result['id2etag'][ident]=task['etag']
  persist();return result
 if path in ['trash/restore','trash/delete','trash/empty']:
  ids=body if isinstance(body,list) else body.get('taskIds',body.get('ids',[]))
  if path.endswith('/empty'):ids=[x['id'] for x in d['tasks'].values() if x.get('deleted')]
  for item in ids:
   ident=item if isinstance(item,str) else item.get('taskId',item.get('id'));task=d['tasks'].get(ident)
   if not task:raise HTTPException(404,'Task not found')
   if path.endswith('/restore'):task['deleted']=0;task['status']=0
   else:del d['tasks'][ident]
  persist();return {}
 if len(parts)>=5 and parts[0]=='project' and parts[2]=='task' and parts[4] in ['comment','comments']:
  pid,tid=parts[1],parts[3];task=d['tasks'].get(tid)
  if not task or task.get('projectId')!=pid:raise HTTPException(404,'Task not found')
  comments=d.setdefault('comments',{}).setdefault(tid,{})
  if method=='GET':return list(comments.values())
  ident=parts[5] if len(parts)>5 else secrets.token_hex(12)
  if len(parts)>5 and ident not in comments:raise HTTPException(404,'Comment not found')
  if len(parts)>5 and comments[ident].get('creator')!=uid and pid in d.get('_shared',{}):raise HTTPException(403,'Only the author or list owner can edit this comment')
  if method=='DELETE':del comments[ident]
  else:
   content=body.get('content',body.get('text',''))
   if not isinstance(content,str) or not content.strip():raise HTTPException(400,'Comment cannot be empty')
   comments[ident]={**body,'id':ident,'taskId':tid,'projectId':pid,'userId':uid,'creator':uid,'content':content,'createdTime':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
  task['commentCount']=len(comments);persist();return comments.get(ident,{})
 if len(parts)==3 and parts[0]=='project' and parts[2]=='duplicate':
  if parts[1] not in d['projects']:raise HTTPException(404,'List not found')
  ident=secrets.token_hex(12);project={**d['projects'][parts[1]],**body,'id':ident};d['projects'][ident]=project
  tasks=[t for t in d['tasks'].values() if t.get('projectId')==parts[1]];mapping={t['id']:secrets.token_hex(12) for t in tasks}
  for task in tasks:
   tid=mapping[task['id']];d['tasks'][tid]={**task,'id':tid,'projectId':ident,'creator':uid,'parentId':mapping.get(task.get('parentId')),'commentCount':0}
  persist();return project
 if path=='task/activity/count/all':return {t:len(v) for t,v in d.get('comments',{}).items()}
 if path.startswith('task/activity/') or (len(parts)==3 and parts[0]=='project' and parts[-1]=='activity'):return []
 if path=='data/export/auto':return {'type':'direct'}
 if path.startswith('data/export/link/'):return {'url':'/api/v2/data/export','downloadUrl':'/api/v2/data/export'}
 if path=='import/restore':
  if not isinstance(body,dict) or body.get('format')!='ticktick-local-backup-v1' or not isinstance(body.get('data'),dict):raise HTTPException(400,'Select a valid TickTick JSON backup')
  source=body['data'];tables=['tasks','projects','columns','tags','filters','projectGroups','habits','habitRecords','habitCheckins','pomodoros','timings','comments','countdowns','attachments']
  for key in tables:
   if key in source:
    if not isinstance(source[key],dict):raise HTTPException(400,'Invalid backup collection')
    d[key]=copy.deepcopy(source[key])
  for task in d['tasks'].values():
   task['creator']=uid
   if str(task.get('projectId','')).startswith('inbox'):task['projectId']='inbox'+str(uid)
   elif task.get('projectId') not in d['projects']:raise HTTPException(400,'Backup contains a task without its list')
  persist();return {'restored':True}
 if path.startswith('import/'):
  text=body.get('_file_text','');pid=secrets.token_hex(12);name=body.get('_filename','Imported tasks').rsplit('.',1)[0];rows=[]
  if path.endswith('/ics'):
   for event in text.split('BEGIN:VEVENT')[1:]:
    fields={line.split(':',1)[0].split(';')[0]:line.split(':',1)[1] for line in event.splitlines() if ':' in line}
    def normalize(value):
     if not value:return None
     import datetime
     try:return datetime.datetime.strptime(value.rstrip('Z'),'%Y%m%d' if len(value)==8 else '%Y%m%dT%H%M%S').replace(tzinfo=datetime.timezone.utc).isoformat()
     except ValueError:raise HTTPException(400,'Invalid calendar event date')
    rows.append({'title':fields.get('SUMMARY',''),'content':fields.get('DESCRIPTION','').replace('\\n','\n'),'startDate':normalize(fields.get('DTSTART')),'dueDate':normalize(fields.get('DTEND')),'isAllDay':len(fields.get('DTSTART',''))==8})
  else:
   try:
    for row in csv.DictReader(io.StringIO(text)):rows.append({'title':row.get('Title',row.get('title',row.get('Task',row.get('task',row.get('CONTENT',''))))),'content':row.get('Notes',row.get('notes',''))})
   except (ValueError,csv.Error):raise HTTPException(400,'Invalid CSV')
  rows=[r for r in rows if r.get('title')]
  if not rows:raise HTTPException(400,'No tasks found in the selected file')
  d['projects'][pid]={**seed['projectProfiles'][0],'id':pid,'name':name,'isOwner':True}
  for row in rows:
   ident=secrets.token_hex(12);d['tasks'][ident]={**row,'id':ident,'projectId':pid,'creator':uid,'kind':'TEXT','status':0,'isAllDay':row.get('isAllDay',not row.get('startDate')),'sortOrder':0}
  persist();return {'projectId':pid,'imported':len(rows)}
 return None
