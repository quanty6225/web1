"""Local sandbox only: captured prices, approval/decline/retry and atomic state."""
import hashlib,json,re,secrets,time
from pathlib import Path
from lxml import html,etree
from fastapi import HTTPException
from websitebench.site_backend import PaymentError
from workspaces import manager
ROOT=Path(__file__).parent

def plans():
 result={};routes=json.loads((ROOT/'frontend/routes.json').read_text())
 for path,info in routes.items():
  match=re.fullmatch(r'/6302022/account/plans/(\d+)/edit',path)
  if not match:continue
  tree=html.fromstring((ROOT/'frontend/pages'/info['file']).read_text());forms=tree.xpath('//form[contains(@action,"/account/plans/")]')
  if not forms:continue
  text=' '.join(forms[0].text_content().split());price=re.search(r'You chose Basecamp (.*?) You’ll pay \$([\d,]+) now for your next (month|year)',text)
  if price:result[match[1]]={'id':match[1],'name':price[1],'amount_minor':int(price[2].replace(',',''))*100,'period':price[3]}
 return result
PLANS=plans()

def initialize(db):
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS bc_payment_results(owner TEXT,idempotency_key TEXT,fingerprint TEXT,result TEXT,PRIMARY KEY(owner,idempotency_key))')

def mutate(db,backend,account,path,payload):
 match=re.fullmatch(r'/6302022/account/plans/(\d+)',path)
 if not match:return None
 manager(account,True);plan=PLANS.get(match[1])
 if not plan:raise HTTPException(404,'Plan not found')
 scenario=payload.get('sandbox_scenario','')
 if scenario not in ['sandbox-approved','sandbox-declined','sandbox-retry']:raise HTTPException(422,'Choose a local payment simulation. Real card details are not accepted.')
 for key in ['street_1','city','country','postal_code']:
  if not str(payload.get('credit_card[address]['+key+']','')).strip():raise HTTPException(422,'Complete your billing address.')
 if payload.get('credit_card[address][country]') in ['US','CA'] and not payload.get('credit_card[address][region]'):raise HTTPException(422,'Choose your state or province.')
 key=str(payload.get('idempotency_key') or secrets.token_hex(20))
 if not re.fullmatch(r'[A-Za-z0-9._:-]{8,180}',key):raise HTTPException(422,'Invalid payment request. Reload this page.')
 owner=account['workspace_id'];fingerprint=hashlib.sha256(json.dumps({'plan':plan,'billing':{k:v for k,v in payload.items() if k.startswith('credit_card[address]')}},sort_keys=True).encode()).hexdigest()
 with db() as c:
  existing=c.execute('SELECT * FROM bc_payment_results WHERE owner=? AND idempotency_key=?',(owner,key)).fetchone()
  if existing:
   if existing['fingerprint']!=fingerprint:raise HTTPException(409,'This payment request was already used for different billing details.')
   return json.loads(existing['result'])
 try:
  flow=backend.payments.create_intent(owner=owner,amount_minor=plan['amount_minor'],currency='USD',fingerprint=fingerprint,idempotency_key=key,adapter='local-sandbox')
  attempt=backend.payments.attempt(flow_id=flow['flow_id'],owner=owner,amount_minor=plan['amount_minor'],currency='USD',fingerprint=fingerprint,scenario_id=scenario,idempotency_key=key+'-attempt')
  result={'status':attempt['status'],'is_simulation':True,'plan':plan,'redirect':path+'/edit?payment='+attempt['status'].lower()}
  with db() as c:
   c.execute('BEGIN IMMEDIATE')
   if attempt['status']=='APPROVED':
    backend.payments.consume_approval(c,flow_id=flow['flow_id'],owner=owner,amount_minor=plan['amount_minor'],currency='USD',fingerprint=fingerprint)
    c.execute('INSERT OR REPLACE INTO bc_settings VALUES(?,"sandbox_plan",?)',(owner,json.dumps(plan)))
   c.execute('INSERT INTO bc_payment_results VALUES(?,?,?,?)',(owner,key,fingerprint,json.dumps(result)))
  return result
 except PaymentError as error:raise HTTPException(409,str(error))

def render(tree,path,owner,c,query):
 for form in tree.xpath('//form[contains(@action,"/account/plans/")]'):
  form.attrib.pop('data-controller',None);form.attrib.pop('data-action',None)
  for iframe in form.xpath('.//iframe'):
   placeholder=etree.Element('span',{'class':'text-subtle'});placeholder.text='Not required for local simulation';iframe.getparent().replace(iframe,placeholder)
  fieldset=etree.Element('fieldset',{'class':'margin-block-24','data-local-payment':'true'});etree.SubElement(fieldset,'legend').text='Local payment simulation';etree.SubElement(fieldset,'p').text='No real payment is made. Do not enter a real card number.'
  label=etree.SubElement(fieldset,'label');label.text='Payment result ';select=etree.SubElement(label,'select',{'name':'sandbox_scenario','class':'input','required':'required'})
  for value,text in [('sandbox-approved','Approve'),('sandbox-declined','Decline'),('sandbox-retry','Temporary failure')]:etree.SubElement(select,'option',{'value':value}).text=text
  etree.SubElement(fieldset,'input',{'type':'hidden','name':'idempotency_key','value':secrets.token_hex(20)});form.insert(0,fieldset)
  state=dict(query or {}).get('payment')
  if state:
   message={'approved':'Local simulation approved. Your local plan has been updated.','declined':'The simulated payment was declined. Your plan has not changed.','retryable':'The simulated payment could not be completed. Please try again.'}.get(state)
   if message:etree.SubElement(fieldset,'p',{'role':'status','class':'text-highlight'}).text=message
