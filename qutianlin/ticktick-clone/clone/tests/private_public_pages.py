import asyncio,json
from pathlib import Path
from local_helpers import actor,BASE
from playwright.async_api import async_playwright
R=Path(__file__).resolve().parents[1]
async def main():
 c,email,_=actor();results=[]
 async with async_playwright() as pw:
  b=await pw.chromium.launch(args=['--no-sandbox']);ctx=await b.new_context();await ctx.add_cookies([{'name':'ticktick_local_session','value':c.cookies.get('ticktick_local_session'),'url':BASE}]);p=await ctx.new_page();errors=[]
  p.on('console',lambda e:errors.append(e.text[:180]) if e.type=='error' else None);p.on('pageerror',lambda e:errors.append(str(e)));p.on('response',lambda r:errors.append(str(r.status)+' '+r.url) if r.status>=400 else None)
  for route in ['/payment','/refer','/payment/card']:
   errors.clear();await p.goto(BASE+route,wait_until='domcontentloaded');await p.wait_for_timeout(1600);text=await p.locator('body').inner_text();results.append({'route':route,'actor':'member','text_length':len(text),'errors':errors.copy()})
  await b.close()
 (R/'artifacts/private-public-pages.json').write_text(json.dumps(results,indent=2));print(results);assert all(not x['errors'] and x['text_length']>400 for x in results)
asyncio.run(main())
