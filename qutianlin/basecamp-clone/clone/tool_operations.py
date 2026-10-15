"""Project tools created from captured tool shells, with isolated empty contents."""
import copy,json,re,secrets,time
from functools import lru_cache
from pathlib import Path
from lxml import html,etree
from fastapi import HTTPException
TYPES={'Message::Board':('message_boards','10398823025','Message Board'),'Todoset':('todosets','10398823029','To-dos'),'Vault':('vaults','10398823035','Docs & Files'),'Schedule':('schedules','10398823037','Calendar'),'Chat::Transcript':('chats','10398823039','Chat'),'Kanban::Board':('card_tables','10398823040','Card Table')}

@lru_cache(maxsize=6)
def dock_prototype(kind):
 tree=html.parse(str(Path(__file__).parent/'frontend/pages/6302022/projects/49234166/index.html'))
 card=tree.xpath('//*[@id="exposed_tools"]/*[@id="recording_'+TYPES[kind][1]+'"]')[0]
 return html.tostring(card,encoding='unicode')

def dock_card(tool,c):
 """Use the captured project tile and its real empty state for a local tool."""
 config=TYPES[tool['kind']];markup=dock_prototype(tool['kind'])
 base=f'/6302022/buckets/{tool["bucket"]}/{config[0]}/{tool["id"]}'
 for old,new in json.loads(tool['mapping']).items():markup=markup.replace(old,new)
 card=html.fromstring(markup);card.set('data-local-tool',tool['id'])
 frame=card.xpath('./turbo-frame')[0]
 frame.attrib.pop('src',None);frame.attrib.pop('data-turbo-permanent',None)
 header=frame.xpath('./header')[0];body=frame.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," dock-card__body ")]')[0]
 for node in list(frame):
  if node not in (header,body):frame.remove(node)
 for node in header.xpath('.//h2'):
  node.text=''
  for child in list(node):node.remove(child)
  etree.SubElement(node,'a',{'href':base}).text=tool['title']
 for node in list(body):
  if node.tag!='a' or 'card__link' not in node.get('class','').split():body.remove(node)
 link=body.xpath('./a')[0]
 for node in list(link):
  if 'dock-card__blank-slate' not in node.get('class','').split():link.remove(node)
 body.set('class','dock-card__body card dock-card__body--blank')
 for link in card.xpath('.//a[@href]'):
  link.set('href',link.get('href').split('?')[0])
 for node in card.xpath('.//*[@data-bridge-desktop-label]'):node.set('data-bridge-desktop-label',tool['title'])
 summaries=[]
 if tool['kind']=='Chat::Transcript':
  for row in c.execute('SELECT body FROM bc_chat_lines WHERE owner=? AND room=? ORDER BY created DESC LIMIT 5',(tool['owner'],tool['id'])):
   summaries.append(' '.join(html.fragment_fromstring(row['body'] or '',create_parent='div').text_content().split()))
 else:
  from record_operations import metadata,fields_for,PREFIX,TITLE,text_value
  for row in c.execute('SELECT id FROM bc_records WHERE owner=? AND (parent=? OR parent LIKE ?) ORDER BY created DESC',(tool['owner'],base,base+'/%')):
   record=metadata(c,tool['owner'],row['id'])
   if not record:continue
   fields=fields_for(c,tool['owner'],record)
   if fields.get('_record_status','active')!='active':continue
   summaries.append(text_value(fields.get(PREFIX[record['kind']]+'['+TITLE[record['kind']]+']',record['title'])))
   if len(summaries)==5:break
 if summaries:
  link=body.xpath('./a')[0]
  for node in list(link):link.remove(node)
  body.set('class','dock-card__body card')
  preview=etree.SubElement(link,'div',{'class':'recording-preview'})
  for summary in summaries:etree.SubElement(preview,'p',{'class':'margin-block-8'}).text=summary
 return card
def initialize(db):
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS bc_tools(id TEXT PRIMARY KEY,owner TEXT,bucket TEXT,kind TEXT,title TEXT,mapping TEXT,active INTEGER DEFAULT 1)')
def all_tools(c,owner):return [dict(row) for row in c.execute('SELECT * FROM bc_tools WHERE owner=?',(owner,))]
def bookmark_target(c,owner,identifier):
 tool=c.execute('SELECT * FROM bc_tools WHERE owner=? AND id=? AND active=1',(owner,identifier)).fetchone()
 if not tool:raise HTTPException(404,'Tool not found')
 config=TYPES[tool['kind']]
 return {'url':f'/6302022/buckets/{tool["bucket"]}/{config[0]}/{tool["id"]}',
         'title':tool['title'],'source':f'/6302022/buckets/49234166/{config[0]}/{config[1]}','prototype':config[1]}
