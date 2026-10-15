"""Personal tasks, message reactions and message-to-project-task workflows."""
import json,secrets,time
from fastapi import HTTPException,Request
from chat_status import EMOJI,data
SCHEMA='''
CREATE TABLE IF NOT EXISTS tw_chat_reactions(owner TEXT NOT NULL,message TEXT NOT NULL,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,emoji TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,message,actor,emoji),FOREIGN KEY(owner,message) REFERENCES tw_chat_messages(owner,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS tw_personal_tasks(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,actor TEXT NOT NULL REFERENCES local_auth_accounts(account_id) ON DELETE CASCADE,name TEXT NOT NULL,completed INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,position INTEGER NOT NULL,created REAL NOT NULL);
'''
def reactions(c,who,actor,mid):
 result={}
 for r in c.execute('SELECT r.emoji,r.actor,a.display_name FROM tw_chat_reactions r JOIN local_auth_accounts a ON a.account_id=r.actor WHERE r.owner=? AND r.message=? ORDER BY r.created,r.actor',(who,mid)):
  row=result.setdefault(r['emoji'],{'emoji':r['emoji'],'count':0,'reacted':False,'people':[]});row['count']+=1;row['reacted']|=r['actor']==actor;row['people'].append({'id':r['actor'],'name':r['display_name']})
 return list(result.values())
def task_name(value):
 if not isinstance(value,str) or not value.strip() or len(value)>20000:raise HTTPException(422,'Enter a task name of up to 20,000 characters.')
 return value.strip()
