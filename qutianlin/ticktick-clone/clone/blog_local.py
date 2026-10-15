"""Serve captured blog pagination and search over the local public corpus."""
import json,re,html
from pathlib import Path
from urllib.parse import parse_qsl
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
ROOT=Path(__file__).parent
DATA=json.loads((ROOT/'blog-data.json').read_text())
async def ajax(req):
 data=dict(parse_qsl((await req.body()).decode())) if req.method=='POST' else dict(req.query_params)
 if data.get('action')!='wppb_posts_addon_load_more':raise HTTPException(400,'Unknown public listing action')
 key=':'.join(data.get(k,'') for k in ['page_id','addon_id','paged']);file=DATA['ajax'].get(key)
 if file is None:raise HTTPException(404,'Listing page not captured')
 return HTMLResponse((ROOT/file).read_text())
def search(query,page=1):
 if query.strip().casefold()=='white noises':
  pages=json.loads((ROOT/'page-routes.json').read_text());return HTMLResponse((ROOT/pages['/blog/white-noises']).read_text())
 if query=='TickTick' and str(page) in DATA['searchpages']:return HTMLResponse((ROOT/DATA['searchpages'][str(page)]).read_text())
 # Search the captured public titles and excerpts. All resulting cards preserve source markup.
 terms=query.casefold().split();seen=set();matches=[]
 for c in DATA['searchcards']:
  if c['url'] in seen:continue
  seen.add(c['url'])
  if all(t in c['text'].casefold() for t in terms):matches.append(c['html'])
 base=(ROOT/DATA['searchpages']['1']).read_text();total=len(matches);start=(page-1)*10
 content=''.join(matches[start:start+10])
 if not content:content=(ROOT/'blog-no-results.html').read_text()
 # Native archive renders each article as a sibling followed by its navigation.
 articles=list(re.finditer(r'<article\b[\s\S]*?</article>',base))
 if articles:base=base[:articles[0].start()]+content+base[articles[-1].end():]
 base=base.replace('Search Results for: TickTick','Search Results for: '+html.escape(query)).replace('value="TickTick"','value="'+html.escape(query,quote=True)+'"')
 nav=''
 if total>10:
  from urllib.parse import quote
  nav='<nav class="navigation pagination" aria-label="Search pages">'+' '.join('<a class="page-numbers" href="/blog/page/'+str(n)+'/?s='+quote(query)+'">'+str(n)+'</a>' for n in range(1,(total+9)//10+1))+'</nav>'
 base=re.sub(r'<nav\b[^>]*class="[^"]*pagination[^\"]*"[\s\S]*?</nav>',lambda _:nav,base)
 return HTMLResponse(base)
