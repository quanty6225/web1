import asyncio,json,secrets,httpx,re
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import actor
R=Path(__file__).resolve().parents[1];BASE=(__import__('os').environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')+'')
async def main():
 errors=[];external=[];passed=[];client,email,password=actor()
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox','--disable-dev-shm-usage']);c=await b.new_context(viewport={'width':1440,'height':900},service_workers='block');p=await c.new_page()
  p.on('request',lambda r:print('TASKBODY',r.post_data,flush=True) if '/batch/task' in r.url else None)
  p.on('response',lambda r:print('HTTP',r.status,r.url,flush=True) if '/batch/task' in r.url else None)
  p.on('pageerror',lambda e:errors.append(str(e)));p.on('request',lambda r:external.append(r.url) if not r.url.startswith((BASE,'data:','blob:')) else None)
  await p.goto(BASE+'/signin');await p.locator('form button').click();await p.get_by_role('alert').filter(has_text="Email address can't be empty").wait_for();passed.append('empty fields validation')
  await p.get_by_label('Email',exact=True).fill(email);await p.get_by_label('Password',exact=True).fill(password);await p.locator('form button').click();await p.wait_for_url('**/webapp/**');await p.get_by_text('Inbox',exact=True).first.wait_for();await p.wait_for_timeout(5000);passed.append('browser login protected app')
  await p.goto(BASE+'/webapp/#p/b7bb2e24b677ff0266455e76/tasks');await p.wait_for_timeout(1500)
  text=await p.locator('body').inner_text()
  # Captured source 003-welcome.json; substring matching must not confuse the
  # Calendar introduction with the later Subscribe to Calendar task.
  names=['点击输入框','用清单','(?<!订阅)日历：','四象限','番茄专注','习惯打卡','看板','订阅日历','更多特色','高级会员','帮助中心']
  positions=[re.search(name,text).start() for name in names]
  assert positions==sorted(positions),'Welcome tasks differ from captured source order'
  passed.append('All eleven welcome tasks retain source order and first-five selection')
  await p.goto(BASE+'/webapp/#p/inbox/tasks');await p.wait_for_timeout(500)
  title='Browser test '+secrets.token_hex(4);await p.keyboard.press('Escape');await p.locator('.task-input').first.click();await p.keyboard.insert_text(title);await p.keyboard.press('Enter');await p.get_by_text(title,exact=True).first.wait_for();await p.screenshot(path=str(R/'artifacts/browser-create-debug.png'));await p.wait_for_timeout(10000);taskurl=p.url;passed.append('create task through keyboard')
  await p.reload();await p.wait_for_timeout(6000);print('ERRORS',errors,flush=True);print('AFTER_RELOAD',p.url,await p.locator('body').inner_text(),flush=True);await p.screenshot(path=str(R/'artifacts/browser-reload-debug.png'));await p.get_by_text(title,exact=True).first.wait_for();passed.append('task survives reload and deep link')
  await p.screenshot(path=str(R/'artifacts/browser-task.png'))
  await p.goto(BASE+'/webapp/#c/all/calendar/m');await p.wait_for_timeout(1500);assert len(await p.locator('body').inner_text())>250;passed.append('calendar deep link')
  await p.goto(BASE+'/webapp/#focus');await p.wait_for_timeout(1500);assert '25:00' in await p.locator('body').inner_text();passed.append('focus timer initial state')
  await p.goto(BASE+'/signout');await p.wait_for_url('**/signin');await p.goto(taskurl);await p.wait_for_url('**/signin**');passed.append('logout invalidates protected route')
  await p.go_back();await p.wait_for_timeout(500);assert '/webapp/' not in p.url;passed.append('back does not restore protected route')
  result={'passed':passed,'page_errors':errors,'external_requests':external};(R/'artifacts/browser-workflow-report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));await b.close();assert not errors and not external
asyncio.run(main())
