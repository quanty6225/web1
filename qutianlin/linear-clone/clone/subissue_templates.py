"""Validate and instantiate sub-issue templates in the parent transaction."""
import json
from fastapi import HTTPException

FIELDS=('title','description','status','priority','assignee','labels','project','attachments')

def default_status(c,wid):
 states=[json.loads(row[0])for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states'",(wid,))]
 return next((s['title']for s in states if s.get('category')=='Backlog'),next((s['title']for s in states if s.get('category')!='Duplicate'),'Todo'))

def maintain_references(c,wid,kind,old,new=None):
 """Keep saved drafts and future task defaults valid after configuration changes."""
 for row in c.execute("SELECT kind,id,document FROM linear_records WHERE workspace_id=? AND kind IN ('issue-templates','recurring-issues','drafts')",(wid,)).fetchall():
  value=json.loads(row['document']);before=json.dumps(value)
  for item in [value,*value.get('subissue_templates',[])]:
   if kind=='labels':item['labels']=[new['title']if new and x==old['title']else x for x in item.get('labels',[])if new or x!=old['title']]
   if kind=='workflow-states'and value.get('team','QQQ')==old.get('team','QQQ')and item.get('status')==old['title']:item['status']=new['title']if new else default_status(c,wid)
   if kind=='projects'and item.get('project')==old['id']and not new:item['project']=None
   if kind=='issue-templates'and item.get('template')==old['id']and not new:item['template']=None
   if kind=='issues'and item.get('parent')==old['id']and not new:item['parent']=None
  if json.dumps(value)!=before:c.execute('UPDATE linear_records SET document=?,revision=revision+1 WHERE workspace_id=? AND kind=? AND id=?',(json.dumps(value),wid,row['kind'],row['id']))

def prepare_children(c,wid,children,now,team='QQQ'):
 from issue_templates import prepare_issue_template
 from issue_attachments import attachments
 if not isinstance(children,list)or len(children)>100:raise HTTPException(422,'Add up to 100 sub-issues.')
 result=[]
 for child in children:
  if not isinstance(child,dict)or child.get('subissue_templates'):raise HTTPException(422,'Invalid sub-issue template.')
  value={**{k:child[k]for k in FIELDS if k in child},'scope_team':team,'team':team,'issue_title':child.get('title',''),'issue_description':child.get('description','')}
  prepare_issue_template(c,wid,value,None,{},now)
  value['description']=value['issue_description'];value['status']=value.get('status')or default_status(c,wid);value['attachments']=attachments(c,wid,value.get('attachments',[]));result.append({k:value.get(k)for k in FIELDS})
 return result

def insert_children(store,c,wid,parent,children,now):
 from issue_properties import prepare_issue
 ids=[]
 for child in prepare_children(c,wid,children,now,parent.get('team','QQQ')):
  from workspaces import next_issue_id
  data={**child,'id':next_issue_id(c,wid,parent.get('team','QQQ')),'parent':parent['id'],'team':parent.get('team','QQQ'),'creator':parent.get('creator'),'comments':[],'description_edited':True}
  if not data.get('project'):data['project']=parent.get('project')
  prepare_issue(c,wid,data,None,data,now)
  c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,'issues',data['id'],json.dumps(data),now,now));store.collect_record_event(c,wid,'issues','create',data,None);ids.append(data['id'])
 return ids
