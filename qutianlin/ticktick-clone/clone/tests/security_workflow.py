import asyncio,httpx,secrets,re,json
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];base=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'');email='ticktick-mfa-'+secrets.token_hex(4)+'@offline.invalid';password='Security-Test-2026!'
def mailcode():
 messages=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()['messages'];m=next(x for x in messages if any(t['Address']==email for t in x['To']));text=httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json()['Text'];return re.search(r'code is (\d{6})',text)[1]
async def main():
 c=httpx.Client(base_url=base);assert c.post('/local/auth/signup',json={'email':email,'password':password}).status_code==200;assert c.post('/local/auth/verify',json={'code':mailcode()}).status_code==200;assert c.post('/local/auth/signin',json={'email':email,'password':password}).status_code==200
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);ctx=await b.new_context();await ctx.add_cookies([{'name':'ticktick_local_session','value':c.cookies['ticktick_local_session'],'url':base}]);p=await ctx.new_page()
  p.on('pageerror',lambda e:print('ERROR',e.stack));p.on('response',lambda r:print('HTTP',r.status,r.url) if r.status>=400 else None)
  p.on('request',lambda r:print('WRITE',r.url,'proof length',len(r.headers.get('x-verify-id','')),re.sub(r'"(?:code|verificationCode)":"[^"]*"','"code":"[REDACTED]"',r.post_data or '')[:400]) if '/user/mfa/' in r.url and r.method!='GET' else None)
  async def click(text):await p.get_by_text(text,exact=True).and_(p.locator(':visible')).last.click()
  await p.goto(base+'/webapp/#p/inbox/tasks?modalType=settings&tabs=profile');await p.wait_for_timeout(2500);await click('Setting');await click('Enable');await click('Send Code');await p.wait_for_timeout(500);await p.locator('input[name=verificationCode]:visible').fill(mailcode());await click('Next');await p.wait_for_timeout(1000)
  await click('Email Verification Code');await p.wait_for_timeout(500)
  await p.locator('input[placeholder="Email Address"]:visible').fill(email)
  await click('Send Code');await p.wait_for_timeout(500)
  await p.locator('input[name=verificationCode]:visible').fill(mailcode());await click('Add');await p.wait_for_timeout(700)
  assert await p.get_by_text('Enabled successfully',exact=True).is_visible()
  await b.close()
 c.get('/signout');r=c.post('/local/auth/signin',json={'email':email,'password':password});assert r.status_code==200,r.text;assert r.json()['redirect']=='/signin/mfa'
 assert c.get('/local/session').status_code==401
 assert c.post('/local/auth/mfa',json={'code':'incorrect'}).status_code==400
 code=mailcode();r=c.post('/local/auth/mfa',json={'code':code});assert r.status_code==200,r.text
 assert c.get('/local/session').status_code==200
 assert c.post('/local/auth/mfa',json={'code':code}).status_code==400
 report={'passed':['Enable email MFA through original settings UI and two SMTP challenges','Backup codes generated','Password alone cannot open protected resources','Wrong second factor rejected','SMTP second factor completes login','Second factor is single use']}
 (ROOT/'artifacts/security-workflow.json').write_text(json.dumps(report,indent=2));print('PASS',len(report['passed']),'MFA checks')
asyncio.run(main())
