"""Structured template fields and validated answers stored with created issues."""
from datetime import date
import re,json
from fastapi import HTTPException
TYPES={'text','long_text','dropdown','checkboxes','date','upload','instructions','title','priority','due_date','label_group'}

def label_group(c,wid,group_id,team=None):
 if not isinstance(group_id,str)or not group_id:raise HTTPException(422,'Select a label group from this workspace.')
 row=c.execute("SELECT kind,document FROM linear_records WHERE workspace_id=? AND id=? AND kind IN ('label-groups','labels')",(wid,group_id)).fetchone()
 group=json.loads(row['document'])if row else None
 if not group or row['kind']=='labels'and not group.get('is_group')or group.get('archived'):raise HTTPException(422,'Select an active label group from this workspace.')
 if team and group.get('team')not in (None,'',team):raise HTTPException(422,'Select a label group available to this team.')
 return group

def group_choices(c,wid,group_id,team=None):
 label_group(c,wid,group_id,team)
 return {row['id']:item for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='labels'",(wid,))if (item:=json.loads(row['document'])).get('group')==group_id and not item.get('is_group')and not item.get('archived')and (not team or item.get('team')in (None,'',team))}

def prepare_fields(fields,c,wid,team=None):
 if not isinstance(fields,list)or len(fields)>50:raise HTTPException(422,'Add up to 50 form fields.')
 result=[];seen=set();properties=set()
 for field in fields:
  if not isinstance(field,dict):raise HTTPException(422,'Invalid form field.')
  id=field.get('id');kind=field.get('type');label=field.get('label','');description=field.get('description','');required=field.get('required',False)
  if not isinstance(id,str)or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',id)or id in seen:raise HTTPException(422,'Invalid form field identifier.')
  if not isinstance(kind,str)or kind not in TYPES:raise HTTPException(422,'Select a form field type.')
  if not isinstance(label,str)or not label.strip()or len(label)>500:raise HTTPException(422,'Add a field label.')
  if not isinstance(description,str)or len(description)>10000 or type(required)is not bool:raise HTTPException(422,'Invalid field description or requirement.')
  options=field.get('options',[])
  if not isinstance(options,list)or len(options)>100 or any(not isinstance(x,str)or not x.strip()or len(x)>500 for x in options)or len(set(options))!=len(options):raise HTTPException(422,'Enter unique field options.')
  if kind in ('dropdown','checkboxes')and not options:raise HTTPException(422,'Add an option.')
  if kind in ('title','priority','due_date'):
   if kind in properties:raise HTTPException(422,'This issue property is already in the form.')
   properties.add(kind)
  prepared={'id':id,'type':kind,'label':label.strip(),'description':description,'required':required,'options':options}
  if kind=='label_group':
   group_id=field.get('label_group_id');label_group(c,wid,group_id,team)
   if group_id in properties:raise HTTPException(422,'This label group is already in the form.')
   properties.add(group_id);prepared.update(label_group_id=group_id,options=[])
  seen.add(id);result.append(prepared)
 return result

def apply_form(store,wid,template,data):
 from issue_attachments import attachments
 fields=template.get('form_fields',[]);answers=data.get('form_answers',{})
 if not isinstance(answers,dict)or any(key not in {f['id']for f in fields}for key in answers):raise HTTPException(422,'Invalid form answers.')
 out=dict(data);normalized={};body=[];files=[]
 with store.auth.connect()as c:
  for field in fields:
   kind=field['type'];value=answers.get(field['id']);label=field['label']
   if kind=='instructions':continue
   choices=group_choices(c,wid,field['label_group_id'],out.get('team','QQQ'))if kind=='label_group'else None
   if field['required']and (value is None or value==''or value==[] or isinstance(value,str)and not value.strip()):raise HTTPException(422,label+' is required.')
   if value is None or value==''or value==[]:continue
   if kind=='label_group':
    if not isinstance(value,str)or value not in choices:raise HTTPException(422,'Choose an available label for '+label+'.')
    labels=out.get('labels',[])
    if not isinstance(labels,list)or any(not isinstance(x,str)for x in labels):raise HTTPException(422,'Select workspace labels.')
    siblings={json.loads(row['document'])['title']for row in c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='labels'",(wid,))if json.loads(row['document']).get('group')==field['label_group_id']}
    out['labels']=list(dict.fromkeys([x for x in labels if x not in siblings]+[choices[value]['title']]))
    normalized[field['id']]=value
    continue
   if kind=='checkboxes':
    if not isinstance(value,list)or any(not isinstance(x,str)or x not in field['options']for x in value):raise HTTPException(422,'Choose valid options for '+label+'.')
    value=list(dict.fromkeys(value));text=', '.join(value)
   elif kind=='upload':
    value=attachments(c,wid,value);files.extend(value);text='\n'.join(f['filename']for f in value)
   else:
    if not isinstance(value,str)or len(value)>30000:raise HTTPException(422,'Enter a valid answer for '+label+'.')
    if kind=='dropdown'and value not in field['options']:raise HTTPException(422,'Choose a valid option for '+label+'.')
    if kind in ('date','due_date'):
     try:date.fromisoformat(value)
     except ValueError:raise HTTPException(422,'Choose a valid date for '+label+'.')
    if kind=='priority'and value not in ('No priority','Urgent','High','Medium','Low'):raise HTTPException(422,'Select an issue priority.')
    text=value
   normalized[field['id']]=value
   if kind in ('title','priority','due_date'):out[kind]=value
   else:body.append('## '+label+'\n'+text)
 out['form_answers']=normalized
 if body:
  rendered='\n\n'.join(body);description=out.get('description','')
  if not isinstance(description,str):raise HTTPException(422,'Enter a valid description.')
  out['description']=description if description.endswith(rendered)else '\n\n'.join(filter(None,[description,rendered]));out['description_edited']=True
 if files:out['attachments']=[*out.get('attachments',[]),*files]
 return out
