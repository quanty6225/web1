import secrets,json
from pathlib import Path
from local_helpers import actor,BASE
passed=[]
buyer,email,_=actor();recipient,re,_=actor()
r=buyer.post('/api/v2/payment/gc/stripe',json={'count':2,'cardType':1,'receiverType':1});assert r.is_success,r.text;checkout='/local/checkout/'+r.json()['sessionId']
assert buyer.post(checkout,json={'scenario':'sandbox-declined','idempotencyKey':secrets.token_hex(8)}).json()['status']=='DECLINED'
assert buyer.get('/api/v1/giftcard/orders').json()==[];passed.append('Declined gift payment creates no order or codes')
r=buyer.post(checkout,json={'scenario':'sandbox-approved','idempotencyKey':secrets.token_hex(8)});assert r.is_success,r.text
orders=buyer.get('/api/v1/giftcard/orders').json();assert len(orders)==1 and orders[0]['count']==2
codes=buyer.get('/api/v1/giftcard/by-order/'+orders[0]['orderId']).json();assert len(codes)==2 and all(code['id']==code['code'] for code in codes)
assert not buyer.get('/api/v2/user/status').json()['pro'];passed.append('Approved gift purchase creates two codes without upgrading buyer')
assert recipient.get('/api/v1/giftcard/by-order/'+orders[0]['orderId']).status_code==404
assert recipient.post('/api/v1/giftcard/apply/'+codes[0]['code']).is_success
assert recipient.get('/api/v2/user/status').json()['pro']
assert buyer.post('/api/v1/giftcard/apply/'+codes[0]['code']).status_code==409;passed.append('Gift codes redeem once and order details remain private')
r=buyer.post('/payment',data={'freq':'Month'});assert r.status_code==303 and '/local/checkout/' in r.headers['location'];passed.append('PayPal form enters local sandbox')
pid=buyer.post('/api/v2/project',json={'name':'Attachment sharing'}).json()['id'];tid=secrets.token_hex(12)
assert buyer.post('/api/v2/batch/task',json={'add':[{'id':tid,'projectId':pid,'title':'Files','status':0}]}).is_success
inv=buyer.post('/api/v2/project/'+pid+'/share',json={'toEmail':re,'permission':'write'}).json()['id'];assert recipient.post('/local/invitations/'+inv,json={'decision':'accept'}).is_success
t=next(x for x in recipient.get('/api/v3/batch/check/0').json()['syncTaskBean']['update'] if x['title']=='Files');fid=secrets.token_hex(12)
r=recipient.post('/api/v1/attachment/upload/'+t['projectId']+'/'+t['id']+'/'+fid,files={'file':('shared.txt',b'shared content','text/plain')});assert r.is_success,r.text
owner_path='/api/v1/attachment/'+pid+'/'+tid+'/'+fid;local_path='/api/v1/attachment/'+t['projectId']+'/'+t['id']+'/'+fid
assert buyer.get(owner_path).content==b'shared content' and recipient.get(local_path).content==b'shared content';passed.append('Editor attachment upload is persisted to owner and readable by both')
assert recipient.delete(local_path).is_success and buyer.get(owner_path).status_code==404;passed.append('Editor attachment delete persists to owner')
assert buyer.delete('/api/v2/project/'+pid+'/share/'+inv).is_success
assert recipient.get(local_path).status_code==404;passed.append('Revocation removes attachment access')
Path('artifacts/gifts-shared-files.json').write_text(json.dumps({'passed':passed},indent=2));print('PASS',len(passed),passed)
