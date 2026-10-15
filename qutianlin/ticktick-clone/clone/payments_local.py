"""Local-only payment sandbox backed by shared exact-state payment intents."""
import hashlib,secrets,time,html
from fastapi import HTTPException
from fastapi.responses import HTMLResponse,JSONResponse
from websitebench.site_backend.errors import PaymentError

def create(req,a,auth,backend,state,save,frequency=None,gift=None):
 freq=frequency or req.query_params.get('freq','Year');amount={'Year':4999,'Month':499}.get(freq)
 if amount is None:raise HTTPException(400,'Unknown plan')
 if gift:amount*=gift['count']
 fingerprint=hashlib.sha256(('ticktick-premium-v1:'+freq+':'+str(amount)+':'+__import__('json').dumps(gift,sort_keys=True)).encode()).hexdigest()
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE');d=state(db,a);flow=backend.payments.create_intent(owner=a['account_id'],amount_minor=amount,currency='USD',fingerprint=fingerprint,idempotency_key=req.headers.get('Idempotency-Key') or secrets.token_hex(20),connection=db)
  d.setdefault('checkouts',{})[flow['flow_id']]={**flow,'frequency':freq,'completed':False,'gift':gift};save(db,a,d)
 return {'sessionId':flow['flow_id'],'url':'/local/checkout/'+flow['flow_id']}

def checkout(ident,req,a,auth,state,style):
 with auth.connect() as db:flow=state(db,a).get('checkouts',{}).get(ident)
 if not flow:raise HTTPException(404,'Checkout not found')
 if flow['completed']:return HTMLResponse('<h1>Payment completed</h1><p>This was a local simulation.</p><a href="/webapp/">Open TickTick</a>')
 title='TickTick Premium Gift Card × '+str(flow['gift']['count']) if flow.get('gift') else 'TickTick Premium';amount=f"US${flow['amount_minor']/100:.2f}";period='year' if flow['frequency']=='Year' else 'month'
 return HTMLResponse('''<!doctype html><html><head><title>TickTick Checkout</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>'''+style+'''</style></head><body><header><a href="/">TickTick</a><a href="/payment">Pricing</a></header><main><h1>'''+title+'''</h1><h2>'''+amount+' / '+period+'''</h2><p>Local payment sandbox. No money will be charged.</p><form><label>Payment result<select name="scenario"><option value="sandbox-approved">Simulated approval</option><option value="sandbox-declined">Simulated decline</option><option value="sandbox-retry">Simulated retry</option></select></label><p><label><input type="checkbox" required style="width:auto;height:auto"> I accept the <a href="/about/tos">Pricing Terms</a>.</label></p><button class="primary">Confirm payment</button><p role="status" id="status"></p></form><a href="/payment">Cancel</a></main><script>const form=document.querySelector('form');form.onsubmit=async e=>{e.preventDefault();const b=form.querySelector('button');b.disabled=true;try{const r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:form.scenario.value,idempotencyKey:crypto.randomUUID()})});const d=await r.json();document.querySelector('#status').textContent=d.message||d.detail;if(d.status==='CONSUMED'){document.querySelector('#status').innerHTML='Payment completed. <a href="/webapp/">Open TickTick</a>';b.remove()}}catch{document.querySelector('#status').textContent='Unable to process payment. Please retry.'}finally{b.disabled=false}}</script></body></html>''')

def pay(ident,body,a,auth,backend,state,save):
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE');d=state(db,a);flow=d.get('checkouts',{}).get(ident)
  if not flow:raise HTTPException(404,'Checkout not found')
  if flow['completed']:return {'status':'CONSUMED','message':'Payment already completed.'}
  facts={k:flow[k] for k in ['flow_id','owner','amount_minor','currency','fingerprint']}
  try:
   attempt=backend.payments.attempt(**facts,scenario_id=body.get('scenario',''),idempotency_key=body.get('idempotencyKey') or secrets.token_hex(20),connection=db)
   if attempt['status']=='APPROVED':
    backend.payments.consume_approval(db,**facts);flow['completed']=True;flow['paidAt']=int(time.time());d.setdefault('orders',{})[ident]={**flow,'status':'paid','isSimulation':True};
    if flow.get('gift'):
     from giftcards_local import fulfill
     fulfill(db,a,d,flow)
    else:d['subscription']={'frequency':flow['frequency'],'ends':max(int(time.time()),d.get('subscription',{}).get('ends',0))+(366 if flow['frequency']=='Year' else 31)*86400,'autoRenew':True,'flowId':ident}
    save(db,a,d);return {'status':'CONSUMED','message':'Payment completed. Local gift codes were delivered by email.' if flow.get('gift') else 'Payment completed. Premium is active in this local copy.'}
   return {'status':attempt['status'],'message':'Payment was declined. Choose another result to retry.' if attempt['status']=='DECLINED' else 'Payment could not be completed. Please retry.'}
  except PaymentError as e:raise HTTPException(400,str(e))
