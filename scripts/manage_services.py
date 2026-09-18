"""Operations CLI: server admin bootstrap, synthetic corpus, reviewed private import."""
import argparse, asyncio, getpass, json, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jinshu.runtime import Runtime

async def run(args):
 r=await Runtime('services').initialize()
 try:
  if args.command=='user':
   name=args.username;password=getpass.getpass('New password (14+ characters): ')
   if len(password)<14:raise ValueError('Password too short')
   if await r.c.store.get('users',name):raise ValueError('Existing user retained')
   await r.c.store.upsert_user(r.c.auth._to_user({'username':name,'name':name,'password':password,'role':args.role,'dept_id':args.department}))
   print('Created user; password not logged.')
  elif args.command=='synthetic':
   from jinshu.mock_pdfs import generate,OUT
   from jinshu.skills import seed_skills
   from jinshu.hooks import seed_controls
   await seed_skills(r.c.store);await seed_controls(r.c.store)
   for d in generate():
    try:
     doc=await r.c.documents.stage_file(OUT/d['file'],d['dept_id'],args.uploader,d['topic'],d['version'],d['manual_sensitivity'])
     print(json.dumps({'id':doc['_id'],'title':doc['title'],'status':doc['status']},ensure_ascii=False))
    except ValueError as e:print(str(e))
   print('Synthetic PDFs staged. Another administrator must review and publish in UI.')
  elif args.command=='import-reviewed':
   from jinshu.corpus import import_reviewed_pack
   rows=await import_reviewed_pack(r,args.corpus,args.approvals)
   print(json.dumps(rows,ensure_ascii=False,indent=2))
  elif args.command=='status':
   from jinshu.live import ping_runtime
   print(json.dumps(await ping_runtime(r),ensure_ascii=False,indent=2))
 finally:await r.close()
p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
u=sub.add_parser('user');u.add_argument('username');u.add_argument('--department',default='');u.add_argument('--role',choices=['student','staff','admin'],default='student')
s=sub.add_parser('synthetic');s.add_argument('--uploader',required=True)
i=sub.add_parser('import-reviewed');i.add_argument('--corpus',type=Path,default=Path('/app/private_corpus'));i.add_argument('--approvals',type=Path,required=True)
sub.add_parser('status')
if __name__=='__main__':asyncio.run(run(p.parse_args()))
