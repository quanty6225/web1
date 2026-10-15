import asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import actor
ROOT=Path(__file__).resolve().parents[1]
async def main():
 results=[];errors=[];requests=[]
 client,email,password=actor();cookie=client.cookies.get('ticktick_local_session')
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox','--disable-dev-shm-usage']);c=await b.new_context(storage_state={'cookies':[{'name':'ticktick_local_session','value':cookie,'domain':'127.0.0.1','path':'/','httpOnly':True,'secure':False,'sameSite':'Lax'}],'origins':[]},viewport={'width':1440,'height':900});p=await c.new_page()
  p.on('pageerror',lambda e:errors.append(e.stack))
  p.on('response',lambda r:requests.append([r.status,r.url]) if r.status>=400 else None)
  async def click(text):await p.get_by_text(text,exact=True).and_(p.locator(':visible')).last.click()
  await p.goto((__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'/webapp/#p/inbox/tasks?modalType=settings&tabs=profile'));await p.wait_for_timeout(3000)
  await p.get_by_text('Manage',exact=True).and_(p.locator(':visible')).nth(1).click();await p.wait_for_timeout(400)
  if await p.get_by_text('Enable Key',exact=True).and_(p.locator(':visible')).count():
   await click('Enable Key');await p.locator('input.select-title:visible').fill('Local automation');await click('Add');await p.wait_for_timeout(900)
  assert await p.get_by_text('Local automation',exact=True).and_(p.locator(':visible')).count();results.append('API key created through settings')
  await p.reload();await p.wait_for_timeout(2200);await p.get_by_text('Manage',exact=True).and_(p.locator(':visible')).nth(1).click();await p.wait_for_timeout(500)
  assert await p.get_by_text('Local automation',exact=True).and_(p.locator(':visible')).count();results.append('API key persists after reload')
  await p.goto((__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'/webapp/#p/inbox/tasks?modalType=settings&tabs=feature'));await p.wait_for_timeout(700)
  if not await p.locator('#plugin-habit').is_checked():await p.locator('label[for="plugin-habit"]').click()
  await p.wait_for_timeout(1200)
  await p.goto((__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'/webapp/#q/all/habit'));await p.wait_for_timeout(1000)
  await p.locator('svg.icon-add:visible').click();title='Read daily '+str(int(time.time()));await p.locator('input[placeholder="Daily Check-in"]:visible').fill(title);await click('Save');await p.wait_for_timeout(2500)
  assert await p.get_by_text(title,exact=True).and_(p.locator(':visible')).count();results.append('Habit created after enabling Habit Tracker')
  await p.reload();await p.wait_for_timeout(3000)
  assert await p.get_by_text(title,exact=True).and_(p.locator(':visible')).count();results.append('Habit persists after reload')
  await p.locator('.progress_10vBT:visible').last.click();await p.wait_for_timeout(1400);await p.reload();await p.wait_for_timeout(2300)
  assert '1 Day' in await p.locator('body').inner_text();results.append('Habit check-in persists after reload')
  await p.goto((__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'/webapp/#p/inbox/tasks?modalType=settings&tabs=feature'));await p.wait_for_timeout(700)
  if not await p.locator('#countdown').is_checked():await p.locator('label[for="countdown"]').click()
  await p.wait_for_timeout(1000);await p.goto((__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'/webapp/#countdown'));await p.wait_for_timeout(800)
  await p.locator('svg.icon-add:visible').click();await p.get_by_text('Countdown',exact=True).and_(p.locator(':visible')).last.click();await p.locator('input[placeholder="Name"]:visible').fill('Project milestone');await click('Next');await click('OK');await p.wait_for_timeout(1800)
  await p.reload();await p.wait_for_timeout(2500);assert await p.get_by_text('Project milestone',exact=True).and_(p.locator(':visible')).count();results.append('Countdown created through both dialogs and persists after reload')
  await p.goto((__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'/webapp/#p/inbox/tasks'));await p.wait_for_timeout(1200)
  async def view_options():
   await p.locator('#tl-bar-action').click();await click('View Options');await p.wait_for_timeout(300)
  await view_options();await p.get_by_role('radio',name='Pop-up',exact=True).click()
  assert await p.get_by_role('radio',name='Pop-up',exact=True).get_attribute('aria-checked')=='true'
  await p.reload();await p.wait_for_timeout(1800);await view_options()
  assert await p.get_by_role('radio',name='Pop-up',exact=True).get_attribute('aria-checked')=='true'
  await p.get_by_role('radio',name='Side peek',exact=True).focus();await p.keyboard.press('Space')
  assert await p.get_by_role('radio',name='Side peek',exact=True).get_attribute('aria-checked')=='true'
  results.append('View mode selection persists and supports keyboard activation')
  await b.close()
 report={'checks':results,'errors':errors,'failedRequests':requests};(ROOT/'artifacts/settings-workflow.json').write_text(json.dumps(report,indent=2));print(report);assert not errors and not requests,report
asyncio.run(main())
