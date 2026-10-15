import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import actor,BASE
async def main():
 client,_,_=actor();errors=[];failed=[];writes=[]
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);c=await b.new_context();await c.add_cookies([{'name':'ticktick_local_session','value':client.cookies.get('ticktick_local_session'),'url':BASE}]);p=await c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.on('response',lambda r:failed.append([r.status,r.url]) if r.status>=400 else None);p.on('request',lambda r:writes.append([r.url,r.post_data]) if r.method not in ['GET','HEAD'] and '/datacollect/' not in r.url else None)
  async def click(text):await p.get_by_text(text,exact=True).and_(p.locator(':visible')).last.click()
  await p.goto(BASE+'/webapp/#p/inbox/tasks?modalType=settings&tabs=feature');await p.wait_for_timeout(2300);await p.locator('label[for="plugin-pomo"]').click();await p.wait_for_timeout(1000);await p.goto(BASE+'/webapp/#focus');await p.wait_for_timeout(1000)
  await p.clock.install();await click('Start');await p.clock.fast_forward(360000);await click('Pause');await click('End');await click('End and Save');await p.wait_for_timeout(2000)
  records=client.get('/api/v2/pomodoro/all').json();assert len(records)==1,records
  stats=client.get('/api/v2/pomodoros/statistics/generalForDesktop').json();assert stats['totalPomoCount']==1 and stats['totalPomoDuration']==6,stats
  await p.reload();await p.wait_for_timeout(2300);assert '6m' in (await p.locator('body').inner_text()).replace('\n',''),await p.locator('body').inner_text()
  assert not errors and not failed,(errors,failed)
  Path('artifacts/focus-browser.json').write_text(json.dumps({'passed':['Start, pause and early-end confirmation','Save a six-minute record using Playwright virtual clock','Record persisted in backend','Overview counts duration correctly','Record survives reload'],'errors':errors,'failed_requests':failed},indent=2));print('PASS 5 focus browser checks')
  await b.close()
asyncio.run(main())
