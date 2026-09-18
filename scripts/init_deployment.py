"""Create local secrets without printing their values; never overwrite existing .env."""
import argparse, os, secrets
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('deploy/compose/.env'));a=p.parse_args()
if a.output.exists():raise SystemExit('Existing config retained; choose a different output path.')
template=Path(__file__).resolve().parents[1]/'deploy/compose/.env.example'
gateway=secrets.token_hex(32);rows=[]
for line in template.read_text().splitlines():
 if line.endswith('=GENERATE'):
  key=line.split('=')[0];value=gateway if key in {'MODEL_GATEWAY_TOKEN','CHAT_API_KEY','EMBEDDING_API_KEY','RERANKER_API_KEY','RELAY_API_KEY'} else secrets.token_hex(32)
  line=key+'='+value
 rows.append(line)
a.output.parent.mkdir(parents=True,exist_ok=True)
fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:f.write('\n'.join(rows)+'\n')
print('Created local config:',a.output,'(values not displayed).')
