"""Consenting local team members and shared-calendar Scheduling Link organizers."""
import copy,hashlib,json,re,secrets,smtplib,time,os
from email.message import EmailMessage
from datetime import datetime,timezone
from fastapi import HTTPException

def public_id(account_id):return str(1000000+int(hashlib.sha256(account_id.encode()).hexdigest()[:12],16))

class TeamScheduling:
 def team_owner(self):return self.get('settings','team-membership',{}).get('owner',self.owner)
 def team_accounts(self):
  owner=self.team_owner()
  with self.connect() as c:
   rows=c.execute("SELECT a.* FROM local_auth_accounts a LEFT JOIN reclaim_records r ON r.account_id=a.account_id AND r.kind='settings' AND r.id='team-membership' WHERE a.account_id=? OR json_extract(r.data,'$.owner')=?",(owner,owner)).fetchall()
  return [dict(r) for r in rows]
 def team_admin(self):
  role=self.get('settings','team-membership',{}).get('role','ADMIN')
  if self.owner!=self.team_owner() and role!='ADMIN':raise HTTPException(403,'Only team admins can make this change.')
 def peer(self,account):
  from business import Business
  with self.connect() as c:return Business(c,self.fixtures,account)
 def local_member(self,account):
  value=copy.deepcopy(self.fixtures['/api/team/current']['members'][0]);peer=self if account['account_id']==self.owner else self.peer(account)
  value.update(email=account['email_normalized'],name=account['display_name'],avatarUrl='',membershipRole=peer.get('settings','team-membership',{}).get('role','ADMIN'),status='ACCEPTED',domainName=account['email_normalized'].rsplit('@',1)[1],timezone=peer.profile()['timezone'],schedulingLinkSlug=peer.primary_group()['slug'])
  value['teamMemberId']={'teamId':int(public_id(self.team_owner())),'userId':'100001' if account['account_id']==self.owner else public_id(account['account_id'])}
  return value
 def team_handle(self,key,method,data,query):
  if key in ('/api/participant-resolution','/api/participant-resolution/scheduling-link') and method=='GET':
   result=[];accounts=self.team_accounts()
   for email in str(query.get('emails','')).split(',')[:50]:
    email=email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):continue
    account=next((a for a in accounts if a['email_normalized']==email),None);peer=self.peer(account) if account else None
    person={'email':email,'name':account['display_name'] if account else email,'firstName':account['display_name'] if account else '', 'lastName':'','avatarUrl':'','reclaimUser':bool(account)}
    if account:person['userId']='100001' if account['account_id']==self.owner else public_id(account['account_id'])
    result.append({'participant':person,'timezone':peer.profile()['timezone'] if peer else None,'visibility':'DEFAULT','matchedEmails':[email],'timeSchemes':peer.get('settings','/api/timeschemes',peer.fixtures['/api/timeschemes']) if peer else []})
   return True,result
  if key in ('/api/team/current','/api/team/current/members','/api/team/current/inviteable','/api/team/current/membership') and method=='GET':
   members=[self.local_member(a) for a in self.team_accounts()]
   if key.endswith('/members'):return True,members
   if key.endswith('/inviteable'):return True,[]
   if key.endswith('/membership'):return True,next(x for x in members if x['teamMemberId']['userId']=='100001')
   result=copy.deepcopy(self.fixtures[key]);result.update(id=int(public_id(self.team_owner())),members=members,totalSeatsUsed=len(members),teamSeatsUsed=len(members));result['membershipSummary'].update(joinedCount=len(members),activeCount=len(members));return True,result
  if key in ('/api/team/current/invitations','/api/team/current/invitations/v2'):
   self.team_admin();owner=self.team_owner()
   with self.connect() as c:
    if method=='GET':return True,[{k:v for k,v in json.loads(r[0]).items() if k!='digest'} for r in c.execute("SELECT data FROM reclaim_records WHERE account_id=? AND kind='team-invitation'",(owner,))]
    if method=='POST':
     entries=data if isinstance(data,list) else [{'email':e,'role':data.get('role','USER')} for e in data.get('emails',[])]
     if not 1<=len(entries)<=50:raise HTTPException(422,'Enter 1–50 email addresses.')
     results=[]
     for item in entries:
      email=str(item.get('email','')).lower().strip();role=item.get('role','USER')
      if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or role not in ('USER','ADMIN'):raise HTTPException(422,'Enter a valid email and team role.')
      if any(a['email_normalized']==email for a in self.team_accounts()):raise HTTPException(409,'This person is already on your team.')
      token=secrets.token_urlsafe(32);id='invite_'+secrets.token_hex(12);value={'id':id,'email':email,'role':role,'status':'PENDING','expiresAt':int(time.time())+7*86400,'digest':hashlib.sha256(token.encode()).hexdigest(),'createdAt':datetime.now(timezone.utc).isoformat()}
      msg=EmailMessage();msg['From']='no-reply@reclaim.clone.test';msg['To']=email;msg['Subject']='Join your Reclaim team';msg.set_content('You have been invited to a Reclaim team.\n\n'+self.origin.rstrip('/')+'/team-invite/'+token+'\n\nSign in with '+email+' to accept. This invitation expires in 7 days.')
      try:
       with smtplib.SMTP(os.environ.get('WEBSITEBENCH_SMTP_HOST','127.0.0.1'),int(os.environ.get('WEBSITEBENCH_SMTP_PORT','1025')),timeout=5) as smtp:smtp.send_message(msg)
      except Exception:raise HTTPException(503,'Unable to send the team invitation. Try again.')
      c.execute("INSERT INTO reclaim_records(account_id,kind,id,data) VALUES(?,'team-invitation',?,?)",(owner,id,json.dumps(value)));results.append({k:v for k,v in value.items() if k!='digest'})
     return True,results
  match=re.fullmatch(r'/api/team/current/invitation/([^/]+)',key)
  if match and method=='DELETE':
   self.team_admin()
   with self.connect() as c:
    if not c.execute("DELETE FROM reclaim_records WHERE account_id=? AND kind='team-invitation' AND id=?",(self.team_owner(),match[1])).rowcount:raise HTTPException(404,'Invitation not found.')
   return True,None
  if key=='/api/team/invitation/accept' and method=='POST':
   token=data.get('token','')
   with self.connect() as c:
    row=c.execute("SELECT account_id,id,data FROM reclaim_records WHERE kind='team-invitation' AND json_extract(data,'$.digest')=?",(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:raise HTTPException(410,'This invitation has expired or been revoked.')
    invite=json.loads(row['data'])
    if invite['status']!='PENDING' or invite['expiresAt']<=time.time():raise HTTPException(410,'This invitation has expired or been revoked.')
    if invite['email']!=self.account['email_normalized']:raise HTTPException(403,'Sign in with the invited email address.')
    if self.team_owner()==self.owner and len(self.team_accounts())>1:raise HTTPException(409,'Remove or transfer your existing team members before joining another team.')
    self.put('settings','team-membership',{'owner':row['account_id'],'role':invite['role']});invite['status']='ACCEPTED';c.execute("UPDATE reclaim_records SET data=? WHERE account_id=? AND kind='team-invitation' AND id=?",(json.dumps(invite),row['account_id'],row['id']))
   return True,{'accepted':True,'redirect':'/account/members'}
  if key=='/api/team/current/leave' and method=='POST':
   if self.team_owner()==self.owner:raise HTTPException(409,'The owner cannot leave their team.')
   self.delete('settings','team-membership');return True,{'left':True}
  if key=='/api/team/current/members' and method in ('DELETE','PATCH'):
   self.team_admin();target=next((a for a in self.team_accounts() if ('100001' if a['account_id']==self.owner else public_id(a['account_id']))==query.get('userId')),None)
   if not target:raise HTTPException(404,'Team member not found.')
   if target['account_id']==self.team_owner():raise HTTPException(409,'The team owner cannot be removed or demoted.')
   peer=self.peer(target)
   if method=='DELETE':peer.delete('settings','team-membership');return True,None
   if data.get('role') not in ('USER','ADMIN'):raise HTTPException(422,'Choose a valid team role.')
   peer.put('settings','team-membership',{'owner':self.team_owner(),'role':data['role']});return True,self.local_member(target)
  return False,None

 def resolve_organizers(self,link,strict=False):
  accounts=self.team_accounts();result=[];seen=set()
  for item in link.get('organizers') or [{'email':self.account['email_normalized'],'attendanceType':'REQUIRED'}]:
   identity=item.get('userId') or (item.get('organizer') or {}).get('userId');email=item.get('email') or (item.get('organizer') or {}).get('email')
   account=next((a for a in accounts if email and a['email_normalized']==email or not email and identity==('100001' if a['account_id']==self.owner else public_id(a['account_id']))),None)
   if not account:
    if strict:raise HTTPException(422,'Select an accepted member of your team as an organizer.')
    result.append((item,None,None));continue
   if account['account_id'] in seen:continue
   seen.add(account['account_id']);peer=self if account['account_id']==self.owner else self.peer(account);uid='100001' if account['account_id']==self.owner else public_id(account['account_id'])
   mode=item.get('attendanceType','REQUIRED')
   if mode not in ('REQUIRED','OPTIONAL','ANY_OF'):raise HTTPException(422,'Choose Required, Optional or Round Robin attendance.')
   result.append(({**item,'userId':uid,'email':account['email_normalized'],'attendanceType':mode},peer,account))
  if strict and not any(item['attendanceType'] in ('REQUIRED','ANY_OF') for item,_,_ in result):raise HTTPException(422,'Choose at least one required or Round Robin organizer.')
  return result

 def group_availability(self,link,day,duration,zone_id=None,ignore_meeting=None):
  from business import parse
  resolved=self.resolve_organizers(link);required=[];pool=[];optional=[];by_user={}
  meeting=self.get('booking',ignore_meeting) if ignore_meeting else None
  for item,peer,account in resolved:
   mode=item.get('attendanceType','REQUIRED');uid=item.get('userId') or (item.get('organizer') or {}).get('userId')
   if peer is None:
    if mode=='REQUIRED':return []
    continue
   own_link=copy.deepcopy(link);own_link['organizers']=[item]
   schemes=peer.get('settings','/api/timeschemes',peer.fixtures['/api/timeschemes']);policy=next(s['policy'] for s in schemes if s['policyType']=='MEETING');own_link['effectiveTimePolicy']=policy
   own_link['_ignore_event_keys']=[x['eventKey'] for x in (meeting or {}).get('participantEvents',[]) if x['accountId']==account['account_id']]
   slots=peer.available_slots(own_link,day,duration,zone_id or self.profile()['timezone']['id'],ignore_meeting if peer.owner==self.owner else None);indexed={parse(s['startTime']).astimezone(timezone.utc).isoformat():s for s in slots};by_user[uid]=indexed
   (required if mode=='REQUIRED' else pool if mode=='ANY_OF' else optional).append(uid)
  available=set.intersection(*(set(by_user[uid]) for uid in required)) if required else set.union(*(set(by_user[uid]) for uid in pool)) if pool else set()
  if pool:available&=set.union(*(set(by_user[uid]) for uid in pool))
  result=[]
  for start in sorted(available):
   if self.booking_limit_reached(link,parse(start),ignore_meeting):continue
   hosts=[*required,*[uid for uid in pool if start in by_user[uid]],*[uid for uid in optional if start in by_user[uid]]]
   slot=copy.deepcopy(next(by_user[uid][start] for uid in hosts if start in by_user[uid]));slot['organizerIds']=hosts;slot['isSuggested']=not result;result.append(slot)
  return result

 def choose_organizers(self,link,slot,ignore_meeting=None):
  entries=self.resolve_organizers(link);available=set(slot['organizerIds']);chosen=[(i,p,a) for i,p,a in entries if p and i['userId'] in available and i['attendanceType']!='ANY_OF'];pool=[(i,p,a) for i,p,a in entries if p and i['userId'] in available and i['attendanceType']=='ANY_OF']
  if pool:
   bookings=[b for b in self.rows('booking') if b['schedulingLinkId']==link['id'] and b['status']!='CANCELLED' and b['meetingId']!=ignore_meeting]
   def rank(entry):
    uid=entry[0]['userId'];assigned=[b for b in bookings if uid in b.get('assignedOrganizerIds',[])];return (len(assigned),max((b.get('bookedAt','') for b in assigned),default=''),uid)
   chosen.append(min(pool,key=rank))
  return chosen

 def clear_participant_events(self,meeting):
  with self.connect() as c:
   for entry in meeting.get('participantEvents',[]):c.execute("DELETE FROM reclaim_records WHERE account_id=? AND kind='event' AND id=?",(entry['accountId'],entry['eventKey']))
