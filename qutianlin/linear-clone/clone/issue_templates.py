"""Workspace and team standard issue templates with validated default properties."""
import json
from fastapi import HTTPException
from documents import clean_content

def prepare_issue_template(c,wid,value,previous,provided,now):
 def bad(message):raise HTTPException(422,message)
 from issue_forms import prepare_fields
 if value.get('template_type','standard')not in ('standard','form'):bad('Select a template type.')
 value.setdefault('template_type','standard');value['form_fields']=prepare_fields(value.get('form_fields',[]),c,wid,value.get('scope_team')or value.get('team'))
 if not isinstance(value.get('title'),str)or not value['title'].strip():bad('Enter a template name.')
 value['title']=value['title'].strip()
 for key in ('description','issue_title','issue_description','issue_content_html'):
  if not isinstance(value.get(key,''),str):bad('Invalid template text.')
  value.setdefault(key,'')
 if 'issue_content_html'in provided:value['issue_content_html'],value['issue_description']=clean_content(value['issue_content_html'])
 from uploads import validate_upload_references
 validate_upload_references(c,wid,value['issue_content_html'])
 for field in ('scope_team','team'):
  team=value.get(field)
  if team is not None and (not isinstance(team,str)or team!='QQQ'and not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='teams' AND id=?",(wid,team)).fetchone()):bad('Select a team from this workspace.')
  value[field]=team
 if value['scope_team']:value['team']=value['scope_team']
 if value.get('priority','No priority')not in ['No priority','Urgent','High','Medium','Low']:bad('Select an issue priority.')
 value.setdefault('priority','No priority')
 if value.get('status'):
  if not value.get('team'):bad('Choose a team before setting a status.')
  if not any(json.loads(r[0])['title']==value['status']and json.loads(r[0]).get('team','QQQ')==value.get('team','QQQ')for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states'",(wid,))):bad('Select an issue status.')
 if value.get('project')is not None and not isinstance(value['project'],str):bad('Select a project from this workspace.')
 if value.get('project')and not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='projects' AND id=?",(wid,value['project'])).fetchone():bad('Select a project from this workspace.')
 owner=c.execute('SELECT a.email_normalized FROM local_auth_accounts a JOIN linear_workspaces w ON w.owner_id=a.account_id WHERE w.id=?',(wid,)).fetchone()
 members={r[0]for r in c.execute('SELECT a.email_normalized FROM local_auth_accounts a JOIN linear_members m ON m.account_id=a.account_id WHERE m.workspace_id=?',(wid,))}
 if value.get('assignee')not in {None,'',*members}:bad('Select a workspace member.')
 labels=value.get('labels',[]);allowed={json.loads(r[0])['title']for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='labels'",(wid,))}
 if not isinstance(labels,list)or any(not isinstance(label,str)or label not in allowed for label in labels):bad('Select workspace labels.')
 value['labels']=list(dict.fromkeys(labels))
 if not isinstance(value.get('icon',''),str)or len(value.get('icon',''))>128:bad('Choose a template icon.')
 value.setdefault('icon','');value['sort_order']=(previous or {}).get('sort_order',now)
 if value.get('subissue_templates'):
  from subissue_templates import prepare_children
  value['subissue_templates']=prepare_children(c,wid,value['subissue_templates'],now,value.get('team')or'QQQ')
 elif 'subissue_templates'in value and value['subissue_templates']!=[]:bad('Invalid sub-issue templates.')
 else:value['subissue_templates']=[]
 for key in ['comments','history','creator','remind_at','parent','favorite','recurrence','is_default']:value.pop(key,None)

def issue_template_defaults(store,wid,data):
 template_id=data.get('template')
 if template_id is None and 'template'not in data:template_id=store.settings(wid,'/qqq153/settings/teams/'+data.get('team','QQQ')+'/templates').get('default-issue-template')
 if not template_id:return data
 template=store.get(wid,'issue-templates',template_id)
 if not template:raise HTTPException(422,'Select an available issue template.')
 if template.get('scope_team')not in (None,data.get('team','QQQ')):raise HTTPException(422,'This template belongs to another team.')
 defaults={'title':template['issue_title'],'description':template['issue_description'],'template':template_id,'subissue_templates':template.get('subissue_templates',[])}
 for field in ['status','priority','assignee','labels','project','team']:
  if template.get(field)is not None:defaults[field]=template[field]
 merged={**defaults,**data}
 if template.get('template_type')=='form':
  from issue_forms import apply_form
  return apply_form(store,wid,template,merged)
 return merged
