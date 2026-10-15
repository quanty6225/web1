"""Task assignment identities are account IDs; display names are presentation only."""
import json
import organization_local
from fastapi import HTTPException

def members(c,who):
 return {r['account_id']:dict(r) for r in c.execute('SELECT account_id,display_name,email_normalized FROM local_auth_accounts WHERE account_id=? OR account_id IN (SELECT account FROM tw_memberships WHERE workspace_owner=?)',(who,who))}

def options(task):return json.loads(task.get('options','{}')) if isinstance(task.get('options','{}'),str) else dict(task.get('options') or {})

def legacy(text,people,strict=False):
 if not isinstance(text,str):raise HTTPException(422,'Choose valid assignees.')
 ids=[];labels=[]
 for name in dict.fromkeys(x.strip() for x in text.split(',') if x.strip()):
  found=[ident for ident,p in people.items() if p['display_name']==name]
  if len(found)==1:ids.append(found[0])
  elif len(found)>1 and strict:raise HTTPException(422,'Choose the person explicitly; several people have this name.')
  else:labels.append(name)
 return list(dict.fromkeys(ids)),labels

def identity(task,people):
 opts=options(task)
 if 'assignee_ids' in opts:return [i for i in opts['assignee_ids'] if i in people],list(opts.get('assignee_labels',[]))
 return legacy(task.get('assignee',''),people)

def assigned_ids(c,who,task):
 people=members(c,who);direct,_=identity(task,people);catalog=organization_local.teams(c,who)
 return list(dict.fromkeys(direct+[person for team in options(task).get('assignee_team_ids',[]) for person in catalog.get(team,{}).get('effective_member_ids',[]) if person in people]))

def input_assignment(c,who,project,data):
 people=members(c,who)
 if 'assignee_ids' in data:
  ids=data['assignee_ids'];labels=[]
  if not isinstance(ids,list) or any(not isinstance(i,str) or i not in people for i in ids):raise HTTPException(422,'Choose assignees in this workspace.')
  ids=list(dict.fromkeys(ids))
 else:ids,labels=legacy(data.get('assignee',''),people,strict=True)
 team_ids=data.get('assignee_team_ids',[]);catalog=organization_local.teams(c,who)
 if not isinstance(team_ids,list) or any(not isinstance(i,str) or i not in catalog for i in team_ids):raise HTTPException(422,'Choose teams in this workspace.')
 team_ids=list(dict.fromkeys(team_ids));effective=list(dict.fromkeys(ids+[person for team in team_ids for person in catalog[team]['effective_member_ids'] if person in people]))
 for ident in effective:
  if ident==who:continue
  policy=c.execute('SELECT permissions,projects FROM tw_member_policies WHERE workspace_owner=? AND account=?',(who,ident)).fetchone()
  if policy:
   rights=json.loads(policy['permissions'])
   if project not in json.loads(policy['projects']) or not (rights.get('Project Administrator') or rights.get('View Tasks & Milestones')):raise HTTPException(422,'The selected assignee cannot access this project.')
 return ids,labels,team_ids

def store(c,who,tid,ids,labels=None,team_ids=None):
 row=c.execute('SELECT options FROM tw_tasks WHERE owner=? AND id=?',(who,tid)).fetchone()
 if not row:return
 people=members(c,who);ids=list(dict.fromkeys(i for i in ids if i in people));labels=list(labels or []);opts=json.loads(row['options']);opts.update(assignee_ids=ids,assignee_labels=labels)
 if team_ids is not None:opts['assignee_team_ids']=list(team_ids)
 catalog=organization_local.teams(c,who)
 display=', '.join([people[i]['display_name'] for i in ids]+[catalog[i]['title'] for i in opts.get('assignee_team_ids',[]) if i in catalog]+labels)
 c.execute('UPDATE tw_tasks SET options=?,assignee=? WHERE owner=? AND id=?',(json.dumps(opts),display,who,tid))

def decorate(task,people,teams=None):
 teams=teams or {};task['options']=options(task);direct,labels=identity(task,people);selected=[i for i in task['options'].get('assignee_team_ids',[]) if i in teams]
 effective=list(dict.fromkeys(direct+[person for team in selected for person in teams[team].get('effective_member_ids',[]) if person in people]))
 task.update(direct_assignee_ids=direct,assignee_team_ids=selected,assignee_ids=effective,assignees=[{'id':i,'name':people[i]['display_name']} for i in effective],assignee_teams=[{'id':i,'name':teams[i]['title']} for i in selected])
 task['assignee']=', '.join([people[i]['display_name'] for i in direct]+[teams[i]['title'] for i in selected]+labels)
 return task

def migrate(c):
 caches={}
 for row in c.execute('SELECT * FROM tw_tasks').fetchall():
  task=dict(row);opts=options(task)
  if 'assignee_ids' in opts:continue
  who=task['owner']
  if who not in caches:caches[who]=members(c,who)
  people=caches[who];ids,labels=legacy(task['assignee'],people);opts.update(assignee_ids=ids,assignee_labels=labels);c.execute('UPDATE tw_tasks SET options=? WHERE owner=? AND id=?',(json.dumps(opts),who,task['id']))

def canonical_options(c,who,task):
 opts=options(task)
 if 'assignee_ids' not in opts:
  ids,labels=legacy(task.get('assignee',''),members(c,who));opts.update(assignee_ids=ids,assignee_labels=labels)
 return opts
