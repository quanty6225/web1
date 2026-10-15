"""Bundled, authenticated loopback inference. No model or prompt leaves this machine."""
import atexit,json,os,secrets,subprocess,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
HERE=Path(__file__).resolve().parent
class LocalInferenceError(RuntimeError):pass
class LocalInference:
 def __init__(self,data_dir,port=None):
  self.directory=Path(data_dir)/'local-ai';self.directory.mkdir(parents=True,exist_ok=True)
  self.port=int(port or os.environ.get('TEAMWORK_AI_PORT','18158'))
  if not 18150<=self.port<=18159:raise LocalInferenceError('Choose a Teamwork-assigned local AI port.')
  self.base='http://127.0.0.1:'+str(self.port);self.process=None;self.lock=threading.Lock();self.key=secrets.token_urlsafe(32);self.log=None;atexit.register(self.close)
 def request(self,path,data=None,timeout=2):
  req=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
  with urlopen(req,timeout=timeout) as response:return json.load(response)
 def ensure(self):
  with self.lock:
   if self.process and self.process.poll() is None:return
   binary=HERE/'inference/llama-server';model=HERE/'models/Qwen3-1.7B-Q8_0.gguf'
   if not binary.exists() or not model.exists():raise LocalInferenceError('The bundled local AI engine or model is missing.')
   # Never attach to or terminate another process occupying the assigned port.
   import socket
   with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try:probe.bind(('127.0.0.1',self.port))
    except OSError:raise LocalInferenceError('The local AI port is already in use. Please retry when it is available.')
   key_file=self.directory/('key-'+str(os.getpid()));key_file.write_text(self.key);key_file.chmod(0o600)
   env={**os.environ,'LD_LIBRARY_PATH':str(HERE/'inference')+(':'+os.environ['LD_LIBRARY_PATH'] if os.environ.get('LD_LIBRARY_PATH') else '')};self.log=(self.directory/'engine.log').open('ab')
   args=[str(binary),'--model',str(model),'--host','127.0.0.1','--port',str(self.port),'--api-key-file',str(key_file),'--offline','--no-webui','--no-webui-mcp-proxy','--log-disable','--alias','teamwork-local','--ctx-size','8192','--parallel','1','--threads','8','--threads-batch','8','--chat-template-kwargs','{"enable_thinking":false}']
   self.process=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=self.log,stderr=self.log)
   for _ in range(240):
    if self.process.poll() is not None:raise LocalInferenceError('The local AI engine could not start. Check its local engine log.')
    try:
     if self.request('/health').get('status')=='ok':return
    except (URLError,TimeoutError,OSError):pass
    time.sleep(.25)
   self.close();raise LocalInferenceError('The local AI engine took too long to start. Please retry.')
 def complete(self,messages,schema=None,max_tokens=1600):
  self.ensure();payload={'model':'teamwork-local','messages':messages,'temperature':0.3,'top_p':0.9,'max_tokens':max_tokens,'stream':False,'chat_template_kwargs':{'enable_thinking':False}}
  if schema:payload['response_format']={'type':'json_schema','json_schema':{'name':'teamwork_draft','schema':schema,'strict':True}}
  try:result=self.request('/v1/chat/completions',payload,timeout=180)
  except (URLError,TimeoutError,OSError) as error:raise LocalInferenceError('Local AI could not finish this request. Please retry.') from error
  choice=result['choices'][0]
  if choice.get('finish_reason')=='length':raise LocalInferenceError('The draft was too long. Try a shorter overview.')
  content=choice['message'].get('content','').strip()
  if not content:raise LocalInferenceError('Local AI returned an empty draft. Please retry.')
  if schema:
   try:
    import jsonschema
    parsed=json.loads(content);jsonschema.validate(parsed,schema);return parsed
   except (ValueError,jsonschema.ValidationError) as error:raise LocalInferenceError('Local AI returned an invalid draft. Please retry.') from error
  return content
 def close(self):
  if self.process and self.process.poll() is None:
   self.process.terminate()
   try:self.process.wait(timeout=10)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
  self.process=None
  if self.log:self.log.close();self.log=None
