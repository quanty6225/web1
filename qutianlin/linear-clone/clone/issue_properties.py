"""Issue relationships and lifecycle changes inside the record transaction."""
import json,re
from datetime import date
from urllib.parse import urlsplit
from fastapi import HTTPException

RELATION_LISTS=('blocked_by','blocks','related')

def issue_documents(c,wid):
 return {row['id']:json.loads(row['document']) for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='issues'",(wid,))}

def prepare_issue(c,wid,value,previous,provided,now):
 from issue_attachments import attachments
 from workspaces import validate_team
 value['team']=validate_team(c,wid,value.get('team','QQQ'))
 value['attachments']=attachments(c,wid,value.get('attachments',[]))
 if not isinstance(value.get('comments',[]),list):raise HTTPException(422,'Invalid comments.')
 for comment in value.get('comments',[]):
  if not isinstance(comment,dict):raise HTTPException(422,'Invalid comment.')
  if 'attachments' in comment:comment['attachments']=attachments(c,wid,comment['attachments'])
 issues=issue_documents(c,wid);id=value['id']
 def invalid(message):raise HTTPException(422,message)
 for field in ('description','title'):
  if field in value and not isinstance(value[field],str):invalid('Invalid issue '+field+'.')
 if value.get('priority') not in ('No priority','Urgent','High','Medium','Low'):invalid('Select an issue priority.')
 if 'remind_at' in provided and provided['remind_at'] is not None:
  reminder=provided['remind_at']
  if type(reminder)is not int or reminder<=now or reminder>253402300799:invalid('Choose a future reminder date and time.')
 value.setdefault('remind_at',None)
 template=value.get('template')
 if template and not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='issue-templates' AND id=?",(wid,template)).fetchone():invalid('Select a template from this workspace.')
 labels=value.get('labels',[])
 allowed_labels={json.loads(row['document'])['title'] for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='labels'",(wid,))}
 if not isinstance(labels,list) or any(not isinstance(label,str) or label not in allowed_labels for label in labels):invalid('Select labels from this workspace.')
 value['labels']=list(dict.fromkeys(labels))
 for field in ('status_updated_at','started_at','completed_at','canceled_at','description_updated_at'):
  if previous and field in previous:value[field]=previous[field]
  else:value.pop(field,None)
 links=value.get('links',[])
 if not isinstance(links,list):invalid('Invalid issue links.')
 seen_links=set()
 for link in links:
  if not isinstance(link,dict) or not isinstance(link.get('id'),str) or not link['id'] or link['id'] in seen_links or not isinstance(link.get('url'),str) or not isinstance(link.get('title',''),str):invalid('Invalid issue link.')
  try:
   url=urlsplit(link['url'])
   if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:invalid('Enter an HTTP or HTTPS link without credentials.')
  except ValueError:invalid('Enter a valid link.')
  seen_links.add(link['id'])
 for field in ('parent','duplicate_of'):
  ref=value.get(field)
  if ref=='':ref=None
  if ref is not None and (not isinstance(ref,str) or ref==id or ref not in issues):invalid('Select another issue from this workspace.')
  value[field]=ref
  seen={id}
  while ref:
   if ref in seen:invalid('Issue relationships cannot form a cycle.')
   seen.add(ref);ref=issues.get(ref,{}).get(field)
 for field in RELATION_LISTS:
  refs=value.get(field,[])
  if not isinstance(refs,list) or any(not isinstance(ref,str) or ref==id or ref not in issues for ref in refs):invalid('Select related issues from this workspace.')
  value[field]=list(dict.fromkeys(refs))
 if value.get('project') is not None and not isinstance(value['project'],str):invalid('Select a project from this workspace.')
 if value.get('project') and not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='projects' AND id=?",(wid,value['project'])).fetchone():invalid('Select a project from this workspace.')
 if value.get('due_date') not in (None,''):
  try:
   if not isinstance(value['due_date'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value['due_date']):raise ValueError()
   date.fromisoformat(value['due_date'])
  except (ValueError,TypeError):invalid('Enter a valid due date.')
 else:value['due_date']=None
 if previous is None and value.get('parent'):
  parent=issues[value['parent']]
  for field in ('priority','project'):
   if field not in provided:value[field]=parent.get(field)
  owner=c.execute('SELECT a.email_normalized FROM linear_workspaces w JOIN local_auth_accounts a ON a.account_id=w.owner_id WHERE w.id=?',(wid,)).fetchone()
  children=[item for item in issues.values() if item.get('parent')==parent['id']]
  if 'assignee' not in provided and parent.get('assignee') and (parent['assignee']==owner['email_normalized'] or children and all(x.get('assignee')==parent['assignee'] for x in children)):value['assignee']=parent['assignee']
 if value.get('duplicate_of'):value['status']='Duplicate'
 categories={json.loads(row['document'])['title']:json.loads(row['document']).get('category') for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states'",(wid,)) if json.loads(row['document']).get('team','QQQ')==value.get('team','QQQ')}
 if previous is None or previous.get('status')!=value.get('status'):
  category=categories.get(value.get('status'))
  value['status_updated_at']=now
  if category=='Started' and not value.get('started_at'):value['started_at']=now
  value['completed_at']=now if category=='Completed' else None
  value['canceled_at']=now if category in ('Canceled','Duplicate') else None
 # Relationship lists on other records are updated after this row is written.
 value['subissues']=[item['id'] for item in issues.values() if item.get('parent')==id]
 history=list((previous or {}).get('description_history',[]))
 value['description_edited']=(previous or {}).get('description_edited',previous is None)
 if previous is not None and previous.get('description','')!=value.get('description',''):
  original_version=any(version.get('description')==value.get('description','') and version.get('description_edited') is False for version in history)
  value['description_edited']=not (provided.get('description_edited') is False and original_version)
  created=c.execute("SELECT created_at FROM linear_records WHERE workspace_id=? AND kind='issues' AND id=?",(wid,id)).fetchone()
  history.append({'description':previous.get('description',''),'description_edited':previous.get('description_edited',False),'at':previous.get('description_updated_at',created['created_at'] if created else now)})
  value['description_updated_at']=now
 value['description_history']=history

def synchronize_issues(store,c,wid,now,deleted=None):
 issues=issue_documents(c,wid)
 categories={(json.loads(row['document']).get('team','QQQ'),json.loads(row['document'])['title']):json.loads(row['document']).get('category') for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states'",(wid,))}
 resolved={id for id,item in issues.items() if categories.get((item.get('team','QQQ'),item.get('status'))) in ('Completed','Canceled','Duplicate')}
 originals={id:json.loads(json.dumps(item)) for id,item in issues.items()}
 for id,item in issues.items():
  if deleted:
   for field in ('parent','duplicate_of'):
    if item.get(field)==deleted:item[field]=None
   for field in RELATION_LISTS:
    if deleted in item.get(field,[]):item[field]=[ref for ref in item[field] if ref!=deleted]
  item['subissues']=[child['id'] for child in issues.values() if child.get('parent')==id]
 # A resolved blocker becomes a related issue on both ends, as documented.
 for id,item in issues.items():
  for target in list(item.get('blocked_by',[])):
   if target in resolved:
    item['blocked_by'].remove(target)
    item['related']=list(dict.fromkeys([*item.get('related',[]),target]))
  if id in resolved:
   for target in list(item.get('blocks',[])):
    if target in issues:
     issues[target]['related']=list(dict.fromkeys([*issues[target].get('related',[]),id]))
   item['blocks']=[]
 for id,item in issues.items():
  if item!=originals[id]:
   c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='issues' AND id=?",(json.dumps(item),now,wid,id))
   store.collect_record_event(c,wid,'issues','update',item,originals[id])
