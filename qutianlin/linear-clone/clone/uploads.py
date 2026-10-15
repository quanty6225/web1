"""Authenticated workspace uploads stored in the site's existing SQLite database."""
import hashlib,html,re,secrets,time,xml.etree.ElementTree as ET
from urllib.parse import quote
from fastapi import HTTPException
from fastapi.responses import Response

MAX_UPLOAD_BYTES=10*1024*1024  # Observed free workspace limit; source file.MB is 1048576.
MAX_IMPORT_BYTES=1024*1024
UPLOAD_PATH=re.compile(r'^/api/uploads/(upload_[a-f0-9]{32})(?:\?download=1)?$')

def safe_svg(data):
 if re.search(br'<!\s*(?:DOCTYPE|ENTITY)',data,re.I):raise HTTPException(422,'This SVG file cannot be displayed safely.')
 try:root=ET.fromstring(data)
 except ET.ParseError:raise HTTPException(422,'This image could not be read.')
 if root.tag.split('}')[-1]!='svg':raise HTTPException(422,'This image could not be read.')
 for node in root.iter():
  for child in list(node):
   if child.tag.split('}')[-1] in {'script','foreignObject','iframe','object','embed'}:node.remove(child)
  for key,value in list(node.attrib.items()):
   short=key.split('}')[-1].lower()
   if short.startswith('on') or short in {'href','src'} and not (value.startswith('#') or re.match(r'data:image/(?:png|jpeg|gif|webp);base64,',value,re.I)):del node.attrib[key]
   elif short=='style' and ('@import' in value.lower() or re.search(r'url\s*\(\s*(?![\x22\x27]?#)',value,re.I)):del node.attrib[key]
  if node.tag.split('}')[-1]=='style' and ('@import' in (node.text or '').lower() or re.search(r'url\s*\(\s*(?![\x22\x27]?#)',node.text or '',re.I)):node.text=''
 return ET.tostring(root,encoding='utf-8')

def media_type(data,declared):
 if data.startswith(b'%PDF-'):return 'application/pdf'
 if data.lstrip().startswith((b'<svg',b'<?xml')) and b'<svg' in data[:4096]:safe_svg(data);return 'image/svg+xml'
 from PIL import Image
 from io import BytesIO
 try:
  with Image.open(BytesIO(data)) as image:
   kind=Image.MIME.get(image.format,'application/octet-stream');image.verify()
   if kind in {'image/png','image/jpeg','image/gif','image/webp','image/avif','image/bmp'}:return kind
 except (OSError,ValueError,Image.DecompressionBombError):pass
 if data.startswith(b'RIFF') and data[8:12]==b'WAVE':return 'audio/wav'
 if data.startswith(b'OggS'):return 'video/ogg' if declared=='video/ogg' else 'audio/ogg'
 if data.startswith(b'fLaC'):return 'audio/flac'
 if data.startswith(b'ID3') or len(data)>1 and data[0]==255 and data[1]&224==224:return 'audio/mpeg'
 if data[4:8]==b'ftyp':return 'audio/mp4' if declared=='audio/mp4' else 'video/mp4'
 if data.startswith(b'\x1aE\xdf\xa3'):return 'audio/webm' if declared=='audio/webm' else 'video/webm'
 return 'application/octet-stream'

def metadata(row):
 return {key:row[key] for key in ['id','filename','mime','size','sha256','created_at','render_type']}|{'url':'/api/uploads/'+row['id'],'download_url':'/api/uploads/'+row['id']+'?download=1'}

async def save_upload(request,store,wid):
 name=request.query_params.get('name','').replace('\\','/').split('/')[-1]
 name=''.join(character for character in name if ord(character)>=32 and ord(character)!=127).strip()[:255]
 if not name:raise HTTPException(422,'Choose a file to upload.')
 chunks=[];size=0
 async for chunk in request.stream():
  size+=len(chunk)
  if size>MAX_UPLOAD_BYTES:raise HTTPException(413,'File uploads for free workspaces are limited to 10MB')
  chunks.append(chunk)
 data=b''.join(chunks);mime=media_type(data,request.headers.get('content-type','').split(';',1)[0]);mode=request.query_params.get('mode','attachment')
 if mode not in {'attachment','media'}:raise HTTPException(422,'Choose a file upload type.')
 if mode=='media' and not mime.startswith(('image/','audio/','video/')):raise HTTPException(422,'This file could not be read as an image, video or audio file.')
 record={'id':'upload_'+secrets.token_hex(16),'filename':name,'mime':mime,'size':size,'sha256':hashlib.sha256(data).hexdigest(),'created_at':int(time.time()),'render_type':mime.split('/')[0] if mode=='media' else 'attachment'}
 with store.auth.connect() as connection:
  connection.execute('INSERT INTO linear_uploads VALUES(?,?,?,?,?,?,?,?,?)',(record['id'],wid,name,mime,size,record['sha256'],record['created_at'],record['render_type'],data));connection.commit()
 return metadata(record)

