"""Offline iCloud application. Source credentials are never read by this runtime."""
import json, os, secrets, smtplib, time, uuid, base64, binascii
from pathlib import Path
from email.message import EmailMessage
from urllib.parse import quote, urlsplit
from html import escape
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from backend.site_backend_integration import open_site_services
from backend.business import seed_demo, seed_defaults, remove_photo_references, expire_photos, expire_notes, PHOTO_RETENTION_SECONDS, migrate as migrate_business
from backend.auth_extensions import ICloudAuthStore
from backend import registration, identity, file_lifecycle, note_folders, contacts, contact_archives, note_sharing, reminders, reminder_sharing, calendar_archives, calendar_sharing, event_invitations, event_attachments, calendar_time, alarms
from backend import find_devices, work_documents
from websitebench.local_clone_auth.store import AuthError, AuthRateLimited

ROOT=Path(__file__).resolve().parent
backend,_initial_auth=open_site_services()
MAIL_WORKER=secrets.token_urlsafe(32)
auth=ICloudAuthStore(backend.lifecycle.database_path,site_id='icloud',mail_mode='SMTP_PENDING',mail_worker_token=MAIL_WORKER)
auth.ensure_schema()
registration.migrate(auth)
identity.migrate(auth)
demo=auth.seed_account(subject_id='icloud-demo',email='demo@icloud.offline.invalid',display_name='Demo',password='IcloudDemo2026!')
with auth.connect() as db:
 migrate_business(db)
 find_devices.migrate(db)
 work_documents.migrate(db)
 seed_demo(db,demo)
COOKIE=backend.config.cookie_name
PUBLIC=json.loads((ROOT/'public/index.json').read_text())
DEFERRED=json.loads((ROOT/'public/deferred.json').read_text()) if (ROOT/'public/deferred.json').exists() else {}
PUBLIC_ALIASES=json.loads((ROOT/'public/aliases.json').read_text()) if (ROOT/'public/aliases.json').exists() else {}
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.middleware('http')
async def security(request,call_next):
 if request.url.path.startswith(('/static/photos/','/static/videos/','/static/details/')):
  state=auth.resolve_session(request.cookies.get(COOKIE))
  if not state or not state['authenticated']:return JSONResponse({'error':'Sign in required'},status_code=401)
  item_id=Path(request.url.path).stem
  with auth.connect() as db:
   row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(state['account']['account_id'],'photos',item_id)).fetchone()
   photo=json.loads(row[0]) if row else None
   if not photo or photo.get('deleted') and photo.get('deleted_at') and photo['deleted_at']<=int(time.time())-PHOTO_RETENTION_SECONDS:return JSONResponse({'error':'Photo not found'},status_code=404)
 if request.method not in ('GET','HEAD','OPTIONS'):
  origin=request.headers.get('origin')
  if origin and urlsplit(origin).netloc!=request.headers.get('host'):return JSONResponse({'error':'Invalid request origin'},status_code=403)
 response=await call_next(request)
 response.headers['Cache-Control']='no-store'
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['Referrer-Policy']='no-referrer'
 response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
 return response

def set_session(response,token):
 response.set_cookie(COOKIE,token,secure=True,httponly=True,samesite='lax',path='/')
 return response
def account(request):
 session=auth.resolve_session(request.cookies.get(COOKIE))
 if not session or not session['authenticated']:raise HTTPException(401,'Sign in required')
 return session['account']
def shell():return HTMLResponse((ROOT/'index.html').read_text())
def send_mail(token,purpose):
 claim=auth.claim_pending_mail_for_session(token,purpose=purpose,worker_token=MAIL_WORKER)
 if not claim:
  status=auth.session_mail_status(token,purpose=purpose)
  if status=='SMTP_SENT' or status is None and purpose=='password-reset':return
  raise HTTPException(503,'Email has not been sent. Please try again.')
 message=EmailMessage();message['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');message['To']=claim['recipient']
 message['Subject']='Verify your email address' if purpose=='registration' else 'Reset your password'
 origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
 path='/account/create/' if purpose=='registration' else '/account/recovery/'
 message.set_content(f"Your verification code is {claim['verification_code']}.\n\nContinue at {origin}{path}\nThis code expires in 15 minutes.\n\niCloud local account\n")
 try:
  deliver_message(message)
 except HTTPException:
  auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=False,error='transport',worker_token=MAIL_WORKER)
  raise
 auth.finish_mail_claim(claim['mail_id'],claim['claim_token'],sent=True,accepted_request_count=1,worker_token=MAIL_WORKER)

def deliver_message(message):
 host=os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
 if host not in ('127.0.0.1','localhost','::1'):raise HTTPException(503,'Local mail service unavailable')
 try:
  with smtplib.SMTP(host,int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=8) as smtp:smtp.send_message(message)
 except (OSError,smtplib.SMTPException):raise HTTPException(503,'Email could not be sent. Please try again.')

def send_identity_mail(recipient,code,purpose):
 message=EmailMessage();message['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');message['To']=recipient
 message['Subject']='Confirm your email address change' if purpose=='email' else 'Confirm your phone number change'
 origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
 message.set_content(f"Your verification code is {code}.\n\nContinue at {origin}/account/manage/\nThis code expires in 15 minutes.\n\niCloud local account\n")
 deliver_message(message)

@app.get('/healthz')
def health():return {'ok':True,'site_id':'icloud'}

@app.get('/api/find/state')
def find_state(request:Request):
 owner=account(request)['account_id']
 with auth.connect() as db:return {'devices':find_devices.states(db,owner),'simulated':True}

