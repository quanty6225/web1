"""Search and activity derived from owned records and actual successful writes."""
import json,re,time,html as escape
from datetime import datetime,timezone,timedelta
from lxml import html,etree
from fastapi import APIRouter,Request,HTTPException
from record_operations import DATA,metadata,fields_for,PREFIX,TITLE,BODY,text_value
from workspaces import allows
from pathlib import Path
WELCOME=json.loads((Path(__file__).parent/'frontend/welcome.json').read_text())
TYPES={'todos':'Todo','messages':'Message','documents':'Document','uploads':'Attachment','schedule_entries':'Schedule::Entry','card_tables/cards':'Kanban::Card','google_documents':'Attachment','todolists':'Todo','subtasks':'Todo','cloud_files':'Attachment','vaults':'Vault'}
def initialize(db):
 with db() as c:c.executescript('''CREATE TABLE IF NOT EXISTS bc_events(id INTEGER PRIMARY KEY AUTOINCREMENT,workspace TEXT,author TEXT,route TEXT,title TEXT,action TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS bc_event_reads(account TEXT,event INTEGER,PRIMARY KEY(account,event));
 CREATE TABLE IF NOT EXISTS bc_event_recipients(event INTEGER,account TEXT,PRIMARY KEY(event,account));''')
def emit(c,account,route,title,action,recipients=()):
 event=c.execute('INSERT INTO bc_events(workspace,author,route,title,action,created) VALUES(?,?,?,?,?,?)',(account['workspace_id'],account['account_id'],route,title,action,time.time())).lastrowid
 from thread_notifications import accessible_member
 for recipient in set(recipients)-{account['account_id']}:
  if accessible_member(c,account['workspace_id'],recipient,route):c.execute('INSERT INTO bc_event_recipients VALUES(?,?)',(event,recipient))
 return event

def record_event(db,account,path,method,referer,record=None):
 if path.startswith(('/api/pings','/6302022/circles','/6302022/my/sidebar/circles')):return
 # Personal preferences and comments have their own semantics. Never infer a
 # new entity from another user's most recent write in this workspace.
 if re.search(r'/(recent_visit|position|read|subscription|comments(?:_closure)?|boosts)(/|$)',path):return
 owner=account['workspace_id'];identifier=path.rstrip('/').rsplit('/',1)[-1]
 with db() as c:
  record=record or metadata(c,owner,identifier)
  if not record:
   match=re.search(r'/(?:todos|messages|documents|uploads|cards|schedule_entries|recordings)/(\d+)',path)
   if match:record=metadata(c,owner,match[1])
  if record:
   state=fields_for(c,owner,record);title=state.get(PREFIX[record['kind']]+'['+TITLE[record['kind']]+']',record['title']);route=record['url']
  elif '/api/chats/' in path:
   title='Chat';room=path.split('/')[3];route='/6302022/buckets/49234166/chats/'+room
  else:
   return
  action='deleted' if method=='DELETE' else 'updated' if method in ['PUT','PATCH'] else 'posted'
  emit(c,account,route,title,action)

def search_records(c,owner,query):
 from column_lifecycle import record_status
 query=query or {};q=str(query.get('q','')).strip().casefold();kinds=query.getlist('type_names[]') if hasattr(query,'getlist') else query.get('type_names[]',[]);buckets=query.getlist('bucket_ids[]') if hasattr(query,'getlist') else query.get('bucket_ids[]',[])
 records=dict(DATA['records']);matches=[]
 for row in c.execute('SELECT id FROM bc_records WHERE owner=?',(owner,)):
  record=metadata(c,owner,row['id'])
  if record:records[record['id']]=record
 for record in records.values():
  fields=fields_for(c,owner,record);prefix=PREFIX[record['kind']];title=fields.get(prefix+'['+TITLE[record['kind']]+']',record['title']);body=text_value(fields.get(prefix+'['+BODY[record['kind']]+']',''))
  if record_status(c,owner,record,fields)!='active' or (kinds and TYPES.get(record['kind']) not in kinds) or (buckets and record['bucket'] not in buckets):continue
  if q and q not in (title+' '+body).casefold():continue
  if not q:continue
  matches.append({'url':record['url'],'title':title,'body':body,'created':record.get('created',0),'kind':TYPES.get(record['kind'],'')})
 if not kinds or 'Comment' in kinds:
  for row in c.execute('SELECT * FROM bc_comments WHERE owner=?',(owner,)):
   parent=metadata(c,owner,row['route'].rsplit('/',1)[-1])
   if parent and record_status(c,owner,parent)!='active':continue
   body=text_value(row['body'])
   if q and q in body.casefold():matches.append({'url':row['route']+'#comment-'+row['id'],'title':'Comment','body':body,'created':row['created'],'kind':'Comment'})
 if query.get('sort')=='recency':matches.sort(key=lambda r:r['created'],reverse=True)
 return matches