def install(app,db,identity,message,workspace):
 with db() as c:c.executescript(SCHEMA)
 def personal(c,who,actor,tid):
  r=c.execute('SELECT * FROM tw_personal_tasks WHERE owner=? AND actor=? AND id=?',(who,actor,tid)).fetchone()
  if not r:raise HTTPException(404,'Personal task not found.')
  return r
 def rows(c,who,actor):return [dict(r) for r in c.execute('SELECT id,name,completed,archived,position FROM tw_personal_tasks WHERE owner=? AND actor=? AND archived=0 ORDER BY position,created,id',(who,actor))]
 @app.get('/api/chat/personal-tasks')
 def list_personal(req:Request):
  with db() as c:
   who,actor=identity(req,c);return rows(c,who,actor)
 @app.post('/api/chat/personal-tasks')
 async def create_personal(req:Request):
  d=await data(req)
  with db() as c:
   who,actor=identity(req,c)
   if set(d)!={'name'}:raise HTTPException(422,'Enter a personal task name.')
   name=task_name(d['name']);tid=secrets.token_hex(12);position=c.execute('SELECT COALESCE(MAX(position),0)+1 FROM tw_personal_tasks WHERE owner=? AND actor=?',(who,actor)).fetchone()[0]
   c.execute('INSERT INTO tw_personal_tasks VALUES(?,?,?,?,0,0,?,?)',(tid,who,actor,name,position,time.time()));return dict(personal(c,who,actor,tid))
 @app.post('/api/chat/personal-tasks/archive-completed')
 def archive_completed(req:Request):
  with db() as c:
   who,actor=identity(req,c);c.execute('UPDATE tw_personal_tasks SET archived=1 WHERE owner=? AND actor=? AND completed=1',(who,actor));return rows(c,who,actor)
 @app.patch('/api/chat/personal-tasks/{tid}')
 async def update_personal(tid:str,req:Request):
  d=await data(req)
  with db() as c:
   who,actor=identity(req,c);r=personal(c,who,actor,tid)
   if not d or set(d)-{'name','completed','archived'}:raise HTTPException(422,'Check the task details.')
   name=task_name(d.get('name',r['name']))
   for key in ['completed','archived']:
    if key in d and type(d[key]) is not bool:raise HTTPException(422,'Choose a valid task state.')
   c.execute('UPDATE tw_personal_tasks SET name=?,completed=?,archived=? WHERE id=?',(name,d.get('completed',r['completed']),d.get('archived',r['archived']),tid));return dict(personal(c,who,actor,tid))
 @app.delete('/api/chat/personal-tasks/{tid}')
 def delete_personal(tid:str,req:Request):
  with db() as c:
   who,actor=identity(req,c);personal(c,who,actor,tid);c.execute('DELETE FROM tw_personal_tasks WHERE id=?',(tid,));return {'ok':True}
 @app.put('/api/chat/personal-tasks/{tid}/position')
 async def reorder(tid:str,req:Request):
  d=await data(req)
  with db() as c:
   who,actor=identity(req,c);r=personal(c,who,actor,tid);after=d.get('after')
   if set(d)!={'after'} or after is not None and not isinstance(after,str) or r['archived']:raise HTTPException(422,'Choose a visible personal task position.')
   tasks=rows(c,who,actor);ids=[x['id'] for x in tasks]
   if after==tid:return tasks
   if after is not None and after not in ids:raise HTTPException(404,'Personal task not found.')
   ids.remove(tid);ids.insert(0 if after is None else ids.index(after)+1,tid)
   for position,ident in enumerate(ids):c.execute('UPDATE tw_personal_tasks SET position=? WHERE id=?',(position,ident))
   return rows(c,who,actor)
 @app.put('/api/chat/messages/{mid}/reaction')
 async def react(mid:str,req:Request):
  d=await data(req)
  with db() as c:
   who,actor=identity(req,c);m=message(c,who,actor,mid)
   from chat_local import channel
   channel(c,who,actor,m['channel'],member=True)
   if m['kind']=='system':raise HTTPException(403,'This message cannot receive reactions.')
   if set(d)!={'emoji','reacted'} or not isinstance(d['emoji'],str) or d['emoji'] not in EMOJI or type(d['reacted']) is not bool:raise HTTPException(422,'Choose a valid reaction.')
   if d['reacted']:c.execute('INSERT OR IGNORE INTO tw_chat_reactions VALUES(?,?,?,?,?)',(who,mid,actor,d['emoji'],time.time()))
   else:c.execute('DELETE FROM tw_chat_reactions WHERE owner=? AND message=? AND actor=? AND emoji=?',(who,mid,actor,d['emoji']))
   return reactions(c,who,actor,mid)
 def task_context(req,mid):
  from app import ACL
  with db() as c:
   who,actor=identity(req,c);m=message(c,who,actor,mid)
   if m['kind']=='system':raise HTTPException(403,'Choose a conversation message.')
   author=(c.execute('SELECT display_name FROM local_auth_accounts WHERE account_id=?',(m['author'],)).fetchone() or ['Former member'])[0]
   from chat_local import channel
   room=channel(c,who,actor,m['channel'],member=True)
   if __import__('chat_conversations').role(c,who,actor)=='guest':raise HTTPException(403,'Guests cannot create project tasks from Chat.')
  ws=workspace(req);projects=[]
  for p in ws['projects']:
   if not ACL['allowed'](req,'Add Tasks',p['id']):continue
   lists=list(dict.fromkeys([r['data']['title'] for r in ws['records'] if r['kind']=='list' and r['parent']==p['id'] and r['data'].get('title')]+[t['list_name'] for t in ws['tasks'] if t['project_id']==p['id']]))
   projects.append({'id':p['id'],'name':p['name'],'lists':lists})
  description='\n\n---\nThis task was created from the following [message]('+room['url']+'/messages/'+mid+') in Teamwork Chat\n\n---\n**'+author+':**\n'+m['body']
  return {'projects':projects,'project_id':room['project_id'],'description':description,'people':ws['people']}
 @app.get('/api/chat/messages/{mid}/task-context')
 def context(mid:str,req:Request):return task_context(req,mid)
 @app.post('/api/chat/messages/{mid}/task')
 async def create_from_message(mid:str,req:Request):
  d=await data(req);context=task_context(req,mid)
  if set(d)-{'title','project_id','list_name','description','priority','start_date','due_date','estimate','assignee_ids'}:raise HTTPException(422,'Check the task details.')
  project=next((p for p in context['projects'] if p['id']==d.get('project_id')),None)
  if not project:raise HTTPException(403,'Choose a project you can add tasks to.')
  if d.get('list_name') not in project['lists']:raise HTTPException(422,'Choose an existing task list in this project.')
  d['title']=task_name(d.get('title'));d.setdefault('description',context['description'])
  if not isinstance(d['description'],str) or not d['description'].strip() or len(d['description'])>100000:raise HTTPException(422,'Enter a task description.')
  from app import create_task_data
  return await create_task_data(req,d)
 @app.get('/api/chat/link-title')
 def link_title(req:Request,url:str):
  from urllib.parse import urlsplit
  from chat_previews import CATALOG,entity,teamwork_card
  with db() as c:identity(req,c)
  if len(url)>8192:raise HTTPException(422,'Use a shorter link.')
  target=entity(url)
  if target:
   card=teamwork_card(workspace(req),*target);return {'title':card.get('title') if card.get('status')=='loaded' else None}
  key=url.rstrip('/');value=CATALOG.get(key)
  if not value:
   parts=urlsplit(url)
   if parts.hostname in ['localhost','127.0.0.1']:value=CATALOG.get('https://www.teamwork.com'+parts.path.rstrip('/')) or CATALOG.get('https://teamwork.com'+parts.path.rstrip('/'))
  return {'title':value.get('title') if value else None}
 @app.post('/api/chat/channels/{cid}/command-add')
 async def command_add(cid:str,req:Request):
  d=await data(req)
  with db() as c:
   who,actor=identity(req,c)
   from chat_local import channel,people
   from chat_conversations import role
   room=channel(c,who,actor,cid,member=True)
   if room['kind'] in ['pair','project']:raise HTTPException(403,'Members of this conversation are managed by its existing access rules.')
   if role(c,who,actor)=='guest' or actor!=room['creator'] and role(c,who,actor)!='admin':raise HTTPException(403,'Only channel administrators and owners can add people.')
   ids=d.get('members');allowed={p['id'] for p in people(c,who)}
   if set(d)!={'members'} or not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in allowed for i in ids):raise HTTPException(422,'Choose people in this workspace.')
   for ident in set(ids):c.execute('INSERT OR IGNORE INTO tw_chat_members VALUES(?,?,?,?,?)',(who,cid,ident,0,0))
   return {'ok':True,'members':list(dict.fromkeys(ids))}