@app.post('/api/find/{device_id}/action')
async def find_action(device_id:str,request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   return {'state':find_devices.act(db,owner,device_id,data),'simulated':True}
 except PermissionError as exc:raise HTTPException(403,str(exc))
 except LookupError as exc:raise HTTPException(404,str(exc))
 except ValueError as exc:raise HTTPException(400,str(exc))
@app.get('/api/session')
def session(request:Request):
 token,data=auth.ensure_session(request.cookies.get(COOKIE))
 data['flows']={purpose:{**auth.session_flow_status(token,purpose=purpose),'mail_status':auth.session_mail_status(token,purpose=purpose)} for purpose in ('registration','password-reset')}
 return set_session(JSONResponse(data),token)
@app.post('/api/auth/{action}')
async def auth_action(action:str,request:Request):
 data=await request.json();token,_=auth.ensure_session(request.cookies.get(COOKIE));result={'ok':True}
 try:
  if action=='captcha':result=registration.issue_challenge(auth,token)
  elif action=='login':
   signed=auth.sign_in_identifier(token,identifier=data.get('email',''),password=data.get('password',''));token=signed['session_token'];result['account']=signed['account']
  elif action=='logout':auth.sign_out(token);token=auth.create_anonymous_session()
  elif action=='logout-all':
   owner=account(request)['account_id']
   with auth.connect() as db:db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL',(int(time.time()),owner))
   token=auth.create_anonymous_session()
  elif action=='register':
   profile=registration.registration_profile(data)
   auth.validate_registration_details(email=data.get('email',''),display_name=profile['first']+' '+profile['last'],password=data.get('password',''))
   registration.consume_challenge(auth,token,data)
   result=auth.start_registration(token,email=data.get('email',''),display_name=profile['first']+' '+profile['last'],password=data.get('password',''),restart_invalid_flow=True)
   registration.save_profile(auth,token,profile)
   if result.get('mail_status')=='SMTP_FAILED':auth.retry_failed_mail_for_session(token,purpose='registration')
   send_mail(token,'registration')
  elif action=='verify-registration':
   auth.verify_registration_code(token,data.get('code',''));old_owner,profile=registration.take_profile(auth,token);signed=auth.complete_registration(token);token=signed['session_token'];result={'ok':True,'account':signed['account']}
   with auth.connect() as db:seed_defaults(db,signed['account']['account_id'])
   registration.finish_profile(auth,old_owner,signed['account']['account_id'],profile)
  elif action=='recover':
   result=auth.start_password_reset(token,email=auth.recovery_identifier(data.get('email','')));send_mail(token,'password-reset')
  elif action=='verify-reset':auth.verify_password_reset_code(token,data.get('code',''))
  elif action=='reset':token=auth.complete_password_reset(token,new_password=data.get('password',''))
  elif action=='change-password':
   account(request)
   if data.get('password')!=data.get('confirm'):raise HTTPException(400,'Passwords do not match.')
   token=auth.change_password(token,current_password=data.get('current_password',''),new_password=data.get('password',''))
  elif action=='retry-mail':
   purpose=data.get('purpose','registration')
   if purpose not in ('registration','password-reset'):raise HTTPException(400,'Unknown email verification flow')
   auth.prepare_mail_retry(token,purpose=purpose);send_mail(token,purpose)
  elif action=='resend':
   purpose=data.get('purpose','registration')
   result=auth.resend_verification(token,purpose=purpose);send_mail(token,purpose)
  elif action=='cancel-verification':
   purpose=data.get('purpose','registration');auth.cancel_verification(token,purpose=purpose)
   if purpose=='registration':
    with auth.connect() as db:db.execute('DELETE FROM icloud_registration_profiles WHERE owner=?',(auth.session_owner_digest(token),))
  else:raise HTTPException(404,'Unknown action')
 except AuthRateLimited as exc:return set_session(JSONResponse({'error':'Please wait before requesting another code.','retry_after':exc.retry_after},status_code=429),token)
 except AuthError as exc:return set_session(JSONResponse({'error':str(exc)},status_code=400),token)
 except HTTPException as exc:return set_session(JSONResponse({'error':exc.detail},status_code=exc.status_code),token)
 return set_session(JSONResponse(result),token)

@app.get('/api/auth/captcha/{identifier}/{kind}')
def captcha_asset(identifier:str,kind:str,request:Request):
 try:content=registration.challenge_asset(auth,request.cookies.get(COOKIE),identifier,kind)
 except AuthError as exc:raise HTTPException(404,str(exc))
 return Response(content,media_type='image/svg+xml' if kind=='image' else 'audio/wav')

@app.get('/api/account')
def account_info(request:Request):
 person=account(request)
 with auth.connect() as db:row=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='settings' AND id='profile'",(person['account_id'],)).fetchone()
 return {'account':person,'profile':json.loads(row[0]) if row else {},'pending_change':identity.status(auth,request.cookies.get(COOKIE))}

@app.post('/api/account/change/{action}')
async def change_identity(action:str,request:Request):
 account(request);token=request.cookies.get(COOKIE)
 try:data=await request.json()
 except ValueError:raise HTTPException(400,'Enter account verification details.')
 if not isinstance(data,dict):raise HTTPException(400,'Enter account verification details.')
 try:
  if action=='start':result=identity.start(auth,token,data,send_identity_mail)
  elif action=='resend':result=identity.start(auth,token,{},send_identity_mail,resend=True)
  elif action=='cancel':identity.cancel(auth,token);result=None
  elif action=='verify':token=identity.verify(auth,token,data.get('code'));result=None
  else:raise HTTPException(404,'Unknown account action')
 except AuthRateLimited as exc:return JSONResponse({'error':'Please wait before requesting another code.','retry_after':exc.retry_after},status_code=429)
 except AuthError as exc:return JSONResponse({'error':str(exc)},status_code=400)
 return set_session(JSONResponse({'ok':True,'pending_change':result}),token)

@app.put('/api/account/profile')
async def account_profile(request:Request):
 owner=account(request)['account_id']
 try:profile=registration.update_profile(auth,owner,await request.json())
 except AuthError as exc:raise HTTPException(400,str(exc))
 return {'profile':profile}

KINDS={'photos','albums','files','contacts','contact_lists','notes','folders','reminders','lists','events','calendars','documents','settings','devices'}

@app.get('/api/contacts/state')
def contact_state(request:Request):
 owner=account(request)['account_id']
 with auth.connect() as db:return {'generation':contact_archives.generation(db,owner)}

@app.get('/api/contacts/archives')
def contact_versions(request:Request):
 owner=account(request)['account_id']
 with auth.connect() as db:return {'archives':contact_archives.versions(db,owner),'generation':contact_archives.generation(db,owner)}

@app.post('/api/contacts/{operation}')
async def contact_operation(operation:str,request:Request):
 owner=account(request)['account_id']
 try:data=await request.json()
 except ValueError:raise HTTPException(400,'Invalid contact request.')
 if not isinstance(data,dict):raise HTTPException(400,'Invalid contact request.')
 try:
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');now=int(time.time())
   if operation in ('import','action','restore'):
    try:contact_archives.check_generation(db,owner,request.headers.get('x-contacts-generation'))
    except ValueError as exc:raise HTTPException(409,str(exc))
   if operation=='restore':
    identifier=data.get('id')
    if not isinstance(identifier,str):raise ValueError('Choose a contact archive.')
    return contact_archives.restore(db,owner,identifier,request.headers.get('x-contacts-generation'),int(time.time()*1000))
   if operation=='import':
    cards=contacts.parse(data.get('content'));identifiers=[]
    contact_archives.snapshot(db,owner,int(time.time()*1000))
    for card in cards:
     contacts.validate_contact(card,{},now);card['id']=uuid.uuid4().hex;identifiers.append(card['id'])
     db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)',(owner,'contacts',card['id'],json.dumps(card),now))
    return {'ids':identifiers}
   if operation=='export':
    content=contacts.export(contacts.selected(db,owner,data.get('ids')))
    return Response(content,media_type='text/vcard',headers={'Content-Disposition':'attachment; filename="Contacts.vcf"'})
   if operation=='action':
    contact_archives.snapshot(db,owner,int(time.time()*1000))
    contacts.action(db,owner,data,now);return {'ok':True}
   raise HTTPException(404,'Unknown contact operation.')
 except ValueError as exc:raise HTTPException(400,str(exc))
 except LookupError as exc:raise HTTPException(404,str(exc))
def remove_uploaded_bytes(item):
 identifier=item.get('id','')
 if item.get('blob')==identifier and len(identifier)==32 and all(c in '0123456789abcdef' for c in identifier):
  (backend.lifecycle.database_path.parent/'uploads'/identifier).unlink(missing_ok=True)

def purge_expired_photos(owner):
 with auth.connect() as db:removed=expire_photos(db,owner,int(time.time()))
 for item in removed:remove_uploaded_bytes(item)

def purge_expired_files(owner):
 with auth.connect() as db:removed=file_lifecycle.expire(db,owner,int(time.time()))
 for item in removed:remove_uploaded_bytes(item)

