"""Local invitations and shared-list permissions, with collision-free recipient IDs."""
import json,time,secrets,hashlib,copy,re,smtplib,os
from email.message import EmailMessage
from fastapi import HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse
SCHEMA='''CREATE TABLE IF NOT EXISTS ticktick_shares(id TEXT PRIMARY KEY,owner TEXT NOT NULL,project TEXT NOT NULL,email TEXT NOT NULL,permission TEXT NOT NULL,status TEXT NOT NULL,alias TEXT NOT NULL,created INTEGER NOT NULL);'''
def alias(share,ident):return hashlib.sha256((share+':'+ident).encode()).hexdigest()[:24]
def map_task(task,ident,pid,taskmap,columnmap):
 result={**task,'id':ident,'projectId':pid}
 for key in ['parentId','columnId']:
  if result.get(key):result[key]=(taskmap if key=='parentId' else columnmap).get(result[key],result[key])
 return result

def overlay(db,a,d):
 d=copy.deepcopy(d);shared={}
 for grant in db.execute("SELECT * FROM ticktick_shares WHERE email=? AND status='accepted'",(a['email_normalized'],)):
  row=db.execute('SELECT data FROM ticktick_actor_state WHERE owner=?',(grant['owner'],)).fetchone()
  if not row:continue
  source=json.loads(row[0]);pid=grant['project'];local_pid=grant['alias'];project=source['projects'].get(pid)
  if not project:continue
  d['projects'][local_pid]={**project,'id':local_pid,'isOwner':False,'userCount':2,'permission':grant['permission']}
  tasks={tid:alias(grant['id'],tid) for tid,t in source['tasks'].items() if t.get('projectId')==pid}
  columns={cid:alias(grant['id'],cid) for cid,c in source.get('columns',{}).items() if c.get('projectId')==pid}
  comments={}
  for tid,local_tid in tasks.items():
   d['tasks'][local_tid]=map_task(source['tasks'][tid],local_tid,local_pid,tasks,columns)
   target=d.setdefault('comments',{}).setdefault(local_tid,{})
   for cid,comment in source.get('comments',{}).get(tid,{}).items():
    local_cid=alias(grant['id'],cid);comments[local_cid]=cid;target[local_cid]={**comment,'id':local_cid,'taskId':local_tid,'projectId':local_pid}
  for cid,local_cid in columns.items():d.setdefault('columns',{})[local_cid]={**source['columns'][cid],'id':local_cid,'projectId':local_pid}
  for fid,attachment in source.get('attachments',{}).items():
   if attachment.get('projectId')==pid and attachment.get('taskId') in tasks:d.setdefault('attachments',{})[fid]={**attachment,'projectId':local_pid,'taskId':tasks[attachment['taskId']]}
  shared[local_pid]={'grant':dict(grant),'tasks':{v:k for k,v in tasks.items()},'columns':{v:k for k,v in columns.items()},'comments':comments}
 d['_shared']=shared;return d

def split_and_save_shared(db,a,d):
 own=copy.deepcopy(d);shared=own.pop('_shared',{})
 for pid,meta in shared.items():
  grant=meta['grant'];active=db.execute("SELECT * FROM ticktick_shares WHERE id=? AND email=? AND status='accepted'",(grant['id'],a['email_normalized'])).fetchone()
  if not active:raise HTTPException(403,'Shared list access was revoked')
  row=db.execute('SELECT data FROM ticktick_actor_state WHERE owner=?',(grant['owner'],)).fetchone();source=json.loads(row[0]);owned_pid=grant['project'];project=own['projects'].pop(pid,None)
  expected={**source['projects'][owned_pid],'id':pid,'isOwner':False,'userCount':2,'permission':grant['permission']}
  if project!=expected:raise HTTPException(403,'Only the owner can change list settings')
  changed=False;writable=grant['permission'] in ['write','edit','admin'];commentable=writable or grant['permission']=='comment'
  for tid,task in list(own['tasks'].items()):
   if task.get('projectId')!=pid:continue
   original_id=meta['tasks'].get(tid,tid);adapted=map_task(task,original_id,owned_pid,meta['tasks'],meta['columns']);del own['tasks'][tid]
   original=source['tasks'].get(original_id)
   if original!=adapted:
    content_changed={k:v for k,v in adapted.items() if k!='commentCount'}!={k:v for k,v in (original or {}).items() if k!='commentCount'}
    if not writable and (content_changed or not commentable):raise HTTPException(403,'This shared list is read only')
    source['tasks'][original_id]=adapted;changed=True
   comments=own.setdefault('comments',{}).pop(tid,{})
   adapted_comments={meta['comments'].get(cid,cid):{**c,'id':meta['comments'].get(cid,cid),'taskId':original_id,'projectId':owned_pid} for cid,c in comments.items()}
   if adapted_comments!=source.setdefault('comments',{}).get(original_id,{}):
    if not commentable:raise HTTPException(403,'This shared list is read only')
    source['comments'][original_id]=adapted_comments;changed=True
  for table in ['tasks','columns']:
   if table=='columns':
    for ident,item in list(own.setdefault(table,{}).items()):
     if item.get('projectId')!=pid:continue
     original_id=meta[table].get(ident,ident);adapted={**item,'id':original_id,'projectId':owned_pid};del own[table][ident]
     if source.setdefault(table,{}).get(original_id)!=adapted:
      if not writable:raise HTTPException(403,'This shared list is read only')
      source[table][original_id]=adapted;changed=True
   for local_id,original_id in meta[table].items():
    if local_id not in d.get(table,{}):
     if not writable:raise HTTPException(403,'This shared list is read only')
     source[table].pop(original_id,None);changed=True
  attachments={}
  for fid,attachment in list(own.setdefault('attachments',{}).items()):
   if attachment.get('projectId')!=pid:continue
   del own['attachments'][fid];attachments[fid]={**attachment,'projectId':owned_pid,'taskId':meta['tasks'].get(attachment['taskId'],attachment['taskId'])}
  original_attachments={fid:x for fid,x in source.get('attachments',{}).items() if x.get('projectId')==owned_pid}
  if attachments!=original_attachments:
   if not writable:raise HTTPException(403,'This shared list is read only')
   for fid in original_attachments:source['attachments'].pop(fid,None)
   source.setdefault('attachments',{}).update(attachments);changed=True
  if changed:db.execute('UPDATE ticktick_actor_state SET data=?,revision=? WHERE owner=?',(json.dumps(source,ensure_ascii=False),int(time.time()*1000),grant['owner']))
 return own

