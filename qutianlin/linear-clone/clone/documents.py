"""Workspace-scoped document content, ownership and saved revisions."""
import base64,html,json,re,time,secrets
from html.parser import HTMLParser
from urllib.parse import urlsplit
from fastapi import HTTPException

class DocumentHTML(HTMLParser):
 allowed={'p','br','strong','b','em','i','u','s','strike','h1','h2','h3','h4','blockquote','pre','code','ul','ol','li','hr','a','img','table','thead','tbody','tr','th','td','span','div','small','video','audio'}
 forbidden={'script','style','iframe','object','svg','math'}
 def __init__(self):super().__init__(convert_charrefs=True);self.output=[];self.text=[];self.blocked=[]
 def handle_starttag(self,tag,attrs):
  if self.blocked:
   if tag in self.forbidden:self.blocked.append(tag)
   return
  if tag in self.forbidden:self.blocked.append(tag);return
  if tag not in self.allowed:return
  attributes=dict(attrs);safe={}
  if tag=='pre':
   for key in ('data-code-id','data-code-language'):
    if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',attributes.get(key,'')):safe[key]=attributes[key]
  if tag=='code':
   language=attributes.get('data-language') or next((part[9:] for part in attributes.get('class','').split() if part.startswith('language-')),'')
   if re.fullmatch(r'[a-zA-Z0-9_+-]{1,32}',language):safe['data-language']=language
  if tag=='ul' and attributes.get('data-type')=='todo_list':safe['data-type']='todo_list'
  if tag=='li' and attributes.get('data-type')=='todo_item':safe.update({'data-type':'todo_item','data-done':'true' if attributes.get('data-done')=='true' else 'false'})
  if tag=='div':
   if attributes.get('data-diagram')=='true':
    safe['data-diagram']='true'
    if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',attributes.get('data-diagram-id','')):safe['data-diagram-id']=attributes['data-diagram-id']
   classes=[x for x in attributes.get('class','').split() if x in {'todo-content','callout-content','collapsible-section','collapsible-heading','collapsible-content'}]
   if classes:safe['class']=' '.join(classes)
   if 'collapsible-section' in classes:safe['data-open']='false' if attributes.get('data-open')=='false' else 'true'
   if attributes.get('data-callout')=='true':
    color=attributes.get('data-color') or '#26b5ce'
    safe.update({'data-callout':'true','data-icon':(attributes.get('data-icon') or 'LightBulb')[:128],'data-color':color if re.fullmatch(r'(?:#[0-9a-fA-F]{6}|lch\([\d.]+% [\d.]+ [\d.]+\))',color) else '#26b5ce'})
  if tag=='a':
   href=attributes.get('href') or ''
   if href.startswith('/') and not href.startswith('//') and '\\' not in href and not any(ord(c)<32 for c in href):safe['href']=href
   else:
    try:
     parsed=urlsplit(href)
     if parsed.scheme in ('http','https','mailto') and (parsed.hostname or parsed.scheme=='mailto'):safe['href']='/external?target='+base64.urlsafe_b64encode(href.encode()).decode().rstrip('=')
    except ValueError:pass
  if tag in ('img','audio','video'):
   src=attributes.get('src','')
   if not (re.fullmatch(r'/api/uploads/upload_[a-f0-9]{32}',src) or tag=='img' and src.startswith('/static/assets/') and '..' not in src and '\\' not in src):return
   safe={'src':src}
   if tag=='img':
    safe['alt']=attributes.get('alt','')
    if re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',attributes.get('data-image-id','')):safe['data-image-id']=attributes['data-image-id']
    for key in ('width','height','data-display-width'):
     raw=attributes.get(key,'')
     if re.fullmatch(r'\d+(?:\.\d+)?',raw) and 0<float(raw)<=10000000:safe[key]=raw
   else:safe['controls']='';safe['preload']='metadata'
  if tag=='a' and attributes.get('data-attachment')=='true' and re.fullmatch(r'/api/uploads/upload_[a-f0-9]{32}\?download=1',safe.get('href','')):
   safe['data-attachment']='true'
   for key in ('data-file-name','data-file-size','data-file-mime'):
    if key in attributes:safe[key]=attributes[key][:255]

  if tag in ('td','th'):
   for key in ('colspan','rowspan'):
    if attributes.get(key,'').isdigit() and 1<=int(attributes[key])<=100:safe[key]=attributes[key]
  self.output.append('<'+tag+''.join(' '+key+'="'+html.escape(value,quote=True)+'"' for key,value in safe.items())+'>')
  if tag in ('br','hr'):self.text.append('\n')
 def handle_endtag(self,tag):
  if self.blocked:
   if self.blocked[-1]==tag:self.blocked.pop()
   return
  if tag in self.allowed and tag not in ('img','br','hr'):self.output.append('</'+tag+'>')
  if tag in ('p','div','li','h1','h2','h3','h4','blockquote','pre','tr'):self.text.append('\n')
 def handle_data(self,data):
  if not self.blocked:self.output.append(html.escape(data));self.text.append(data)

