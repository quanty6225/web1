"""Persistent application operations, separated from source frontend transport."""
import secrets,hashlib,time,json,datetime
from fastapi import HTTPException
from fastapi.responses import Response
from websitebench.local_clone_auth.store import _hash_secret,_verify_secret
from account_security import handle as security_handle
UNHANDLED=object()
def iso(stamp=None):return datetime.datetime.fromtimestamp(stamp or time.time(),datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','+0000')
def handle(path,method,body,req,a,d,db,auth,save,profile,actorid,password):
 def persist():save(db,a,d)
 def collection(name):return d.setdefault(name,{})
 uid=actorid(a);now=int(time.time());owner=a['account_id']
 if path in ['statistics/general','user/ranking']:
  from statistics_local import statistics
  return statistics(d,a,ranking=path=='user/ranking')
 if path=='statistics/color':return {'project2color':{**{p['name']:p.get('color') for p in d['projects'].values()},'INBOX':None}}
 if path=='payment/isBlacklist':return False
 if path=='payment/order_spec':return [{'count':1,'unit':'year','amount':49.99},{'count':1,'unit':'month','amount':4.99}]
 if path=='user/geoInfo':return {'countryCode':''}
 if path=='giftcard/orders':return list(d.get('giftOrders',{}).values())
 if path=='user-settings/privacy':
  value=d.setdefault('aiPrivacy',{'data_collection_opt_in':True})
  if method!='GET':
   if not isinstance(body.get('data_collection_opt_in'),bool):raise HTTPException(400,'Choose a privacy setting')
   value.update(data_collection_opt_in=body['data_collection_opt_in']);persist()
  return value
 if path=='user/unbinding':
  d.setdefault('providerBindings',{}).pop(req.query_params.get('siteId',''),None);persist();return {}
 if path=='user/regTime':return datetime.datetime.fromtimestamp(a.get('created_at',time.time()),datetime.timezone.utc).strftime('%Y%m%d')
 if path=='user/sendVerifyCode':
  from account_security import challenge
  email=req.query_params.get('email',body.get('email','')).strip().lower()
  if not __import__('re').fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(400,'Invalid email address')
  if db.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=?',(email,)).fetchone():raise HTTPException(409,'Email is already registered')
  ident=challenge(d,email,'change-email');persist();return {'id':ident,'sent':True}
 if path=='user/changeEmail':
  from account_security import verify
  row=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(owner,)).fetchone()
  if not _verify_secret('ticktick:'+body.get('password',''),bytes(row['password_salt']),bytes(row['password_hash'])):raise HTTPException(400,'Current password is incorrect')
  email=str(body.get('email','')).strip().lower();challenge_row=next(reversed(d.get('securityChallenges',{}).values()),None)
  if not challenge_row or challenge_row['recipient']!=email or challenge_row['purpose']!='change-email':raise HTTPException(400,'Verify the new email first')
  if db.execute('SELECT 1 FROM local_auth_accounts WHERE email_normalized=?',(email,)).fetchone():raise HTTPException(409,'Email is already registered')
  try:verify(d,body.get('id',body.get('code','')))
  except HTTPException:persist();db.commit();raise
  db.execute('UPDATE local_auth_accounts SET email_normalized=? WHERE account_id=?',(email,owner));persist();return profile({**a,'email_normalized':email})
 if path in ['user/verify/deleteAccount','user/verify/deleteThirdSiteAccount']:
  from account_security import require_proof
  require_proof(d,req)
  db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=?',(now,owner));db.execute("UPDATE ticktick_shares SET status='revoked' WHERE owner=? OR email=?",(owner,a['email_normalized']));db.execute('DELETE FROM ticktick_actor_state WHERE owner=?',(owner,));db.execute('DELETE FROM local_auth_accounts WHERE account_id=?',(owner,));return {'deleted':True}
 if path.startswith('user/mfa'):return security_handle(path,method,body,req,a,d,db,save,uid)
 if path in ['user/profile','user/profile/name','user/profile/updateFakedName'] and method!='GET':
  name=body.get('name',body.get('displayName',body if isinstance(body,str) else ''))
  if not isinstance(name,str) or not name.strip() or len(name)>128:raise HTTPException(400,'Name must contain 1-128 characters')
  db.execute('UPDATE local_auth_accounts SET display_name=? WHERE account_id=?',(name.strip(),owner));return profile({**a,'display_name':name.strip()})
 if path=='user/changePassword':
  current=body.get('oldpassword',body.get('password',''));new=body.get('newPassword1',body.get('newpassword',body.get('newPassword','')))
  row=db.execute('SELECT * FROM local_auth_accounts WHERE account_id=?',(owner,)).fetchone()
  if not _verify_secret('ticktick:'+current,bytes(row['password_salt']),bytes(row['password_hash'])):raise HTTPException(400,'Current password is incorrect')
  salt,digest=_hash_secret(password(new));db.execute('UPDATE local_auth_accounts SET password_salt=?,password_hash=?,password_updated_at=? WHERE account_id=?',(salt,digest,now,owner))
  current_session=auth._session_row(db,req.cookies.get('ticktick_local_session'))
  db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND session_digest<>?',(now,owner,current_session['session_digest'] if current_session else ''));return {'changed':True}
 if path.startswith('user/preferences/apiToken/'):
  keys=collection('apiKeys');parts=path.split('/');ident=parts[3]
  if ident=='all':return list(keys.values())
  if ident=='create' and method=='POST':
   if len(keys)>=(5 if d.get('subscription',{}).get('ends',0)>time.time() else 1):raise HTTPException(403,{'errorCode':'need_pro'})
   ident=secrets.token_hex(12);keys[ident]={'id':ident,'name':str(body.get('name',''))[:128],'token':'tt_local_'+secrets.token_urlsafe(32),'createdTime':iso()};persist();return keys[ident]
  if ident not in keys:raise HTTPException(404,'API key not found')
  if method=='DELETE':del keys[ident];persist();return {}
  if len(parts)>4 and parts[4]=='name':keys[ident]['name']=str(body.get('name',''))[:128]
  elif len(parts)>4 and parts[4] in ['reset','refresh']:keys[ident]['token']='tt_local_'+secrets.token_urlsafe(32)
  else:return keys[ident]
  persist();return keys[ident]
 if path.startswith('user/session'):
  current=auth._session_row(db,req.cookies.get('ticktick_local_session'));current_id=current['session_digest'] if current else ''
  rows=db.execute('SELECT * FROM local_auth_sessions WHERE account_id=? AND revoked_at IS NULL AND expires_at>?',(owner,now)).fetchall()
  # Expose stable display IDs, never cookie/session digests.
  ids={hashlib.sha256(('device:'+r['session_digest']).encode()).hexdigest()[:24]:r for r in rows}
  if method=='GET':return [{'id':ident,'device':'Local browser','ip':None,'city':None,'createdTime':iso(r['created_at']),'modifiedTime':iso(r['created_at']),'current':r['session_digest']==current_id,'deviceInfo':{'os':'Web','device':'Browser','version':'1','id':ident,'channel':'website','campaign':'','websocket':'','name':'This device' if r['session_digest']==current_id else 'Local browser','platform':'web'}} for ident,r in ids.items()]
  ident=path.rsplit('/',1)[-1]
  if ident=='others':db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND session_digest<>?',(now,owner,current_id))
  elif ident=='all':db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=?',(now,owner))
  elif ident in ids:db.execute('UPDATE local_auth_sessions SET revoked_at=? WHERE account_id=? AND session_digest=?',(now,owner,ids[ident]['session_digest']))
  else:raise HTTPException(404,'Device not found')
  return {}
 if path=='user/mfa/setting':
  mfa=collection('mfa');return {'id':uid,'mfaEnabled':bool(mfa.get('enabled')),'mailOption':{'enabled':bool(mfa.get('mailEnabled'))},'phoneOption':None,'appOption':{'enabled':bool(mfa.get('appEnabled'))},'backupOption':{'enabled':bool(mfa.get('backupCodes'))}}
 if path=='habitSections':return list(collection('habitSections').values())
 if path in ['habits/batch','habitSections/batch','habitCheckins/batch']:
  name={'habits/batch':'habits','habitSections/batch':'habitSections','habitCheckins/batch':'habitCheckins'}[path];records=collection(name);result={'id2etag':{},'id2error':{}}
  for action in ['add','update','delete']:
   for item in body.get(action,[]):
    ident=item if isinstance(item,str) else item.get('id') or secrets.token_hex(12)
    if action=='delete':records.pop(ident,None);continue
    if action=='update' and ident not in records:raise HTTPException(404,'Record not found')
    if name=='habitCheckins' and item.get('habitId') not in collection('habits'):raise HTTPException(404,'Habit not found')
    records[ident]={**records.get(ident,{}),**item,'id':ident,'etag':secrets.token_hex(8)};result['id2etag'][ident]=records[ident]['etag']
  persist();return result
 if path in ['habitCheckins/query','getHabitRecords']:
  ids=body.get('habitIds',[]);name='habitCheckins' if path.startswith('habitCheckins') else 'habitRecords'
  return {'checkins' if name=='habitCheckins' else 'habitRecords':{ident:[x for x in collection(name).values() if x.get('habitId')==ident] for ident in ids}}
 if path=='habitRecords':
  rows=body if isinstance(body,list) else [body];records=collection('habitRecords')
  for item in rows:
   if item.get('habitId') not in collection('habits'):raise HTTPException(404,'Habit not found')
   ident=item.get('id') or secrets.token_hex(12);records[ident]={**item,'id':ident}
  persist();return rows
 if path=='habits/statistics/week/current':
  from statistics_local import habit_week
  return habit_week(d)
 if path=='pomodoro' and method=='POST':
  records=collection('pomodoros');rows=body if isinstance(body,list) else body.get('add',[body])
  for item in rows:
   ident=item.get('id') or secrets.token_hex(12);records[ident]={**item,'id':ident};records[ident].setdefault('createdTime',iso())
  persist();return rows if isinstance(body,list) else records[ident]
 if path in ['pomodoro/all','pomodoro/filter']:return list(collection('pomodoros').values())
 if path.startswith('pomodoro/timing/') or (path.startswith('pomodoro/') and path.count('/')==1 and not path.endswith('/all')):
  name='timings' if path.startswith('pomodoro/timing/') else 'pomodoros';records=collection(name);ident=path.rsplit('/',1)[-1]
  if ident not in records:raise HTTPException(404,'Focus record not found')
  if method=='DELETE':del records[ident];persist();return {}
  return records[ident]
 if path in ['pomodoros/timing','timer'] and method!='GET':
  ident=body.get('id') or secrets.token_hex(12);collection('timings')[ident]={**body,'id':ident};persist();return d['timings'][ident]
 if path in ['data/export','data/export/backup','data/export/pomodoro']:
  payload={'format':'ticktick-local-backup-v1','exportedAt':iso(),'data':{k:v for k,v in d.items() if k in ['tasks','projects','columns','tags','filters','projectGroups','habits','habitRecords','habitCheckins','pomodoros','timings','comments','countdowns','attachments']}}
  return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="ticktick-backup.json"'})
 if path=='project/share/recentProjectUsers':return []
 if path.startswith('project/') and path.endswith('/tasks'):
  pid=path.split('/')[1]
  if pid not in d['projects'] and pid!='inbox'+str(uid):raise HTTPException(404,'List not found')
  return [x for x in d['tasks'].values() if x.get('projectId')==pid and not x.get('deleted')]
 if path in ['subscribe/info','subscribe/status']:
  subscription=d.get('subscription',{});active=subscription.get('ends',0)>time.time()
  return {'userId':uid,'userName':a['email_normalized'],'isPro':active,'needSubscribe':not subscription.get('autoRenew',False),'subscribeFreq':subscription.get('frequency'),'subscribeType':'local-sandbox' if active else None,'oldPrice':None,'price':49.99 if subscription.get('frequency')=='Year' else 4.99 if active else None,'currency':'USD' if active else None,'proEndDate':iso(subscription['ends']) if active else ''}
 if path.startswith('payment/cancel/') or path=='subscribe/cancel':
  d.setdefault('subscription',{})['autoRenew']=False;persist();return {'cancelled':True}
 if path=='payment/history':return list(d.get('orders',{}).values())
 if path=='payment/last':return next(reversed(d.get('orders',{}).values()),None)
 if path in ['subscribe/list','calendar/third/accounts','calendar/bind','calendar/bind/events/all']:return []
 return UNHANDLED
