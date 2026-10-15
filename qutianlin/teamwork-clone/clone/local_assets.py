"""Serve captured resources with their recorded source media types."""
import json
from pathlib import Path
from starlette.staticfiles import StaticFiles

class CapturedStaticFiles(StaticFiles):
 def __init__(self,*,directory,**kwargs):
  super().__init__(directory=directory,**kwargs)
  self.media_types=json.loads(Path(directory).parent.joinpath('backend/asset-media-types.json').read_text())
 async def get_response(self,path,scope):
  response=await super().get_response(path,scope)
  if path in self.media_types and response.status_code in [200,206,304]:response.headers['content-type']=self.media_types[path]
  return response