def clean_content(value):
 parser=DocumentHTML();parser.feed(value);parser.close();return ''.join(parser.output),''.join(parser.text).strip()

def prepare_document(c,wid,value,previous,provided,now):
 def invalid(message):raise HTTPException(422,message)
 owner=c.execute('SELECT a.email_normalized,a.display_name FROM linear_workspaces w JOIN local_auth_accounts a ON a.account_id=w.owner_id WHERE w.id=?',(wid,)).fetchone()
 for key in ('title','description','content_html'):
  if key in value and not isinstance(value[key],str):invalid('Invalid document '+key+'.')
 value['title']=value.get('title','').strip() or 'New document'
 if value.get('owner',owner['email_normalized'])!=owner['email_normalized']:invalid('Select a document owner from this workspace.')
 value['owner']=owner['email_normalized']
 parent=value.get('parent')
 if parent is not None:
  if not isinstance(parent,dict) or parent.get('kind') not in ('issues','projects','teams') or not isinstance(parent.get('id'),str):invalid('Select a document location from this workspace.')
  if not (parent['kind']=='teams' and parent['id']=='QQQ') and not c.execute('SELECT 1 FROM linear_records WHERE workspace_id=? AND kind=? AND id=?',(wid,parent['kind'],parent['id'])).fetchone():invalid('Select a document location from this workspace.')
  value['parent']={key:parent[key] for key in ('kind','id')}
 teams={'QQQ',*(r['id'] for r in c.execute("SELECT id FROM linear_records WHERE workspace_id=? AND kind='teams'",(wid,)))}
 pins=value.get('pinned_teams',[])
 if not isinstance(pins,list) or any(not isinstance(x,str) or x not in teams for x in pins):invalid('Select a team from this workspace.')
 value['pinned_teams']=list(dict.fromkeys(pins))
 subscribers=value.get('subscribers',[owner['email_normalized']])
 if not isinstance(subscribers,list) or any(x not in (owner['email_normalized'],'linear','agent') for x in subscribers):invalid('Select document subscribers from this workspace.')
 value['subscribers']=list(dict.fromkeys(subscribers))
 if 'remind_at' in provided and provided['remind_at'] is not None:
  reminder=provided['remind_at']
  if type(reminder) is not int or reminder<=now or reminder>253402300799:invalid('Choose a future reminder date and time.')
 value.setdefault('remind_at',None)
 if 'icon' in value and (not isinstance(value['icon'],str) or len(value['icon'])>128):invalid('Choose a document icon.')
 for key in ('favorite','show_authors'):
  if key in value and not isinstance(value[key],bool):invalid('Invalid document preference.')
  value.setdefault(key,False)
 if 'content_html' in provided:content=provided['content_html']
 elif 'description' in provided:content='<p>'+html.escape(provided['description']).replace('\n','<br>')+'</p>'
 else:content=value.get('content_html','')
 value['content_html'],value['description']=clean_content(content)
 from uploads import validate_upload_references
 validate_upload_references(c,wid,value['content_html'])
 value['comments']=list((previous or {}).get('comments',[]))
 history=list((previous or {}).get('history',[]))
 if previous and any(previous.get(key,'')!=value.get(key,'') for key in ('title','content_html')):
  row=c.execute("SELECT created_at,updated_at FROM linear_records WHERE workspace_id=? AND kind='documents' AND id=?",(wid,value['id'])).fetchone()
  history.append({'title':previous.get('title','New document'),'content_html':previous.get('content_html',''),'description':previous.get('description',''),'at':previous.get('content_updated_at',row['created_at']),'author':previous.get('last_editor',owner['display_name'])})
 value['history']=history
 changed=previous is None or any(previous.get(key,'')!=value.get(key,'') for key in ('title','content_html'))
 value['content_updated_at']=now if changed else previous.get('content_updated_at',now)
 value['last_editor']=owner['display_name'] if changed else previous.get('last_editor',owner['display_name'])

