"""Local persistence for captured Q&A forms and editor attachments."""
import json,re,time,uuid
from pathlib import Path
from urllib.parse import quote,urlsplit
from fastapi import Request,HTTPException,UploadFile,File
from fastapi.responses import Response,JSONResponse
from markdown_it import MarkdownIt

def register(app,db,owner):
    root=Path(__file__).parent
    catalog=json.loads((root/'content/community-forms.json').read_text())
    labels=json.loads((root/'static/community-draft-labels.json').read_text())
    markdown=MarkdownIt('js-default').enable(['table','strikethrough'])
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS community_posts(id TEXT PRIMARY KEY,thread TEXT NOT NULL,target TEXT NOT NULL,owner TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL,request_id TEXT NOT NULL,UNIQUE(owner,request_id))')
        c.execute('CREATE TABLE IF NOT EXISTS community_attachments(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL,created INTEGER NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS community_post_attachments(post_id TEXT NOT NULL,attachment_id TEXT NOT NULL,PRIMARY KEY(post_id,attachment_id))')
    def thread(qid):
        if qid not in catalog:raise HTTPException(404,'Question not found')
        return catalog[qid]
    def body_html(body):
        return markdown.render(body)
    @app.get('/api/taxonomies')
    def taxonomy(name:str):
        if name!='devlang':raise HTTPException(404,'Taxonomy not found')
        return Response((root/'static/community-editor/taxonomy-devlang.json').read_bytes(),media_type='application/json')
    @app.get('/api/community/{qid}/posts')
    def posts(qid:str):
        thread(qid)
        with db() as c:
            rows=c.execute('SELECT p.*,a.display_name FROM community_posts p JOIN local_auth_accounts a ON a.account_id=p.owner WHERE thread=? ORDER BY created,id',(qid,)).fetchall()
        return {'posts':[{'id':r['id'],'target':r['target'],'body':r['body'],'html':body_html(r['body']),'author':r['display_name'],'created':r['created']} for r in rows]}
    @app.post('/api/community/{qid}/posts')
    async def create_post(qid:str,request:Request):
        source=thread(qid);uid=owner(request);body=await request.json()
        if not isinstance(body,dict) or set(body)!={'target','body','request_id'} or any(not isinstance(body[k],str) for k in body):raise HTTPException(400,'Invalid post')
        form=source['forms'].get(body['target'])
        if not form:raise HTTPException(404,'Posting form not found')
        content=body['body'].strip()
        if not content:raise HTTPException(400,form['errors']['input-required'].replace('{inputLabel}',form['label']))
        if len(content)<form['minimum']:raise HTTPException(400,form['errors']['input-min-length'].replace('{inputLabel}',form['label']).replace('{minLength}',str(form['minimum'])))
        if len(content)>1_000_000:raise HTTPException(413,'Request too large')
        if not re.fullmatch(r'[A-Za-z0-9-]{16,80}',body['request_id']):raise HTTPException(400,'Invalid request identifier')
        attachments=set()
        for token in markdown.parse(content):
            for child in token.children or []:
                if child.type!='image':continue
                image=child.attrGet('src') or '';path=urlsplit(image)
                if path.scheme or path.netloc or not re.fullmatch(r'/api/attachments/[a-f0-9]{32}\.[a-z]+',path.path):raise HTTPException(400,labels['external_images'].replace('{urls}',image))
        attachments.update(re.findall(r'/api/attachments/([a-f0-9]{32}\.[a-z]+)',content))
        if form['max_attachments'] is not None and len(attachments)>form['max_attachments']:raise HTTPException(400,labels['attachment_limit'].replace('{maximumCount}',str(form['max_attachments'])))
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM community_posts WHERE owner=? AND request_id=?',(uid,body['request_id'])).fetchone()
            if old:
                if old['thread']!=qid or old['target']!=body['target'] or old['body']!=content:raise HTTPException(409,'Request identifier already used')
                return {'id':old['id'],'navigation':form['navigation']}
            for aid in attachments:
                attachment=c.execute('SELECT owner FROM community_attachments WHERE id=?',(aid,)).fetchone()
                if not attachment or attachment['owner']!=uid:raise HTTPException(403,'Attachment access denied')
            pid='local-'+uuid.uuid4().hex
            c.execute('INSERT INTO community_posts VALUES(?,?,?,?,?,?,?)',(pid,qid,body['target'],uid,content,int(time.time()),body['request_id']))
            c.executemany('INSERT INTO community_post_attachments VALUES(?,?)',[(pid,aid) for aid in attachments])
        return {'id':pid,'navigation':form['navigation']}
    @app.post('/api/attachments')
    async def attachment(request:Request,formFile:UploadFile=File(...),platform:str=''):
        uid=owner(request)
        def failure(code,status=400):return JSONResponse({'ErrorCode':code},status_code=status)
        if platform!='QnA':return failure('platform-invalid')
        name=Path((formFile.filename or '').replace('\\','/')).name;extension=Path(name).suffix.lower()
        if extension not in {'.xml','.pdf','.txt','.log','.jpeg','.jpg','.png','.gif'}:return failure('extension-not-permitted')
        data=await formFile.read(3145729)
        if not data:return failure('size-less-than-minimum')
        if len(data)>3145728:return failure('size-more-than-maximum',413)
        mime='application/octet-stream'
        if extension in {'.png','.jpeg','.jpg','.gif'}:
            valid=data.startswith(b'\x89PNG\r\n\x1a\n') if extension=='.png' else data.startswith(b'\xff\xd8\xff') if extension in {'.jpg','.jpeg'} else data.startswith((b'GIF87a',b'GIF89a'))
            if not valid:return failure('extension-not-permitted')
            mime='image/png' if extension=='.png' else 'image/jpeg' if extension in {'.jpg','.jpeg'} else 'image/gif'
        aid=uuid.uuid4().hex+extension
        with db() as c:c.execute('INSERT INTO community_attachments VALUES(?,?,?,?,?,?)',(aid,uid,name,mime,data,int(time.time())))
        return {'path':'/api/attachments/'+aid+'?platform=QnA'}
    @app.get('/api/attachments/{aid}')
    def get_attachment(aid:str,request:Request):
        with db() as c:
            row=c.execute('SELECT * FROM community_attachments WHERE id=?',(aid,)).fetchone()
            if not row:raise HTTPException(404,'Attachment not found')
            published=c.execute('SELECT 1 FROM community_post_attachments WHERE attachment_id=?',(aid,)).fetchone()
        if not published and owner(request)!=row['owner']:raise HTTPException(404,'Attachment not found')
        disposition='inline' if row['mime'].startswith('image/') else 'attachment'
        return Response(bytes(row['content']),media_type=row['mime'],headers={'Content-Disposition':disposition+"; filename*=UTF-8''"+quote(row['name'],safe=''),'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})
