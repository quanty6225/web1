"""Create a new local environment from bundled, hash-checked wheels only."""
import argparse,hashlib,json,os,platform,subprocess,sys,sysconfig,venv
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BOOTSTRAP='''import runpy,sys
def deny_network(event,args):
    if event in ('socket.connect','socket.getaddrinfo','socket.sendto'):
        raise RuntimeError('Offline installer blocked a network operation: '+event)
sys.addaudithook(deny_network)
sys.path.insert(0,sys.argv.pop(1))
sys.argv[0]='pip'
runpy.run_module('pip',run_name='__main__')
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--dest',type=Path,default=ROOT/'.venv',help='New virtual environment directory (must not exist).')
 parser.add_argument('--tests',action='store_true',help='Also install the bundled pytest and HTTP test dependencies.')
 args=parser.parse_args()
 if sys.implementation.name!='cpython' or sys.version_info[:2] not in ((3,12),(3,13),(3,14)) or platform.system()!='Linux' or platform.machine()!='x86_64' or sysconfig.get_config_var('Py_GIL_DISABLED'):
  parser.error('Bundled compiled wheels target Linux x86_64 CPython 3.12–3.14 with the GIL enabled.')
 if args.dest.exists() or args.dest.is_symlink():parser.error('The destination already exists; choose a new directory. No existing environment was changed.')
 wheels=ROOT/'wheels';manifest=json.loads((wheels/'MANIFEST.json').read_text())
 for record in manifest['files']:
  name=record['file']
  if Path(name).name!=name or not name.endswith('.whl'):raise ValueError('Invalid wheel filename in manifest.')
  path=wheels/name
  if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
   raise ValueError('Wheel checksum mismatch: '+name)
 pip=[r for r in manifest['files'] if r['name']=='pip']
 if len(pip)!=1:raise ValueError('Expected one bundled pip wheel.')
 target=args.dest.absolute();venv.EnvBuilder(with_pip=False,symlinks=True).create(target)
 python=target/'bin/python'
 env={k:v for k,v in os.environ.items() if not k.startswith(('PIP_','PYTHON'))}
 env['PIP_CONFIG_FILE']=os.devnull
 prefix=[str(python),'-I','-c',BOOTSTRAP,str(wheels/pip[0]['file']),'--isolated','--disable-pip-version-check','--no-cache-dir']
 lock=ROOT/('requirements-offline-test.txt' if args.tests else 'requirements-offline.txt')
 subprocess.run(prefix+['install','--no-input','--no-index','--find-links',str(wheels),'--only-binary=:all:','--require-hashes','-r',str(lock)],env=env,check=True)
 subprocess.run(prefix+['check'],env=env,check=True)
 print('Offline installation complete:',target)
 print('Run:',python,ROOT/'serve.py','--port','18110')

if __name__=='__main__':main()
