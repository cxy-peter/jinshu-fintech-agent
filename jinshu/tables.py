"""Turn synthetic tabular inputs into versioned, header-preserving retrieval documents."""
from __future__ import annotations
import csv,hashlib,json
from .fixtures import DATA
TABLE_DEPTS={'products.csv':'dept_wealth','weekly_raw.csv':'dept_release','onboarding.csv':'dept_risk','cases.csv':'dept_risk','features.csv':'dept_risk','statements.csv':'dept_release'}
def build_table_documents():
 docs=json.loads((DATA/'documents.json').read_text())
 docs=[d for d in docs if not d['topic'].startswith('table-')]
 for name,dept in TABLE_DEPTS.items():
  raw=(DATA/name).read_bytes();rows=list(csv.reader(raw.decode('utf-8-sig').splitlines()));header=rows[0]
  content=f'# {name} 结构化输入（模拟）\n\n仅用于复现软件流程，数值不代表任何机构。CSV SHA256：{hashlib.sha256(raw).hexdigest()}\n\n## 数据行\n\n'
  content+='|'+'|'.join(header)+'|\n|'+'|'.join('---' for _ in header)+'|\n'
  content+='\n'.join('|'+'|'.join(c.replace('|','／') for c in row)+'|' for row in rows[1:])
  file='table-'+name.replace('.csv','.md');(DATA/file).write_text(content,encoding='utf-8')
  docs.append({'topic':'table-'+name,'dept_id':dept,'title':name+'模拟输入','version':1,'status':'active','file':file,'source_csv':name})
 (DATA/'documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2))
 return docs
if __name__=='__main__':print('documents',len(build_table_documents()))