def purge_expired_notes(owner):
 with auth.connect() as db:expire_notes(db,owner,int(time.time()))

def sharing_error(exc):
 if isinstance(exc,PermissionError):return HTTPException(403,str(exc))
 if isinstance(exc,LookupError):return HTTPException(404,str(exc))
 if isinstance(exc,FileExistsError):return HTTPException(409,str(exc))
 return HTTPException(400,str(exc))

@app.post('/api/note-shares')
async def invite_note(request:Request):
 person=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Enter sharing details.')
  if data.get('method','link') not in ('link','email'):raise ValueError('Choose Email or Copy Link.')
  message=data.get('message','')
  if not isinstance(message,str) or len(message)>2000:raise ValueError('The message is too long.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   key,emails=note_sharing.invite(db,person,data,int(time.time()))
   path='/notes/share/'+key+'/'
   if data.get('method')=='email':
    origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
    for recipient in emails:
     mail=EmailMessage();mail['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');mail['To']=recipient;mail['Subject']='Invitation to collaborate in Notes'
     mail.set_content(person['display_name']+' invited you to collaborate in Notes.\n\n'+message+'\n\n'+origin+path+'\nSign in with the invited local account to accept.\n')
     deliver_message(mail)
   return {'id':key,'path':path}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.get('/api/note-shares/{key}')
def note_share(key:str,request:Request):
 person=account(request)
 try:
  with auth.connect() as db:return note_sharing.summary(db,key,person)
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/note-shares/{key}')
async def note_share_action(key:str,request:Request):
 person=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose a sharing action.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');note_sharing.action(db,key,person,data)
  return {'ok':True}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/notes/shared-create')
async def create_shared_note(request:Request):
 person=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict) or not isinstance(data.get('folder'),str):raise ValueError('Choose a shared folder.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');return note_sharing.create_note(db,person,data['folder'],int(time.time()))
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/notes/move')
async def move_note_or_folder(request:Request):
 owner=account(request)['account_id'];purge_expired_notes(owner)
 try:data=await request.json()
 except ValueError:raise HTTPException(400,'Choose a note or folder.')
 if not isinstance(data,dict):raise HTTPException(400,'Choose a note or folder.')
 try:
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if isinstance(data.get('id'),str) and data['id'].startswith(note_sharing.PREFIX):
    from backend.note_personal import move
    item=move(db,account(request),data.get('kind'),data['id'],data.get('folder'))
   else:item=note_folders.move(db,owner,data.get('kind'),data.get('id'),data.get('folder'),int(time.time()))
 except ValueError as exc:raise HTTPException(400,str(exc))
 except LookupError as exc:raise HTTPException(404,str(exc))
 except PermissionError as exc:raise HTTPException(403,str(exc))
 return item

@app.post('/api/notes/{note_id}/recover')
def recover_note(note_id:str,request:Request):
 owner=account(request)['account_id'];purge_expired_notes(owner)
 with auth.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='notes' AND id=?",(owner,note_id)).fetchone()
  if not row:raise HTTPException(404,'Note not found.')
  data=json.loads(row[0])
  if not data.get('deleted'):raise HTTPException(400,'This note is not in Recently Deleted.')
  data.update(deleted=False,folder='notes');data.pop('deleted_at',None)
  db.execute("UPDATE icloud_entities SET payload=?,updated_at=? WHERE owner=? AND kind='notes' AND id=?",(json.dumps(data),int(time.time()),owner,note_id))
 return {'ok':True}

@app.post('/api/notes/{note_id}/pin')
async def pin_note(note_id:str,request:Request):
 person=account(request);purge_expired_notes(person['account_id'])
 try:
  data=await request.json()
  if not isinstance(data,dict) or set(data)!={'pinned'}:raise ValueError('Choose a pin state.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');item=note_sharing.set_pin(db,person,note_id,data['pinned'])
  return {'item':item}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/files/trash')
async def file_trash(request:Request):
 owner=account(request)['account_id']
 try:data=await request.json()
 except ValueError:raise HTTPException(400,'Select files to continue.')
 if not isinstance(data,dict):raise HTTPException(400,'Select files to continue.')
 purge_expired_files(owner)
 try:
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   removed=file_lifecycle.apply(db,owner,data.get('kind','files'),data.get('ids'),data.get('action'),int(time.time()))
   db.commit()
 except LookupError as exc:raise HTTPException(404,str(exc))
 except ValueError as exc:raise HTTPException(400,str(exc))
 for item in removed:remove_uploaded_bytes(item)
 return {'ok':True}

def send_reminder_invitation(actor,recipient,key):
 origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
 mail=EmailMessage();mail['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');mail['To']=recipient;mail['Subject']='Invitation to a shared reminder list'
 mail.set_content(actor['display_name']+' invited you to share a reminder list.\n\nJoin Reminders List: '+origin+'/reminders/share/'+key+'/\nSign in with the invited local account.\n')
 deliver_message(mail)

@app.post('/api/reminder-shares')
async def invite_reminder_list(request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Enter sharing details.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,actor['account_id'],request.headers.get('x-calendar-generation'));key,emails=reminder_sharing.invite(db,actor,data)
   for email in emails:send_reminder_invitation(actor,email,key)
  return {'id':key,'path':'/reminders/share/'+key+'/'}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.get('/api/reminder-shares/{key}')
def get_reminder_share(key:str,request:Request):
 actor=account(request)
 try:
  with auth.connect() as db:return {**reminder_sharing.summary(db,key,actor),'generation':calendar_archives.generation(db,actor['account_id'])}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/reminder-shares/{key}')
async def reminder_share_action(key:str,request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose a sharing action.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,actor['account_id'],request.headers.get('x-calendar-generation'));email=reminder_sharing.action(db,key,actor,data)
   if email:send_reminder_invitation(actor,email,key)
  return {'ok':True}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

def send_calendar_mail(actor,recipient,action,key,name):
 origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
 mail=EmailMessage();mail['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');mail['To']=recipient
 mail['Subject']='Calendar sharing invitation' if action=='invited' else 'Calendar no longer shared'
 mail.set_content((actor['display_name']+' invited you to '+name+'.\nJoin Calendar: '+origin+'/calendar/share/'+key+'/') if action=='invited' else name+' is no longer shared with you.')
 deliver_message(mail)

def deliver_calendar_jobs(jobs):
 origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
 for email,subject,text,path in jobs:
  mail=EmailMessage();mail['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');mail['To']=email;mail['Subject']=subject
  mail.set_content(text+('\n\n'+origin+path if path else ''));deliver_message(mail)

@app.get('/api/event-occurrence/{item_id}')
def event_occurrence(item_id:str,request:Request,occurrence:str|None=None):
 actor=account(request)
 try:
  with auth.connect() as db:
   item=next((e for e in calendar_sharing.visible(db,actor,'events') if e['id']==item_id),None)
   if not item:raise HTTPException(404,'Event not found.')
   if occurrence is None:
    occurrence=next(calendar_time.candidate_dates(item,calendar_time.date.fromisoformat(item['start'][:10]),calendar_time.date.max),None)
    if occurrence is None:raise HTTPException(404,'No remaining occurrence is available.')
    occurrence=occurrence.isoformat()
   selected=calendar_time.instance(item,occurrence)
   return {**selected,'_edit_occurrence':item.get('_recurrence_date',occurrence),
           '_end_timestamp':calendar_time.end_timestamp(selected,calendar_time.account_zone(db,actor['account_id']))}
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/calendar-time-settings')
def calendar_time_settings(request:Request,include_zones:bool=True):
 actor=account(request)
 with auth.connect() as db:return {'timezone':calendar_time.account_zone(db,actor['account_id']),'zones':calendar_time.zones() if include_zones else []}

