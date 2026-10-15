"""Workspace-owned clients and team membership used by tasks and home filters."""
import json,re
from fastapi import HTTPException

def client_id(c,who,value):
 if value in ['',None]:return ''
 if not isinstance(value,str) or not c.execute("SELECT 1 FROM tw_records WHERE owner=? AND id=? AND kind='client'",(who,value)).fetchone():raise HTTPException(422,'Choose a client in this workspace.')
 return value

def teams(c,who):
 result={r['id']:{'id':r['id'],**json.loads(r['data'])} for r in c.execute("SELECT id,data FROM tw_records WHERE owner=? AND kind='team'",(who,))}
 for ident,team in result.items():
  people=set(team.get('member_ids',[]));queue=[ident];seen=set()
  while queue:
   parent=queue.pop()
   if parent in seen:continue
   seen.add(parent)
   for child in result.values():
    if child.get('parent_team_id')==parent:people.update(child.get('member_ids',[]));queue.append(child['id'])
  team['effective_member_ids']=sorted(people)
 return result

def validate(c,who,kind,data,ident=''):
 if kind not in ['team','client']:return
 title=data.get('title')
 if not isinstance(title,str) or not title.strip():raise HTTPException(422,'Enter a '+('team' if kind=='team' else 'client')+' name.')
 data['title']=title.strip()
 if kind=='client':return
 data.pop('effective_member_ids',None)
 selected=data.get('member_ids',[])
 people={r[0] for r in c.execute('SELECT account_id FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(who,who))}
 if not isinstance(selected,list) or any(not isinstance(i,str) or i not in people for i in selected):raise HTTPException(422,'Choose team members in this workspace.')
 data['member_ids']=list(dict.fromkeys(selected))
 handle=data.get('handle','')
 if not isinstance(handle,str) or handle and not re.fullmatch('[a-z0-9]+',handle):raise HTTPException(422,'Team handles contain lowercase letters and numbers only.')
 catalog=teams(c,who);parent=data.get('parent_team_id','')
 if not isinstance(parent,str) or parent and parent not in catalog:raise HTTPException(422,'Choose a parent team in this workspace.')
 seen={ident} if ident else set()
 while parent:
  if parent in seen:raise HTTPException(422,'A team cannot be its own ancestor.')
  seen.add(parent);parent=catalog[parent].get('parent_team_id','')
  if parent and parent not in catalog:break
 if handle and any(t.get('handle')==handle and t['id']!=ident for t in catalog.values()):raise HTTPException(409,'This team handle is already in use.')

def remove_team(c,who,ident):
 for row in c.execute('SELECT id,options FROM tw_tasks WHERE owner=?',(who,)).fetchall():
  options=json.loads(row['options'])
  if ident in options.get('assignee_team_ids',[]):
   options['assignee_team_ids'].remove(ident);c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(options),who,row['id']))
 for row in c.execute("SELECT id,data FROM tw_records WHERE owner=? AND kind='team'",(who,)).fetchall():
  data=json.loads(row['data'])
  if data.get('parent_team_id')==ident:data['parent_team_id']='';c.execute('UPDATE tw_records SET data=? WHERE owner=? AND id=?',(json.dumps(data),who,row['id']))