def detach_documents(store,c,wid,kind,id,now):
 if kind=='documents':
  for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='notifications'",(wid,)).fetchall():
   if json.loads(row['document']).get('document_id')==id:c.execute("DELETE FROM linear_records WHERE workspace_id=? AND kind='notifications' AND id=?",(wid,row['id']))
  return
 if kind not in ('issues','projects','teams'):return
 for row in c.execute("SELECT id,document FROM linear_records WHERE workspace_id=? AND kind='documents'",(wid,)).fetchall():
  previous=json.loads(row['document']);value={**previous};changed=False
  if value.get('parent')=={'kind':kind,'id':id}:value['parent']=None;changed=True
  if kind=='teams' and id in value.get('pinned_teams',[]):value['pinned_teams']=[x for x in value['pinned_teams'] if x!=id];changed=True
  if changed:
   c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='documents' AND id=?",(json.dumps(value),now,wid,row['id']))
   store.collect_record_event(c,wid,'documents','update',value,previous)


def deliver_document_reminders(store,wid):
 now=int(time.time())
 with store.auth.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  for row in c.execute("SELECT id,kind,document FROM linear_records WHERE workspace_id=? AND kind IN ('documents','issues')",(wid,)).fetchall():
   value=json.loads(row['document']);due=value.get('remind_at')
   if type(due)is not int or due>now:continue
   id='reminder_'+secrets.token_hex(12);field='document_id'if row['kind']=='documents'else'issue_id'
   notification={'id':id,'title':value['title'],'description':value.get('description',''),'read':False,field:row['id'],'type':'reminder','reminded_at':due}
   c.execute('INSERT INTO linear_records VALUES(?,?,?,?,1,?,?)',(wid,'notifications',id,json.dumps(notification),now,now))
   value['remind_at']=None
   c.execute("UPDATE linear_records SET document=?,revision=revision+1 WHERE workspace_id=? AND kind=? AND id=?",(json.dumps(value),wid,row['kind'],row['id']))
  c.commit()


