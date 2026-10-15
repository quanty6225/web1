import json,secrets,time,hmac,hashlib,os
from pathlib import Path
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import JSONResponse
from backend.services import auth,backend,db,COOKIE,check_csrf,require_account,set_session,csrf,survey_owned
from backend.survey_model import new_id
from websitebench.site_backend.errors import PaymentError
router=APIRouter();PROVIDERS={'Google','Apple','Microsoft','Facebook','LinkedIn','SSO'}
secret_path=backend.lifecycle.database_path.parent/'local-provider.key'
if not secret_path.exists():
 fd=os.open(secret_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48))
PROVIDER_KEY=secret_path.read_text().strip()
@router.post('/api/oauth/start')
async def oauth_start(request:Request):
 check_csrf(request);data=await request.json();provider=data.get('provider')
 if provider not in PROVIDERS:raise HTTPException(422,'Unknown sign-in provider.')
 state=secrets.token_urlsafe(32);owner=auth.session_owner_digest(request.cookies.get(COOKIE))
 with db() as c:c.execute('INSERT INTO sm_oauth_states VALUES (?,?,?,?,0)',(state,owner,provider,int(time.time())+600))
 return {'url':'/local/oauth/?state='+state,'provider':provider}
@router.get('/api/oauth/state/{state}')
def oauth_state(state:str,request:Request):
 owner=auth.session_owner_digest(request.cookies.get(COOKIE))
 with db() as c:row=c.execute('SELECT provider FROM sm_oauth_states WHERE state=? AND owner=? AND expires>? AND consumed=0',(state,owner,int(time.time()))).fetchone()
 if not row:raise HTTPException(400,'The authorization request has expired. Start again.')
 return {'provider':row['provider'],'email':row['provider'].lower()+'-demo@surveymonkey.offline.invalid'}
@router.post('/api/oauth/complete')
async def oauth_complete(request:Request):
 check_csrf(request);data=await request.json();state=data.get('state','');owner=auth.session_owner_digest(request.cookies.get(COOKIE))
 with db() as c:
  c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM sm_oauth_states WHERE state=? AND owner=? AND expires>? AND consumed=0',(state,owner,int(time.time()))).fetchone()
  if not row:raise HTTPException(400,'The authorization request has expired or was already used.')
  c.execute('UPDATE sm_oauth_states SET consumed=1 WHERE state=?',(state,))
 if data.get('cancel'):return {'cancelled':True}
 provider=row['provider'];email=provider.lower()+'-demo@surveymonkey.offline.invalid';password=hmac.new(PROVIDER_KEY.encode(),provider.encode(),hashlib.sha256).hexdigest()+'A!'
 auth.seed_account(subject_id='local-provider-'+provider.lower(),email=email,display_name=provider+' demo',password=password)
 result=auth.sign_in(request.cookies[COOKIE],email=email,password=password);token=result['session_token']
 return set_session(JSONResponse({'ok':True,'csrf':csrf(token)}),token)

@router.get('/api/surveys/{id}/notes')
def get_notes(id:str,request:Request):
 owner=require_account(request)['account_id']
 with db() as c:survey_owned(c,id,owner);return {'notes':[dict(r) for r in c.execute('SELECT id,body,created FROM sm_notes WHERE survey_id=? ORDER BY created',(id,))]}
@router.post('/api/surveys/{id}/notes')
async def add_note(id:str,request:Request):
 check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();body=str(data.get('body','')).strip()
 if not body or len(body)>10000:raise HTTPException(422,'Enter a comment of up to 10,000 characters.')
 note=new_id()
 with db() as c:survey_owned(c,id,owner);c.execute('INSERT INTO sm_notes VALUES (?,?,?,?,?)',(note,id,owner,body,int(time.time())))
 return {'id':note}
@router.delete('/api/surveys/{id}/notes/{note}')
def delete_note(id:str,note:str,request:Request):
 check_csrf(request);owner=require_account(request)['account_id']
 with db() as c:survey_owned(c,id,owner);c.execute('DELETE FROM sm_notes WHERE id=? AND survey_id=? AND owner=?',(note,id,owner))
 return {'ok':True}