@app.get('/api/reminder-preferences')
def reminder_preferences(request:Request):
 actor=account(request)
 with auth.connect() as db:return alarms.preferences(db,actor['account_id'])

@app.put('/api/reminder-preferences')
async def save_reminder_preferences(request:Request):
 actor=account(request)
 try:
  data=await request.json()
  with auth.connect() as db:return alarms.save_preferences(db,actor['account_id'],data)
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/alarms')
def alarm_schedule(request:Request):
 actor=account(request)
 with auth.connect() as db:return alarms.schedule(db,actor)

@app.post('/api/alarms/{alarm_id}')
async def alarm_action(alarm_id:str,request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose a valid reminder action.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   return alarms.act(db,actor,alarm_id,data.get('action'),minutes=data.get('minutes'))
 except FileNotFoundError as exc:raise HTTPException(410,str(exc))
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.get('/api/calendar-view')
def calendar_view(request:Request,start:str,end:str,time_zone_support:bool=False):
 actor=account(request)
 try:
  with auth.connect() as db:
   zone=calendar_time.account_zone(db,actor['account_id'])
   events=calendar_sharing.visible(db,actor,'events')
   formats=event_invitations.preferences(db,actor['account_id'])
   return {'timezone':zone,'days':calendar_time.project(events,start,end,zone,time_zone_support,formats)}
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/calendar-preferences')
def calendar_preferences(request:Request):
 actor=account(request)
 with auth.connect() as db:return {**event_invitations.preferences(db,actor['account_id']),'send_from':actor['email_normalized']}

@app.put('/api/calendar-preferences')
async def update_calendar_preferences(request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose calendar settings.')
  with auth.connect() as db:return event_invitations.save_preferences(db,owner,data)
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/event-invitations/{token}')
def event_invitation(token:str,request:Request):
 actor=account(request)
 try:
  with auth.connect() as db:return event_invitations.summary(db,token,actor)
 except (ValueError,LookupError,PermissionError) as exc:raise sharing_error(exc)

@app.post('/api/event-invitations/{token}')
async def event_invitation_reply(token:str,request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose an invitation response.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');jobs=event_invitations.reply(db,token,actor,data.get('status'));deliver_calendar_jobs(jobs)
  return {'ok':True}
 except (ValueError,LookupError,PermissionError) as exc:raise sharing_error(exc)

@app.get('/api/calendar-inbox')
def calendar_inbox(request:Request):
 actor=account(request)
 with auth.connect() as db:return {**calendar_sharing.inbox(db,actor),'events':event_invitations.inbox(db,actor),'generation':calendar_archives.generation(db,actor['account_id'])}

@app.get('/api/calendar-shares/{key}')
def calendar_share_summary(key:str,request:Request):
 actor=account(request)
 try:
  with auth.connect() as db:return {**calendar_sharing.summary(db,key,actor),'generation':calendar_archives.generation(db,actor['account_id'])}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/calendar-shares')
async def configure_calendar_share(request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Enter calendar sharing details.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,actor['account_id'],request.headers.get('x-calendar-generation'))
   result,mail=calendar_sharing.configure(db,actor,data)
   for email,action,key,name in mail:
    if event_invitations.wants_email(db,email):send_calendar_mail(actor,email,action,key,name)
  return result
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/calendar-shares/{key}')
async def calendar_share_action(key:str,request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose a calendar sharing action.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,actor['account_id'],request.headers.get('x-calendar-generation'))
   if data.get('action')=='email-public':
    share,person=calendar_sharing.access(db,key,actor)
    if person or not share['public_token']:raise PermissionError('Only the owner can send this public calendar.')
    addresses=data.get('recipients')
    if not isinstance(addresses,list) or not 1<=len(addresses)<=30:raise ValueError('Enter recipient email addresses.')
    from websitebench.local_clone_auth.store import _normalize_email
    try:addresses=list({_normalize_email(v) for v in addresses})
    except AuthError:raise ValueError('Enter valid email addresses.')
    origin=os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/')
    for email in addresses:
     mail=EmailMessage();mail['From']=os.environ.get('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test');mail['To']=email;mail['Subject']='Public calendar invitation'
     mail.set_content('View the public calendar:\n'+origin+'/api/calendar-public/'+share['public_token']+'.ics');deliver_message(mail)
   else:calendar_sharing.act(db,actor,key,data.get('action'))
  return {'ok':True}
 except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)

def event_attachment_response(row):
 return Response(bytes(row['content']),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['name'],safe=''),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.post('/api/event-attachments/upload')
async def upload_event_attachment(request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose an attachment.')
  with auth.connect() as db:return event_attachments.upload(db,actor,data)
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/event-attachments/{identifier}/download')
def event_attachment_download(identifier:str,request:Request,event:str|None=None):
 actor=account(request)
 try:
  with auth.connect() as db:return event_attachment_response(event_attachments.download(db,actor,identifier,event))
 except (LookupError,PermissionError) as exc:raise sharing_error(exc)

@app.get('/api/calendar-public/{token}/events/{event_id}/attachments/{identifier}')
def public_event_attachment(token:str,event_id:str,identifier:str):
 try:
  with auth.connect() as db:return event_attachment_response(event_attachments.public_download(db,token,event_id,identifier))
 except LookupError as exc:raise HTTPException(404,str(exc))

@app.get('/api/calendar-public/{token}.ics')
def public_calendar_feed(token:str):
 try:
  with auth.connect() as db:content=calendar_sharing.public_feed(db,token,os.environ.get('BASE_URL','http://127.0.0.1:18110').rstrip('/'))
  return Response(content,media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="calendar.ics"','Cache-Control':'no-store'})
 except LookupError as exc:raise HTTPException(404,str(exc))

@app.get('/api/calendars/archives')
def calendar_archive_versions(request:Request):
 owner=account(request)['account_id']
 with auth.connect() as db:return {'archives':calendar_archives.versions(db,owner),'generation':calendar_archives.generation(db,owner)}

@app.post('/api/calendars/restore')
async def restore_calendar_version(request:Request):
 actor=account(request)
 try:
  data=await request.json()
  if not isinstance(data,dict) or not isinstance(data.get('id'),str):raise ValueError('Choose a calendar archive.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   return calendar_archives.restore(db,actor,data['id'],request.headers.get('x-calendar-generation'),int(time.time()*1000))
 except (ValueError,LookupError,FileExistsError) as exc:raise sharing_error(exc)

@app.post('/api/reminders/clear-completed')
async def clear_completed_reminders(request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Choose a reminder list.')
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,owner,request.headers.get('x-calendar-generation'))
   resource_owner,list_id,_,_=reminder_sharing.locate_list(db,account(request),data.get('list'))
   calendar_archives.snapshot(db,resource_owner,int(time.time()*1000));count=reminders.clear_completed(db,resource_owner,list_id,int(time.time()))
  return {'ok':True,'deleted':count}
 except ValueError as exc:raise HTTPException(400,str(exc))
 except LookupError as exc:raise HTTPException(404,str(exc))
 except PermissionError as exc:raise HTTPException(403,str(exc))
 except FileExistsError as exc:raise HTTPException(409,str(exc))

@app.get('/api/items/{kind}')
def list_items(kind:str,request:Request):
 owner=account(request)['account_id']
 if kind not in KINDS:raise HTTPException(404)
 if kind in ('photos','albums'):purge_expired_photos(owner)
 if kind in ('files','documents'):purge_expired_files(owner)
 if kind=='notes':purge_expired_notes(owner)
 with auth.connect() as db:
  if kind in ('notes','folders'):return {'items':note_sharing.list_items(db,account(request),kind)}
  if kind in ('lists','reminders'):return {'items':reminder_sharing.visible(db,account(request),kind),'generation':calendar_archives.generation(db,owner)}
  if kind in ('calendars','events'):return {'items':calendar_sharing.visible(db,account(request),kind),'generation':calendar_archives.generation(db,owner)}
  rows=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? ORDER BY updated_at,id',(owner,kind)).fetchall()
 return {'items':[json.loads(r[0]) for r in rows]}
@app.get('/api/items/{kind}/{item_id}')
def get_item(kind:str,item_id:str,request:Request):
 owner=account(request)['account_id']
 if kind in ('photos','albums'):purge_expired_photos(owner)
 if kind in ('files','documents'):purge_expired_files(owner)
 if kind=='notes':purge_expired_notes(owner)
 with auth.connect() as db:
  if kind in ('calendars','events'):
   value=next((v for v in calendar_sharing.visible(db,account(request),kind) if v['id']==item_id),None)
   if value is None:raise HTTPException(404,'Item not found')
   return value
  if kind in ('notes','folders','lists','reminders'):
   values=note_sharing.list_items(db,account(request),kind) if kind in ('notes','folders') else reminder_sharing.visible(db,account(request),kind)
   result=next((v for v in values if v['id']==item_id),None)
   if result is None:raise HTTPException(404,'Item not found')
   return result
  row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,item_id)).fetchone()
 if not row:raise HTTPException(404,'Item not found')
 return json.loads(row[0])
@app.api_route('/api/items/{kind}/{item_id}',methods=['PUT','DELETE'])
async def write_item(kind:str,item_id:str,request:Request):
 owner=account(request)['account_id']
 if kind not in KINDS or len(item_id)>120:raise HTTPException(400)
 if kind=='devices':raise HTTPException(403,'Device identity and capabilities cannot be edited here.')
 if kind=='settings' and item_id=='calendar':raise HTTPException(403,'Use calendar settings to change notification preferences.')
 if kind=='settings' and item_id=='profile':raise HTTPException(403,'Use account settings to update your profile.')
 if kind=='lists' and item_id.startswith(reminder_sharing.PREFIX):raise HTTPException(403,'Only the owner can change or delete this list. Use Leave List to stop participating.')
 if kind=='calendars' and item_id.startswith(calendar_sharing.PREFIX):raise HTTPException(403,'Only the owner can change this calendar.')
 if kind=='events':
  try:
   data=await request.json() if await request.body() else {}
   if not isinstance(data,dict) or len(json.dumps(data))>200000:raise ValueError('Invalid event.')
   with auth.connect() as db:
    db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,owner,request.headers.get('x-calendar-generation'))
    jobs=[];item=calendar_sharing.write_event(db,account(request),item_id,data,int(time.time()),delete=request.method=='DELETE',mail=jobs)
    if '_prompt_event_updates' in data:
     event_invitations.save_preferences(db,owner,{'prompt_event_updates':data['_prompt_event_updates']})
    deliver_calendar_jobs(jobs)
   return {'ok':True,'item':item}
  except FileNotFoundError as exc:raise HTTPException(410,str(exc))
  except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)
 if kind=='reminders':
  try:
   data={} if request.method=='DELETE' else await request.json()
   if not isinstance(data,dict) or len(json.dumps(data))>200000:raise ValueError('Invalid reminder.')
   with auth.connect() as db:
    db.execute('BEGIN IMMEDIATE');calendar_archives.check_generation(db,owner,request.headers.get('x-calendar-generation'));item=reminder_sharing.write(db,account(request),item_id,data,int(time.time()),delete=request.method=='DELETE')
   return {'ok':True,'item':item}
  except FileNotFoundError as exc:raise HTTPException(410,str(exc))
  except (ValueError,LookupError,PermissionError,FileExistsError) as exc:
   raise sharing_error(exc)
 if kind in ('notes','folders') and item_id.startswith(note_sharing.PREFIX):
  try:
   data={} if request.method=='DELETE' else await request.json()
   if not isinstance(data,dict) or len(json.dumps(data))>200000:raise ValueError('Invalid note.')
   with auth.connect() as db:
    db.execute('BEGIN IMMEDIATE')
    item=note_sharing.update_shared(db,account(request),kind,item_id,data,int(time.time()),delete=request.method=='DELETE')
   return {'ok':True,'item':item}
  except (ValueError,LookupError,PermissionError,FileExistsError) as exc:raise sharing_error(exc)
 if kind=='photos':purge_expired_photos(owner)
 if kind in ('files','documents'):purge_expired_files(owner)
 if kind=='notes':purge_expired_notes(owner)
 contact_change=kind in ('contacts','contact_lists') or (kind=='settings' and item_id=='contacts')
 with auth.connect() as db:
  if request.method=='DELETE':
   db.execute('BEGIN IMMEDIATE')
   if kind in calendar_archives.KINDS:
    try:calendar_archives.check_generation(db,owner,request.headers.get('x-calendar-generation'))
    except FileExistsError as exc:raise HTTPException(409,str(exc))
    calendar_archives.snapshot(db,owner,int(time.time()*1000))
   if contact_change:
    try:contact_archives.check_generation(db,owner,request.headers.get('x-contacts-generation'))
    except ValueError as exc:raise HTTPException(409,str(exc))
    contact_archives.snapshot(db,owner,int(time.time()*1000))
   old=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,item_id)).fetchone()
   if not old:raise HTTPException(404,'Item not found')
   if kind=='notes':db.execute('INSERT OR IGNORE INTO icloud_entity_tombstones VALUES (?,?,?,?)',(owner,kind,item_id,int(time.time())))
   if kind=='calendars':
    if len(reminders.rows(db,owner,'calendars'))<=1:raise HTTPException(400,'Keep at least one calendar.')
    calendar_sharing.revoke(db,account(request),item_id)
    for event in reminders.rows(db,owner,'events').values():
     if event.get('calendar')==item_id:
      deliver_calendar_jobs(event_invitations.sync(db,owner,None,event,int(time.time())))
      reminders.delete(db,owner,'events',event['id'],int(time.time()))
    reminders.delete(db,owner,'calendars',item_id,int(time.time()));removed=[]
   elif kind in ('lists','reminders'):
    reminders.delete(db,owner,kind,item_id,int(time.time()));removed=[]
   elif kind=='folders':
    try:note_folders.delete_folder(db,owner,item_id,int(time.time()))
    except ValueError as exc:raise HTTPException(400,str(exc))
    removed=[]
   elif kind in ('files','documents'):
    file_lifecycle.apply(db,owner,kind,[item_id],'trash',int(time.time()))
    removed=file_lifecycle.apply(db,owner,kind,[item_id],'delete',int(time.time()))
   else:
    db.execute('DELETE FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,item_id))
    removed=[json.loads(old[0])]
   if kind in ('notes','folders'):note_sharing.revoke_deleted(db,owner)
   if kind=='photos':remove_photo_references(db,owner,item_id)
   if kind=='contacts':contacts.remove_references(db,owner,[item_id],int(time.time()))
   db.commit()
   for item in removed:remove_uploaded_bytes(item)
  else:
   try:data=await request.json()
   except ValueError:raise HTTPException(400,'Invalid item.')
   if not isinstance(data,dict) or len(json.dumps(data))>200000:raise HTTPException(400)
   db.execute('BEGIN IMMEDIATE')
   if kind in calendar_archives.KINDS:
    try:calendar_archives.check_generation(db,owner,request.headers.get('x-calendar-generation'))
    except FileExistsError as exc:raise HTTPException(409,str(exc))
    calendar_archives.snapshot(db,owner,int(time.time()*1000))
   if contact_change:
    try:contact_archives.check_generation(db,owner,request.headers.get('x-contacts-generation'))
    except ValueError as exc:raise HTTPException(409,str(exc))
    contact_archives.snapshot(db,owner,int(time.time()*1000))
   if kind in ('notes','folders','lists','reminders','calendars','events') and db.execute('SELECT 1 FROM icloud_entity_tombstones WHERE owner=? AND kind=? AND id=?',(owner,kind,item_id)).fetchone():raise HTTPException(410,'This item was permanently deleted.')
   old=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,item_id)).fetchone()
   previous=json.loads(old[0]) if old else {}
   if kind in ('notes','folders'):
    if kind=='notes' and previous and (data.get('_revision') is not None or note_sharing.inherited(db,owner,kind,item_id)):
     if data.get('_revision')!=note_sharing.revision(previous):raise HTTPException(409,'This note changed. Reload before saving your changes.')
    for key in ('_revision','_share','_original_id','_modified'):data.pop(key,None)
    if kind=='notes' and previous:
     if 'pinned' in previous:data['pinned']=previous['pinned']
     else:data.pop('pinned',None)
   if kind in ('lists','calendars'):data.pop('_sharing',None);data.pop('_original_id',None)
   contact_list=data.pop('contact_list',None) if kind=='contacts' else None
   if contact_list is not None:
    if not isinstance(contact_list,str) or not db.execute("SELECT 1 FROM icloud_entities WHERE owner=? AND kind='contact_lists' AND id=?",(owner,contact_list)).fetchone():raise HTTPException(400,'List not found.')
   if kind=='photos' and item_id.startswith('photo-') and not old:raise HTTPException(403,'Photo belongs to another account')
   if data.get('blob')!=previous.get('blob'):raise HTTPException(400,'File contents must be uploaded')
   try:
    if kind=='folders':note_folders.validate_folder(db,owner,item_id,data,previous)
    if kind=='notes':note_folders.validate_note(db,owner,data,previous)
    if kind=='contacts':contacts.validate_contact(data,previous,int(time.time()))
    if kind in ('lists','calendars'):reminders.validate_list(data,previous)
    if kind=='reminders':
     reminders.validate(db,owner,data,previous,int(time.time()))
     reminders.repeat_after_completion(db,owner,data,previous,int(time.time()))
    if kind=='settings' and item_id=='preferences':
     data['timezone']=calendar_time.validate_zone(data.get('timezone',previous.get('timezone','America/Toronto')),False)
    if kind=='contact_lists':contacts.validate_list(db,owner,item_id,data)
    if kind=='settings' and item_id=='contacts' and data.get('my_card'):
     if not isinstance(data['my_card'],str) or not db.execute("SELECT 1 FROM icloud_entities WHERE owner=? AND kind='contacts' AND id=?",(owner,data['my_card'])).fetchone():raise ValueError('Contact not found.')
   except ValueError as exc:raise HTTPException(400,str(exc))
   if kind in ('files','documents'):
    if kind=='documents':
     if not previous.get('_editor') and any(k in data for k in ('_editor','_editor_revision')):raise HTTPException(400,'Create editable documents through the document editor.')
     if previous.get('_editor'):
      data['_editor']=previous['_editor']
      data['_editor_revision']=previous['_editor_revision']+1
      if data.get('folder'):raise HTTPException(400,'A document cannot become a folder.')
     if data.get('app') not in ('pages','numbers','keynote'):raise HTTPException(400,'Choose a document application.')
     if previous and data['app']!=previous.get('app'):raise HTTPException(400,'A document cannot change applications.')
     if data.get('parent'):
      parent=file_lifecycle.records(db,owner,kind).get(data['parent'])
      if not parent or parent.get('app')!=data['app']:raise HTTPException(400,'Choose a folder in this application.')
    # Download identity belongs to the server; renaming or moving cannot point
    # an entity at a different account's upload.
    for field in ('blob','size','type'):
     if field in previous:data[field]=previous[field]
     elif field=='blob':data.pop(field,None)
    if bool(data.get('deleted'))!=bool(previous.get('deleted')):raise HTTPException(400,'Use the file deletion or recovery action.')
    try:file_lifecycle.validate_parent(file_lifecycle.records(db,owner,kind),item_id,data.get('parent'))
    except ValueError as exc:raise HTTPException(400,str(exc))
    for field in ('deleted_at','deleted_group'):
     data.pop(field,None)
     if field in previous:data[field]=previous[field]
   if kind=='notes':
    if previous.get('deleted') and not data.get('deleted'):raise HTTPException(409,'Recover this note before editing it.')
    if previous.get('deleted') and data.get('deleted') and any(data.get(field)!=previous.get(field) for field in ('title','body','html','folder','pinned')):raise HTTPException(409,'Recover this note before editing it.')
   if kind in ('photos','notes'):
    if data.get('deleted'):data['deleted_at']=previous.get('deleted_at') if previous.get('deleted') and previous.get('deleted_at') else int(time.time())
    else:data.pop('deleted_at',None)
   data['id']=item_id
   if kind=='notes' and data.get('deleted') and not previous.get('deleted'):note_sharing.clear_pin(db,owner,owner,item_id)
   if kind=='folders':note_sharing.revoke_moved(db,owner,kind,item_id,previous,data.get('parent'))
   db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?) ON CONFLICT(owner,kind,id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(owner,kind,item_id,json.dumps(data),int(time.time())))
   if contact_list is not None:contacts.action(db,owner,{'action':'add','list':contact_list,'ids':[item_id]},int(time.time()))
   if kind in ('notes','folders'):
    note_sharing.revoke_deleted(db,owner)
    visible=note_sharing.decorate(data,note_sharing.inherited(db,owner,kind,item_id),kind=kind)
    if kind=='notes':note_sharing.personalize_pin(db,owner,owner,visible)
    return {'ok':True,'item':visible}
   if kind in ('lists','reminders'):return {'ok':True,'item':data}
 return {'ok':True}

