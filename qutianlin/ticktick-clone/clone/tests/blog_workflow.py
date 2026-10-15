"""Public blog paging, local search, sharing and mobile navigation in the browser."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
from local_helpers import BASE
R=Path(__file__).resolve().parents[1]
async def main():
 checks=[];errors=[];remote=[]
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);c=await b.new_context(viewport={'width':1440,'height':900});p=await c.new_page()
  c.on('request',lambda r:remote.append(r.url) if r.url.startswith('http') and not r.url.startswith(BASE) else None)
  p.on('console',lambda e:errors.append(e.text) if e.type=='error' else None);p.on('pageerror',lambda e:errors.append(str(e)));p.on('requestfailed',lambda r:errors.append(r.url+':'+str(r.failure)));p.on('response',lambda r:errors.append(str(r.status)+' '+r.url) if r.status>=400 else None)
  await p.goto(BASE+'/blog');assert await p.locator('.wppb-post-grid-title').count()==6
  while await p.get_by_text('Load More',exact=True).count():
   async with p.expect_response('**/blog/wp-admin/admin-ajax.php'):await p.get_by_text('Load More',exact=True).click()
   await p.wait_for_timeout(80)
  assert await p.locator('.wppb-post-grid-title').count()==120;checks.append('All 120 original home cards reached through native Load More; no fixed page cap')
  await p.goto(BASE+'/blog/updates');first=await p.locator('.wppb-post-grid-title').first.inner_text()
  await p.locator('.wppb-posts-paginate-link[data-paged="2"]').first.click();await p.get_by_text('Review of Recent Updates in TickTick',exact=True).first.wait_for()
  await p.locator('.wppb-posts-paginate-link[data-paged="1"]').first.click();await p.get_by_text(first,exact=True).wait_for();checks.append('Category pagination returns to the original first page')
  await p.goto(BASE+'/blog/?s=white+noises');assert await p.locator('article').count()==9
  await p.goto(BASE+'/blog/?s=unfindablelocalterm347589');await p.get_by_text('Sorry, but nothing matched your search terms. Please try again with some different keywords.',exact=True).wait_for();checks.append('Captured search and genuine empty search state')
  await p.goto(BASE+'/blog/author/appest/');first=await p.locator('article h2').first.inner_text()
  await p.locator('a.page-numbers').filter(has_text='2').first.click();await p.wait_for_url('**/blog/author/appest/page/2*');assert await p.locator('article h2').first.inner_text()!=first
  await p.go_back();await p.wait_for_url('**/blog/author/appest*');assert await p.locator('article h2').first.inner_text()==first;checks.append('Native author archive pagination and browser Back preserve the original page')
  await p.goto(BASE+'/blog/2020/03/11/streamline-to-do-list-ticktick-zapier')
  async with p.expect_popup() as popup:await p.locator('[role=button][tabindex="0"]:visible').first.click()
  tab=await popup.value;await tab.wait_for_load_state();assert '/external?target=' in tab.url;await tab.get_by_role('heading',name='External link').wait_for();await tab.close();checks.append('Social sharing shows the original destination locally')
  await p.set_viewport_size({'width':390,'height':844});await p.goto(BASE+'/blog');await p.locator('.menu-toggle').click();assert await p.get_by_role('link',name='Updates',exact=True).first.is_visible();checks.append('Native mobile menu reveals navigation')
  assert not errors,errors;assert not remote,remote;await b.close()
 (R/'artifacts/blog-workflow.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'runtime_errors':errors,'remote_requests':remote},indent=2));print('PASS',len(checks),'blog workflows')
asyncio.run(main())
