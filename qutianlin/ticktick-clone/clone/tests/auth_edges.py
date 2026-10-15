import os,tempfile,sys,json,re
from pathlib import Path
os.environ['TICKTICK_DATA_DIR']=tempfile.mkdtemp(prefix='auth-edge-',dir='run')
sys.path.insert(0,str((Path('clone') if Path('clone/app.py').exists() else Path('.')).resolve()))
from fastapi.testclient import TestClient
import app
from unittest.mock import patch
import httpx
passed=[]
def ck(n,v):assert v,n;passed.append(n);print('PASS',n)
clock=[app.auth._now()];app.auth._now=lambda:clock[0]
c=TestClient(app.app);email='ticktick-edge-'+Path(os.environ['TICKTICK_DATA_DIR']).name+'@offline.invalid'
def post(action,**kw):return c.post('/local/auth/'+action,json=kw)
with patch('app.smtplib.SMTP',side_effect=OSError('test failure')):
 r=post('signup',email=email,password='123456');ck('SMTP failure is reported',r.status_code==503);ck('retry session retained','ticktick_local_session' in c.cookies)
clock[0]+=61
ck('resend after SMTP failure sends real message',post('resend',purpose='registration').status_code==200)
def code():
 msgs=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages'];m=next(x for x in msgs if any(a['Address']==email for a in x['To']));body=httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json()['Text'];return re.search(r'code is (\d{6})',body)[1]
first=code();clock[0]+=61;ck('resend rotates code',post('resend',purpose='registration').status_code==200);second=code();ck('old code invalidated',first!=second and post('verify',code=first).status_code==400)
clock[0]+=601;ck('expired code rejected',post('verify',code=second).status_code==400)
clock[0]+=61;ck('expired flow can resend',post('resend',purpose='registration').status_code==200);third=code();ck('latest code accepted',post('verify',code=third).status_code==200)
ck('source six-character password supported',post('signin',email=email,password='123456').status_code==200)
a=app.auth.resolve_session(c.cookies.get('ticktick_local_session'))['account']
subscription='1e7a2f5d58060c80e83f1230';calendar='4f159184d1a37afcd31edf71'
with app.auth.connect() as db:
 d=app.state(db,a);d.pop('seed_order_version');d['tasks'][subscription]['sortOrder']=d['tasks'][calendar]['sortOrder'];app.save(db,a,d)
with app.auth.connect() as db:
 d=app.state(db,a);ck('legacy welcome ordering repaired without resetting tasks',d['tasks'][subscription]['sortOrder']>d['tasks']['909348163afb2da75c567de5']['sortOrder'])
 d['tasks'][subscription]['sortOrder']=d['tasks'][calendar]['sortOrder'];app.save(db,a,d)
with app.auth.connect() as db:
 d=app.state(db,a);ck('explicit user ordering is retained after migration',d['tasks'][subscription]['sortOrder']==d['tasks'][calendar]['sortOrder'])
Path('artifacts/auth-edge-report.json').write_text(json.dumps({'passed':passed},indent=2))
