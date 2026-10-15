"""Preserve source-observed dialogs separately from default route baselines."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import actor
R=Path(__file__).resolve().parents[1];BASE=os.environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')
async def main():
 client,_,_=actor();passed=[];errors=[];external=[]
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);c=await b.new_context(viewport={'width':1440,'height':900});await c.add_cookies([{'name':'ticktick_local_session','value':client.cookies['ticktick_local_session'],'url':BASE}]);p=await c.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.on('request',lambda r:external.append(r.url) if not r.url.startswith((BASE+'/','data:','blob:')) else None)
  await p.goto(BASE+'/webapp/#p/inbox/tasks?modalType=settings&tabs=profile');await p.get_by_text('Setting',exact=True).and_(p.locator(':visible')).click();await p.get_by_text('Enable',exact=True).and_(p.locator(':visible')).wait_for();assert await p.locator('img[src*="8b53ee24a1d362c444bf96f9bc23f44d"]').evaluate('(x)=>x.complete&&x.naturalWidth>0');passed.append('Profile 2-Step Verification introductory dialog and original illustration')
  await p.reload();await p.get_by_text('Features',exact=True).and_(p.locator(':visible')).click();await p.locator('#plugin-habit').wait_for();assert await p.locator('img:visible').count()>=7;passed.append('Features tab with original six feature illustrations')
  await p.goto(BASE+'/webapp/#c/all/calendar/m');await p.get_by_text('Monthly View',exact=True).and_(p.locator(':visible')).wait_for();await p.get_by_text('Upgrade Now',exact=True).and_(p.locator(':visible')).wait_for();assert await p.locator('img[src*="upgrade-cal-"]').count()==7;passed.append('Calendar free-tier monthly preview and upgrade dialog')
  await p.goto(BASE+'/webapp/#p/b7bb2e24b677ff0266455e76/tasks/a103549eae278e73812ef182');await p.reload();await p.wait_for_timeout(1600)
  # Source 009-date-picker state follows the task date control.
  await p.locator('.td-header #quick-set').first.click(timeout=3000)
  await p.locator('.nav-selector:visible').wait_for();passed.append('First-five task date picker opens with navigation')
  await b.close()
 report={'passed':passed,'errors':errors,'external':external,'source_evidence':['038-account-return-2.json','017-enable-pomo-ui.json','010-calendar.json','009-date-picker.json']};(R/'artifacts/transient-states.json').write_text(json.dumps(report,indent=2));print(report);assert not errors and not external
asyncio.run(main())
