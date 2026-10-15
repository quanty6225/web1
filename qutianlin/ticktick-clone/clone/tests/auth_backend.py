"""Live HTTP and SMTP integration checks. Reads only this test's Mailpit messages."""
import httpx,time,re,json,secrets
from pathlib import Path
BASE=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'');stamp=secrets.token_hex(6);email='ticktick-test-'+stamp+'@offline.invalid';pw='test-password-'+stamp
c=httpx.Client(base_url=BASE,follow_redirects=False);report=[]
def check(name,condition):
 assert condition,name
 report.append(name);print('PASS',name,flush=True)
def post(action,**body):return c.post('/local/auth/'+action,json=body)
def code():
 ms=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages']
 msg=next(m for m in ms if any(x['Address']==email for x in m['To']))
 content=httpx.get('http://127.0.0.1:8025/api/v1/message/'+msg['ID']).json()
 text=content.get('Text','');check('mail local sender and link',content['From']['Address']=='no-reply@ticktick.clone.test' and BASE in text)
 return re.search(r'code is (\d{6})',text)[1]
check('protected anonymous denied',c.get('/api/v3/batch/check/0').status_code==401)
r=post('signup',email=email,password=pw);check('registration sends SMTP',r.status_code==200)
first=code();check('incorrect verification rejected',post('verify',code='000000' if first!='000000' else '111111').status_code==400)
check('resend cooldown enforced',post('resend',purpose='registration').status_code==400)
check('verification succeeds',post('verify',code=first).status_code==200)
check('verification single use',post('verify',code=first).status_code==400)
check('verified registration requires login',c.get('/local/session').status_code==401)
check('wrong password rejected',post('signin',email=email,password='wrong-password').status_code==400)
check('login succeeds',post('signin',email=email,password=pw).status_code==200)
old=c.cookies.get('ticktick_local_session');check('protected session allowed',c.get('/webapp/').status_code==200)
batch=c.get('/api/v3/batch/check/0').json();inbox=batch['inboxId'];ident=secrets.token_hex(12)
r=c.post('/api/v2/batch/task',json={'add':[{'id':ident,'projectId':inbox,'title':'Persistence '+stamp,'status':0}],'update':[],'delete':[]});check('task creation',r.status_code==200)
check('task stored',any(x['id']==ident for x in c.get('/api/v3/batch/check/0').json()['syncTaskBean']['update']))
other=httpx.Client(base_url=BASE);other.post('/local/auth/signin',json={'email':'demo@ticktick.offline.invalid','password':'TickTick-Demo-2026!'})
check('other account cannot read task',other.get('/api/v2/task/'+ident).status_code==404)
check('other account cannot update task',other.post('/api/v2/batch/task',json={'update':[{'id':ident,'title':'attack'}]}).status_code==404)
check('invalid project rejected',c.post('/api/v2/batch/task',json={'add':[{'id':secrets.token_hex(12),'projectId':'someone-else','title':'bad'}]}).status_code==403)
c.get('/signout');check('logout session revoked',httpx.get(BASE+'/local/session',cookies={'ticktick_local_session':old}).status_code==401)
check('recovery SMTP',post('recover',email=email).status_code==200);reset=code();check('password reset',post('reset',code=reset,password=pw+'new').status_code==200)
check('old password invalid',post('signin',email=email,password=pw).status_code==400);check('new password valid',post('signin',email=email,password=pw+'new').status_code==200)
check('reset single use',post('reset',code=reset,password=pw).status_code==400)
check('cross origin mutation rejected',c.post('/api/v2/batch/task',json={},headers={'Origin':'https://untrusted.invalid'}).status_code==403)
Path('artifacts/auth-backend-report.json').write_text(json.dumps({'passed':report,'test_recipient':email,'task_id':ident},indent=2))
Path('run/persistence-test.json').write_text(json.dumps({'cookie':c.cookies.get('ticktick_local_session'),'task_id':ident}));Path('run/persistence-test.json').chmod(0o600)
