"""Validate the complete entrypoint and write non-secret deployment identity."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from compileall import compile_dir
assert compile_dir(str(ROOT/'unified'),quiet=1)
source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['unified','jinshu','engine/backend/app'] for p in sorted((ROOT/folder).rglob('*')) if p.suffix in {'.py','.js','.css','.html'}}
info={'version':'8.0.0','entrypoint':'index.py','runtime':'jinshu.runtime.Runtime','git_commit':os.getenv('VERCEL_GIT_COMMIT_SHA'),'source_hashes':source,'runtime_configuration_checked':False}
(ROOT/'unified/web/build-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
print('Built one complete backend. No credentials tested or embedded.')