class DiagramSources(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.depth=0;self.active=None;self.code=0;self.parts=[];self.sources={}
 def handle_starttag(self,tag,attrs):
  if tag=='div':
   self.depth+=1;attrs=dict(attrs)
   if self.active is None and attrs.get('data-diagram')=='true' and attrs.get('data-diagram-id'):
    self.active=(attrs['data-diagram-id'],self.depth);self.parts=[]
  if tag=='code' and self.active:self.code+=1
  if tag=='br' and self.active and self.code:self.parts.append('\n')
 def handle_data(self,value):
  if self.active and self.code:self.parts.append(value)
 def handle_endtag(self,tag):
  if tag=='code' and self.code:self.code-=1
  if tag=='div':
   if self.active and self.active[1]==self.depth:
    identity=self.active[0];self.sources[identity]=None if identity in self.sources else ''.join(self.parts);self.active=None;self.code=0
   self.depth-=1


class ImageSources(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.sources={}
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs);identity=attrs.get('data-image-id')
  if tag=='img' and identity:
   self.sources[identity]=None if identity in self.sources else {'quote':attrs.get('alt') or 'Image','image_src':attrs.get('src','')}


def change_document_comment(store,wid,document_id,account,data,comment_id=None):
 if not isinstance(data,dict):raise HTTPException(422,'Enter a comment object.')
 now=int(time.time())
 with store.auth.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute("SELECT document FROM linear_records WHERE workspace_id=? AND kind='documents' AND id=?",(wid,document_id)).fetchone()
  if not row:raise HTTPException(404,'Document not found.')
  previous=json.loads(row['document']);value={**previous};comments=[dict(item) for item in previous.get('comments',[])]
  if comment_id is None:
   body=data.get('body');quote=data.get('quote','');parent=data.get('parent');diagram_id=data.get('diagram_id');image_id=data.get('image_id');image_src=None
   if not isinstance(body,str) or not body.strip():raise HTTPException(422,'Enter a comment.')
   if not isinstance(quote,str):raise HTTPException(422,'Select text in this document.')
   quote=quote.strip()
   if parent:
    target=next((item for item in comments if item['id']==parent and not item.get('parent')),None)
    if not target:raise HTTPException(422,'Comment thread not found.')
    quote=target['quote'];diagram_id=target.get('diagram_id');image_id=target.get('image_id');image_src=target.get('image_src')
   elif image_id is not None:
    if diagram_id is not None or not isinstance(image_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',image_id):raise HTTPException(422,'Select an image in this document.')
    images=ImageSources();images.feed(value.get('content_html',''));images.close();image=images.sources.get(image_id)
    if image is None:raise HTTPException(422,'Select an image in this document.')
    quote=image['quote'];image_src=image['image_src']
   elif diagram_id is not None:
    if not isinstance(diagram_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',diagram_id):raise HTTPException(422,'Select a diagram in this document.')
    diagrams=DiagramSources();diagrams.feed(value.get('content_html',''));diagrams.close();quote=diagrams.sources.get(diagram_id)
    if not quote or not quote.strip():raise HTTPException(422,'Select a diagram with source code in this document.')
    quote=quote.strip()
   elif not quote or quote not in value.get('description',''):raise HTTPException(422,'Select text in this document.')
   item={'id':'comment_'+secrets.token_hex(12),'body':body.strip(),'quote':quote,'parent':parent,'author':account['display_name'],'account_id':account['account_id'],'created_at':now,'updated_at':now,'resolved':False}
   if diagram_id is not None:item['diagram_id']=diagram_id
   if image_id is not None:item.update({'image_id':image_id,'image_src':image_src})
   comments.append(item)
  else:
   item=next((x for x in comments if x['id']==comment_id),None)
   if not item:raise HTTPException(404,'Comment not found.')
   if 'resolved' in data:
    if type(data['resolved']) is not bool or item.get('parent'):raise HTTPException(422,'Select a comment thread.')
    item['resolved']=data['resolved']
   if 'body' in data:
    if item['account_id']!=account['account_id']:raise HTTPException(403,'Only the author can edit this comment.')
    if not isinstance(data['body'],str) or not data['body'].strip():raise HTTPException(422,'Enter a comment.')
    item['body']=data['body'].strip()
   item['updated_at']=now
  value['comments']=comments
  c.execute("UPDATE linear_records SET document=?,revision=revision+1,updated_at=? WHERE workspace_id=? AND kind='documents' AND id=?",(json.dumps(value),now,wid,document_id))
  store.collect_event(c,wid,'Comment','create' if comment_id is None else 'update',{**item,'documentId':document_id})
  c.commit()
 return store.get(wid,'documents',document_id)
