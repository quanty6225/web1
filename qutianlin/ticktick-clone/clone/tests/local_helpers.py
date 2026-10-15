import httpx,secrets,re,json
from pathlib import Path
BASE=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'');passed=[]
def code(email):
 ms=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages'];m=next(m for m in ms if any(x['Address']==email for x in m['To']));return re.search(r'code is (\d{6})',httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json()['Text'])[1]
def actor():
 c=httpx.Client(base_url=BASE);email='ticktick-data-'+secrets.token_hex(5)+'@offline.invalid';pw='Data-Test-2026!';assert c.post('/local/auth/signup',json={'email':email,'password':pw}).is_success;assert c.post('/local/auth/verify',json={'code':code(email)}).is_success;assert c.post('/local/auth/signin',json={'email':email,'password':pw}).is_success;return c,email,pw
