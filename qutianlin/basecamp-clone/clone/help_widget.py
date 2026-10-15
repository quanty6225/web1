"""Local rendering and persistence for the captured help contact widgets."""
import hashlib,json,re,secrets,smtplib,time
from functools import lru_cache
from pathlib import Path
from html import escape
from lxml import html,etree
from fastapi import APIRouter,Request,HTTPException
ROOT=Path(__file__).parent

@lru_cache(maxsize=1)
def settings():
 return json.loads((ROOT/'frontend/help-widget.json').read_text())

@lru_cache(maxsize=1)
def answer_evidence():
 return json.loads((ROOT/'frontend/help-answers.json').read_text())

def article_route(path):
 if not re.fullmatch(r'/help/2/article/[a-z0-9-]+',path):raise HTTPException(404,'Article not found.')
 routes=json.loads((ROOT/'frontend/routes.json').read_text())
 if path not in routes or routes[path].get('boundary'):raise HTTPException(404,'Article not found.')
 return path

def render(markup,path):
 match=re.match(r'^/help/(2|5|classic)(?:/|$)',path)
 if not match:return markup
 version=match[1];tree=html.document_fromstring(markup)
 for node in tree.xpath('//*[@id="beacon-container" or @id="beaconLoader"]'):node.getparent().remove(node)
 head=tree.find('head');etree.SubElement(head,'script',{'src':'/static/help.js','defer':'defer'})
 if version=='classic':return html.tostring(tree,encoding='unicode',doctype='<!DOCTYPE html>')
 config=settings()[version];labels=config['labels'];e=escape
 etree.SubElement(head,'link',{'rel':'stylesheet','href':'/static/help.css'})
 tabs='<nav role="tablist" aria-label="Help"><button type="button" role="tab" aria-selected="true" aria-controls="help-ask" id="help-ask-tab">Ask</button><button type="button" role="tab" aria-selected="false" aria-controls="help-answers" id="help-answers-tab">Answers</button></nav>' if version=='2' else ''
 title='Our support team is here to help!' if version=='2' else 'Send a message'
 description='We usually respond in a few hours' if version=='2' else "Friendly folks - standing by.<br>We'll reply back as soon as we can."
 avatars=''.join(f'<img src="{e(src)}" alt="" width="48" height="48">' for src in config['avatars'])
 fields=''.join(f'<label>{e(labels[key])}<input name="{name}" type="{kind}" maxlength="{limit}" required autocomplete="{name}"></label>' for name,kind,limit,key in [('name','text',40,'nameLabel'),('email','email',255,'emailLabel')])
 emojis=''.join(f'<button type="button" data-emoji="{emoji}">{emoji}</button>' for emoji in ['🦄','❤️','🙂','🙁','👍','👎'])
 widget=f'''<div id="local-help" data-version="{version}" style="--help-color:{e(config['color'])}">
 <section id="help-panel" aria-label="Contact support" hidden>{tabs}
 <div id="help-ask"{' role="tabpanel" aria-labelledby="help-ask-tab"' if version=='2' else ''}>
 <header><div class="help-avatars">{avatars}</div><h2>{title}</h2><p>{description}</p></header>
 <form id="help-contact-form" aria-label="Contact form" novalidate>{fields}
 <label>{e(labels['messageLabel'])}<textarea name="message" title="{e(labels['messageLabel'])}" maxlength="524288" required></textarea></label>
 <div class="help-actions"><input hidden type="file" name="file" aria-label="Attach a file"><button type="button" aria-label="Attach a file" data-attach>＋</button><button type="button" aria-label="Emoji Picker" aria-expanded="false" data-emoji-toggle>☺</button></div>
 <div class="help-emojis" hidden>{emojis}</div><ul class="help-files"></ul><p class="help-error" role="alert" hidden></p>
 <button class="help-send" type="submit">{e(labels['messageSubmitLabel'])}</button></form>
 <div class="help-confirmation" role="status" hidden><h2>{e(labels['weAreOnIt'])}</h2><p>{e(labels['messageConfirmationText'])}</p></div></div>
 <div id="help-answers" role="tabpanel" aria-labelledby="help-answers-tab" hidden><button type="button" class="help-search-back" hidden>Go back</button><h2>Instant Answers</h2><form id="help-answer-search"><input aria-label="Search Doc articles" placeholder="{e(labels['searchLabel'])}" type="search"><button aria-label="Submit search query" type="submit">⌕</button></form><div class="help-search-results" aria-live="polite"></div><div class="help-get-in-touch" hidden><p>Can’t find an answer?</p><button type="button">Get in touch</button></div></div>
 </section><button id="help-launcher" type="button" aria-controls="help-panel" aria-expanded="false" data-label="{e(config['launcher'])}">{e(config['launcher'])}</button>
 <dialog id="help-reader" aria-labelledby="help-reader-title"><div class="help-reader-controls"><button type="button" aria-label="Close" data-reader-close>×</button><button type="button" aria-label="Collapse" data-reader-size>↙</button></div><header><a id="help-reader-link" target="_blank" rel="noopener"><span id="help-reader-title"></span><span class="help-new-window">Open in a new window</span></a></header><div class="help-reader-body"></div><footer role="toolbar" aria-label="Article feedback"><span class="help-feedback-label">Did this answer your question?</span><button type="button" data-rating="yes" aria-label='Send feedback: Yes. For "Did this answer your question?"'>☺</button><button type="button" data-rating="no" aria-label='Send feedback: No. For "Did this answer your question?"'>☹</button></footer><p class="help-reader-error" role="alert" hidden></p></dialog></div>'''
 tree.find('body').append(html.fragment_fromstring(widget))
 return html.tostring(tree,encoding='unicode',doctype='<!DOCTYPE html>')

