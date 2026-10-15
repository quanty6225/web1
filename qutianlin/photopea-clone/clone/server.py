import sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
import uvicorn
if __name__=='__main__':uvicorn.run('app:app',host='127.0.0.1',port=int(os.environ.get('PORT','18160')),log_level='warning')
