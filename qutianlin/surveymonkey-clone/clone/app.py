import json,html,os,time,asyncio
from contextlib import asynccontextmanager,suppress
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from backend.services import auth,backend,COOKIE,csrf,set_session,check_csrf,require_account,account,db,deliver_auth
from backend.survey_api import router
from websitebench.local_clone_auth import AuthError

ROOT=Path(__file__).parent
@asynccontextmanager
async def lifespan(app):
    from backend.notifications import digest_worker
    task=asyncio.create_task(digest_worker())
    try:yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):await task
app=FastAPI(title='SurveyMonkey',docs_url=None,redoc_url=None,lifespan=lifespan)
app.include_router(router)
from backend.media_api import router as media_router
app.include_router(media_router)
from backend.account_api import router as account_router
app.include_router(account_router)
from backend.public_api import router as public_router
app.include_router(public_router)
from backend.notifications import router as notification_router
app.include_router(notification_router)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.middleware('http')
async def privacy_headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self' data: blob:; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; form-action 'self'; base-uri 'self'"
    if not request.url.path.startswith('/static/'):response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(AuthError)
async def auth_error(request,exc):
    retry=getattr(exc,'retry_after',None)
    return JSONResponse({'detail':str(exc),**({'retry_after':retry} if retry else {})},status_code=429 if retry else 400,headers={'Retry-After':str(retry)} if retry else None)

@app.get('/api/session')
def session(request:Request):
    token,value=auth.ensure_session(request.cookies.get(COOKIE))
    return set_session(JSONResponse({'account':value.get('account'),'authenticated':value.get('authenticated',False),'csrf':csrf(token)}),token)

@app.post('/api/auth/{action}')
async def authenticate(action:str,request:Request):
    check_csrf(request);data=await request.json();token=request.cookies[COOKIE]
    if action=='login':
        result=auth.sign_in(token,email=data.get('email',''),password=data.get('password',''));token=result['session_token'];payload={'ok':True}
    elif action=='logout':
        auth.sign_out(token);token,_=auth.ensure_session(None);payload={'ok':True}
    elif action=='register':
        auth.start_registration(token,email=data.get('email',''),display_name=data.get('name',''),password=data.get('password',''),restart_invalid_flow=True)
        mail=deliver_auth(token,'registration')
        if not mail or mail['status']!='SMTP_SENT':raise HTTPException(503,'We could not send your verification email. Please retry delivery.')
        payload={'ok':True,'mail':{'status':mail['status']}}
    elif action=='verify':
        auth.verify_registration_code(token,data.get('code',''));result=auth.complete_registration(token);token=result['session_token'];payload={'ok':True}
    elif action=='reset':
        auth.start_password_reset(token,email=data.get('email',''),restart_invalid_flow=True);mail=deliver_auth(token,'password-reset')
        if mail and mail['status']!='SMTP_SENT':raise HTTPException(503,'We could not send your reset email. Please retry delivery.')
        payload={'ok':True,'message':'If an account matches this email, a reset code has been sent.'}
    elif action=='reset-complete':
        auth.verify_password_reset_code(token,data.get('code',''));token=auth.complete_password_reset(token,new_password=data.get('password',''));payload={'ok':True}
    elif action in ('resend','retry-mail'):
        purpose=data.get('purpose','registration')
        if purpose not in ('registration','password-reset'):raise HTTPException(422,'Invalid mail purpose.')
        if action=='retry-mail':
            auth.retry_failed_mail_for_session(token,purpose=purpose)
        else:
            auth.resend_challenge(token,purpose=purpose)
        mail=deliver_auth(token,purpose)
        if (mail and mail['status']!='SMTP_SENT') or (not mail and purpose=='registration'):raise HTTPException(503,'Email delivery is unavailable. Try again shortly.')
        payload={'ok':True,'message':'If an account matches this email, a new code has been sent.' if purpose=='password-reset' else 'A new verification code has been sent.'}
    else:raise HTTPException(404,'Action not found.')
    payload['csrf']=csrf(token)
    return set_session(JSONResponse(payload),token)

@app.get('/api/profile')
def profile(request:Request):
    user=require_account(request)
    with db() as c:
        row=c.execute('SELECT preferences,plan FROM sm_profiles WHERE owner=?',(user['account_id'],)).fetchone()
    return {'account':user,'preferences':json.loads(row['preferences']) if row else {},'plan':row['plan'] if row else 'Basic'}

