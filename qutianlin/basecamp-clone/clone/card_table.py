"""Persistent cards and columns over the captured Card Table layout."""
import json,re,copy,secrets,time
from pathlib import Path
from functools import lru_cache
from lxml import html,etree
from fastapi import HTTPException
DATA=json.loads((Path(__file__).parent/'frontend/business-fixtures.json').read_text())

@lru_cache(maxsize=1)
def source_cards():
 cards=copy.deepcopy(DATA['cards'])
 # Slim Done/Not Now columns have their actual cards on the column page.
 for column in DATA['columns'].values():
  path=Path(__file__).parent/'frontend/pages'/column['board'].split('/card_tables/')[0].lstrip('/')/'card_tables/columns'/column['id']/'index.html'
  if not path.exists():continue
  tree=html.parse(path)
  for node in tree.xpath('//article[starts-with(@id,"on_board_recording_")]')[:5]:
   identifier=node.get('id').removeprefix('on_board_recording_')
   if identifier in DATA['records'] and identifier not in cards:
    cards[identifier]={'board':column['board'],'column':column['id'],'html':html.tostring(node,encoding='unicode')}
 return cards

def is_done(column):
 return bool(column and 'kanban-grid__done-column' in column.get('html',''))

def is_special(column):
 # Type is retained when a column is renamed or copied into a new board.
 if not column or not column.get('html'):return False
 classes=set(html.fromstring(column['html']).get('class','').split())
 return bool(classes & {'kanban-triage','kanban-grid__notnow-column','kanban-grid__done-column'})

def columns_for(connection,owner):
 columns=copy.deepcopy(DATA['columns'])
 for row in connection.execute('SELECT name,value FROM bc_settings WHERE owner=? AND name LIKE "card-column-%"',(owner,)):
  identifier=row['name'].removeprefix('card-column-');columns.setdefault(identifier,{}).update(json.loads(row['value']))
 from column_lifecycle import load_status
 load_status(connection,owner,columns)
 return columns

def parent_columns(columns):
 # New project boards retain the source shell's IDs in stored HTML. Resolve
 # those IDs within their board, rather than confusing them with source IDs.
 roots={};trees={}
 for identifier,column in columns.items():
  if column.get('html'):
   tree=html.fromstring(column['html']);trees[identifier]=tree
   roots[(column['board'],tree.get('id'))]=identifier
 parents={key:column['parent'] for key,column in columns.items() if column.get('parent') in columns}
 for identifier,tree in trees.items():
  for child in tree.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," kanban-column-onhold ")]'):
   actual=roots.get((columns[identifier]['board'],child.get('id')))
   if actual and actual!=identifier:parents[actual]=identifier
 return parents

def column_lineage(identifier,parents):
 seen=set()
 while identifier and identifier not in seen:
  yield identifier;seen.add(identifier);identifier=parents.get(identifier)

def cards_for(connection,owner):
 cards=copy.deepcopy(source_cards())
 from record_operations import metadata,fields_for
 for row in connection.execute('SELECT id FROM bc_records WHERE owner=? AND kind="card_tables/cards"',(owner,)):
  record=metadata(connection,owner,row['id']);fields=fields_for(connection,owner,record)
  seeds=source_cards();prototype=record['id'] if record.get('relocated_source') and record['id'] in seeds else next(iter(DATA['cards']));markup=seeds[prototype]['html'].replace(prototype,record['id']).replace(seeds[prototype]['board'].split('/')[3],record['bucket']);node=html.fromstring(markup)
  from record_attribution import card_summary
  if not record.get('relocated_source'):card_summary(node,connection,owner,record)
  for old in node.xpath('.//*[contains(@class,"kanban-card__assignee")]|.//*[contains(@class,"kanban-card__subtasks")]'):
   if old.getparent() is not None:old.getparent().remove(old)
  cards[record['id']]={'board':record['parent'],'column':fields.get('_column_id','10398823042'),'html':html.tostring(node,encoding='unicode'),'new':True}
 return cards

def save_column(c,owner,column):
 column={key:value for key,value in column.items() if key!='_record_status'}
 c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(owner,'card-column-'+column['id'],json.dumps(column)))

