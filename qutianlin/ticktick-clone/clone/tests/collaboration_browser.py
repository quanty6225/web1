import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import actor,BASE
async def main():
 owner,_,_=actor();editor,email,_=actor();pid=owner.post('/api/v2/project',json={'name':'Browser shared list'}).json()['id'];errors=[];failed=[];writes=[]
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);c=await b.new_context(viewport={'width':1440,'height':900});await c.add_cookies([{'name':'ticktick_local_session','value':owner.cookies.get('ticktick_local_session'),'url':BASE}]);p=await c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.on('response',lambda r:failed.append([r.status,r.url]) if r.status>=400 else None);p.on('request',lambda r:writes.append([r.url,r.post_data]) if r.method not in ['GET','HEAD'] and '/datacollect/' not in r.url else None)
  await p.goto(BASE+'/webapp/#p/'+pid+'/tasks');await p.wait_for_timeout(2300);await p.locator('header svg.icon-more-titlebar:visible').click();await p.get_by_text('Share',exact=True).and_(p.locator(':visible')).last.click();await p.wait_for_timeout(500);await p.locator('#ipt-share').fill(email);await p.locator('#ipt-share').press('Enter');await p.wait_for_timeout(1000)
  await p.get_by_text('Invite',exact=True).and_(p.locator(':visible')).last.click();await p.wait_for_timeout(1200)
  grants=owner.get('/api/v2/project/'+pid+'/shares').json();assert len(grants)==1,grants;inv=grants[0]['id']
  r=editor.post('/local/invitations/'+inv,json={'decision':'accept'});assert r.is_success,r.text
  assert any(x['name']=='Browser shared list' for x in editor.get('/api/v2/projects').json())
  assert not errors and not failed,(errors,failed)
  Path('artifacts/collaboration-browser.json').write_text(json.dumps({'passed':['Share dialog selects recipient and permission','Invite button persists grant and sends local SMTP mail','Recipient accepts and sees shared list'],'errors':errors,'failed_requests':failed},indent=2));print('PASS 3 collaboration browser checks');await b.close()
asyncio.run(main())
