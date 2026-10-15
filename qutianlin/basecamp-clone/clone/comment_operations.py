"""Comments tied to their recording, with authorship and native form actions."""
import json,re,secrets,time
from datetime import datetime,timezone
from lxml import html,etree
from fastapi import HTTPException
from local_render import safe_rich_text
from record_operations import metadata,fields_for

def initialize(db):
 with db() as c:
  if 'author' not in {row['name'] for row in c.execute('PRAGMA table_info(bc_comments)')}:c.execute('ALTER TABLE bc_comments ADD COLUMN author TEXT')
  c.execute('UPDATE bc_comments SET author=owner WHERE author IS NULL')
 from comment_replies import initialize as initialize_replies
 initialize_replies(db)
def content(value):
 body=safe_rich_text(str(value));tree=html.fragment_fromstring(body,create_parent='div')
 if not tree.text_content().strip() and not tree.xpath('.//img'):raise HTTPException(422,'Please write a comment.')
 return body

def mutate(c,account,path,payload,method):
 owner=account['workspace_id']
 closure=re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/comments_closure',path)
 if closure:
  record=metadata(c,owner,closure[2])
  if not record or record['bucket']!=closure[1]:raise HTTPException(404,'Record not found')
  if account['role'] not in ['owner','admin'] and record.get('author')!=account['account_id']:raise HTTPException(403,'Only the author or an administrator can close comments.')
  fields=fields_for(c,owner,record);fields['_comments_closed']=method!='DELETE';c.execute('INSERT OR REPLACE INTO bc_mutations VALUES(?,?,?,?,?)',(owner,record['url'],'record',json.dumps(fields),int(time.time())))
  return {'redirect':record['url']}
 match=re.fullmatch(r'/6302022/buckets/(\d+)/recordings/(\d+)/comments',path)
 if match:
  record=metadata(c,owner,match[2])
  if not record or record['bucket']!=match[1]:raise HTTPException(404,'The item to comment on was not found.')
  if fields_for(c,owner,record).get('_comments_closed'):raise HTTPException(409,'Comments are closed on this item.')
  body=content(payload.get('comment[content]',''));identifier='local-'+secrets.token_hex(8)
  from comment_replies import snapshot
  quote=snapshot(c,account,record,payload)
  c.execute('INSERT INTO bc_comments(id,owner,route,body,created,author,reply) VALUES(?,?,?,?,?,?,?)',(identifier,owner,record['url'],body,int(time.time()),account['account_id'],json.dumps(quote) if quote else None))
  from thread_notifications import comment_posted
  comment_posted(c,account,record,identifier,quote['author'] if quote else None)
  return {'redirect':record['url']+'#comment-'+identifier,'id':identifier}
 match=re.fullmatch(r'/6302022/buckets/(\d+)/comments/(local-[a-f0-9]+)',path)
 if not match:return None
 row=c.execute('SELECT * FROM bc_comments WHERE id=? AND owner=?',(match[2],owner)).fetchone()
 if not row or '/buckets/'+match[1]+'/' not in row['route']:raise HTTPException(404,'Comment not found')
 if row['author']!=account['account_id']:raise HTTPException(403,'You can only change your own comments.')
 if method=='DELETE':c.execute('DELETE FROM bc_comments WHERE id=?',(row['id'],))
 else:c.execute('UPDATE bc_comments SET body=? WHERE id=?',(content(payload.get('comment[content]','')),row['id']))
 return {'redirect':row['route'],'id':row['id']}