def mutate_column(c,owner,path,payload,method):
 match=re.fullmatch(r'/6302022/buckets/(\d+)/card_tables/(?:(\d+)/columns|columns/(\d+)(/on_hold)?)',path)
 if not match:return None
 c.execute('BEGIN IMMEDIATE')
 columns=columns_for(c,owner)
 if match[3]:
  column=columns.get(match[3])
  if not column or column.get('deleted') or '/buckets/'+match[1]+'/' not in column['board']:raise HTTPException(404,'Column not found')
  if match[4]:
   if method not in ('POST','DELETE'):raise HTTPException(405,'Use POST or DELETE for On hold.')
   if is_special(column):raise HTTPException(409,'Triage, Not Now and Done cannot have an On hold area.')
   from column_on_hold import mutate as mutate_on_hold
   return mutate_on_hold(c,owner,column,method)
 else:
  board=path.removesuffix('/columns')
  if not any(x['board']==board for x in columns.values()):raise HTTPException(404,'Card Table not found')
  from column_order import workflow
  ordered=workflow(columns,board,include_inactive=True)
  position=max((item.get('position',index) for index,item in enumerate(ordered,1)),default=0)+1
  column={'id':str(900000000000+secrets.randbelow(99999999999)),'board':board,'count':0,'new':True,'position':position}
 if method=='DELETE':
  if is_special(column):raise HTTPException(409,'Triage, Not Now and Done cannot be deleted.')
  cards=cards_for(c,owner);parents=parent_columns(columns)
  from record_operations import metadata,fields_for
  for identifier,card in cards.items():
   record=metadata(c,owner,identifier)
   if record and fields_for(c,owner,record).get('_record_status','active')!='active':continue
   moved=c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route LIKE ? AND kind="moves"',(owner,'%/cards/'+identifier+'/moves')).fetchone()
   current=json.loads(moved['payload']).get('column_id') if moved else card['column']
   if column['id'] in column_lineage(current,parents):raise HTTPException(409,'Move the cards out of this column before deleting it.')
  column['deleted']=True
 else:
  name=str(payload.get('kanban_column[name]',column.get('name',''))).strip()
  if not name:raise HTTPException(422,'Give the column a name.')
  column.update({'name':name,'description':str(payload.get('kanban_column[description]',column.get('description','')))})
 save_column(c,owner,column);return {'redirect':column['board'],'column_id':column['id']}

def dynamic_info(c,owner,path,routes):
 match=re.fullmatch(r'/6302022/buckets/(\d+)/card_tables/(columns|lists)/(\d+)(/edit)?',path)
 if not match:return None
 column=columns_for(c,owner).get(match[3])
 if not column or not column.get('new') or column.get('deleted'):return None
 source_id=html.fromstring(column['html']).get('id','').removeprefix('recording_') if column.get('html') else '10398823110'
 preferred='/6302022/buckets/49234166/card_tables/'+match[2]+'/'+source_id+(match[4] or '')
 prototype=preferred if preferred in routes else next((p for p in routes if re.fullmatch(r'/6302022/buckets/\d+/card_tables/'+match[2]+r'/\d+'+(match[4] or ''),p)),None)
 if not prototype:return None
 tool=c.execute('SELECT mapping FROM bc_tools WHERE owner=? AND id=? AND kind="Kanban::Board"',(owner,column['board'].rsplit('/',1)[-1])).fetchone()
 substitutions=json.loads(tool['mapping']) if tool else {}
 substitutions.update({prototype.split('/')[3]:match[1],prototype.split('/')[6]:match[3],'10398823040':column['board'].rsplit('/',1)[-1]})
 from record_operations import bookmark_reference
 reference=bookmark_reference(routes[prototype]['file'])
 if reference:substitutions[reference]='/6302022/my/bookmarks/local-'+column['id']
 return {**routes[prototype],'substitutions':substitutions,'local_column':column,'bookmark_source':{'reference':reference,'id':prototype.split('/')[6]}}

def prepare_column(markup):
 tree=html.document_fromstring(markup)
 for node in tree.xpath('//article[starts-with(@id,"on_board_recording_")]|//*[@data-comment]'):
  if node.getparent() is not None:node.getparent().remove(node)
 for node in tree.xpath('//*[@data-source-comment-total]'):node.set('data-source-comment-total','0')
 return html.tostring(tree,encoding='unicode',doctype='<!doctype html>')

