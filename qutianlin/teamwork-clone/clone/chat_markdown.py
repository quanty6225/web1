"""Source-observed Chat Markdown with local-only resource and link rendering."""
import html,json,re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit,quote
import mistune

CATALOG = json.loads((Path(__file__).parent / 'static/chat-link-previews.json').read_text())

class ChatRenderer(mistune.HTMLRenderer):
 def link(self,text,url,title=None):
  url=url.strip()
  try:parts=urlsplit(url)
  except ValueError:return text
  if not parts.scheme and url.startswith('/') and not url.startswith('//') and '\\' not in url:local=url
  elif parts.scheme in ['https','http']:
   local='/outbound?url='+quote(url,safe='')
   captured=CATALOG.get(url.rstrip('/'))
   if captured:local=captured['url']
   path=parts.fragment if parts.fragment.startswith('/') else parts.path
   if parts.hostname and parts.hostname.endswith('.teamwork.com') and re.match(r'^/(?:app/)?(?:tasks|projects)/[A-Za-z0-9_-]+(?:/|$)',path):local=path if path.startswith('/app/') else '/app'+path
  else:return text
  return '<a href="'+html.escape(local,quote=True)+'">'+text+'</a>'
 def image(self,text,url,title=None):
  # Pasted remote images never make a browser or server fetch the destination.
  return self.link(html.escape(text or url),url,title)

@lru_cache(maxsize=2048)
def render(text):
 parser=mistune.create_markdown(renderer=ChatRenderer(escape=True),plugins=['strikethrough','url'])
 parser.block.rules=[rule for rule in parser.block.rules if rule not in ['atx_heading','setex_heading']]
 return parser(text)
