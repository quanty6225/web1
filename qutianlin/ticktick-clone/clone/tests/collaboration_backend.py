import httpx,secrets,re,json
from pathlib import Path
BASE=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'')
def actor():
 c=httpx.Client(base_url=BASE);email='ticktick-share-'+secrets.token_hex(5)+'@offline.invalid';pw='Sharing-2026!';assert c.post('/local/auth/signup',json={'email':email,'password':pw}).status_code==200
 ms=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages'];m=next(m for m in ms if any(x['Address']==email for x in m['To']));code=re.search(r'code is (\d{6})',httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json()['Text'])[1]
 c.post('/local/auth/verify',json={'code':code});c.post('/local/auth/signin',json={'email':email,'password':pw});return c,email
owner,oe=actor();editor,ee=actor();viewer,ve=actor();pid=owner.post('/api/v2/project',json={'name':'Shared project'}).json()['id'];tid=secrets.token_hex(12)
assert owner.post('/api/v2/batch/task',json={'add':[{'id':tid,'projectId':pid,'title':'Shared task','status':0}]}).status_code==200
assert editor.get('/api/v2/task/'+tid).status_code==404
r=owner.post('/api/v2/project/'+pid+'/share',json={'toEmail':ee,'permission':'write'});assert r.status_code==200,r.text;inv=r.json()['id'];assert editor.get('/api/v2/task/'+tid).status_code==404
assert viewer.get('/local/invitations/'+inv).status_code==404
r=editor.post('/local/invitations/'+inv,json={'decision':'accept'});assert r.status_code==200,r.text
batch=editor.get('/api/v3/batch/check/0').json();task=next(x for x in batch['syncTaskBean']['update'] if x['title']=='Shared task');assert task['id']!=tid and task['projectId']!=pid
assert editor.post('/api/v2/batch/task',json={'update':[{**task,'title':'Edited by member'}]}).status_code==200
assert owner.get('/api/v2/task/'+tid).json()['title']=='Edited by member'
localtid=task['id'];localpid=task['projectId']
r=editor.post('/api/v2/project/'+localpid+'/task/'+localtid+'/comment',json={'content':'Member comment'});assert r.is_success,r.text;assert owner.get('/api/v2/project/'+pid+'/task/'+tid+'/comments').json()[0]['content']=='Member comment'
r=owner.post('/api/v2/column',json={'projectId':pid,'name':'Shared section'});assert r.is_success,r.text;assert any(x['name']=='Shared section' for x in editor.get('/api/v2/column/project/'+localpid).json())
assert editor.put('/api/v2/project/'+task['projectId'],json={'name':'Not allowed'}).status_code==403
assert owner.delete('/api/v2/project/'+pid+'/share/'+inv).status_code==200
assert editor.get('/api/v2/task/'+task['id']).status_code==404
r=owner.post('/api/v2/project/'+pid+'/share',json={'toEmail':ve,'permission':'read'});assert r.status_code==200,r.text;inv=r.json()['id'];viewer.post('/local/invitations/'+inv,json={'decision':'accept'});task=next(x for x in viewer.get('/api/v3/batch/check/0').json()['syncTaskBean']['update'] if x['title']=='Edited by member')
assert viewer.post('/api/v2/batch/task',json={'update':[{**task,'title':'Unauthorized'}]}).status_code==403
assert owner.get('/api/v2/task/'+tid).json()['title']=='Edited by member'
Path('artifacts/collaboration-backend.json').write_text(json.dumps({'passed':['Private before invitation','Pending invitation grants no access','Invitation requires exact recipient','Accept projects/tasks use isolated aliases','Editor task updates reach owner','Editor cannot change owner settings','Revoked recipient immediately loses access','Read-only recipient cannot modify data','Shared comments persist to owner','Shared columns are visible to recipient']},indent=2));print('PASS 10 collaboration checks')
