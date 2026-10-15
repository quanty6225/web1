"""Chat attachments: real uploaded bytes, transactional claiming and access checks."""
import json,secrets,time
from pathlib import Path
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from upload_stream import save,mime
SCHEMA='''CREATE TABLE IF NOT EXISTS tw_chat_files(owner TEXT NOT NULL,id TEXT NOT NULL,channel TEXT NOT NULL,actor TEXT NOT NULL,message TEXT,name TEXT NOT NULL,type TEXT NOT NULL,size INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(owner,id),FOREIGN KEY(owner,channel) REFERENCES tw_chat_channels(owner,id) ON DELETE CASCADE,FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);'''
SCHEMA += '''CREATE TABLE IF NOT EXISTS tw_chat_draft_files(owner TEXT NOT NULL,id TEXT NOT NULL,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,name TEXT NOT NULL,type TEXT NOT NULL,size INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(owner,id));'''

def attachments(c,who,mid):
 return [dict(r) for r in c.execute('SELECT id,name,type,size,digest FROM tw_chat_files WHERE owner=? AND message=?',(who,mid))]
def validate(c,who,cid,actor,ids):
 if not isinstance(ids,list) or len(ids)>1 or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):raise HTTPException(422,'Choose valid attachments.')
 rows=[]
 for fid in ids:
  r=c.execute('SELECT * FROM tw_chat_files WHERE owner=? AND id=? AND channel=? AND actor=? AND message IS NULL',(who,fid,cid,actor)).fetchone()
  if not r:raise HTTPException(404,'Pending attachment not found.')
  rows.append(dict(r))
 from upload_stream import MAX_BYTES
 if sum(r['size'] for r in rows)>MAX_BYTES:raise HTTPException(413,'Maximum upload size is 2 GB.')
 return rows

def paths(c,root,who,mid=None,cid=None):
 sql='SELECT id FROM tw_chat_files WHERE owner=?';args=[who]
 if mid is not None:sql+=' AND message=?';args.append(mid)
 if cid is not None:sql+=' AND channel=?';args.append(cid)
 result=[root/row['id'] for row in c.execute(sql,args)]
 if mid is None and cid is None:result += [root/r['id'] for r in c.execute('SELECT id FROM tw_chat_draft_files WHERE owner=?',(who,))]
 return result

def install(app,db,identity,uploads):
 from chat_local import channel
 root=uploads/'chat';root.mkdir(parents=True,exist_ok=True)
 with db() as c:c.executescript(SCHEMA)
 @app.post('/api/chat/channels/{cid}/files')
 @app.post('/api/chat/conversations/files')
 async def upload(req:Request,cid:str|None=None):
  with db() as c:
   who,actor=identity(req,c)
   if cid:channel(c,who,actor,cid,member=True)
  form=await req.form();file=form.get('file')
  if not file or not hasattr(file,'read'):raise HTTPException(422,'Choose a file.')
  fid=secrets.token_hex(16);dest=root/fid;name=Path((file.filename or 'file').replace('\\','/')).name or 'file'
  try:
   details=await save(file,dest)
   with db() as c:
    # Long uploads must not retain authorization after membership is revoked.
    who2,actor2=identity(req,c)
    if (who,actor)!=(who2,actor2):raise HTTPException(403,'The active workspace changed during upload.')
    if cid:
     channel(c,who,actor,cid,member=True);c.execute('INSERT INTO tw_chat_files VALUES(?,?,?,?,?,?,?,?,?)',(who,fid,cid,actor,None,name,mime(details['signature']),details['size'],details['sha256']))
    else:c.execute('INSERT INTO tw_chat_draft_files VALUES(?,?,?,?,?,?,?)',(who,fid,actor,name,mime(details['signature']),details['size'],details['sha256']))
  except BaseException:dest.unlink(missing_ok=True);raise
  return {'id':fid,'name':name,'size':details['size'],'type':mime(details['signature'])}
 @app.get('/api/chat/files/{fid}')
 def download(fid:str,req:Request,inline:bool=False):
  with db() as c:
   who,actor=identity(req,c);r=c.execute('SELECT * FROM tw_chat_files WHERE owner=? AND id=?',(who,fid)).fetchone()
   if r:
    channel(c,who,actor,r['channel'])
    if r['message'] is None and r['actor']!=actor:raise HTTPException(404,'File not found.')
    if r['message']:
     import chat_conversations
     message=c.execute('SELECT created FROM tw_chat_messages WHERE owner=? AND id=?',(who,r['message'])).fetchone()
     if message['created']<=chat_conversations.cutoff(c,who,r['channel'],actor):raise HTTPException(404,'File not found.')
   else:
    r=c.execute('SELECT * FROM tw_chat_draft_files WHERE owner=? AND id=? AND actor=?',(who,fid,actor)).fetchone()
    if not r:raise HTTPException(404,'File not found.')
  path=root/fid
  if not path.is_file():raise HTTPException(404,'File bytes are unavailable.')
  preview=inline and r['type']!='application/octet-stream';return FileResponse(path,filename=r['name'],media_type=r['type'] if preview else 'application/octet-stream',content_disposition_type='inline' if preview else 'attachment')
 @app.delete('/api/chat/files/{fid}')
 def discard(fid:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);r=c.execute('SELECT * FROM tw_chat_files WHERE owner=? AND id=? AND actor=? AND message IS NULL',(who,fid,actor)).fetchone()
   if not r:
    r=c.execute('SELECT * FROM tw_chat_draft_files WHERE owner=? AND id=? AND actor=?',(who,fid,actor)).fetchone()
    if not r:raise HTTPException(404,'Pending attachment not found.')
    c.execute('DELETE FROM tw_chat_draft_files WHERE owner=? AND id=?',(who,fid))
   else:c.execute('DELETE FROM tw_chat_files WHERE owner=? AND id=?',(who,fid))
  (root/fid).unlink(missing_ok=True);return {'ok':True}
 return root
