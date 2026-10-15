import time,json
from pathlib import Path
from fastapi import APIRouter,Request,UploadFile,File,HTTPException
from fastapi.responses import FileResponse
from backend.services import db,require_account,account,check_csrf,backend,survey_owned
from backend.survey_model import new_id
router=APIRouter();FILES=backend.lifecycle.database_path.parent/'uploads';FILES.mkdir(exist_ok=True)
ALLOWED={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','image/gif':'.gif','application/pdf':'.pdf','text/plain':'.txt','text/csv':'.csv'}
async def store(file,survey,collector,owner):
 content=await file.read(5*1024*1024+1)
 if not content or len(content)>5*1024*1024:raise HTTPException(422,'Choose a file between 1 byte and 5 MB.')
 mime=file.content_type or 'application/octet-stream'
 if mime not in ALLOWED:raise HTTPException(422,'Choose a PNG, JPG, WEBP, GIF, PDF, TXT or CSV file.')
 if mime=='image/png' and not content.startswith(b'\x89PNG\r\n\x1a\n') or mime=='image/jpeg' and not content.startswith(b'\xff\xd8') or mime=='image/gif' and not content.startswith((b'GIF87a',b'GIF89a')) or mime=='image/webp' and not(content.startswith(b'RIFF') and content[8:12]==b'WEBP') or mime=='application/pdf' and not content.startswith(b'%PDF-'):raise HTTPException(422,'The file content does not match its type.')
 id=new_id();name=Path(file.filename or 'attachment').name[:200];path=id+ALLOWED[mime];(FILES/path).write_bytes(content)
 try:
  with db() as c:c.execute('INSERT INTO sm_attachments VALUES (?,?,?,?,?,?,?,?,?)',(id,survey,collector,owner,name,mime,path,len(content),int(time.time())))
 except Exception:
  (FILES/path).unlink(missing_ok=True);raise
 return {'id':id,'name':name,'size':len(content),'url':'/api/media/'+id,'mime':mime}
@router.post('/api/surveys/{id}/media')
async def owner_upload(id:str,request:Request,file:UploadFile=File(...)):
 check_csrf(request);owner=require_account(request)['account_id']
 with db() as c:survey_owned(c,id,owner)
 if not(file.content_type or '').startswith('image/'):raise HTTPException(422,'Choose an image for your survey.')
 return await store(file,id,None,owner)
@router.post('/api/respond/{token}/files')
async def respondent_upload(token:str,request:Request,file:UploadFile=File(...)):
 check_csrf(request)
 with db() as c:
  row=c.execute('SELECT * FROM sm_collectors WHERE token=? AND status="open"',(token,)).fetchone()
  if not row:raise HTTPException(404,'This survey is unavailable.')
  survey_owned(c,row['survey_id'],c.execute('SELECT owner FROM sm_surveys WHERE id=?',(row['survey_id'],)).fetchone()[0])
 return await store(file,row['survey_id'],row['id'],None)
@router.get('/api/media/{id}')
def get_media(id:str,request:Request):
 user=account(request)
 with db() as c:
  row=c.execute('SELECT a.*,s.owner survey_owner,s.deleted FROM sm_attachments a JOIN sm_surveys s ON s.id=a.survey_id WHERE a.id=?',(id,)).fetchone()
  if not row or row['deleted']:raise HTTPException(404,'File not found.')
  owned=user and user['account_id']==row['survey_owner']
  public_image=row['collector_id'] is None and c.execute('SELECT 1 FROM sm_collectors WHERE survey_id=? AND status="open"',(row['survey_id'],)).fetchone()
  if not owned and not public_image:raise HTTPException(404,'File not found.')
  return FileResponse(FILES/row['path'],media_type=row['mime'],filename=row['name'],content_disposition_type='inline' if row['collector_id'] is None else 'attachment')
