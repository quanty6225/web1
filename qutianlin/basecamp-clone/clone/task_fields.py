"""Assignees, due dates, and task completion reflected in source detail/list UI."""
import json,re,time
from pathlib import Path
from datetime import date
from lxml import html,etree
from fastapi import HTTPException
from record_operations import DATA,metadata,fields_for,PREFIX
PEOPLE=json.loads((Path(__file__).parent/'frontend/people-fixtures.json').read_text())

def people(c,account):
 result={k:dict(v) for k,v in PEOPLE.items()}
 from workspaces import members
 for member in members(c,account['workspace_id']):result[member['account']]={'value':member['account'],'name':member['name'],'avatar_url':'/api/avatar.svg?person='+member['account'],'type':'person','mentionable':{'name':member['name'],'type':'person','gid':'local-person:'+member['account']}}
 if '53382586' in result:
  owner=result.get(account['workspace_id'],{'name':account['display_name'],'avatar_url':'/api/avatar.svg'})
  result['53382586']={**result['53382586'],'name':owner['name'],'avatar_url':owner['avatar_url']}
 return result

def project_people(c,account,bucket):
 from thread_notifications import accessible_member
 result=people(c,account);result.pop('53382586',None)
 return {identifier:person for identifier,person in result.items() if (identifier in PEOPLE and bucket=='49234166') or (identifier not in PEOPLE and accessible_member(c,account['workspace_id'],identifier,'/6302022/buckets/'+bucket+'/'))}

def validate(fields,kind):
 prefix=PREFIX[kind]
 for suffix in ['due_on','starts_on']:
  value=fields.get(prefix+'['+suffix+']')
  if value:
   try:date.fromisoformat(value)
   except (ValueError,TypeError):raise HTTPException(422,'Choose a valid due date.')
 if fields.get(prefix+'[starts_on]') and fields.get(prefix+'[due_on]') and fields[prefix+'[starts_on]']>fields[prefix+'[due_on]']:raise HTTPException(422,'The end date cannot be before the start date.')

def record_assignments(c,account,kind,fields,previous,route=None):
 if not account:return
 key=PREFIX[kind]+'[assignees]'
 if key not in fields:return
 raw=fields[key];values=raw if isinstance(raw,list) else str(raw).split(',')
 assigned=[]
 for value in values:
  identifier=str(value).strip()
  if identifier=='me':identifier=account['account_id']
  if identifier=='53382586':identifier=account['workspace_id']
  if identifier and identifier not in assigned:assigned.append(identifier)
 catalog=people(c,account)
 if any(identifier not in catalog for identifier in assigned):raise HTTPException(422,'Choose someone who belongs to this project or account.')
 from task_notifications import identifiers,validate_people
 if route:validate_people(c,account,route,assigned)
 before=set(identifiers(previous.get(key,''),account))
 authors={identifier:author for identifier,author in previous.get('_assignment_authors',{}).items() if identifier in assigned}
 for identifier in assigned:
  if identifier not in before:authors[identifier]=account['account_id']
 fields[key]=','.join(assigned);fields['_assignment_authors']=authors

def mutate(c,account,path,payload,method):
 from task_notifications import complete,assignment_changed
 completion=complete(c,account,path,method)
 if completion:return completion
 match=re.fullmatch(r'/6302022/buckets/(\d+)/(todos|card_tables/cards)/(\d+)/assignments',path)
 if not match:return None
 c.execute('BEGIN IMMEDIATE')
 record=metadata(c,account['workspace_id'],match[3])
 if not record or record['url']!=path.removesuffix('/assignments'):raise HTTPException(404,'Item not found')
 fields=fields_for(c,account['workspace_id'],record);previous=dict(fields);key=PREFIX[record['kind']]+'[assignees]';assigned=[x for x in str(fields.get(key,'')).split(',') if x]
 choices=str(payload.get('assignee_id',payload.get('assignees','me'))).split(',');choices=[account['account_id'] if x=='me' else x.strip() for x in choices if x.strip()]
 if any(chosen not in people(c,account) for chosen in choices):raise HTTPException(404,'Person not found')
 if method=='DELETE':assigned=[x for x in assigned if x not in choices]
 elif 'assignees' in payload:assigned=list(dict.fromkeys(choices))
 else:assigned=list(dict.fromkeys(assigned+choices))
 fields[key]=','.join(assigned);record_assignments(c,account,record['kind'],fields,previous,record['url']);c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(account['workspace_id'],record['url'],'record',json.dumps(fields),int(time.time())))
 assignment_changed(c,account,record,previous)
 return {'redirect':record['url'],'activity_handled':True}