def render(tree,path,owner,c,account):
 record=metadata(c,owner,path.rsplit('/',1)[-1])
 if record and record['url']==path and account and account['role'] not in ['owner','admin'] and record.get('author')!=account['account_id']:
  for link in tree.xpath('//a[contains(@href,"/comments_closure")]'):
   link.getparent().remove(link)
 if record and record['url']==path and fields_for(c,owner,record).get('_comments_closed'):
  for link in tree.xpath('//a[contains(@href,"/boosts/new")]'):
   link.getparent().remove(link)
  for link in tree.xpath('//a[contains(@href,"/comments_closure")]'):
   link.set('data-turbo-method','delete');link.set('data-method','delete')
   for node in link.iter():
    if node.text and 'Close comments' in node.text:node.text=node.text.replace('Close comments','Reopen comments')
  for form in tree.xpath('//form[contains(@action,"/comments") and not(contains(@action,"/comments/local-"))]'):
   note=etree.Element('p',{'class':'text-subtle','role':'status'});note.text='Comments are closed on this item.';form.getparent().replace(form,note)
 rows=c.execute('SELECT m.*,a.display_name FROM bc_comments m LEFT JOIN local_auth_accounts a ON a.account_id=m.author WHERE m.owner=? AND m.route=? ORDER BY m.created,m.id',(owner,path)).fetchall()
 targets=tree.xpath('//*[@id="thread_entries"]') or tree.xpath('//main')
 if not targets:return
 for row in rows:
  # Use the native thread layout. The old plain-text fallback class overrides
  # its avatar gutter and preserves template whitespace inside reply quotes.
  node=etree.Element('article',{'class':'thread-entry recording','data-local-comment':row['id'],'id':'comment-'+row['id']})
  from record_attribution import avatar_url
  header=etree.SubElement(node,'header',{'class':'thread-entry__header'});etree.SubElement(header,'img',{'class':'avatar thread-entry__avatar','src':avatar_url(row['author'],path.rsplit('/',1)[-1]),'alt':row['display_name'] or 'Member'})
  title=etree.SubElement(header,'h3',{'class':'thread-entry__title'});etree.SubElement(title,'strong',{'class':'thread-entry__author'}).text=row['display_name'] or 'Member'
  timestamp=datetime.fromtimestamp(row['created'],timezone.utc);etree.SubElement(title,'time',{'class':'thread-entry__time','datetime':timestamp.isoformat()}).text=' '+timestamp.strftime('%b %d, %H:%M UTC')
  from comment_replies import bubble,append_button
  if row['reply']:node.append(bubble(json.loads(row['reply'])))
  body=etree.SubElement(node,'div',{'class':'formatted_content'});fragment=html.fragment_fromstring(safe_rich_text(row['body']),create_parent='div');body.text=fragment.text
  for child in fragment:body.append(child)
  if record and not fields_for(c,owner,record).get('_comments_closed'):append_button(node,record,row['id'])
  if account and row['author']==account['account_id']:
   action='/6302022/buckets/'+path.split('/')[3]+'/comments/'+row['id'];details=etree.SubElement(node,'details',{'class':'margin-top-8'});etree.SubElement(details,'summary',{'class':'decorated'}).text='Edit'
   edit=etree.SubElement(details,'form',{'action':action,'method':'post'});etree.SubElement(edit,'input',{'type':'hidden','name':'_method','value':'patch'});field=etree.SubElement(edit,'textarea',{'name':'comment[content]','required':'required','class':'input input--full-width','aria-label':'Edit comment'});field.text=row['body'];etree.SubElement(edit,'button',{'class':'btn btn--primary','type':'submit'}).text='Save changes'
   remove=etree.SubElement(details,'form',{'action':action,'method':'post'});etree.SubElement(remove,'input',{'type':'hidden','name':'_method','value':'delete'});etree.SubElement(remove,'button',{'type':'submit','class':'btn btn--negative'}).text='Delete comment'
  targets[0].append(node)
 for node in tree.xpath('//*[@data-source-comment-total]'):
  source_total=int(node.get('data-source-comment-total','0'));total=source_total+len(rows)
  node.set('data-local-comment-total',str(total))
  for label in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," local-comment-total ")]'):label.text=str(total)+(' comment' if total==1 else ' comments')
  for boundary in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," local-comment-boundary ")]'):
   if not source_total:boundary.getparent().remove(boundary)
   elif rows:boundary.text=str(source_total)+' original comments · Showing the first 5 original comments in this local copy.'
