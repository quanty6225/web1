"""Saved document templates in the existing workspace entity store."""
from fastapi import HTTPException
from documents import clean_content

def prepare_template(c,wid,value,previous,provided,now):
 title=value.get('title')
 if not isinstance(title,str) or not title.strip():raise HTTPException(422,'Enter a template name.')
 value['title']=title.strip()
 if not isinstance(value.get('content_html',''),str):raise HTTPException(422,'Invalid template content.')
 value['content_html'],value['description']=clean_content(value.get('content_html',''))
 from uploads import validate_upload_references
 validate_upload_references(c,wid,value['content_html'])
 team=value.get('team')
 if team is not None and (not isinstance(team,str) or team!='QQQ' and not c.execute("SELECT 1 FROM linear_records WHERE workspace_id=? AND kind='teams' AND id=?",(wid,team)).fetchone()):raise HTTPException(422,'Select a team from this workspace.')
 value['team']=team
 if previous is not None:value['sort_order']=previous.get('sort_order',0)
 else:
  import json
  records=[json.loads(row['document']) for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='document-templates'",(wid,))]
  value['sort_order']=max((item.get('sort_order',0) for item in records if item.get('team')==team),default=0)+1000
 if not isinstance(value.get('icon',''),str) or len(value.get('icon',''))>128:raise HTTPException(422,'Select a template icon.')
 value.setdefault('icon','')
 for key in ['history','comments','owner','last_editor','subscribers','remind_at','parent','pinned_teams','favorite']:
  value.pop(key,None)


def reorder_templates(store,wid,data):
 import json,time
 if not isinstance(data,dict) or not isinstance(data.get('ids'),list) or any(not isinstance(id,str) for id in data['ids']):raise HTTPException(422,'Select templates to reorder.')
 ids=data['ids'];team=data.get('team')
 with store.auth.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  rows={row['id']:json.loads(row['document']) for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='document-templates'",(wid,)).fetchall()}
  scoped={id:value for id,value in rows.items() if value.get('team')==team}
  if len(set(ids))!=len(ids) or set(ids)!=set(scoped):raise HTTPException(422,'Template list changed. Refresh and try again.')
  for index,id in enumerate(ids):
   value=scoped[id];value['sort_order']=(index+1)*1000
   c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='document-templates' AND id=?",(json.dumps(value),int(time.time()),wid,id))
  c.commit()
 return store.list(wid,'document-templates')
