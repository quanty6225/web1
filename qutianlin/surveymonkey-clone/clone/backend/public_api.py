import json,re,time
from fastapi import APIRouter,Request,HTTPException
from backend.services import db,check_csrf,auth,COOKIE
from backend.survey_model import new_id
router=APIRouter()
@router.post('/api/public/contact')
async def contact(request:Request):
 check_csrf(request);data=await request.json();fields=data.get('fields',{});key=str(data.get('key',''))
 if not isinstance(fields,dict) or len(key)<12 or len(key)>100:raise HTTPException(422,'Refresh the form and try again.')
 required=('email','firstname','lastname','phone','company','contact_country__c','what_can_we_help_you_with_')
 clean={k:str(fields.get(k,'')).strip() for k in required}
 if any(not v or len(v)>1000 for v in clean.values()):raise HTTPException(422,'Complete all required fields.')
 if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',clean['email']):raise HTTPException(422,'Enter a valid business email address.')
 clean['communications_consent']=bool(fields.get('communications_consent'));owner=auth.session_owner_digest(request.cookies.get(COOKIE))
 with db() as c:
  existing=c.execute('SELECT id FROM sm_public_submissions WHERE owner=? AND submission_key=?',(owner,key)).fetchone()
  if existing:return {'ok':True,'id':existing['id'],'duplicate':True}
  id=new_id();c.execute('INSERT INTO sm_public_submissions VALUES (?,?,?,?,?,?)',(id,owner,key,'contact-sales',json.dumps(clean),int(time.time())))
 return {'ok':True,'id':id,'message':'Your request has been saved in this local copy.'}

@router.post('/api/public/help-feedback')
async def help_feedback(request:Request):
 check_csrf(request);data=await request.json();path=str(data.get('path',''));vote=data.get('helpful')
 if not path.startswith('/help/') or not isinstance(vote,bool):raise HTTPException(422,'Choose a valid article and response.')
 owner=auth.session_owner_digest(request.cookies.get(COOKIE));key='help:'+path[:90]
 with db() as c:
  c.execute('INSERT INTO sm_public_submissions VALUES (?,?,?,?,?,?) ON CONFLICT(owner,submission_key) DO UPDATE SET fields=excluded.fields,created=excluded.created',(new_id(),owner,key,'help-feedback',json.dumps({'path':path,'helpful':vote}),int(time.time())))
 return {'ok':True}