def invite_email(email,title,url):
 msg=EmailMessage();msg['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@ticktick.clone.test');msg['To']=email;msg['Subject']='TickTick invitation: '+title;msg.set_content('You have been invited to '+title+'.\nOpen this local link to review the invitation:\n'+url+'\n')
 try:
  host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
  if host not in ['127.0.0.1','localhost','::1']:raise ValueError('Local SMTP required')
  with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=10) as s:s.send_message(msg)
 except Exception:raise HTTPException(503,'Invitation email could not be sent')

def handle(path,method,body,req,a,d,db,save,actorid):
 parts=path.split('/');owner=a['account_id']
 if path in ['share/shareContacts','share/contacts','share/contacts/query']:
  rows=db.execute('SELECT DISTINCT email FROM ticktick_shares WHERE owner=?',(owner,)).fetchall();return {'contacts':[{'email':r[0],'name':r[0].split('@')[0]} for r in rows]}
 if len(parts)<3 or parts[0]!='project' or parts[2] not in ['share','shares','users','collaboration']:return None
 pid=parts[1]
 if pid not in d['projects']:raise HTTPException(404,'List not found')
 if pid in d.get('_shared',{}):raise HTTPException(403,'Only the owner can manage sharing')
 rows=db.execute("SELECT * FROM ticktick_shares WHERE owner=? AND project=? AND email<>'*' AND status IN ('pending','accepted')",(owner,pid)).fetchall()
 if path.endswith('/share/check-quota'):return max(0,(28 if d.get('subscription',{}).get('ends',0)>time.time() else 1)-len(rows))
 if parts[2]=='users':
  users=[]
  for row in rows:
   user=db.execute('SELECT * FROM local_auth_accounts WHERE email_normalized=?',(row['email'],)).fetchone()
   if user and row['status']=='accepted':users.append({'id':actorid(dict(user)),'userId':actorid(dict(user)),'name':user['display_name'],'username':row['email'],'permission':row['permission']})
  return users
 if parts[2]=='collaboration':
  links=d.setdefault('inviteLinks',{});ident=links.get(pid)
  if method=='DELETE':
   links.pop(pid,None)
   if ident:db.execute("UPDATE ticktick_shares SET status='revoked' WHERE id=? AND email='*'",(ident,))
   save(db,a,d);return {'inviteUrl':None,'permission':None}
  if method=='POST' and not ident:
   ident=secrets.token_urlsafe(20);links[pid]=ident;permission=body.get('permission','write')
   db.execute('INSERT INTO ticktick_shares VALUES(?,?,?,?,?,?,?,?)',(ident,owner,pid,'*',permission,'pending',secrets.token_hex(12),int(time.time())));save(db,a,d)
  return {'inviteUrl':str(req.base_url).rstrip('/')+'/local/invitations/'+ident if ident else None,'permission':'write' if ident else None}
 if method=='GET':return [{'id':r['id'],'recordId':r['id'],'toEmail':r['email'],'toUsername':r['email'],'toUserCode':None,'accepted':r['status']=='accepted','createdTime':r['created']*1000,'email':r['email'],'permission':r['permission'],'status':r['status'],'projectId':pid} for r in rows]
 if method=='DELETE':
  ident=parts[-1];changed=db.execute("UPDATE ticktick_shares SET status='revoked' WHERE id=? AND owner=? AND project=?",(ident,owner,pid)).rowcount
  if not changed:raise HTTPException(404,'Invitation not found')
  return {}
 items=body if isinstance(body,list) else body.get('shares',[body]);result=[]
 for item in items:
  email=str(item.get('toUsername',item.get('toEmail',item.get('email',item.get('username',''))))).strip().lower()
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(400,'Invalid email address')
  if email==a['email_normalized']:raise HTTPException(400,'You already own this list')
  existing=next((r for r in rows if r['email']==email),None)
  if existing:result.append(dict(existing));continue
  if len(rows)+len(result)>=(29 if d.get('subscription',{}).get('ends',0)>time.time() else 2)-1:raise HTTPException(403,'Member limit reached')
  permission=item.get('permission','write')
  if permission not in ['write','read','edit','comment']:raise HTTPException(400,'Invalid permission')
  ident=secrets.token_urlsafe(20);local_pid=secrets.token_hex(12);url=str(req.base_url).rstrip('/')+'/local/invitations/'+ident
  invite_email(email,d['projects'][pid]['name'],url)
  db.execute('INSERT INTO ticktick_shares VALUES(?,?,?,?,?,?,?,?)',(ident,owner,pid,email,permission,'pending',local_pid,int(time.time())))
  result.append({'id':ident,'recordId':ident,'toUserCode':None,'accepted':False,'createdTime':int(time.time()*1000),'toEmail':email,'toUsername':email,'username':email,'permission':permission,'status':'pending'})
 return {'records':result,'errors':[]} if isinstance(body,list) else result[0] if len(result)==1 else result