@app.post('/api/work')
async def create_work(request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   return work_documents.create(db,owner,data)
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/work/import')
async def import_work(request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  if not isinstance(data,dict) or data.get('app') not in work_documents.APPS:raise ValueError('Choose a local document backup.')
  body=work_documents.clean_body(data['app'],data.get('body'))
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   item=work_documents.create(db,owner,data)
   return work_documents.save(db,owner,item['id'],{'body':body,'name':item['name'],'revision':1})
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/work/{item_id}/versions')
def work_versions(item_id:str,request:Request):
 owner=account(request)['account_id']
 try:
  with auth.connect() as db:return {'versions':work_documents.versions(db,owner,item_id)}
 except LookupError as exc:raise HTTPException(404,str(exc))

@app.post('/api/work/{item_id}/restore')
async def restore_work(item_id:str,request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');return work_documents.restore(db,owner,item_id,data)
 except LookupError as exc:raise HTTPException(404,str(exc))
 except FileExistsError as exc:raise HTTPException(409,str(exc))
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/work/{item_id}/duplicate')
def duplicate_work(item_id:str,request:Request):
 owner=account(request)['account_id']
 try:
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE');original=work_documents.load(db,owner,item_id)
   item=work_documents.create(db,owner,{'app':original['app'],'name':original['name'][:250]+' copy','parent':original.get('parent')})
   return work_documents.save(db,owner,item['id'],{'name':item['name'],'body':original['_editor'],'revision':1})
 except LookupError as exc:raise HTTPException(404,str(exc))
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/work/{item_id}')
def get_work(item_id:str,request:Request):
 owner=account(request)['account_id']
 try:
  with auth.connect() as db:return work_documents.load(db,owner,item_id)
 except LookupError as exc:raise HTTPException(404,str(exc))

@app.put('/api/work/{item_id}')
async def save_work(item_id:str,request:Request):
 owner=account(request)['account_id']
 try:
  data=await request.json()
  with auth.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   return work_documents.save(db,owner,item_id,data)
 except LookupError as exc:raise HTTPException(404,str(exc))
 except FileExistsError as exc:raise HTTPException(409,str(exc))
 except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/files/upload')
async def upload_file(request:Request):
 owner=account(request)['account_id'];data=await request.json()
 if not isinstance(data,dict):raise HTTPException(400,'Choose a file to upload.')
 work=data.get('app')
 if work is not None and work not in ('pages','numbers','keynote'):raise HTTPException(400,'Choose a document application.')
 if work and data.get('photo'):raise HTTPException(400,'Choose one upload destination.')
 try:content=base64.b64decode(data.get('content',''),validate=True)
 except (ValueError,binascii.Error,TypeError):raise HTTPException(400,'Invalid file contents')
 if not content or len(content)>20*1024*1024:raise HTTPException(400,'Choose a file smaller than 20 MB')
 item_id=uuid.uuid4().hex;name=Path(str(data.get('name','Untitled'))).name[:200];kind='photos' if data.get('photo') else 'documents' if work else 'files'
 item={'id':item_id,'name':name,'blob':item_id,'type':str(data.get('type','application/octet-stream'))[:100],'size':len(content),'deleted':False,'modified':time.strftime('%Y-%m-%d')}
 if work:item['app']=work
 if kind=='photos':
  if item['type'] not in ('image/jpeg','image/png','image/webp','image/gif','image/avif'):raise HTTPException(400,'Choose a JPEG, PNG, WebP, GIF or AVIF image')
  item.update({'order':-int(time.time()),'date':time.strftime('%Y-%m-%dT%H:%M:%SZ'),'favorite':False,'hidden':False,'src':'/api/files/'+item_id+'/download','subtype':0})
 else:
  parent=data.get('parent')
  if parent:
   with auth.connect() as db:row=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=? AND id=?',(owner,kind,parent)).fetchone()
   if not row or not json.loads(row[0]).get('folder') or json.loads(row[0]).get('deleted'):raise HTTPException(400,'Folder not found')
   if work and json.loads(row[0]).get('app')!=work:raise HTTPException(400,'Choose a folder in this application.')
   item['parent']=parent
 folder=backend.lifecycle.database_path.parent/'uploads';folder.mkdir(exist_ok=True)
 (folder/item_id).write_bytes(content)
 with auth.connect() as db:db.execute('INSERT INTO icloud_entities VALUES (?,?,?,?,?)',(owner,kind,item_id,json.dumps(item),int(time.time())))
 return item

@app.get('/api/files/{item_id}/download')
def download_file(item_id:str,request:Request):return file_response(item_id,request,False)

@app.get('/api/files/{item_id}/preview')
def preview_file(item_id:str,request:Request):return file_response(item_id,request,True)

def file_response(item_id,request,preview):
 owner=account(request)['account_id']
 purge_expired_photos(owner)
 purge_expired_files(owner)
 with auth.connect() as db:row=db.execute('SELECT payload,kind FROM icloud_entities WHERE owner=? AND id=? AND kind IN (?,?,?)',(owner,item_id,'files','photos','documents')).fetchone()
 if not row:raise HTTPException(404,'File not found')
 item=json.loads(row[0]);blob=item.get('blob','')
 if item.get('deleted') and row['kind']!='photos':raise HTTPException(404,'Recover this file before opening it.')
 if row['kind']=='documents' and item.get('_editor'):
  try:content,media_type,extension=work_documents.export(item,int(request.query_params.get('sheet','0')))
  except ValueError as exc:raise HTTPException(400,str(exc))
  filename=quote(item['name']+extension,safe='')
  return Response(content,media_type=media_type,headers={'Content-Disposition':('inline' if preview else 'attachment')+"; filename*=UTF-8''"+filename})
 if not blob or Path(blob).name!=blob:raise HTTPException(404,'File not found')
 path=backend.lifecycle.database_path.parent/'uploads'/blob
 if not path.is_file():
  path=ROOT/'fixtures/files'/blob
 if not path.is_file():raise HTTPException(404,'File not found')
 media_type=item.get('type','application/octet-stream')
 if preview and media_type not in ('application/pdf','image/jpeg','image/png','image/webp','image/gif','image/avif','text/plain'):raise HTTPException(415,'Preview is unavailable for this file type')
 return FileResponse(path,media_type=media_type,filename=item.get('name','Document'),content_disposition_type='inline' if preview else 'attachment')

@app.get('/boundary/')
def boundary(target:str='',collection:str='',item:str='',back:str='/',reason:str=''):
 if not back.startswith('/') or back.startswith('//') or '\\' in back or any(ord(c)<32 for c in back):back='/'
 message='This page is pending implementation in this local edition.' if reason=='deferred' else 'This is a regional version of the same iCloud user guide. This local edition includes the captured English guide.' if reason=='language' else 'This Apple product is outside the iCloud product scope.' if target else 'This item is beyond the first five details in this collection.'
 return HTMLResponse('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>iCloud</title><link rel="stylesheet" href="/static/app.css"></head><body data-boundary-page><header><a href="/home/">iCloud</a></header><main class="boundary"><h1>'+escape(item or 'iCloud')+'</h1><p>'+escape(collection or 'Apple')+'</p><p>'+message+'</p><p>'+escape(target)+'</p><a href="'+escape(back,quote=True)+'">Back</a></main><footer><a href="/help/welcome/">iCloud User Guide</a></footer></body></html>')
@app.get('/account/region/')
def account_region(request:Request):
 back=request.query_params.get('return','/account/create/')
 if back not in ('/account/create/','/account/recovery/','/account/'):back='/account/create/'
 choices=json.loads((ROOT/'static/auth-choices.json').read_text())['countries']
 links=''.join('<a href="'+back+'?region='+quote(row['value'])+'">'+escape(row['label'])+'</a>' for row in choices)
 return HTMLResponse('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Choose your country or region - Apple Account</title><link rel="stylesheet" href="/static/app.css"></head><body><header><a href="/account/">Apple Account</a><a href="'+back+'">Back</a></header><main class="account-region"><h1>Choose your country or region</h1><input type="search" aria-label="Search countries and regions" placeholder="Search countries and regions"><nav class="region-list" aria-label="Countries and regions">'+links+'</nav></main><script src="/static/account-region.js"></script></body></html>')

@app.get('/help/search/')
def search(q:str='',query:str='',bookid:str=''):
 q=q or query
 guides={'icloud':('iCloud User Guide','/help/welcome/'), 'icloud-windows':('iCloud for Windows User Guide','/help/windows/')}
 for name in ('pages','numbers','keynote'):
  key=name+'-icloud'
  entry=next((p for p,d in PUBLIC.items() if d.get('guide')==key and 'User Guide for iCloud' in d['title']),None)
  if entry:guides[key]=(name.title()+' for iCloud User Guide',entry)
 results=[(p,d) for p,d in PUBLIC.items() if (p.startswith(('/help/','/account/help/')) or d.get('guide') in guides) and q.lower() in d['text'].lower() and (bookid not in guides or d.get('guide')==bookid)]
 guide_title,guide_path=guides.get(bookid,guides['icloud'])
 hidden='<input type="hidden" name="bookid" value="'+bookid+'">' if bookid in guides else ''
 return HTMLResponse('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/app.css"><title>Search '+guide_title+'</title></head><body><header><a href="'+guide_path+'">'+guide_title+'</a></header><main class="boundary"><form>'+hidden+'<input name="q" aria-label="Search" value="'+escape(q,quote=True)+'"><button>Search</button></form>'+''.join('<p><a href="'+p+'">'+escape(d['title'])+'</a></p>' for p,d in results)+'</main></body></html>')

@app.post('/api/help/feedback')
async def help_feedback(request:Request):
 try:data=await request.json()
 except ValueError:raise HTTPException(400,'Enter article feedback.')
 if not isinstance(data,dict):raise HTTPException(400,'Enter article feedback.')
 path=data.get('page');comment=data.get('comment','')
 if not isinstance(path,str) or path not in PUBLIC or not path.startswith('/help/') or not isinstance(data.get('helpful'),bool):raise HTTPException(400,'Choose an iCloud help article and a rating.')
 if not isinstance(comment,str) or len(comment)>250:raise HTTPException(400,'Maximum character limit is 250.')
 token,_=auth.ensure_session(request.cookies.get(COOKIE));owner=auth.session_owner_digest(token)
 with auth.connect() as db:db.execute('INSERT OR REPLACE INTO icloud_help_feedback VALUES (?,?,?,?,?)',(owner,path,int(data['helpful']),comment,int(time.time())))
 return set_session(JSONResponse({'ok':True}),token)
@app.get('/{path:path}')
def page(path:str,request:Request):
 route='/'+path
 suffix=('?'+request.url.query) if request.url.query else ''
 if route.rstrip('/')=='/drive':return RedirectResponse('/iclouddrive/'+suffix,status_code=303)
 if not route.endswith('/') and (route+'/' in PUBLIC or route.split('/')[1] in {'signin','home','photos','iclouddrive','contacts','calendar','notes','reminders','pages','numbers','keynote','find','settings','plan','storage','recovery','detail','account'}):return RedirectResponse(route+'/'+suffix,status_code=303)
 if route in ('/signin/','/account/create/','/account/recovery/'):return shell()
 if route=='/settings/account/':return RedirectResponse('/account/',status_code=303)
 if route in PUBLIC:return HTMLResponse((ROOT/'public'/PUBLIC[route]['file']).read_text())
 if route in PUBLIC_ALIASES:return RedirectResponse(PUBLIC_ALIASES[route],status_code=303)
 if route in DEFERRED:return boundary(target=DEFERRED[route],reason='deferred',back='/help/welcome/')
 if route.startswith(('/home','/photos','/iclouddrive','/contacts','/calendar','/notes','/reminders','/pages','/numbers','/keynote','/find','/settings','/plan','/storage','/recovery','/detail','/account/manage')):
  session=auth.resolve_session(request.cookies.get(COOKIE))
  if not session or not session['authenticated']:return RedirectResponse('/signin/?return='+quote(route+suffix,safe=''),status_code=303)
  if route=='/iclouddrive/folder/downloads/':return RedirectResponse('/iclouddrive/browse/?folder=downloads',status_code=303)
  if route.startswith('/detail/'):return detail_route(route,session['account']['account_id'])
  return shell()
 return HTMLResponse('<h1>iCloud</h1><p>This page is pending implementation.</p><a href="/">Home</a>',status_code=503)

def detail_route(route,owner):
 parts=route.strip('/').split('/')
 if len(parts)!=3 or not parts[2].isdigit():raise HTTPException(404,'Detail not found')
 listing=parts[1];position=int(parts[2])
 if position<1 or position>5:raise HTTPException(404,'Detail not found')
 kind='photos' if listing.startswith('photos-') else {'drive-recents':'files','contacts':'contacts','notes-all':'notes','notes-folder':'notes','find-devices':'devices'}.get(listing)
 if listing=='photos-albums':kind='albums'
 if not kind:raise HTTPException(404,'Collection not found')
 with auth.connect() as db:rows=db.execute('SELECT payload FROM icloud_entities WHERE owner=? AND kind=?',(owner,kind)).fetchall()
 records=[json.loads(row[0]) for row in rows];records=[r for r in records if not r.get('deleted')]
 records.sort(key=lambda r:r.get('order',0))
 photo_paths={'photos-library':'/photos/','photos-recents':'/photos/recents/','photos-favorites':'/photos/favorites/','photos-videos':'/photos/media/videos/','photos-live':'/photos/media/live/','photos-portrait':'/photos/media/portrait/','photos-panoramas':'/photos/media/panoramas/','photos-screenshots':'/photos/media/screenshots/','photos-animated':'/photos/media/animated/'}
 if kind=='photos':
  records=[r for r in records if not r.get('hidden')]
  if listing=='photos-favorites':records=[r for r in records if r.get('favorite')]
  elif listing=='photos-videos':records=[r for r in records if any(t in r.get('type','') for t in ('movie','video','mpeg-4'))]
  elif listing in ('photos-live','photos-panoramas','photos-screenshots'):records=[r for r in records if r.get('subtype')=={'photos-live':2,'photos-panoramas':1,'photos-screenshots':3}[listing]]
  elif listing=='photos-portrait':records=[r for r in records if r.get('portrait')]
  elif listing=='photos-animated':records=[r for r in records if 'gif' in r.get('type','')]
 elif kind=='files':records=[r for r in records if not r.get('folder')]
 elif listing=='notes-folder':records=[r for r in records if r.get('folder')=='notes']
 if len(records)<position:raise HTTPException(404,'Detail not found')
 item=quote(records[position-1]['id'],safe='')
 if kind=='albums':target='/photos/albums/'+item+'/'
 elif kind=='photos':target=photo_paths.get(listing,'/photos/')+'?item='+item
 elif kind=='devices':target='/find/?device='+item
 else:target='/'+{'files':'iclouddrive','notes':'notes','contacts':'contacts'}[kind]+'/?item='+item
 return RedirectResponse(target,status_code=303)
