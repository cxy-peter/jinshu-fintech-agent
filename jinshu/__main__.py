import argparse,asyncio,json,os
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description='金枢｜金融产品中后台自进化 Agent')
 sub=p.add_subparsers(dest='command',required=True)
 serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8766);serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--profile',choices=['offline','services'],default='offline')
 sub.add_parser('loop-demo');sub.add_parser('generate-data')
 ask=sub.add_parser('ask');ask.add_argument('query');ask.add_argument('--workflow');ask.add_argument('--params',default='{}')
 worker=sub.add_parser('worker');worker.add_argument('--profile',choices=['offline','services'],default='services')
 args=p.parse_args()
 if args.command=='serve':
  import uvicorn
  from .api import create_app
  if args.profile=='offline' and args.host!='127.0.0.1':p.error('离线演示账号不允许公网监听')
  uvicorn.run(create_app(args.profile),host=args.host,port=args.port)
 elif args.command=='generate-data':
  from .fixtures import generate
  from .tables import build_table_documents
  print(generate());print('全部文档',len(build_table_documents()))
 elif args.command=='loop-demo':
  from .demo import run_loop_lab
  report=asyncio.run(run_loop_lab());path=Path('evidence/loop_lab.json');path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str));print(path)
 else:
  from .runtime import Runtime
  async def run():
   r=await Runtime(getattr(args,'profile','offline')).initialize()
   try:
    if args.command=='worker':await r.worker()
    else:print(json.dumps(await r.ask(args.query,workflow=args.workflow,params=json.loads(args.params)),ensure_ascii=False,indent=2,default=str))
   finally:await r.close()
  asyncio.run(run())
if __name__=='__main__':main()
