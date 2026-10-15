"""All homepage feature previews load locally; scroll cancellation is handled."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
BASE=os.environ.get('TICKTICK_TEST_BASE','http://127.0.0.1:18120')
async def main():
 results=[]
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);ctx=await b.new_context(viewport={'width':1440,'height':900});p=await ctx.new_page();errors=[];external=[];posters=set()
  p.on('pageerror',lambda e:errors.append(str(e)));p.on('console',lambda m:errors.append(m.text) if m.type=='error' else None);p.on('response',lambda r:errors.append(str(r.status)+' '+r.url) if r.status>=400 else None);p.on('request',lambda r:external.append(r.url) if not r.url.startswith((BASE+'/','data:','blob:')) else None);p.on('response',lambda r:posters.add(r.url.split('/playback/')[-1]) if '/playback/' in r.url and r.status==200 else None)
  await p.goto(BASE+'/');await p.wait_for_timeout(1200)
  for offset in [1500,3000,4500,6000,8000,-20000]:await p.mouse.wheel(0,offset);await p.wait_for_timeout(120)
  for name in ['Kanban','Timeline','Split View','Eisenhower Matrix','Sticky Note','Calendar']:
   control=p.get_by_role('button',name=name,exact=True)
   await control.click();await p.wait_for_timeout(550);assert await control.get_attribute('aria-pressed')=='true';results.append(name)
  for name in ['the_verge','mkbhd','mashable','digitaltrends','gizmodo','androidcentral','androidauthority','makeuseof']:
   control=p.get_by_role('button',name=name,exact=True)
   await control.scroll_into_view_if_needed();await control.focus();await control.press('Enter');await p.wait_for_timeout(550)
   assert await control.get_attribute('aria-pressed')=='true',name
   image=p.locator('img[src*="/media/avatar/'+name+'.png"]:visible')
   assert await image.count() and await image.first.evaluate('e=>e.complete&&e.naturalWidth>0'),name
   results.append('media: '+name)
  await b.close()
 assert not errors and not external,(errors,external)
 assert {'kanban.jpg','timeline.jpg','split-view.jpg','matrix.jpg','note.jpg'}<=posters,posters
 Path('artifacts/homepage-media.json').write_text(json.dumps({'previews':results,'loaded_posters':sorted(posters),'errors':errors,'external':external},indent=2));print('PASS homepage previews',len(results))
asyncio.run(main())