def invitation(ident,req,a,auth,method,body,style):
 with auth.connect() as db:
  row=db.execute('SELECT * FROM ticktick_shares WHERE id=?',(ident,)).fetchone()
  if not row or row['email'] not in [a['email_normalized'],'*']:raise HTTPException(404,'Invitation not found')
  if row['status'] not in ['pending','accepted']:raise HTTPException(410,'Invitation is no longer available')
  if method=='POST':
   decision=body.get('decision')
   if decision not in ['accept','decline']:raise HTTPException(400,'Choose accept or decline')
   if row['email']=='*':
    if decision=='decline':return {'redirect':'/webapp/'}
    if row['owner']==a['account_id']:return {'redirect':'/webapp/#p/'+row['project']+'/tasks'}
    existing=db.execute("SELECT * FROM ticktick_shares WHERE owner=? AND project=? AND email=? AND status='accepted'",(row['owner'],row['project'],a['email_normalized'])).fetchone()
    if existing:return {'redirect':'/webapp/#p/'+existing['alias']+'/tasks'}
    total=db.execute("SELECT count(*) FROM ticktick_shares WHERE owner=? AND project=? AND email<>'*' AND status IN ('pending','accepted')",(row['owner'],row['project'])).fetchone()[0]
    if total>=1:raise HTTPException(403,'Member limit reached')
    local_pid=secrets.token_hex(12);db.execute('INSERT INTO ticktick_shares VALUES(?,?,?,?,?,?,?,?)',(secrets.token_urlsafe(20),row['owner'],row['project'],a['email_normalized'],row['permission'],'accepted',local_pid,int(time.time())));return {'redirect':'/webapp/#p/'+local_pid+'/tasks'}
   db.execute('UPDATE ticktick_shares SET status=? WHERE id=?',('accepted' if decision=='accept' else 'declined',ident));return {'redirect':'/webapp/#p/'+row['alias']+'/tasks' if decision=='accept' else '/webapp/'}
  source=db.execute('SELECT data FROM ticktick_actor_state WHERE owner=?',(row['owner'],)).fetchone();title=json.loads(source[0])['projects'][row['project']]['name']
 import html
 return HTMLResponse('<!doctype html><html><head><title>TickTick Invitation</title><style>'+style+'</style></head><body><header><a href="/">TickTick</a></header><main><h1>Join '+html.escape(title)+'</h1><p>You have been invited to collaborate on this list.</p><button class="primary" data-action="accept">Accept</button><button data-action="decline">Decline</button><p role="alert"></p></main><script>document.querySelectorAll("button").forEach(b=>b.onclick=async()=>{const r=await fetch(location.pathname,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision:b.dataset.action})});const d=await r.json();if(r.ok)location.href=d.redirect;else document.querySelector("[role=alert]").textContent=d.detail})</script></body></html>')