def unread_events(c,account):
 rows=c.execute('SELECT e.*,a.display_name FROM bc_events e JOIN bc_event_recipients recipient ON recipient.event=e.id AND recipient.account=? LEFT JOIN local_auth_accounts a ON a.account_id=e.author WHERE e.workspace=? AND e.author!=? AND NOT EXISTS(SELECT 1 FROM bc_event_reads r WHERE r.account=? AND r.event=e.id) ORDER BY e.created DESC',(account['account_id'],account['workspace_id'],account['account_id'],account['account_id'])).fetchall()
 return [event for event in rows if allows(account,event['route'])]

def native_unreads(c,account):
 read={r['name'].removeprefix('welcome-read-') for r in c.execute('SELECT name FROM bc_settings WHERE owner=? AND name LIKE "welcome-read-%" AND value="true"',(account['account_id'],))}
 items=[{'section':'inbox','readable':r['unread_path'].rsplit('/',1)[-1],'identifier':r['identifier']} for r in WELCOME if r['id'] not in read]
 for event in unread_events(c,account):items.append({'section':'inbox','readable':'local-event-'+str(event['id']),'identifier':'local-event:'+account['workspace_id']+':'+str(event['id'])})
 from pings import unreads
 items.extend(unreads(c,account))
 return items

def sidebar_state(db,account):
 from bubble_up import pending
 with db() as c:
  unreads=native_unreads(c,account)
  reminders=[(row['target'],row['due'],row['due']<=time.time()) for row,item in pending(c,account,include_future=True)]
  from pings import listing
  conversations=[(row['id'],row['updated'],row['title']) for row in listing(c,account)]
 return unreads,json.dumps([unreads,reminders,conversations],sort_keys=True)

def render(tree,path,owner,c,account,query):
 from pings import render_sidebar,unreads as ping_unreads
 render_sidebar(tree,c,account)
 if path=='/6302022/search':
  query=query or {};q=str(query.get('q',''));matches=search_records(c,owner,query)
  from workspaces import allows
  matches=[match for match in matches if allows(account,match['url'])]
  for field in tree.xpath('//input[@name="q"]'):field.set('value',q)
  targets=tree.xpath('//main')
  if targets and q:
   section=etree.SubElement(targets[0],'section',{'class':'search-results margin-block-24','aria-live':'polite','data-local-search-results':'true'});etree.SubElement(section,'h2').text=str(len(matches))+' results'
   if not matches:etree.SubElement(section,'p').text='No results found.'
   for match in matches[:100]:
    node=etree.SubElement(section,'article',{'class':'margin-block-24'});heading=etree.SubElement(node,'h3');etree.SubElement(heading,'a',{'href':match['url'],'class':'decorated'}).text=match['title'];etree.SubElement(node,'p',{'class':'text-subtle'}).text=match['body'][:360]
 if path=='/6302022/activity' or re.fullmatch(r'/6302022/(?:buckets|projects)/\d+/activity',path):
  targets=tree.xpath('//*[@id="today_events_list"]|//*[@id="timeline_activity-pagination-list"]') or tree.xpath('//main')
  if not targets:return
  settings=c.execute('SELECT payload FROM bc_mutations WHERE owner=? AND route="/6302022/activity/settings" ORDER BY updated DESC LIMIT 1',(account['account_id'],)).fetchone();filters=json.loads(settings['payload']) if settings else {}
  for event in c.execute('SELECT e.*,a.display_name FROM bc_events e LEFT JOIN local_auth_accounts a ON a.account_id=e.author WHERE workspace=? ORDER BY e.created DESC LIMIT 100',(owner,)):
   if event['author']=='system:reminder':continue
   if filters.get('people_ids[]') and event['author'] not in filters['people_ids[]']:continue
   projects=filters.get('project_ids[]',[])
   if projects and not any('/buckets/'+identifier+'/' in event['route'] for identifier in projects):continue
   if '/activity' in path and path!='/6302022/activity' and '/buckets/'+path.split('/')[3]+'/' not in event['route']:continue
   node=etree.SubElement(targets[0],'article',{'class':'timeline-event margin-block-16','data-local-event':str(event['id'])});etree.SubElement(node,'strong').text=(event['display_name'] or 'Member')+' '+event['action']+' ';etree.SubElement(node,'a',{'href':event['route']}).text=event['title'];etree.SubElement(node,'time',{'class':'text-subtle'}).text=' '+datetime.fromtimestamp(event['created'],timezone.utc).strftime('%b %d, %H:%M')
 if path=='/6302022/my/sidebar/inbox':
  targets=tree.xpath('//*[@id="sidebar_unreads"]')
  if not targets:return
  for event in unread_events(c,account):
   node=etree.SubElement(targets[0],'article',{'id':'local_notification_'+str(event['id']),'class':'reading list-grid','data-local-notification':str(event['id']),'data-reading':'true','data-sidebar--readings-target':'reading','data-morph-version':'local-event-'+str(event['id']),'data-section':'inbox','data-unread-readable-identifier':'local-event:'+account['workspace_id']+':'+str(event['id'])})
   link=etree.SubElement(node,'a',{'href':event['route'],'class':'reading__link list-grid','data-roving-tabindex-target':'focusable','data-sidebar--readings-target':'control'});content=etree.SubElement(link,'div',{'class':'reading__content','data-quick-find-target':'searchable'});etree.SubElement(content,'h4',{'class':'reading__description margin-block-0'}).text=event['title'];etree.SubElement(content,'div',{'class':'reading__metadata text-subtle'}).text=event['action'] if event['author']=='system:reminder' else (event['display_name'] or 'Member')+' '+event['action']
   form=etree.SubElement(node,'form',{'action':'/6302022/my/events/'+str(event['id'])+'/read','method':'post','class':'reading__extras','data-turbo-frame':'sidebar_frame'});etree.SubElement(form,'button',{'type':'submit','class':'btn btn--sm','data-sidebar--readings-target':'control'}).text='Mark as read'
 for badge in tree.xpath('//*[@id="sidebar_badge"]//*[contains(concat(" ",normalize-space(@class)," ")," unread-badge ")]'):
  if (badge.text or '').isdigit():badge.text=str(int(badge.text)+len(unread_events(c,account))+len(ping_unreads(c,account)))