def install(app,db,csrf_check,send_mail):
 with db() as connection:
  connection.execute('CREATE TABLE IF NOT EXISTS bc_help_contact(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL,message TEXT NOT NULL,version TEXT NOT NULL,page TEXT NOT NULL,attachments TEXT NOT NULL,created INTEGER NOT NULL)')
  connection.execute('CREATE TABLE IF NOT EXISTS bc_help_feedback(visitor TEXT NOT NULL,article TEXT NOT NULL,rating TEXT NOT NULL,created INTEGER NOT NULL,PRIMARY KEY(visitor,article))')
 router=APIRouter()
 @router.get('/api/help/2/answers')
 async def answers(query:str=''):
  term=query.strip()[:200]
  if not term:return {'items':[]}
  evidence=answer_evidence()
  if term.casefold()==evidence['query'].casefold():return {'items':evidence['items']}
  from public_operations import help_index
  matches=[item for item in help_index() if item['url'].startswith('/help/2/article/') and all(word in item['text'].casefold() for word in term.casefold().split())]
  matches.sort(key=lambda item:(term.casefold() not in item['title'].casefold(),item['title'].casefold()))
  return {'items':[{'route':item['url'],'label':item['title'],'snippet':item['text'].removeprefix(item['title']).strip()[:200]} for item in matches[:10]]}
 def visitor(request):return hashlib.sha256(request.cookies.get('basecamp_local_session','').encode()).hexdigest()
 @router.get('/api/help/2/feedback')
 async def feedback_state(request:Request,article:str):
  article_route(article)
  with db() as connection:row=connection.execute('SELECT rating FROM bc_help_feedback WHERE visitor=? AND article=?',(visitor(request),article)).fetchone()
  return {'rating':row[0] if row else None}
 @router.post('/api/help/2/feedback')
 async def feedback(request:Request):
  data=await request.json();csrf_check(request,data);article=article_route(str(data.get('article','')));rating=data.get('rating')
  if rating not in ('yes','no'):raise HTTPException(422,'Choose Yes or No.')
  with db() as connection:
   connection.execute('INSERT OR IGNORE INTO bc_help_feedback VALUES(?,?,?,?)',(visitor(request),article,rating,int(time.time())))
   row=connection.execute('SELECT rating FROM bc_help_feedback WHERE visitor=? AND article=?',(visitor(request),article)).fetchone()
  return {'rating':row[0]}
 @router.post('/api/help/contact')
 async def contact(request:Request):
  data=await request.form();csrf_check(request,data)
  name=str(data.get('name','')).strip();email=str(data.get('email','')).strip();message=str(data.get('message','')).strip();version=str(data.get('version',''));page=str(data.get('page',''))
  if version not in settings() or not re.fullmatch(r'/help/'+re.escape(version)+r'(?:/[^?#]*)?',page):raise HTTPException(422,'Invalid help page.')
  errors={}
  if not name or len(name)>40:errors['name']='required'
  if len(email)>255 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):errors['email']=settings()[version]['labels']['emailValidationLabel']
  if not message or len(message)>524288:errors['message']='required'
  if errors:raise HTTPException(422,errors)
  attachments=[]
  for upload in data.getlist('file'):
   if not getattr(upload,'filename',''):continue
   content=await upload.read(10*1024*1024+1)
   if len(content)>10*1024*1024:raise HTTPException(413,settings()[version]['labels']['attachmentSizeErrorText'])
   attachments.append({'name':Path(upload.filename).name,'type':upload.content_type,'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),'content':content.hex()})
  identifier=secrets.token_hex(12)
  try:send_mail(email,'Your local Basecamp support request',f'Hello {name},\n\nYour request {identifier} has been received by the local Basecamp copy.\n\n{message}\n\nThis is a local confirmation. It has not been sent to the Basecamp support team.')
  except (OSError,smtplib.SMTPException):raise HTTPException(503,'We couldn’t send your confirmation email. Please try again.')
  with db() as connection:connection.execute('INSERT INTO bc_help_contact VALUES(?,?,?,?,?,?,?,?)',(identifier,name,email,message,version,page,json.dumps(attachments),int(time.time())))
  return {'id':identifier,'saved':True}
 app.include_router(router)
