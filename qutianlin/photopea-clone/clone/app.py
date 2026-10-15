import json,html,mimetypes
from pathlib import Path
from fastapi import FastAPI,Request
from local_backend import router
from fastapi.responses import HTMLResponse,FileResponse,Response,JSONResponse
ROOT=Path(__file__).resolve().parent;PUBLIC=ROOT/'public';ASSETS=json.loads((ROOT/'asset-routes.json').read_text());app=FastAPI(docs_url=None,redoc_url=None)
app.include_router(router)
@app.middleware('http')
async def offline(request,call_next):
 if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') and request.headers['origin']!=str(request.base_url).rstrip('/'):
  return JSONResponse({'detail':'Cross-origin request rejected'},403)
 response=await call_next(request);
 if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
 response.headers['Content-Security-Policy']="default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' data: blob:; img-src 'self' data: blob:; media-src 'self' blob:; frame-src 'self' blob:; worker-src 'self' blob:; font-src 'self' data:; object-src 'none'; base-uri 'self'";response.headers['Referrer-Policy']='no-referrer';return response
@app.get('/healthz')
def health():return {'status':'ok','site_id':'photopea'}
@app.api_route('/papi/event.php',methods=['GET','POST'])
@app.api_route('/cdn-cgi/rum',methods=['GET','POST'])
def telemetry():return Response(status_code=204)
@app.api_route('/offline/resource',methods=['GET','HEAD'])
def resource(url:str):
 asset=ASSETS.get(url)
 if asset:return FileResponse(PUBLIC/asset['path'].lstrip('/'),media_type=asset['mime'])
 return JSONResponse({'error':'This external resource is outside the offline core scope.'},404)
@app.get('/boundary')
def boundary(url:str=''):
 return HTMLResponse('<!doctype html><meta charset="utf-8"><title>Photopea</title><style>body{background:#282828;color:#eee;font:18px system-ui;max-width:760px;margin:80px auto;padding:24px}a{color:#9dd5ff}code{overflow-wrap:anywhere}</style><header><a href="/">Photopea</a></header><main data-boundary-page><h1>Photopea navigation boundary</h1><p>This destination is outside the user-approved core editing scope. Its original address is shown below.</p><code>'+html.escape(url)+'</code><p><a href="/">Return to Photopea</a></p></main>')
@app.get('/{path:path}')
def page(path:str):
 if path in ('plugins/gallery.html','code/storages/googledriveStorage.html'):
  return boundary('https://www.photopea.com/'+path)
 if path in ('account','login','register','recover') or path=='papi/login.php':return FileResponse(PUBLIC/'account.html')
 if path.rstrip('/') in ('learn','learn/opening-saving','learn/layers'):return FileResponse(PUBLIC/(path.rstrip('/')+'.html'))
 path=path or 'index.html';target=(PUBLIC/path).resolve()
 if target.is_relative_to(PUBLIC) and target.is_file():return FileResponse(target)
 return JSONResponse({'error':'Local resource not captured','path':path},404)
