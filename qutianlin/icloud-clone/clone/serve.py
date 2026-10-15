"""Standalone local entry point; no neighboring checkout or source session."""
import argparse,os
from pathlib import Path
import uvicorn

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--port',type=int,default=18110)
 parser.add_argument('--host',default='127.0.0.1')
 parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parent/'data')
 args=parser.parse_args()
 os.environ.setdefault('WEBSITEBENCH_SITE_BACKEND_DATABASE',str(args.data_dir.resolve()/'icloud.sqlite3'))
 os.environ.setdefault('WEBSITEBENCH_SMTP_HOST','127.0.0.1')
 os.environ.setdefault('WEBSITEBENCH_SMTP_PORT','1025')
 os.environ.setdefault('WEBSITEBENCH_SMTP_FROM','no-reply@icloud.clone.test')
 os.environ.setdefault('BASE_URL',f'http://127.0.0.1:{args.port}')
 uvicorn.run('app:app',host=args.host,port=args.port,access_log=False)

if __name__=='__main__':main()
