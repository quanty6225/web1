"""Native file staging, publishing, versions, and owned download rendering."""
import json,re,secrets,time
from pathlib import Path
from urllib.parse import quote
from lxml import html,etree
from fastapi import HTTPException
from record_operations import DATA,metadata,fields_for
from local_render import safe_rich_text

def make_record(c,owner,bucket,parent,file):
 prototype=next(r for r in DATA['records'].values() if r['kind']=='uploads');identifier=str(900000000000+secrets.randbelow(99999999999));url=f'/6302022/buckets/{bucket}/uploads/{identifier}'
 fields={'upload[base_name]':Path(file['filename']).stem,'upload[description]':'','_file_id':file['id'],'_record_status':'draft'}
 data={'url':url,'kind':'uploads','bucket':bucket,'fields':fields,'prototype':prototype['id'],'created':time.time(),'is_new':True,'author':file['uploader']}
 c.execute('INSERT INTO bc_records VALUES(?,?,?,?,?,?,?,?)',(identifier,owner,parent,'uploads',file['filename'],'',json.dumps(data),int(time.time())))
 return identifier,url

def mutate(c,owner,path,payload,method):
 match=re.fullmatch(r'/6302022(?:/buckets/(\d+)(?:/vaults/(\d+))?)?/uploads(?:/stage)?',path)
 if match and payload.get('file'):
  file=c.execute('SELECT * FROM bc_files WHERE id=? AND owner=? AND uploaded=1',(str(payload['file']),owner)).fetchone()
  if not file:raise HTTPException(404,'Uploaded file not found')
  bucket=match[1] or '49234166';parent=f'/6302022/buckets/{bucket}/vaults/'+(match[2] or '10398823035')
  identifier,url=make_record(c,owner,bucket,parent,file)
  return {'json':{'id':identifier,'sgid':file['id'],'filename':file['filename'],'filesize':file['size'],'contentType':file['content_type'],'human_size':str(file['size'])+' bytes','visible_to_clients':False,'representable':file['content_type'].startswith('image/'),'representation_url':'/files/'+file['id']+'/'+quote(file['filename']),'trash_url':url}}
 match=re.fullmatch(r'/6302022/buckets/(\d+)/vaults/(\d+)/uploads/publish',path)
 if match:
  ids=payload.get('uploads[][id]',[]);ids=ids if isinstance(ids,list) else [ids]
  if not ids:raise HTTPException(422,'Choose at least one file to upload.')
  names=payload.get('uploads[][base_name]',[]);names=names if isinstance(names,list) else [names]
  descriptions=payload.get('uploads[][description]',[]);descriptions=descriptions if isinstance(descriptions,list) else [descriptions]
  for index,identifier in enumerate(ids):
   record=metadata(c,owner,str(identifier))
   if not record or not record.get('is_new') or record['kind']!='uploads' or record['bucket']!=match[1]:raise HTTPException(404,'Uploaded file not found')
   state=fields_for(c,owner,record);state['_record_status']='active'
   if index<len(names):state['upload[base_name]']=str(names[index]).strip() or record['title']
   if index<len(descriptions):state['upload[description]']=safe_rich_text(str(descriptions[index]))
   parent=path.removesuffix('/uploads/publish');c.execute('UPDATE bc_records SET parent=? WHERE id=? AND owner=?',(parent,identifier,owner));c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,record['url'],'record',json.dumps(state),int(time.time())))
  return {'redirect':path.removesuffix('/uploads/publish')}
 match=re.fullmatch(r'/6302022/buckets/(\d+)/uploads/(\d+)/versions',path)
 if match:
  record=metadata(c,owner,match[2]);ids=payload.get('uploads[][sgid]',payload.get('file',''));file_id=ids[0] if isinstance(ids,list) and ids else ids
  file=c.execute('SELECT * FROM bc_files WHERE id=? AND owner=? AND uploaded=1',(file_id,owner)).fetchone()
  if not record or record['url']!=path.removesuffix('/versions') or not file:raise HTTPException(404,'File not found')
  state=fields_for(c,owner,record);versions=state.get('_versions',[])
  if state.get('_file_id'):versions.append(state['_file_id'])
  state.update({'_file_id':file_id,'_versions':versions,'upload[base_name]':Path(file['filename']).stem});c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,record['url'],'record',json.dumps(state),int(time.time())))
  return {'redirect':record['url']}
 return None

def render(tree,path,owner,c):
 match=re.fullmatch(r'/6302022/buckets/\d+/uploads/(\d+)',path)
 if not match:return
 record=metadata(c,owner,match[1])
 if not record:return
 fields=fields_for(c,owner,record)
 if not fields.get('_file_id'):return
 file=c.execute('SELECT * FROM bc_files WHERE id=? AND owner=? AND uploaded=1',(fields['_file_id'],owner)).fetchone()
 if not file:return
 url='/files/'+file['id']+'/'+quote(file['filename']);articles=tree.xpath('//article[contains(@class,"recordable")]') or tree.xpath('//main')
 if not articles:return
 article=articles[0]
 for header in tree.xpath('//header[contains(@class,"perma-header")]//*[contains(@class,"perma-header__content")]'):
  for size in header.xpath('./span[contains(@class,"meta-dot") and not(.//img) and not(.//time)]'):
   size.text=str(file['size'])+' bytes'
   for child in list(size):size.remove(child)
 for link in article.xpath('.//a[@download or contains(@href,"/static/assets/")]'):link.set('href',url);link.set('download',file['filename'])
 for node in article.xpath('.//img[not(contains(@class,"avatar"))]|.//video|.//audio|.//iframe'):
  if node.tag=='img' and file['content_type'].startswith('image/'):node.set('src',url);node.attrib.pop('srcset',None);node.set('alt',file['filename'])
  elif node.getparent() is not None:node.getparent().remove(node)
 if not article.xpath('.//a[@href="'+url+'"]'):
  link=etree.SubElement(article,'a',{'href':url,'class':'btn btn--primary','download':file['filename']});link.text='Download '+file['filename']
 if fields.get('_versions'):
  versions=etree.SubElement(article,'section',{'class':'margin-block-24'});etree.SubElement(versions,'h3').text='Previous versions'
  for identifier in fields['_versions']:
   old=c.execute('SELECT filename FROM bc_files WHERE id=? AND owner=?',(identifier,owner)).fetchone()
   if old:etree.SubElement(versions,'a',{'href':'/files/'+identifier+'/'+quote(old['filename'])}).text=old['filename']
