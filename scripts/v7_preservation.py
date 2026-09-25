"""Verify exact retained source and frozen labels; no network or confidential inputs."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent.parent
files=json.loads((R/'scripts/v7_preserved_sources.json').read_text())
failed=[p for p,h in files.items() if not (R/p).is_file() or hashlib.sha256((R/p).read_bytes()).hexdigest()!=h]
for p,h in json.loads((R/'evaluation/label_identity.json').read_text()).items():
 if hashlib.sha256((R/'evaluation'/p).read_bytes()).hexdigest()!=h:failed.append('evaluation/'+p)
result={'preserved_source_files':len(files),'frozen_label_files':2,'failed':failed,'scope':'Exact code and label identity; not proof of semantic quality or deployment.'}
out=R/'evidence/v7';out.mkdir(parents=True,exist_ok=True);(out/'preservation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert not failed,failed