def render(tree,path,owner,c,account):
 if not account:return
 catalog=people(c,account);records=dict(DATA['records']);project_catalogs={}
 for row in c.execute('SELECT id FROM bc_records WHERE owner=?',(owner,)):
  record=metadata(c,owner,row['id'])
  if record:records[record['id']]=record
 for identifier,record in records.items():
  if record['kind'] not in ['todos','subtasks','card_tables/cards']:continue
  changed=record.get('is_new') or c.execute('SELECT 1 FROM bc_mutations WHERE owner=? AND route=? AND kind="record"',(owner,record['url'])).fetchone()
  fields=fields_for(c,owner,record);prefix=PREFIX[record['kind']];containers=tree.xpath('//*[@data-recording-id="'+identifier+'"]|//*[@id="on_board_recording_'+identifier+'"]')
  from task_notifications import identifiers
  if record['bucket'] not in project_catalogs:project_catalogs[record['bucket']]=project_people(c,account,record['bucket'])
  choices=project_catalogs[record['bucket']]
  for suffix in ('assignees','completion_subscribers'):
   key=prefix+'['+suffix+']';selected=identifiers(fields.get(key,''),account)
   for widget in tree.xpath('//form[@action="'+record['url']+'"]//bc-autocomplete[.//input[@name="'+key+'"]]'):
    widget.set('value',','.join(selected));widget.set('preload',json.dumps([choices[person] for person in selected if person in choices]))
    for chip in widget.xpath('./*[@data-role="autocompletable"]'):widget.remove(chip)
    for field in widget.xpath('.//input[@name="'+key+'"]'):field.set('value',','.join(selected))
  if path==record['url']:containers=tree.xpath('//article[contains(@class,"recordable")]') or containers
  for checkbox in tree.xpath('//input[@name="todo_complete"]'):
   if checkbox.get('data-url','').split('?')[0]==record['url']+'/completion':checkbox.set('aria-label',fields.get(prefix+'[content]',record['title']))
  if changed:
   assigned=[catalog[x] for x in str(fields.get(prefix+'[assignees]','')).split(',') if x in catalog];due=fields.get(prefix+'[due_on]','')
   for container in containers:
    for row in container.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," field-row ")]'):
     labels=row.xpath('./*[contains(@class,"field-row__label")]');content=row.xpath('./*[contains(@class,"field-row__content")]')
     if not labels or not content:continue
     label=labels[0].text_content().strip();target=content[0]
     if label not in ['Assigned to','Due on','When done']:continue
     for child in list(target):target.remove(child)
     target.text=''
     if label=='Due on':
      link=etree.SubElement(target,'a',{'href':record['url']+'/edit','class':'field-row__date'});link.text=date.fromisoformat(due).strftime('%a, %b %d, %Y') if due else 'Choose a date…'
     else:
      selected=assigned if label=='Assigned to' else [catalog[x] for x in str(fields.get(prefix+'[completion_subscribers]','')).split(',') if x in catalog]
      for person in selected:
       span=etree.SubElement(target,'span',{'class':'field-row__assignee'});etree.SubElement(span,'img',{'class':'avatar','src':person['avatar_url'],'alt':person['name'],'width':'24','height':'24'});etree.SubElement(span,'a',{'href':record['url']+'/edit'}).text=person['name']
      if not selected:etree.SubElement(target,'a',{'href':record['url']+'/edit','class':'field-row__placeholder'}).text='Assign someone…' if label=='Assigned to' else 'Notify these people…'
  completion=c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="completion"',(owner,record['url']+'/completion')).fetchone()
  if completion and record['kind']=='todos':
   done=json.loads(completion['payload']).get('active',False)
   for container in containers:
    if container.tag!='li':continue
    parent=container.getparent()
    if parent is None or parent.tag!='ul' or 'todos' not in parent.get('class',''):continue
    group=next((node for node in parent.iterancestors() if 'todolist' in node.get('class','') or node.tag=='main'),tree)
    targets=group.xpath('.//ul[contains(@class,"todos") and contains(@class,"'+('completed' if done else 'remaining')+'")]')
    if targets and targets[0]!=parent:parent.remove(container);targets[0].append(container)