@router.get('/api/surveys/{id}/views')
def get_views(id:str,request:Request):
 owner=require_account(request)['account_id']
 with db() as c:survey_owned(c,id,owner);return {'views':[{'id':r['id'],'name':r['name'],'filters':json.loads(r['filters'])}for r in c.execute('SELECT * FROM sm_saved_views WHERE survey_id=?',(id,))]}
@router.post('/api/surveys/{id}/views')
async def add_view(id:str,request:Request):
 check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();name=str(data.get('name','')).strip()[:100]
 if not name:raise HTTPException(422,'Enter a view name.')
 with db() as c:survey_owned(c,id,owner);c.execute('INSERT INTO sm_saved_views VALUES (?,?,?,?)',(new_id(),id,name,json.dumps(data.get('filters',{}))))
 return {'ok':True}

PLANS={'team-advantage':{'name':'Team Advantage','monthly_minor':3000,'users':3,'period':12},'team-premier':{'name':'Team Premier','monthly_minor':8400,'users':3,'period':12}}
PLANS['team-advantage-monthly']={'name':'Team Advantage','monthly_minor':5400,'users':3,'period':1}
@router.get('/api/billing/plans')
def plans():return {'plans':PLANS,'currency':'CAD','scenarios':backend.config.payments['local_sandbox']['scenarios']}
@router.post('/api/billing/intent')
async def payment_intent(request:Request):
 check_csrf(request);owner=require_account(request)['account_id'];data=await request.json();plan=data.get('plan');users=data.get('users',3)
 if plan not in PLANS or not isinstance(users,int) or not 3<=users<=1000:raise HTTPException(422,'Choose a plan and at least 3 users.')
 amount=PLANS[plan]['monthly_minor']*users*PLANS[plan]['period'];fingerprint=hashlib.sha256(json.dumps({'plan':plan,'users':users,'amount':amount,'currency':'CAD'},sort_keys=True).encode()).hexdigest()
 try:flow=backend.payments.create_intent(owner=owner,amount_minor=amount,currency='CAD',fingerprint=fingerprint,idempotency_key=str(data.get('key','')))
 except PaymentError as e:raise HTTPException(400,str(e))
 with db() as c:c.execute('INSERT OR IGNORE INTO sm_checkouts VALUES (?,?,?,?,?,?,?)',(flow['flow_id'],owner,plan,users,amount,fingerprint,'pending'))
 return flow
@router.post('/api/billing/attempt')
async def payment_attempt(request:Request):
 check_csrf(request);owner=require_account(request)['account_id'];data=await request.json()
 with db() as c:row=c.execute('SELECT * FROM sm_checkouts WHERE id=? AND owner=?',(data.get('flow_id'),owner)).fetchone()
 if not row:raise HTTPException(404,'Checkout not found.')
 if row['status']=='complete':return {'status':'CONSUMED','plan':PLANS[row['plan']]['name']}
 try:
  result=backend.payments.attempt(flow_id=row['id'],owner=owner,amount_minor=row['amount'],currency='CAD',fingerprint=row['fingerprint'],scenario_id=data.get('scenario'),idempotency_key=data.get('key',''))
  if result.get('status')=='APPROVED':
   with db() as c:
    c.execute('BEGIN IMMEDIATE');backend.payments.consume_approval(c,flow_id=row['id'],owner=owner,amount_minor=row['amount'],currency='CAD',fingerprint=row['fingerprint'])
    c.execute('INSERT INTO sm_profiles(owner,plan) VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET plan=excluded.plan',(owner,PLANS[row['plan']]['name']));c.execute('UPDATE sm_checkouts SET status="complete" WHERE id=?',(row['id'],))
  return result
 except PaymentError as e:raise HTTPException(400,str(e))
@router.get('/api/billing/history')
def billing_history(request:Request):
 owner=require_account(request)['account_id']
 with db() as c:return {'invoices':[dict(r)for r in c.execute('SELECT id,plan,users,amount,status FROM sm_checkouts WHERE owner=? AND status="complete"',(owner,))]}