@app.patch('/api/profile')
async def update_profile(request:Request):
    check_csrf(request);user=require_account(request);data=await request.json()
    preferences=data.get('preferences',{})
    if not isinstance(preferences,dict) or len(json.dumps(preferences))>20000:raise HTTPException(422,'Enter valid preferences.')
    if 'marketing' in preferences and (not isinstance(preferences['marketing'],dict) or any(not isinstance(v,bool) for v in preferences['marketing'].values())):raise HTTPException(422,'Select valid notification preferences.')
    if 'response_alerts' in preferences and (not isinstance(preferences['response_alerts'],dict) or any(not isinstance(v,bool) for v in preferences['response_alerts'].values())):raise HTTPException(422,'Select valid response alerts.')
    name=None
    if 'first_name' in data or 'last_name' in data:
        first=str(data.get('first_name','')).strip();last=str(data.get('last_name','')).strip()
        if not first or len(first)>100 or len(last)>100:raise HTTPException(422,'Enter a first name and keep each name within 100 characters.')
        name=(first+' '+last).strip();preferences.update(first_name=first,last_name=last)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT preferences FROM sm_profiles WHERE owner=?',(user['account_id'],)).fetchone()
        merged=json.loads(row['preferences']) if row else {}
        for key,value in preferences.items():
            merged[key]={**merged.get(key,{}),**value} if key in ('marketing','response_alerts') else value
        c.execute('INSERT INTO sm_profiles(owner,preferences) VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET preferences=excluded.preferences',(user['account_id'],json.dumps(merged)))
        if name:c.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(name,user['account_id']))
        if 'existing' in preferences.get('response_alerts',{}):
            for row in c.execute('SELECT id,settings FROM sm_surveys WHERE owner=? AND deleted=0',(user['account_id'],)).fetchall():
                settings=json.loads(row['settings']);settings['response_alerts']=preferences['response_alerts']['existing']
                c.execute('UPDATE sm_surveys SET settings=? WHERE id=?',(json.dumps(settings),row['id']))
    return {'ok':True}

@app.get('/health')
def health():return {'status':'ok','site':'surveymonkey'}

SHELL='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SurveyMonkey</title><link rel="stylesheet" href="/static/app.css"><script src="/static/app.js" defer></script></head><body><div id="app"><div class="loading">Loading SurveyMonkey…</div></div><div id="toast" role="status"></div><div id="modal"></div></body></html>'''
AUTH=('/user/sign-in','/user/sign-up','/user/password','/sign-up','/reset','/login','/forgot','/verify')
MEMBER=('/subscribe','/checkout','/home','/create','/authoring','/collect','/analyze','/account','/myaccount','/dashboard','/datastudio','/notifications','/billing')
@app.get('/{path:path}')
def page(path:str,request:Request):
    route='/'+path
    if route.startswith('/user/account'):return RedirectResponse('/account/'+('billing/' if 'billing' in route else ''),status_code=303)
    if route.startswith('/local/external'):
        destination=request.query_params.get('destination','');return HTMLResponse('<!doctype html><html lang="en"><link rel="stylesheet" href="/static/app.css"><title>SurveyMonkey — External destination</title><header class="topbar"><a class="brand" href="/">SurveyMonkey</a><a href="/home/">Home</a></header><main class="boundary"><h1>External destination</h1><p>'+html.escape(destination)+'</p><p>This destination is outside the local SurveyMonkey experience.</p><a class="button primary" href="/">Return to SurveyMonkey</a></main></html>')
    if route.startswith(MEMBER) and not account(request):return RedirectResponse('/user/sign-in/?return_to='+quote(str(request.url.path)+'?'+str(request.url.query),safe=''),status_code=303)
    if route.startswith(AUTH+MEMBER+('/r/','/local/')):return HTMLResponse(SHELL)
    index=ROOT/'frontend'/'public-routes.json'
    if index.exists():
        routes=json.loads(index.read_text());file=routes.get(route) or routes.get(route.rstrip('/')+'/')
        if file:return FileResponse(ROOT/'frontend'/file,media_type='text/html')
    metadata_file=ROOT/'frontend'/'boundary-routes.json'
    metadata=json.loads(metadata_file.read_text()) if metadata_file.exists() else {}
    item=metadata.get(route) or metadata.get(route.rstrip('/')+'/') or {}
    title=html.escape(item.get('title') or 'Page unavailable')
    collection=html.escape(item.get('collection') or 'SurveyMonkey')
    back=item.get('return_path') or '/'
    if not back.startswith('/') or back.startswith('//') or back==route:back='/'
    explanation='This item is beyond the first five details in this collection. Its original title is preserved here.' if item.get('reason')=='detail-quota' else 'This page has not been captured completely in this local copy.'
    return HTMLResponse('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/static/app.css"><title>'+title+' — SurveyMonkey</title><body><header class="topbar"><a class="brand" href="/">SurveyMonkey</a><a href="/home/">Home</a><a href="/create/start/">Create survey</a></header><main class="boundary"><p>'+collection+'</p><h1>'+title+'</h1><p>'+explanation+'</p><a class="button primary" href="'+html.escape(back,quote=True)+'">Back to '+collection+'</a><a class="button" href="/">SurveyMonkey homepage</a></main><footer class="app-footer"><a href="/mp/legal/privacy/">Privacy Notice</a> · <a href="/help/en/">Help Center</a></footer></body></html>')
