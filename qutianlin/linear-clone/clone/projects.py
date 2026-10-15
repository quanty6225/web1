"""Validate project properties and workspace-scoped relationships."""
from datetime import date
from fastapi import HTTPException

def validate_project(store,wid,account,data,id=None):
 previous=store.get(wid,'projects',id) if id else {}
 if id and not previous:raise HTTPException(404,'Item not found.')
 if not id:data.setdefault('teams',['QQQ']);data.setdefault('lead_team','QQQ')
 value={**(previous or {}),**data}
 def invalid(message):raise HTTPException(422,message)
 for key in ['title','summary','description']:
  if key in value and not isinstance(value[key],str):invalid('Invalid project '+key+'.')
 if not value.get('title','').strip():invalid('Project name required. The project name cannot be empty.')
 if value.get('status','Backlog') not in [s['title'] for s in store.list(wid,'project-statuses')]:invalid('Invalid project status.')
 if value.get('priority','No priority') not in ['No priority','Urgent','High','Medium','Low']:invalid('Invalid project priority.')
 if value.get('lead') not in [None,'',account['email_normalized']]:invalid('Select a project lead from this workspace.')
 members=value.get('members',[])
 if not isinstance(members,list) or any(m!=account['email_normalized'] for m in members) or len(members)!=len(set(members)):invalid('Select project members from this workspace.')
 for key in ['start_date','target_date']:
  if value.get(key):
   try:date.fromisoformat(value[key])
   except (ValueError,TypeError):invalid('Invalid project date.')
  if value.get(key+'_precision','day') not in ['day','month','quarter','half-year','year']:invalid('Invalid date precision.')
 for key,kind in [('labels','project-labels'),('dependencies','projects')]:
  refs=value.get(key,[])
  if not isinstance(refs,list) or len(refs)>100 or any(not isinstance(v,str) for v in refs):invalid('Invalid project '+key+'.')
  if len(refs)!=len(set(refs)) or any(not store.get(wid,kind,ref) for ref in refs):invalid('Select '+key+' from this workspace.')
 if id:
  graph={p['id']:p.get('dependencies',[]) for p in store.list(wid,'projects')};seen=set();pending=list(value.get('dependencies',[]))
  while pending:
   node=pending.pop()
   if node==id:invalid('Project dependencies cannot form a cycle.')
   if node not in seen:seen.add(node);pending.extend(graph.get(node,[]))
 milestones=value.get('milestones',[])
 if not isinstance(milestones,list) or len(milestones)>100:invalid('Invalid project milestones.')
 ids=[]
 for m in milestones:
  if not isinstance(m,dict) or not isinstance(m.get('id'),str) or not m['id'] or not isinstance(m.get('title'),str) or not m['title'].strip() or not isinstance(m.get('description',''),str):invalid('Enter a name for each milestone.')
  if m.get('target_date'):
   try:date.fromisoformat(m['target_date'])
   except (ValueError,TypeError):invalid('Invalid milestone date.')
  if m.get('target_date_precision','day') not in ['day','month','quarter','half-year','year']:invalid('Invalid milestone date precision.')
  ids.append(m['id'])
 if len(ids)!=len(set(ids)):invalid('Milestone identifiers must be unique.')

 for key in ['favorite','archived']:
  if key in value and not isinstance(value[key],bool):invalid('Invalid project '+key+'.')
 if 'health' in value and value['health'] not in [None,'onTrack','atRisk','offTrack','outdated','noUpdate']:invalid('Invalid project health.')
 links=value.get('links',[])
 from urllib.parse import urlsplit
 if not isinstance(links,list) or len(links)>100:invalid('Invalid project links.')
 for link in links:
  if not isinstance(link,dict) or not isinstance(link.get('title'),str) or not link['title'].strip() or not isinstance(link.get('url'),str) or urlsplit(link['url']).scheme not in ['http','https'] or not urlsplit(link['url']).hostname:invalid('Enter a title and a valid URL.')

 teams=value.get('teams',[])
 allowed_teams={'QQQ',*[x['id'] for x in store.list(wid,'teams')]}
 if not isinstance(teams,list) or any(not isinstance(t,str) or t not in allowed_teams for t in teams):invalid('Select teams from this workspace.')
 if value.get('lead_team') and value['lead_team'] not in allowed_teams:invalid('Select a lead team from this workspace.')
