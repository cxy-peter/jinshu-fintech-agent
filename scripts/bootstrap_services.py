"""One-time explicit synthetic bootstrap and interactive administrator provisioning."""
import asyncio,getpass,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jinshu.runtime import Runtime

async def main():
    os.environ['JINSHU_BOOTSTRAP']='1'
    r=await Runtime('services').initialize()
    try:
        name=input('New administrator username: ').strip()
        password=getpass.getpass('Password (at least 14 characters): ')
        if not name or len(password)<14:raise ValueError('Username/password requirements not met')
        if await r.c.store.get('users',name):raise ValueError('Existing user will not be overwritten')
        user=r.c.auth._to_user({'username':name,'password':password,'name':name,'role':'admin','dept_id':''})
        await r.c.store.upsert_user(user)
        print('Synthetic corpus and administrator created. Provision a second independent reviewer before publication.')
    finally:await r.close()
if __name__=='__main__':asyncio.run(main())
