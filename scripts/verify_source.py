"""Verify original archive preservation, accounting for explicit public-data exclusions."""
import argparse,hashlib,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--public',action='store_true');a=p.parse_args()
root=Path(__file__).resolve().parents[1]
original=json.loads((root/'evidence/original_files_sha256.json').read_text())
allowed=set(json.loads((root/'evidence/preservation.json').read_text())['modified'])
excluded=set(json.loads((root/'evidence/public_exclusions.json').read_text())) if a.public else set()
errors=[];present=0
for name,digest in original.items():
 file=root/'engine'/name
 if not file.exists():
  if name not in excluded:errors.append('missing:'+name)
 else:
  present+=1
  if name not in allowed and hashlib.sha256(file.read_bytes()).hexdigest()!=digest:errors.append('unexpected change:'+name)
result={'original_files':len(original),'present':present,'declared_public_exclusions':len(excluded),'declared_patches':sorted(allowed),'errors':errors}
print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(bool(errors))