def mutate(c,owner,path,payload,method):
 match=re.fullmatch(r'/6302022/buckets/(\d+)/dock/tools(?:\.html)?',path)
 if not match:return None
 from project_lifecycle import source_projects
 from trash import erased
 if match[1] not in source_projects() or erased(c,owner,match[1]):raise HTTPException(404,'Project not found')
 if method!='POST':raise HTTPException(405,'Use POST to add a tool.')
 kind=payload.get('tool_type');config=TYPES.get(kind)
 if not config:raise HTTPException(422,'This tool has no captured setup page in the available source account.')
 c.execute('BEGIN IMMEDIATE')
 if c.execute('SELECT 1 FROM bc_tools WHERE owner=? AND bucket=? AND kind=? AND active=1',(owner,match[1],kind)).fetchone():raise HTTPException(409,'This project already has this tool.')
 identifier=str(900000000000+secrets.randbelow(99999999999));mapping={'49234166':match[1],config[1]:identifier};title=str(payload.get('title',config[2])).strip()
 if not title:raise HTTPException(422,'Give the tool a name.')
 url=f'/6302022/buckets/{match[1]}/{config[0]}/{identifier}'
 if kind=='Kanban::Board':
  from card_table import DATA,save_column
  for old,column in DATA['columns'].items():
   new=str(900000000000+secrets.randbelow(99999999999));mapping[old]=new;column={**copy.deepcopy(column),'id':new,'board':url,'count':0,'new':True};save_column(c,owner,column)
 c.execute('INSERT INTO bc_tools VALUES(?,?,?,?,?,?,1)',(identifier,owner,match[1],kind,title,json.dumps(mapping)))
 return {'redirect':url,'id':identifier}
def dynamic_info(c,owner,path,routes):
 from record_operations import bookmark_reference
 title=re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/title/edit',path)
 if title:
  tool=c.execute('SELECT * FROM bc_tools WHERE owner=? AND bucket=? AND id=? AND active=1',(owner,title[1],title[2])).fetchone()
  if tool:
   prototype='/6302022/buckets/49234166/recordings/10398823423/title/edit'
   info=routes.get(prototype)
   if info:
    config=TYPES[tool['kind']]
    return {**info,'substitutions':{'49234166':tool['bucket'],'10398823423':tool['id']},'local_record':{'url':f'/6302022/buckets/{tool["bucket"]}/{config[0]}/{tool["id"]}'}}
 bookmark=re.fullmatch(r'/6302022/my/bookmarks/local-tool-(\d+)/quick_toggle',path)
 if bookmark:
  target=bookmark_target(c,owner,bookmark[1]);reference=bookmark_reference(routes[target['source']]['file'])
  info=routes.get(reference+'/quick_toggle') if reference else None
  if not info:raise HTTPException(404,'Bookmark control not found')
  return {**info,'component':True,'local_record':target,'substitutions':{target['prototype']:bookmark[1],reference:path.removesuffix('/quick_toggle')}}
 for tool in all_tools(c,owner):
  if not tool['active']:continue
  config=TYPES[tool['kind']];base=f'/6302022/buckets/{tool["bucket"]}/{config[0]}/{tool["id"]}'
  if path!=base and not path.startswith(base+'/'):continue
  mapping=json.loads(tool['mapping']);source=path
  for old,new in mapping.items():source=source.replace(new,old)
  info=routes.get(source)
  if info:
   reference=bookmark_reference(info['file'])
   if reference:mapping[reference]='/6302022/my/bookmarks/local-tool-'+tool['id']
   return {**info,'substitutions':mapping,'local_tool':tool}
 return None

def prepare(markup,tool):
 tree=html.document_fromstring(markup);mapping=json.loads(tool['mapping'])
 # Locally created tools already have a user-selected title. Keep editing
 # that local title usable without the captured account's pro-pack CSS lock.
 for frame in tree.xpath('//*[@id="recording_title_recording_'+tool['id']+'"]'):
  frame.set('class',' '.join(value for value in frame.get('class','').split() if value!='inline-edit-form--pro-pack-dependent'))
 # Only template data is removed here, before local records are rendered.
 for selector in ['//ul[contains(@class,"article-list")]/li','//*[@id="todoset_todolists-pagination-list"]/*','//*[starts-with(@id,"vaultables_recording_")]/*','//*[contains(concat(" ",normalize-space(@class)," ")," chat-line ")]','//*[starts-with(@id,"on_board_recording_")]','//*[contains(@class,"kanban-grid__cards-stacks")]/*']:
  for node in tree.xpath(selector):
   if node.getparent() is not None:node.getparent().remove(node)
 for node in tree.xpath('//*[@id="recording_title_recording_'+tool['id']+'"]//h1|//*[@id="recording_title_recording_'+tool['id']+'"]//h2|//*[@id="recording_title_recording_'+tool['id']+'"]/a'):
  node.text=tool['title']
  for child in list(node):node.remove(child)
 for node in tree.xpath('//*[contains(@class,"kanban-column__cards-number")]'):node.text='0'
 for node in tree.xpath('//*[@data-recording-count]'):node.set('data-recording-count','0')
 for node in tree.xpath('//a[contains(@href,"/projects/'+tool['bucket']+'")]'):
  if not node.xpath('.//img'):node.text='My Project'
 return html.tostring(tree,encoding='unicode',doctype='<!DOCTYPE html>')

def render(tree,path,owner,c):
 tools=all_tools(c,owner)
 for tool in tools:
  action=f'/6302022/buckets/{tool["bucket"]}/recordings/{tool["id"]}/title'
  for field in tree.xpath('//form[@action="'+action+'"]//input[@name="title"]'):field.set('value',tool['title'])
  if not tool['active'] or path not in ['/6302022/projects/'+tool['bucket'],'/6302022/buckets/'+tool['bucket']+'/dock/edit']:continue
  config=TYPES[tool['kind']];targets=tree.xpath('//*[@id="exposed_tools"]') or tree.xpath('//main')
  if targets:
   card=dock_card(tool,c);add=targets[0].xpath('./*[@id="dock_add_card"]')
   if add:targets[0].insert(targets[0].index(add[0]),card)
   else:targets[0].append(card)
