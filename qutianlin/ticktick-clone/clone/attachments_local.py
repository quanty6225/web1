"""Account scoped binary attachments with original frontend upload routes."""
import base64,secrets
from urllib.parse import quote
from fastapi import HTTPException
from fastapi.responses import Response

def handle(path,method,body,req,a,d,db,save):
 if not path.startswith('attachment/'):return None
 parts=path.split('/');records=d.setdefault('attachments',{})
 if path=='attachment/isUnderQuota':return True
 if path=='attachment/dailyLimit':return 1 if d.get('subscription',{}).get('ends',0)==0 else 99
 upload=len(parts)>1 and parts[1]=='upload';offset=2 if upload else 1
 if len(parts)<offset+3:return None
 pid,tid,ident=parts[offset:offset+3];ident=ident.split('.',1)[0];task=d['tasks'].get(tid)
 if not task or task.get('projectId')!=pid:raise HTTPException(404,'Task not found')
 if upload:
  if pid in d.get('_shared',{}) and d['_shared'][pid]['grant']['permission'] not in ['write','edit','admin']:raise HTTPException(403,'This shared list is read only')
  raw=body.get('_file_bytes')
  if not isinstance(raw,bytes):raise HTTPException(400,'Choose an attachment')
  if len(raw)>10*1024*1024:raise HTTPException(413,'Attachment exceeds 10 MB')
  name=body.get('_filename','attachment');mime=body.get('_mime','application/octet-stream')
  if ident in records and (records[ident]['projectId']!=pid or records[ident]['taskId']!=tid):raise HTTPException(409,'Attachment ID already exists')
  records[ident]={'projectId':pid,'taskId':tid,'name':name,'mime':mime,'data':base64.b64encode(raw).decode()};save(db,a,d)
  return {'id':ident,'refId':ident,'projectId':pid,'taskId':tid,'fileName':name,'fileType':name.rsplit('.',1)[-1],'size':len(raw),'path':'/api/v1/attachment/'+pid+'/'+tid+'/'+ident,'status':0}
 row=records.get(ident)
 if not row or row['projectId']!=pid or row['taskId']!=tid:raise HTTPException(404,'Attachment not found')
 if method=='DELETE':del records[ident];save(db,a,d);return {}
 return Response(base64.b64decode(row['data']),media_type=row['mime'],headers={'Content-Disposition':('attachment' if req.query_params.get('action')=='download' else 'inline')+"; filename*=UTF-8''"+quote(row['name']),'Content-Security-Policy':"sandbox; default-src 'none'"})
