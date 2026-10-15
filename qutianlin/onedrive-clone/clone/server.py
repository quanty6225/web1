"""Standalone bootstrap: uses physically bundled dependencies, without site packages."""
import sys,os
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'vendor'))
sys.path.insert(0,str(root))
import uvicorn
if __name__=='__main__':
 uvicorn.run('app:app',host='127.0.0.1',port=int(os.environ.get('PORT','18100')),access_log=False)
