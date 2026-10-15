"""Source settings with persisted, observable project and collection behavior."""
import json,re,time,secrets,copy
from pathlib import Path
from lxml import html,etree
from fastapi import HTTPException
from record_operations import apply_fields,put_rich,DATA,fields_for
FIXTURES=json.loads((Path(__file__).parent/'frontend/ui-fixtures.json').read_text())
TOOL_NAMES={'message_boards':'Message Board','todosets':'To-dos','vaults':'Docs & Files','schedules':'Calendar','chat_transcripts':'Chat','kanban_boards':'Card Table','questionnaires':'Automatic Check-ins','inboxes':'Email Forwards'}

def save(c,owner,path,fields,kind='settings'):
 old=c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind=?',(owner,path,kind)).fetchone();result=json.loads(old['payload']) if old else {};result.update(fields)
 c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,path,kind,json.dumps(result),int(time.time())))
 return result

def mutate(c,owner,path,payload,method,account):
 match=re.fullmatch(r'/6302022/projects/(\d+)',path)
 if match:
  if path not in FIXTURES['forms']:return None
  if 'project[name]' in payload and not str(payload['project[name]']).strip():raise HTTPException(422,'Give the project a name.')
  if method=='DELETE':payload={'_status':'trashed'}
  save(c,owner,path,{k:v for k,v in payload.items() if k.startswith('project[') or k.startswith('_')},'project')
  return {'redirect':'/6302022/' if method=='DELETE' else path}
 match=re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/title',path)
 if match:
  title=str(payload.get('title','')).strip()
  if not title:raise HTTPException(422,'Enter a title.')
  tool=c.execute('SELECT * FROM bc_tools WHERE owner=? AND bucket=? AND id=? AND active=1',(owner,match[1],match[2])).fetchone()
  if tool:
   from tool_operations import TYPES
   c.execute('UPDATE bc_tools SET title=? WHERE owner=? AND id=?',(title,owner,tool['id']))
   return {'redirect':f'/6302022/buckets/{tool["bucket"]}/{TYPES[tool["kind"]][0]}/{tool["id"]}'}
  save(c,owner,path,{'title':title},'title');target=next((p for p in FIXTURES['titles'] if p.endswith('/'+match[2])),f'/6302022/projects/{match[1]}');return {'redirect':target}
 if path=='/6302022/account/custom_tool_names/reset':
  c.execute('DELETE FROM bc_mutations WHERE owner=? AND route LIKE "/6302022/account/custom_tool_names/%"',(owner,));return {'redirect':'/6302022/account/custom_tool_names'}
 match=re.fullmatch(r'/6302022/account/custom_tool_names/(\w+)',path)
 if match and match[1] in TOOL_NAMES:
  if not str(payload.get('account_custom_tool_name[name]','')).strip():raise HTTPException(422,'Enter a tool name.')
  save(c,owner,path,{'account_custom_tool_name[name]':str(payload['account_custom_tool_name[name]']).strip()});return {'redirect':'/6302022/account/custom_tool_names'}
 if path in ['/6302022/account/administratorships','/6302022/account/ownerships']:
  from workspaces import manager
  c.execute('BEGIN IMMEDIATE')
  actor=c.execute('SELECT role FROM bc_members WHERE workspace=? AND account=?',(owner,account['account_id'])).fetchone()
  manager({**account,'role':actor['role'] if actor else 'member'},path.endswith('/ownerships'));identifier=str(payload.get('person_id',''));identifier=account['account_id'] if identifier=='53382586' else identifier
  member=c.execute('SELECT * FROM bc_members WHERE workspace=? AND account=?',(owner,identifier)).fetchone()
  if not member:raise HTTPException(404,'Choose someone who belongs to this account.')
  role='owner' if path.endswith('/ownerships') else 'admin'
  if role=='admin' and member['role']=='owner':raise HTTPException(409,'Account owners cannot be demoted by changing administrator status.')
  if method=='DELETE':
   if member['role']=='owner':raise HTTPException(409,'Account owners cannot be removed here.')
   role='member'
  c.execute('UPDATE bc_members SET role=? WHERE workspace=? AND account=?',(role,owner,identifier));return {'redirect':'/6302022/account/owners' if path.endswith('/ownerships') else '/6302022/account/administrators'}
 match=re.fullmatch(r'(/6302022/(?:account|buckets/\d+/recordings/\d+)/(categories|user_groups|companies))(?:/(\d+))?',path)
 if match:
  parent,kind,identifier=match.groups();prefix={'categories':'category','user_groups':'user_group','companies':'company'}[kind];fields={k:v for k,v in payload.items() if k.startswith(prefix+'[')}
  if method!='DELETE' and not str(fields.get(prefix+'[name]','')).strip():raise HTTPException(422,'Enter a name.')
  if not identifier:identifier=str(900000000000+secrets.randbelow(99999999999))
  fields.update({'_id':identifier,'_kind':kind,'_parent':parent,'_deleted':method=='DELETE'});save(c,owner,parent+'/'+identifier,fields,'entity');return {'redirect':parent,'id':identifier}
 if path.endswith(('/order_preference','/view_preference')) or re.search(r'/(message_boards|schedules)/\d+(?:/settings)?$',path):
  if 'order' in payload and payload['order'] not in ['title','created_at','updated_at','positioning','last_comment_at']:raise HTTPException(422,'Choose a valid sort order.')
  if 'view' in payload and payload['view'] not in ['grid','list']:raise HTTPException(422,'Choose grid or list view.')
  save(c,owner,path,payload);return {'redirect':re.sub(r'/(order_preference|view_preference|settings)$','',path)}
 return None

