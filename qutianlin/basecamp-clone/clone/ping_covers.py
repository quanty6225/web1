"""Private Ping cover images with the same participant access as messages."""
import io
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError


def initialize(db):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS bc_ping_covers(ping TEXT PRIMARY KEY,file TEXT NOT NULL,updated REAL NOT NULL)')


def cover_url(c, identifier):
    row=c.execute('SELECT file FROM bc_ping_covers WHERE ping=?',(identifier,)).fetchone()
    return '/api/pings/'+identifier+'/cover?v='+row['file'] if row else None


def install(router, db, require_user, csrf_check, data_root, publish):
    from pings import require_ping
    from ping_files import MAX_BYTES
    from trash import cleanup_files
    initialize(db)
    folder=Path(data_root)/'private-ping-covers'

    @router.get('/api/pings/{identifier}/cover')
    def read(identifier:str,request:Request):
        account=require_user(request)
        with db() as c:
            require_ping(c,account,identifier)
            row=c.execute('SELECT file FROM bc_ping_covers WHERE ping=?',(identifier,)).fetchone()
            if not row or not (folder/row['file']).is_file():raise HTTPException(404,'Cover not found')
            path=folder/row['file']
        return FileResponse(path,media_type='image/png',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @router.post('/api/pings/{identifier}/cover')
    async def upload(identifier:str,request:Request):
        account=require_user(request);csrf_check(request,{})
        with db() as c:require_ping(c,account,identifier)
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>MAX_BYTES:raise HTTPException(413,'The maximum file size is 100 MB.')
        try:
            with Image.open(io.BytesIO(body)) as original:
                original.verify()
            with Image.open(io.BytesIO(body)) as original:
                picture=ImageOps.exif_transpose(original).convert('RGBA')
                picture.thumbnail((1600,1600))
                encoded=io.BytesIO();picture.save(encoded,format='PNG')
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
            raise HTTPException(422,'Choose an image for the Ping cover.')
        folder.mkdir(parents=True,exist_ok=True)
        filename=secrets.token_hex(24)+'.png';path=folder/filename
        path.write_bytes(encoded.getvalue());old=None
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
                old=c.execute('SELECT file FROM bc_ping_covers WHERE ping=?',(identifier,)).fetchone()
                c.execute('INSERT INTO bc_ping_covers VALUES(?,?,?) ON CONFLICT(ping) DO UPDATE SET file=excluded.file,updated=excluded.updated',(identifier,filename,time.time()))
                if old:c.execute('INSERT OR IGNORE INTO bc_file_cleanup(id,storage) VALUES(?,"private-ping-covers")',(old['file'],))
                result=cover_url(c,identifier)
        except BaseException:
            path.unlink(missing_ok=True);raise
        cleanup_files(db,data_root)
        await publish(identifier,{'type':'metadata'})
        return {'cover_url':result}

    @router.delete('/api/pings/{identifier}/cover')
    async def remove(identifier:str,request:Request):
        account=require_user(request);csrf_check(request,{})
        with db() as c:
            c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
            old=c.execute('SELECT file FROM bc_ping_covers WHERE ping=?',(identifier,)).fetchone()
            c.execute('DELETE FROM bc_ping_covers WHERE ping=?',(identifier,))
            if old:c.execute('INSERT OR IGNORE INTO bc_file_cleanup(id,storage) VALUES(?,"private-ping-covers")',(old['file'],))
        cleanup_files(db,data_root)
        await publish(identifier,{'type':'metadata'})
        return {'cover_url':None}
