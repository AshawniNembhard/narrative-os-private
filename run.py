import os
from pathlib import Path
if __name__ == '__main__':
    env=Path(__file__).parent/'.env'
    if env.exists():
        for line in env.read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:continue
            k,v=line.split('=',1)
            if k and k not in os.environ:os.environ[k]=v.strip().strip('"').strip("'")
    import uvicorn
    uvicorn.run('app:app',host='127.0.0.1',port=int(os.getenv('PORT','8000')),reload=False)