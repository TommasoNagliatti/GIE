"""Run one logical API process; workers=1 is required for registry ownership."""
import argparse
import uvicorn
from .api import create_app

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8520);args=parser.parse_args()
    uvicorn.run(create_app(),host='127.0.0.1',port=args.port,workers=1,access_log=False)

if __name__=='__main__':main()
