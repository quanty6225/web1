"""Owned local account exports and cancellation, without source-side requests."""
import html,io,json,re,secrets,smtplib,time,zipfile
from pathlib import Path
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import RedirectResponse,Response
from workspaces import manager
from record_operations import DATA,metadata,fields_for,PREFIX,TITLE,BODY
from local_render import safe_rich_text

def export_comment(row):
 quote=row.get('reply');quoted=''
 if quote:
  body=html.escape(quote['excerpt']) if quote.get('excerpt') else safe_rich_text(quote['body'])
  quoted='<blockquote data-original-comment="'+html.escape(quote['id'],quote=True)+'"><strong>Re: '+html.escape(quote['name'])+'</strong>'+body+'</blockquote>'
 avatar='<img src="'+html.escape(row['avatar'],quote=True)+'" alt="" width="40" height="40">' if row.get('avatar','').startswith('/static/assets/') else ''
 heading='<header>'+avatar+'<strong>'+html.escape(row.get('name','Member'))+'</strong> <time datetime="'+html.escape(row.get('timestamp',''),quote=True)+'">'+html.escape(row.get('timestamp',''))+'</time></header>'
 return '<article id="comment-'+html.escape(row['id'],quote=True)+'">'+heading+quoted+safe_rich_text(row['body'])+'</article>'

def install(app,db,require_user,csrf_check,send_mail,origin,basic_page,data_root):
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS bc_exports(id TEXT PRIMARY KEY,owner TEXT,author TEXT,buckets TEXT,created INTEGER)')
 router=APIRouter()
 @router.post('/6302022/account/exports')
 async def export(request:Request):
  account=require_user(request);manager(account,True);data=await request.form();csrf_check(request,data);buckets=data.getlist('bucket_ids[]')
  if not buckets or any(not str(bucket).isdigit() for bucket in buckets):raise HTTPException(422,'Select at least one project to export.')
  from trash import erased
  with db() as c:
   if any(erased(c,account['workspace_id'],bucket) for bucket in buckets):raise HTTPException(404,'Project not found')
  identifier=secrets.token_urlsafe(24)
  with db() as c:c.execute('INSERT INTO bc_exports VALUES(?,?,?,?,?)',(identifier,account['workspace_id'],account['account_id'],json.dumps(buckets),int(time.time())))
  try:send_mail(account['email_normalized'],'Your Basecamp export is ready',f'Your local Basecamp export is ready to download. Sign in to your account to open this link:\n\n{origin}/6302022/account/exports/{identifier}.zip\n')
  except (OSError,smtplib.SMTPException):raise HTTPException(503,'We couldn’t email your download link. Please try again.')
  return RedirectResponse('/6302022/account/exports/new?ready=1',303)
 @router.get('/6302022/account/exports/{identifier}.zip')
 def download(identifier:str,request:Request):
  account=require_user(request);manager(account,True)
  with db() as c:
   export=c.execute('SELECT * FROM bc_exports WHERE id=? AND owner=?',(identifier,account['workspace_id'])).fetchone()
   if not export:raise HTTPException(404,'Export not found')
   buckets=json.loads(export['buckets']);records=dict(DATA['records']);output=io.BytesIO();index=[];files=set();structured=[]
   for row in c.execute('SELECT id FROM bc_records WHERE owner=?',(account['workspace_id'],)):
    record=metadata(c,account['workspace_id'],row['id'])
    if record:records[record['id']]=record
   with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
    from export_assets import Assets
    assets=Assets(archive,c,account['workspace_id'],data_root)
    for record in records.values():
     if record['bucket'] not in buckets:continue
     fields=fields_for(c,account['workspace_id'],record)
     from column_lifecycle import record_status
     if record_status(c,account['workspace_id'],record,fields)!='active':continue
     prefix=PREFIX[record['kind']];title=fields.get(prefix+'['+TITLE[record['kind']]+']',record['title']);body=fields.get(prefix+'['+BODY[record['kind']]+']','');folder=record['bucket'];filename=folder+'/'+record['id']+'.html'
     from export_comments import discussion
     comments,counts=discussion(c,account,record)
     note='<p>'+str(counts['total'])+' comments</p>'
     if counts['source_total']>counts['source_retained']:note+='<p>'+str(counts['source_total'])+' original comments · Showing the first '+str(counts['source_retained'])+' original comments in this local copy.</p>'
     index.append('<li><a href="'+filename+'">'+html.escape(title)+'</a></li>');archive.writestr(filename,assets.render('<!doctype html><meta charset="utf-8"><title>'+html.escape(title)+'</title><a href="../index.html">Back to projects</a><h1>'+html.escape(title)+'</h1>'+body+note+''.join(export_comment(row) for row in comments)));structured.append({'id':record['id'],'bucket':folder,'kind':record['kind'],'title':title,'fields':fields,'comments':comments,'comment_counts':counts})
     files.update((folder,value) for value in [fields.get('_file_id'),*fields.get('_versions',[])] if value)
    for bucket,identifier in files:
     file=c.execute('SELECT * FROM bc_files WHERE id=? AND owner=? AND uploaded=1',(identifier,account['workspace_id'])).fetchone();path=Path(data_root)/'uploads'/identifier
     if file and path.is_file():archive.write(path,bucket+'/files/'+identifier+'-'+Path(file['filename']).name)
    routes=json.loads((Path(__file__).parent/'frontend/routes.json').read_text());room_buckets={route.split('/chats/')[1].split('/')[0].split('@')[0].split('?')[0]:route.split('/')[3] for route in routes if '/chats/' in route}
    room_buckets.update({row['id']:row['bucket'] for row in c.execute('SELECT id,bucket FROM bc_tools WHERE owner=? AND kind="Chat::Transcript"',(account['workspace_id'],))})
    chats=[dict(row) for row in c.execute('SELECT room,body,created,author FROM bc_chat_lines WHERE owner=?',(account['workspace_id'],)) if room_buckets.get(row['room']) in buckets]
    archive.writestr('chats.json',json.dumps(chats,ensure_ascii=False,indent=2))
    archive.writestr('records.json',json.dumps(structured,ensure_ascii=False,indent=2));archive.writestr('index.html','<!doctype html><meta charset="utf-8"><title>Basecamp export</title><h1>Basecamp export</h1><ul>'+''.join(index)+'</ul>')
  return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="basecamp-export.zip"'})
 @router.post('/6302022/account/cancellation')
 async def cancel(request:Request):
  account=require_user(request);manager(account,True);csrf_check(request,await request.form())
  with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"cancelled_at",?)',(account['workspace_id'],json.dumps(int(time.time()))))
  return RedirectResponse('/account-closed',303)
 @router.get('/account-closed')
 def closed(request:Request):
  account=require_user(request)
  if not account.get('closed'):return RedirectResponse('/6302022/',303)
  return basic_page('Account closed','<p>Your local Basecamp account is closed.</p>',request)
 app.include_router(router)
