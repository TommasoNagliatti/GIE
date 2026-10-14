import os
from pathlib import Path
import uvicorn
from gie_multistation.api import create_app

def main():
    directory=Path(os.environ['GIE_PANEL_RUNTIME'])
    app=create_app(data_dir=directory/'registry',panel_dir=directory/'panel')
    uvicorn.run(app,host='127.0.0.1',port=8520,access_log=False)
if __name__=='__main__':main()
