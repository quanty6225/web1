"""Local public forms and search over the captured help collection."""
import hashlib,json,re,secrets,smtplib,time
from functools import lru_cache
from pathlib import Path
from lxml import html,etree
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import RedirectResponse
import help_widget
ROOT=Path(__file__).parent

@lru_cache(maxsize=1)
def help_index():
 routes=json.loads((ROOT/'frontend/routes.json').read_text());items={}
 for route,info in routes.items():
  if not re.match(r'^/help/(2|5|classic)/',route):continue
  tree=html.fromstring((ROOT/'frontend/pages'/info['file']).read_text())
  for link in tree.xpath('//a[contains(@href,"/article/")]'):
   url=link.get('href','').split('?')[0];title=' '.join(link.text_content().split())
   if title and re.match(r'^/help/(2|5|classic)/article/',url):items.setdefault(url,{'url':url,'title':title,'text':title})
  if '/article/' in route and not info.get('boundary'):
   article=tree.xpath('//*[@id="fullArticle"]')
   if article:
    headings=article[0].xpath('.//h1');title=' '.join((headings[0].text_content() if headings else info['title']).split())
    items[route]={'url':route,'title':title,'text':' '.join(article[0].text_content().split())}
 return list(items.values())

def render(markup,path,query,account=None,connection=None):
 markup=help_widget.render(markup,path)
 if path!='/support' and not re.fullmatch(r'/help/(2|5|classic)/search',path) and path not in ['/settings/edit','/launchpad/']:return markup
 tree=html.document_fromstring(markup)
 if path=='/support':
  for form in tree.xpath('//form[.//*[@name="ticket[details]"]]'):form.set('action','/api/support');form.set('enctype','multipart/form-data')
  if query.get('sent')=='1':
   forms=tree.xpath('//form[.//*[@name="ticket[details]"]]')
   if forms:
    message=etree.Element('p',{'role':'status'});message.text='Your support request has been saved locally and a confirmation email has been sent.';forms[0].addprevious(message)
 elif path.startswith('/help/'):
  term=query.get('query','').strip()[:200]
  for field in tree.xpath('//*[@name="query"]'):field.set('value',term)
  for heading in tree.xpath('//*[@id="serp"]//h1/strong'):heading.text=term
  matches=[item for item in help_index() if item['url'].startswith(path.rsplit('/',1)[0]+'/') and all(word in item['text'].casefold() for word in term.casefold().split())] if term else []
  target=tree.xpath('//*[@id="serp"]')
  if target and matches:
   for empty in target[0].xpath('.//*[@class="nada"]'):empty.getparent().remove(empty)
   listing=etree.SubElement(target[0],'ul',{'class':'articleList','data-local-search-results':'true'})
   for item in sorted(matches,key=lambda item:(term.casefold() not in item['title'].casefold(),item['title'].casefold())):
    row=etree.SubElement(listing,'li');etree.SubElement(row,'a',{'href':item['url']}).text=item['title']
 elif account and connection:
  row=connection.execute('SELECT value FROM bc_settings WHERE owner=? AND name="launchpad"',(account['account_id'],)).fetchone();settings=json.loads(row['value']) if row else {}
  for field in tree.xpath('//input[@name="alias"]'):field.set('value',settings.get('alias',''))
  for field in tree.xpath('//input[@name="visible" and @type="checkbox"]'):
   field.attrib.pop('checked',None)
   if settings.get('visible',True):field.set('checked','checked')
 return html.tostring(tree,encoding='unicode',method='html',doctype='<!DOCTYPE html>')

def install(app,db,csrf_check,send_mail,require_user):
 help_widget.install(app,db,csrf_check,send_mail)
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS bc_support(id TEXT PRIMARY KEY,email TEXT,issue TEXT,details TEXT,attachments TEXT,created INTEGER)')
 router=APIRouter()
 @router.post('/api/support')
 async def support(request:Request):
  data=await request.form();csrf_check(request,data)
  email=str(data.get('ticket[email_address]','')).strip();issue=str(data.get('ticket[issue_type]','')).strip();details=str(data.get('ticket[details]','')).strip()
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not issue or not details:raise HTTPException(422,'Select a topic and enter your question and a valid email address.')
  if len(details)>50000:raise HTTPException(422,'Please keep your request below 50,000 characters.')
  attachments=[];total=0
  for upload in data.getlist('ticket[files][]'):
   if not getattr(upload,'filename',''):continue
   content=await upload.read(10*1024*1024+1);total+=len(content)
   if total>10*1024*1024:raise HTTPException(413,'Attachments must total no more than 10 MB.')
   attachments.append({'name':Path(upload.filename).name,'type':upload.content_type,'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),'content':content.hex()})
  identifier=secrets.token_hex(12)
  try:send_mail(email,'Your local Basecamp support request',f'Your request {identifier} has been received by the local Basecamp copy.\n\nTopic: {issue}\n\n{details}\n\nThis is a local confirmation. It has not been sent to the Basecamp support team.')
  except (OSError,smtplib.SMTPException):raise HTTPException(503,'We couldn’t send your confirmation email. Please try again.')
  with db() as c:c.execute('INSERT INTO bc_support VALUES(?,?,?,?,?,?)',(identifier,email,issue,details,json.dumps(attachments),int(time.time())))
  return RedirectResponse('/support?sent=1',303)
 @router.api_route('/users/{identifier}/settings',methods=['POST','PATCH'])
 async def shortcuts(identifier:str,request:Request):
  account=require_user(request);data=await request.form();csrf_check(request,data)
  with db() as c:
   row=c.execute('SELECT value FROM bc_settings WHERE owner=? AND name="launchpad"',(account['account_id'],)).fetchone();settings=json.loads(row['value']) if row else {}
   if 'alias' in data:settings['alias']=str(data['alias']).strip()[:120]
   if 'visible' in data:settings['visible']=data['visible']=='1'
   c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"launchpad",?)',(account['account_id'],json.dumps(settings)))
  return RedirectResponse('/settings/edit',303)
 app.include_router(router)
