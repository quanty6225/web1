"""Private chat uploads: staged by their author, published only into one Ping."""
import base64
import hashlib
import hmac
import html as escape
import secrets
import time
from pathlib import Path
from urllib.parse import quote
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, Response
from lxml import etree
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 12  # Captured BC.Chat.maxUploads.
IMAGES = {'PNG':'image/png','JPEG':'image/jpeg','GIF':'image/gif','WEBP':'image/webp','AVIF':'image/avif'}
AUDIO = {'audio/webm','audio/ogg','audio/mpeg','audio/wav','audio/mp4','audio/x-m4a'}


def initialize(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS bc_ping_files(
            id TEXT PRIMARY KEY,ping TEXT NOT NULL,uploader TEXT NOT NULL,
            filename TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,
            checksum TEXT NOT NULL,uploaded INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL,posted_line TEXT,preview_type TEXT NOT NULL DEFAULT '')''')
        c.execute('CREATE INDEX IF NOT EXISTS bc_ping_files_line ON bc_ping_files(ping,posted_line)')
        existing={row[1] for row in c.execute('PRAGMA table_info(bc_ping_files)')}
        for column in ('image_width','image_height'):
            if column not in existing:c.execute('ALTER TABLE bc_ping_files ADD COLUMN '+column+' INTEGER NOT NULL DEFAULT 0')


def url(row, download=False):
    return '/api/pings/'+row['ping']+'/files/'+row['id']+'/'+quote(row['filename'],safe='')+('?download=1' if download else '')


def for_line(c, ping, line):
    return [dict(r) for r in c.execute('SELECT * FROM bc_ping_files WHERE ping=? AND posted_line=? AND uploaded=1 ORDER BY created,id',(ping,line))]


def validate(c, account, ping, values):
    if not isinstance(values,list) or len(values)>MAX_FILES or any(not isinstance(v,str) for v in values) or len(values)!=len(set(values)):
        raise HTTPException(422,'Choose up to 12 different files.')
    for identifier in values:
        row=c.execute('SELECT * FROM bc_ping_files WHERE id=? AND ping=? AND uploader=? AND uploaded=1 AND posted_line IS NULL',(identifier,ping,account['account_id'])).fetchone()
        if not row:raise HTTPException(404,'A staged file was not found in this Ping.')
    return values


def attach(c, files, line):
    for identifier in files:c.execute('UPDATE bc_ping_files SET posted_line=? WHERE id=?',(line,identifier))


def markup(c, ping, line):
    output=[]
    for row in for_line(c,ping,line):
        name=escape.escape(row['filename']);target=escape.escape(url(row),quote=True);download=escape.escape(url(row,True),quote=True)
        preview=''
        if row['preview_type'].startswith('image/'):
            preview='<a href="'+target+'" data-local-ping-image><img src="'+target+'" alt="Zoom '+name+'" loading="lazy" data-behavior="lightboxable" data-src="'+target+'" data-width="'+str(row['image_width'])+'" data-height="'+str(row['image_height'])+'" data-download-url="'+target+'" data-filename="'+name+'" data-human-size="'+str(row['size'])+' bytes" style="max-width:100%;max-height:360px"></a>'
        elif row['preview_type'].startswith('audio/'):
            preview='<audio controls preload="metadata" src="'+target+'"></audio>'
        output.append('<figure class="attachment" data-local-ping-file="'+row['id']+'">'+preview+'<figcaption><a href="'+download+'" download>'+name+'</a> <span class="text-subtle">'+str(row['size'])+' bytes</span></figcaption></figure>')
    return ''.join(output)


def preview_type(path, mime):
    try:
        with Image.open(path) as img:
            kind=IMAGES.get(img.format,'');img.verify()
            if kind:return kind
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):pass
    mime=mime.split(';',1)[0].strip().lower()
    return mime if mime in AUDIO else ''


def install(router, db, require_user, csrf_check, data_root, page_response):
    from pings import require_ping
    initialize(db);folder=Path(data_root)/'private-ping-files'

    @router.post('/api/pings/{identifier}/files/direct')
    async def begin(identifier:str,request:Request):
        account=require_user(request);data=await request.json();csrf_check(request,data)
        blob=data.get('blob',data)
        if not isinstance(blob,dict):raise HTTPException(422,'Choose a file to upload.')
        try:size=int(blob.get('byte_size',-1))
        except (ValueError,TypeError):raise HTTPException(422,'Invalid file size.')
        if size<0 or size>MAX_BYTES:raise HTTPException(413,'The maximum file size is 100 MB.')
        filename=str(blob.get('filename','attachment')).replace('\\','/').rsplit('/',1)[-1] or 'attachment'
        if len(filename)>250 or any(ord(char)<32 for char in filename):raise HTTPException(422,'Invalid filename.')
        checksum=str(blob.get('checksum',''))
        if checksum:
            try:
                if len(base64.b64decode(checksum,validate=True))!=16:raise ValueError()
            except ValueError:raise HTTPException(422,'Invalid upload checksum.')
        file_id=secrets.token_urlsafe(24);mime=str(blob.get('content_type','application/octet-stream'))
        row={'id':file_id,'ping':identifier,'uploader':account['account_id'],'filename':filename,'mime':mime,'size':size,'checksum':checksum,'created':time.time()}
        with db() as c:
            require_ping(c,account,identifier)
            c.execute('INSERT INTO bc_ping_files(id,ping,uploader,filename,mime,size,checksum,created) VALUES(:id,:ping,:uploader,:filename,:mime,:size,:checksum,:created)',row)
        return {'id':file_id,'signed_id':file_id,'key':file_id,'filename':filename,'content_type':mime,'byte_size':size,'checksum':checksum,'attachable_sgid':file_id,'url':url(row),'direct_upload':{'url':'/api/pings/'+identifier+'/files/'+file_id,'headers':{'X-CSRF-Token':request.headers.get('x-csrf-token') or str(data.get('_csrf',''))}}}

    @router.put('/api/pings/{identifier}/files/{file_id}')
    async def upload(identifier:str,file_id:str,request:Request):
        account=require_user(request);csrf_check(request,{})
        with db() as c:
            require_ping(c,account,identifier)
            row=c.execute('SELECT * FROM bc_ping_files WHERE id=? AND ping=? AND uploader=?',(file_id,identifier,account['account_id'])).fetchone()
            if not row:raise HTTPException(404,'File not found')
            if row['uploaded']:raise HTTPException(409,'This upload is already complete.')
            row=dict(row)
        folder.mkdir(parents=True,exist_ok=True)
        temporary=folder/('pending-'+secrets.token_hex(16));size=0;checksum=hashlib.md5()
        try:
            with temporary.open('xb') as stream:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>row['size']:raise HTTPException(422,'The upload size does not match.')
                    stream.write(chunk);checksum.update(chunk)
            if size!=row['size']:raise HTTPException(422,'The upload size does not match.')
            if row['checksum'] and not hmac.compare_digest(base64.b64encode(checksum.digest()).decode(),row['checksum']):raise HTTPException(422,'The upload checksum does not match.')
            preview=preview_type(temporary,row['mime']);width=height=0
            if preview.startswith('image/'):
                with Image.open(temporary) as picture:width,height=picture.size
            with db() as c:
                c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
                current=c.execute('SELECT uploaded FROM bc_ping_files WHERE id=? AND ping=? AND uploader=?',(file_id,identifier,account['account_id'])).fetchone()
                if not current:raise HTTPException(404,'File not found')
                if current['uploaded']:raise HTTPException(409,'This upload is already complete.')
                temporary.replace(folder/file_id)
                c.execute('UPDATE bc_ping_files SET uploaded=1,preview_type=?,image_width=?,image_height=? WHERE id=?',(preview,width,height,file_id))
        finally:temporary.unlink(missing_ok=True)
        return Response(status_code=204)

    @router.delete('/api/pings/{identifier}/files/{file_id}')
    def discard(identifier:str,file_id:str,request:Request):
        account=require_user(request);csrf_check(request,{})
        with db() as c:
            c.execute('BEGIN IMMEDIATE');require_ping(c,account,identifier)
            row=c.execute('SELECT * FROM bc_ping_files WHERE id=? AND ping=? AND uploader=?',(file_id,identifier,account['account_id'])).fetchone()
            if not row:raise HTTPException(404,'File not found')
            if row['posted_line']:raise HTTPException(409,'Delete the posted message to remove this attachment.')
            c.execute('DELETE FROM bc_ping_files WHERE id=?',(file_id,));(folder/file_id).unlink(missing_ok=True)
        return Response(status_code=204)

    @router.get('/api/pings/{identifier}/files/{file_id}/{filename}')
    def download(identifier:str,file_id:str,filename:str,request:Request):
        account=require_user(request)
        with db() as c:
            require_ping(c,account,identifier)
            row=c.execute('SELECT * FROM bc_ping_files WHERE id=? AND ping=? AND uploaded=1',(file_id,identifier)).fetchone()
            if not row:raise HTTPException(404,'File not found')
            if row['posted_line']:
                if not c.execute('SELECT 1 FROM bc_ping_lines WHERE id=? AND ping=?',(row['posted_line'],identifier)).fetchone():raise HTTPException(404,'File not found')
            elif row['uploader']!=account['account_id']:raise HTTPException(404,'File not found')
            path=folder/file_id
            if not path.is_file():raise HTTPException(404,'File not found')
            inline=bool(row['preview_type']) and request.query_params.get('download')!='1' and request.query_params.get('disposition')!='attachment'
            return FileResponse(path,filename=row['filename'],media_type=row['preview_type'] if inline else 'application/octet-stream',content_disposition_type='inline' if inline else 'attachment',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @router.get('/6302022/my/sidebar/circles/{identifier}/uploads')
    def files(identifier:str,request:Request):
        account=require_user(request)
        with db() as c:
            require_ping(c,account,identifier)
            rows=[dict(row) for row in c.execute('SELECT f.*,a.display_name FROM bc_ping_files f JOIN bc_ping_lines l ON l.id=f.posted_line AND l.ping=f.ping JOIN local_auth_accounts a ON a.account_id=f.uploader WHERE f.ping=? AND f.uploaded=1 ORDER BY l.created DESC,f.created,f.id',(identifier,))]
        section=etree.Element('section',{'class':'sidebar__panel padding-16','data-local-ping-files':''})
        etree.SubElement(section,'a',{'href':'/6302022/my/sidebar/circles/'+identifier,'data-turbo-frame':'sidebar_frame'}).text='Back to Ping'
        etree.SubElement(section,'h3').text='Files posted here'
        listing=etree.SubElement(section,'div',{'class':'sidebar__panel-scrollable'})
        if not rows:etree.SubElement(listing,'p',{'class':'text-subtle'}).text='No files have been posted here yet.'
        for row in rows:
            entry=etree.SubElement(listing,'article',{'class':'margin-block-16','data-local-ping-file':row['id']})
            etree.SubElement(entry,'a',{'href':url(row,True),'download':''}).text=row['filename']
            etree.SubElement(entry,'p',{'class':'text-subtle margin-block-0'}).text=row['display_name']+' · '+str(row['size'])+' bytes'
        return page_response(section,request,'Files posted here')
