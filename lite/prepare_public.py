"""Copy only the existing project-created synthetic fixtures into the public Lite build."""
from pathlib import Path
import csv,json,hashlib
root=Path(__file__).resolve().parents[1]; source=root/'data/synthetic';out=root/'lite/web';out.mkdir(parents=True,exist_ok=True)
data={}
for p in source.glob('*.csv'):
 with p.open(encoding='utf-8-sig') as f:data[p.stem]=list(csv.DictReader(f))
data['calendar']=json.loads((source/'calendar.json').read_text())
data['hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*') if p.is_file()}
(out/'fixtures.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