def read_upload(request,store,wid,id):
 with store.auth.connect() as connection:row=connection.execute('SELECT * FROM linear_uploads WHERE id=? AND workspace_id=?',(id,wid)).fetchone()
 if not row:raise HTTPException(404,'File not found.')
 content=row['content'];download=request.query_params.get('download')=='1' or row['mime']=='application/octet-stream'
 if row['mime']=='image/svg+xml' and not download:content=safe_svg(content)
 size=len(content)
 headers={'Content-Disposition':('attachment' if download else 'inline')+"; filename*=UTF-8''"+quote(row['filename'],safe=''),'Accept-Ranges':'bytes','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; sandbox",'Cache-Control':'private, no-store'}
 status=200;start=0;end=size-1
 if request.headers.get('range'):
  match=re.fullmatch(r'bytes=(\d*)-(\d*)',request.headers['range'])
  if not match or len(request.headers['range'])>128 or not any(match.groups()):return Response(status_code=416,headers={**headers,'Content-Range':f'bytes */{size}'})
  if match[1]:start=int(match[1]);end=min(int(match[2]) if match[2] else size-1,size-1)
  else:start=max(0,size-int(match[2]))
  if start>end or start>=size:return Response(status_code=416,headers={**headers,'Content-Range':f'bytes */{size}'})
  status=206;headers['Content-Range']=f'bytes {start}-{end}/{size}'
 body=content[start:end+1];headers['Content-Length']=str(len(body))
 return Response(b'' if request.method=='HEAD' else body,status_code=status,media_type=row['mime'],headers=headers)

def validate_upload_references(connection,wid,content):
 from html.parser import HTMLParser
 class References(HTMLParser):
  def handle_starttag(self,tag,attrs):
   for key,value in attrs:
    if key not in ('href','src') or not value or not value.startswith('/api/uploads/'):continue
    match=UPLOAD_PATH.fullmatch(value)
    if not match:raise HTTPException(422,'Invalid file reference.')
    row=connection.execute('SELECT mime FROM linear_uploads WHERE id=? AND workspace_id=?',(match[1],wid)).fetchone()
    if not row:raise HTTPException(422,'Select a file from this workspace.')
    if key=='src' and tag in ('img','audio','video') and not row['mime'].startswith({'img':'image/','audio':'audio/','video':'video/'}[tag]):raise HTTPException(422,'The file does not match this media type.')
 References().feed(content)

def import_text_file(data):
 from markdown_it import MarkdownIt
 from documents import clean_content
 if not isinstance(data,dict) or not isinstance(data.get('text'),str) or not isinstance(data.get('filename'),str):raise HTTPException(422,'Choose a text or Markdown file.')
 if not re.search(r'\.(?:md|txt)$',data['filename'],re.I):raise HTTPException(422,'Choose a text or Markdown file.')
 if len(data['text'].encode())>MAX_IMPORT_BYTES:raise HTTPException(413,'Files larger than 1 MB can’t be imported. Attach the file instead.')
 rendered=MarkdownIt('commonmark',{'html':False,'xhtmlOut':True}).enable(['table','strikethrough']).render(data['text']);root=ET.fromstring('<root>'+rendered+'</root>')
 for container in root.iter('ul'):
  task=False
  for item in container.findall('li'):
   first=item.find('p');first=item if first is None else first;match=re.match(r'^\[([ xX])\]\s+',first.text or '')
   if not match:continue
   first.text=first.text[match.end():];item.set('data-type','todo_item');item.set('data-done','false' if match[1]==' ' else 'true');wrapper=ET.Element('div',{'class':'todo-content'});wrapper.text=item.text;item.text=None
   for child in list(item):item.remove(child);wrapper.append(child)
   item.append(wrapper);task=True
  if task:container.set('data-type','todo_list')
 def serialized():return ''.join(ET.tostring(child,encoding='unicode',method='html') for child in root)
 full=clean_content(serialized())[0];title=None
 if len(root) and root[0].tag=='h1' and ''.join(root[0].itertext()).strip():title=''.join(root[0].itertext()).strip();root.remove(root[0])
 body=clean_content(serialized())[0]
 return {'title':title,'content_html':body,'full_content_html':full}