def change_text(node,value):
 node.text=str(value)
 for child in list(node):node.remove(child)

def render(tree,path,owner,c,query):
 rows=c.execute('SELECT * FROM bc_mutations WHERE owner=?',(owner,)).fetchall();query=dict(query or {})
 for row in rows:
  route=row['route'];fields=json.loads(row['payload']);kind=row['kind'];apply_fields(tree,route,fields)
  if kind=='project':
   identifier=route.rsplit('/',1)[-1];name=fields.get('project[name]');description=fields.get('project[description]');removed=fields.get('_status')=='trashed'
   for link in tree.xpath('//a[@href]'):
    href=link.get('href').split('?')[0]
    if href in [route,'/6302022/buckets/'+identifier,'/6302022/buckets/'+identifier+'/title/edit']:
     if removed and path not in [route,'/6302022/buckets/'+identifier]:
      container=next((a for a in link.iterancestors() if a.tag=='article'),link)
      if container.getparent() is not None:container.getparent().remove(container)
     elif name:
      headings=link.xpath('.//h2|.//h3|.//*[contains(@class,"project-card__title")]');change_text(headings[0] if headings else link,name)
   if path in [route,'/6302022/buckets/'+identifier] and description is not None:
    for node in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," project-header__description ")]'):put_rich(node,description)
  if kind=='title':
   identifier=route.split('/')[-2]
   for node in tree.xpath('//*[@id="recording_title_recording_'+identifier+'"]//h1|//*[@id="recording_title_recording_'+identifier+'"]//h2'):
    targets=node.xpath('./a');change_text(targets[0] if targets else node,fields['title'])
  if '/account/custom_tool_names/' in route and fields.get('account_custom_tool_name[name]'):
   old=TOOL_NAMES.get(route.rsplit('/',1)[-1]);new=fields['account_custom_tool_name[name]']
   if old:
    for node in tree.xpath('//a|//h1|//h2|//h3|//span|//strong|//label'):
     if len(node)==0 and (node.text or '').strip()==old:node.text=(node.text or '').replace(old,new)
  if kind=='entity':
   identifier=fields['_id'];parent=fields['_parent'];entity_kind=fields['_kind'];prefix={'categories':'category','user_groups':'user_group','companies':'company'}[entity_kind]
   nodes=tree.xpath('//*[@id="'+prefix+'_'+identifier+'"]')
   if fields.get('_deleted'):
    for node in nodes:node.getparent().remove(node)
    continue
   if path==parent and not nodes:
    if entity_kind=='categories':
     samples=tree.xpath('//*[@id="categories_list"]/*[starts-with(@id,"category_")]')
     if samples:
      original=samples[0];old_id=original.get('id').removeprefix('category_');node=html.fromstring(html.tostring(original,encoding='unicode').replace(old_id,identifier));original.getparent().append(node);apply_fields(tree,route,fields)
    else:
     targets=tree.xpath('//main')
     if targets:
      node=etree.SubElement(targets[0],'div',{'class':'settings-list__item','id':prefix+'_'+identifier});link=etree.SubElement(node,'a',{'href':route+'/edit','class':'decorated'});link.text=fields.get(prefix+'[name]','')
   for node in tree.xpath('//*[@id="'+prefix+'_'+identifier+'"]'):
    for label in node.xpath('.//strong|.//a[not(@data-method)]'):
     if len(label)==0 and label.text and label.text.strip() not in ['Edit','Delete','Remove']:label.text=fields.get(prefix+'[name]',label.text)
  if route.endswith('/view_preference') and path==route.removesuffix('/view_preference'):
   for container in tree.xpath('//*[starts-with(@id,"vaultables_recording_")]'):
    if fields.get('view')=='list':
     container.set('class','vault__children')
     for node in container.xpath('./article'):
      node.set('class','vaultable-line')
      for item in node.iterdescendants():
       if item.get('class'):item.set('class',item.get('class').replace('vaultable-tile__figure','vaultable-line__icon').replace('vaultable-tile__title','vaultable-line__name'))
  if fields.get('order')=='title' and path==re.sub(r'/(order_preference|settings)$','',route):
   containers=tree.xpath('//*[starts-with(@id,"vaultables_recording_")]|//ul[contains(@class,"article-list")]')
   for container in containers:
    children=list(container)
    for child in sorted(children,key=lambda node:' '.join(node.text_content().split()).casefold()):container.append(child)

def dynamic_info(c,owner,path,routes):
 match=re.fullmatch(r'(/6302022/account/(user_groups|companies)/(\d+))(?:/edit)?',path)
 if not match:return None
 row=c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="entity"',(owner,match[1])).fetchone()
 if not row:return None
 fields=json.loads(row['payload'])
 if fields.get('_deleted'):raise HTTPException(404,'Item not found')
 parent=fields['_parent'];fixture=FIXTURES['forms'].get(parent)
 if not fixture:return None
 source=routes.get(fixture['route'])
 return {**source,'form_action':{'from':parent,'to':match[1]}} if source else None
