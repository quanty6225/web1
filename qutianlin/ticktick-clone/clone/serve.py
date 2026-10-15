"""Standalone launcher, also used by the isolated verification runtime."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
import uvicorn
if __name__=='__main__':uvicorn.run('app:app',host='127.0.0.1',port=int(os.environ.get('PORT','18120')),log_level='warning')