def install(app,db,require_user,csrf_check):
 router=APIRouter()
 from navigation_search import install as install_navigation_search
 install_navigation_search(router,db,require_user)
 @router.put('/6302022/my/unreads')
 async def mark_readables(request:Request):
  account=require_user(request);data=await request.json();csrf_check(request,data)
  readables=data.get('readables',[])
  if not isinstance(readables,list) or any(not isinstance(value,str) for value in readables):raise HTTPException(422,'Choose notifications to mark as read.')
  with db() as c:
   eligible={item['readable'] for item in native_unreads(c,account)}
   for readable in readables:
    if readable not in eligible:continue
    welcome=next((item for item in WELCOME if item['unread_path'].rsplit('/',1)[-1]==readable),None)
    if welcome:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,"true")',(account['account_id'],'welcome-read-'+welcome['id']))
    elif readable.startswith('local-event-'):c.execute('INSERT OR IGNORE INTO bc_event_reads VALUES(?,?)',(account['account_id'],int(readable.removeprefix('local-event-'))))
  from fastapi.responses import Response
  return Response(status_code=204)
 def response(request,account,data):
  from fastapi.responses import RedirectResponse,Response
  if 'turbo-stream' in request.headers.get('accept',''):
   if request.url.path=='/6302022/my/bulk_read' or request.url.path.startswith('/6302022/my/readings/'):
    # These captured controls move rows optimistically. Replacing their panel
    # mid-animation also disconnects custom input elements before setup ends.
    return Response(status_code=204)
   from bubble_up import sidebar_streams
   return Response(sidebar_streams(db,account,request.headers.get('x-csrf-token') or str(data.get('_csrf',''))),media_type='text/vnd.turbo-stream.html')
  return RedirectResponse('/6302022/my/sidebar/inbox',303)
 @router.post('/api/events/{identifier}/read')
 @router.post('/6302022/my/events/{identifier}/read')
 async def read(identifier:int,request:Request):
  account=require_user(request);data=await request.form();csrf_check(request,data)
  with db() as c:
   event=c.execute('SELECT e.* FROM bc_events e JOIN bc_event_recipients r ON r.event=e.id AND r.account=? WHERE e.id=? AND e.workspace=?',(account['account_id'],identifier,account['workspace_id'])).fetchone()
   if not event or not allows(account,event['route']):raise HTTPException(404,'Notification not found')
   c.execute('INSERT OR IGNORE INTO bc_event_reads VALUES(?,?)',(account['account_id'],identifier))
  return response(request,account,data)
 @router.post('/6302022/my/bulk_read')
 async def read_all(request:Request):
  account=require_user(request);data=await request.form();csrf_check(request,data)
  from bubble_up import WELCOME
  with db() as c:
   for item in WELCOME.values():c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,"true")',(account['account_id'],'welcome-read-'+item['id']))
   for event in unread_events(c,account):c.execute('INSERT OR IGNORE INTO bc_event_reads VALUES(?,?)',(account['account_id'],event['id']))
  return response(request,account,data)
 @router.api_route('/6302022/my/readings/{identifier}',methods=['POST','PATCH','DELETE'])
 async def reading(identifier:str,request:Request):
  account=require_user(request);data=await request.form();csrf_check(request,data)
  from bubble_up import WELCOME
  item=WELCOME.get(identifier)
  if not item:raise HTTPException(404,'Notification not found')
  read=str(data.get('_method',request.method)).upper()=='DELETE'
  with db() as c:c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,?,?)',(account['account_id'],'welcome-read-'+item['id'],json.dumps(read)))
  return response(request,account,data)
 app.include_router(router)
