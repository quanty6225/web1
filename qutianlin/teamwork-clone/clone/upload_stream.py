"""Bounded-memory upload storage matching Teamwork's documented 2GB upload limit."""
import hashlib,os,secrets
from pathlib import Path
from fastapi import HTTPException
MAX_BYTES=2*1024*1024*1024
CHUNK=1024*1024
async def save(file,destination):
 if getattr(file,'size',None) is not None and file.size>MAX_BYTES:raise HTTPException(413,'Maximum upload size is 2 GB.')
 destination=Path(destination);temp=destination.with_name(destination.name+'.'+secrets.token_hex(6)+'.part');size=0;digest=hashlib.sha256();signature=b''
 try:
  with temp.open('xb') as target:
   while chunk:=await file.read(CHUNK):
    size+=len(chunk)
    if size>MAX_BYTES:raise HTTPException(413,'Maximum upload size is 2 GB.')
    if not signature:signature=chunk[:64]
    digest.update(chunk);target.write(chunk)
  os.replace(temp,destination)
 except BaseException:
  temp.unlink(missing_ok=True);raise
 return {'size':size,'sha256':digest.hexdigest(),'signature':signature}
def mime(signature):
 if signature.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
 if signature.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
 if signature.startswith((b'GIF87a',b'GIF89a')):return 'image/gif'
 if signature.startswith(b'RIFF') and signature[8:12]==b'WEBP':return 'image/webp'
 if signature[4:8]==b'ftyp':return 'video/mp4'
 if signature.startswith(b'\x1aE\xdf\xa3'):return 'video/webm'
 return 'application/octet-stream'
