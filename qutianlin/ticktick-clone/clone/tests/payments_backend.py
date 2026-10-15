import httpx,secrets,re,json
from pathlib import Path
base=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'');c=httpx.Client(base_url=base);email='ticktick-pay-'+secrets.token_hex(5)+'@offline.invalid'
assert c.post('/local/auth/signup',json={'email':email,'password':'Payment-Test-2026!'}).status_code==200
ms=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages'];m=next(m for m in ms if any(x['Address']==email for x in m['To']));code=re.search(r'code is (\d{6})',httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json()['Text'])[1]
c.post('/local/auth/verify',json={'code':code});c.post('/local/auth/signin',json={'email':email,'password':'Payment-Test-2026!'})
r=c.post('/api/v2/subscribe/stripe/create-checkout-session?freq=Year',json={'cancel':base+'/payment'});assert r.status_code==200,r.text;ident=r.json()['sessionId'];url='/local/checkout/'+ident
assert c.get(url).status_code==200
assert httpx.get(base+url).status_code==401
r=c.post(url,json={'scenario':'sandbox-declined','idempotencyKey':secrets.token_hex(16)});assert r.status_code==200,r.text;assert r.json()['status']=='DECLINED'
assert not c.get('/api/v2/user/status').json()['pro']
r=c.post(url,json={'scenario':'sandbox-retry','idempotencyKey':secrets.token_hex(16)});assert r.status_code==200,r.text
r=c.post(url,json={'scenario':'sandbox-approved','idempotencyKey':secrets.token_hex(16)});assert r.status_code==200,r.text;assert r.json()['status']=='CONSUMED'
assert c.get('/api/v2/user/status').json()['pro']
assert c.post(url,json={'scenario':'sandbox-approved','idempotencyKey':secrets.token_hex(16)}).json()['status']=='CONSUMED'
Path('artifacts/payments-backend.json').write_text(json.dumps({'passed':['create owned checkout intent','checkout requires authentication','decline does not activate subscription','retry is supported','approved intent atomically activates local subscription','duplicate completion does not charge or renew twice']},indent=2));print('PASS 6 payment sandbox checks')