def move(connection,account,path,payload,method):
 match=re.fullmatch(r'/6302022/buckets/(\d+)/card_tables/(?:cards/(\d+)|(\d+))/moves',path)
 if not match:return False
 if method!='POST':raise HTTPException(405,'Use POST to move a card or column.')
 owner=account['workspace_id'];connection.execute('BEGIN IMMEDIATE')
 identifier=match[2] or str(payload.get('source_id',''));column=str(payload.get('column_id',payload.get('target_id','')));columns=columns_for(connection,owner)
 try:
  position=int(payload.get('position',1))
  if position<1:raise ValueError()
 except (ValueError,TypeError):raise HTTPException(422,'Choose a valid position.')
 if column.startswith('wh-'):
  from record_operations import metadata
  from column_lifecycle import record_status
  from card_wormholes import move as move_through_wormhole
  record=metadata(connection,owner,identifier)
  if not record or record['kind']!='card_tables/cards' or record['bucket']!=match[1] or record_status(connection,owner,record)!='active':raise HTTPException(404,'Card not found')
  if match[3] and record['parent']!=path.removesuffix('/moves'):raise HTTPException(404,'Card not found on this board')
  result=move_through_wormhole(connection,account,record,column)
  if result:return result
  raise HTTPException(404,'Wormhole not found')
 if identifier in columns and match[3]:
  source=columns[identifier]
  if source['board']!=path.removesuffix('/moves'):raise HTTPException(404,'Column not found')
  from column_order import move as move_column
  move_column(connection,owner,columns,source,column,position);return True
 card=cards_for(connection,owner).get(identifier);destination=columns.get(column)
 if not card or not destination or destination.get('deleted') or card['board']!=destination['board'] or '/buckets/'+match[1]+'/' not in card['board']:raise HTTPException(404,'Card or column not found')
 from column_lifecycle import require_active
 require_active(columns,column)
 if match[3] and card['board']!=path.removesuffix('/moves'):raise HTTPException(404,'Card Table not found')
 from record_operations import metadata,fields_for
 record=metadata(connection,owner,identifier)
 if not record or fields_for(connection,owner,record).get('_record_status','active')!='active':raise HTTPException(404,'Card not found')
 route=f'/6302022/buckets/{match[1]}/card_tables/cards/{identifier}/moves'
 previous=connection.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route=? AND kind="moves"',(owner,route)).fetchone()
 previous=json.loads(previous['payload']) if previous else {'column_id':card['column']}
 state={'column_id':column,'position':position}
 if is_done(destination):
  if is_done(columns.get(previous['column_id'])):
   state.update({key:previous[key] for key in ('completed_at','completed_by') if key in previous})
  else:state.update(completed_at=time.time(),completed_by=account['account_id'])
 connection.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,strftime("%s","now"))',(owner,route,'moves',json.dumps(state)))
 if column!=previous['column_id']:
  from thread_notifications import subscribers
  from activity_search import emit
  fields=fields_for(connection,owner,record)
  action='completed' if is_done(destination) else 'reopened' if is_done(columns.get(previous['column_id'])) else 'moved'
  from column_watching import audience as column_audience
  emit(connection,account,record['url'],fields.get('kanban_card[title]',record['title']),action,subscribers(connection,account,record) | column_audience(connection,account,column,previous=previous['column_id']))
 return True

