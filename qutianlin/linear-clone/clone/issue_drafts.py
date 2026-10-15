"""Saved issue drafts, isolated by workspace and published transactionally."""
import calendar,json,time
from datetime import datetime,timezone
from fastapi import HTTPException
from issue_properties import prepare_issue
FIELDS={'draft_account_id','id','title','description','status','priority','assignee','labels','project','template','parent','links','team','attachments','form_answers'}

def prepare_draft(c,wid,value,previous,provided,now):
 for key in list(value):
  if key not in FIELDS:value.pop(key,None)
 value.setdefault('title','');value.setdefault('description','');value.setdefault('status','Todo');value.setdefault('priority','No priority');value.setdefault('labels',[]);value.setdefault('assignee',None);value.setdefault('project',None)
 if not isinstance(value['title'],str)or not isinstance(value['description'],str):raise HTTPException(422,'Enter draft text.')
 if not isinstance(value['status'],str):raise HTTPException(422,'Select an issue status.')
 if not value.get('title','').strip()and not value.get('description','').strip()and not value.get('attachments')and not value.get('form_answers'):raise HTTPException(422,'Enter a title or description to save a draft.')
 statuses={json.loads(r[0])['title']for r in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='workflow-states'",(wid,))}
 if value['status']not in statuses:raise HTTPException(422,'Select an issue status.')
 prepare_issue(c,wid,value,None,value,now)
 for key in list(value):
  if key not in FIELDS:value.pop(key,None)

def prune_drafts(store,wid):
 today=datetime.fromtimestamp(time.time(),timezone.utc);index=today.year*12+today.month-1-6;year,month=divmod(index,12);month+=1;cutoff=int(today.replace(year=year,month=month,day=min(today.day,calendar.monthrange(year,month)[1])).timestamp())
 with store.auth.connect()as c:c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='drafts' AND created_at<?",(wid,cutoff));c.commit()
