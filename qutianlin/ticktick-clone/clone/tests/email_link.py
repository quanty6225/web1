import httpx,secrets,re,json
from pathlib import Path
base=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'');email='ticktick-link-'+secrets.token_hex(5)+'@offline.invalid';a=httpx.Client(base_url=base)
assert a.post('/local/auth/signup',json={'email':email,'password':'abcdef'}).status_code==200
messages=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages'];m=next(x for x in messages if any(t['Address']==email for t in x['To']));text=httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json()['Text'];url=re.search(r'http://\S+',text)[0];code=re.search(r'code is (\d{6})',text)[1]
b=httpx.Client(base_url=base);assert b.get(url).status_code==200;assert b.post('/local/auth/verify',json={'code':code}).status_code==200;assert a.post('/local/auth/verify',json={'code':code}).status_code==400;assert b.post('/local/auth/signin',json={'email':email,'password':'abcdef'}).status_code==200
Path('artifacts/email-link-report.json').write_text(json.dumps({'passed':['verification link works in a fresh browser session','link/code cannot be consumed twice','six-character password sign-in after link verification']},indent=2));print('PASS 3 email-link checks')