def render(tree,path,owner,connection):
 from record_operations import metadata,fields_for,apply_fields
 from card_render import column_label
 columns=columns_for(connection,owner);cards=cards_for(connection,owner);rows=connection.execute('SELECT * FROM bc_mutations WHERE owner=?',(owner,)).fetchall();positions={};counts={k:v.get('count',0) for k,v in columns.items()}
 parents=parent_columns(columns)
 viewed=re.fullmatch(r'/6302022/buckets/\d+/card_tables/(?:columns|lists)/(\d+)',path)
 prototype=DATA['columns'].get('10398823110')
 for identifier,column in columns.items():
  nodes=tree.xpath('//*[@id="recording_'+identifier+'"]')
  if column.get('new') and identifier not in parents and path==column['board'] and prototype and not nodes:
   markup=prototype['html'].replace(prototype['board'],column['board']).replace('/buckets/49234166/','/buckets/'+column['board'].split('/')[3]+'/')
   source=html.fromstring(markup.replace(prototype['id'],identifier))
   for article in source.xpath('.//article'):
    if article.getparent() is not None:article.getparent().remove(article)
   candidates=tree.xpath('//*[@id="kanban-workflow"]')
   if candidates:candidates[0].append(source);nodes=[source]
  from column_lifecycle import status as column_status
  if column.get('deleted') or (path==column['board'] and column_status(columns,identifier,parents)!='active'):
   for node in nodes:node.getparent().remove(node)
   continue
  if column.get('name'):
   name=column_label(column,columns)
   for node in nodes:
    for title in node.xpath('.//h2[contains(@class,"kanban-column__title")]/a'):title.text=name;title.getparent().set('title',name)
    for toggle in node.xpath('.//*[@aria-label]'):
     if toggle.get('aria-label','').endswith(' column options'):toggle.set('aria-label',name+' column options')
     elif toggle.get('aria-label','').startswith('Toggle ') and toggle.get('aria-label','').endswith(' column'):toggle.set('aria-label','Toggle '+name+' column')
   action='/6302022/buckets/'+column['board'].split('/')[3]+'/card_tables/columns/'+identifier
   apply_fields(tree,action,{'kanban_column[name]':name,'kanban_column[description]':column.get('description','')})
   if viewed and viewed[1]==identifier:
    for title in tree.xpath('//*[@id="recording_title_recording_'+identifier+'"]//a'):title.text=name
    for title in tree.xpath('//head/title'):title.text=name
 from column_order import render as render_order
 render_order(tree,columns,path)
 from column_on_hold import render as render_on_hold
 render_on_hold(tree,columns)
 for row in rows:
  match=re.search(r'/card_tables/cards/(\d+)/moves$',row['route'])
  if match:positions[match[1]]=json.loads(row['payload'])
 for identifier,card in cards.items():
  from trash import erased
  state=positions.get(identifier,{});column=state.get('column_id',card['column']);record=metadata(connection,owner,identifier);fields=fields_for(connection,owner,record) if record else {};active=fields.get('_record_status','active')=='active' and not erased(connection,owner,identifier)
  if record and path.rstrip('/') in (record['url'],record['url']+'/edit'):
   from card_render import detail
   detail(tree,record,card,columns,state)
  if card.get('new'):
   if record.get('relocated_source'):
    original=source_cards().get(identifier)
    if original:
     for ancestor in column_lineage(original['column'],parents):counts[ancestor]=counts.get(ancestor,0)-1
   if active:
    for ancestor in column_lineage(column,parents):counts[ancestor]=counts.get(ancestor,0)+1
  elif state or not active:
   for ancestor in column_lineage(card['column'],parents):counts[ancestor]=counts.get(ancestor,0)-1
   if active:
    for ancestor in column_lineage(column,parents):counts[ancestor]=counts.get(ancestor,0)+1
  if not state and not card.get('new') and active:continue
  elements=tree.xpath('//*[@id="on_board_recording_'+identifier+'"]');targets=tree.xpath('//*[@id="recording_'+column+'_cards"]')
  if not targets and viewed and viewed[1] in column_lineage(column,parents):targets=tree.xpath('//*[@data-infinite-page-container]') or tree.xpath('//*[@id="kanban_cards"]') or tree.xpath('//main')
  for element in elements:
   if element.getparent() is not None:element.getparent().remove(element)
  if targets and active:
   element=html.fromstring(card['html']);target=targets[0];index=max(0,int(state.get('position',1))-1);target.insert(min(index,len(target)),element)
 for identifier,count in counts.items():
  count=max(0,count)
  for badge in tree.xpath('//*[@id="kanban_list_'+identifier+'_counter"]'):
   spans=badge.xpath('./span[not(@hidden)]')
   if spans:badge.text='';spans[-1].text=str(count)
   else:badge.text=str(count)
 for row in rows:
  match=re.search(r'/card_tables/columns/(\d+)/(color)$',row['route'])
  if not match:continue
  payload=json.loads(row['payload']);nodes=tree.xpath('//*[@id="recording_'+match[1]+'"]')
  for node in nodes:
   if match[2]=='color':
    value=str(payload.get('color',payload.get('recording[color]','')))
    if value in ['white','yellow','orange','red','pink','purple','blue','green','brown']:node.set('style','--recording-color: var(--recording-color-'+value+');')
 return tree
