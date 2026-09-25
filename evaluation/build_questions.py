# Reproduce previously frozen PE500 labels; these are not a new blind holdout.
from pathlib import Path
import json,hashlib,datetime,collections
D=Path(__file__).resolve().parent;R=D.parent;C=json.loads((R/'lite/web/knowledge.json').read_text());by={x['id']:x for x in C};base=json.loads((R/'lite/web/benchmark100.json').read_text())['rows'];gold={i['gold_ids'][0]:i for i in base if len(i['gold_ids'])==1 and i['id']<='B056'}
rows=[]
for x in base: rows.append({**x,'suite':'legacy_regression','family':'/'.join(x['gold_ids']) or 'unanswerable','expected_routes':x['expected_routes']})
def add(q,ids,cat,previous=None):
 ids=ids.split(',') if isinstance(ids,str) else ids
 for i in ids:assert i in by
 keys=[]
 for i in ids:
  if i in gold: keys+=gold[i]['key_points'][:2]
  else:
   g=next((x for x in base if i in x['gold_ids'] and x['key_points']),None)
   keys+=g['key_points'][:2] if g else [by[i]['content'][:8]]
 x={'id':f'N{len(rows)-99:03d}','question':q,'category':cat,'gold_ids':ids,'key_points':list(dict.fromkeys(keys)),'expected_routes':sorted(set(by[i]['flow'] for i in ids if by[i]['flow']!='all')),'expect_abstain':not ids,'suite':'new_capability','family':'/'.join(ids) or 'unanswerable'}
 if previous:x['previous']=previous
 rows.append(x)
for line in (D/'new_concepts.tsv').read_text().splitlines():
 i,q1,q2=line.split('\t');add(q1,'learn-'+i,'concept_application');add(q2,'learn-'+i,'concept_boundary')
for line in (D/'business_extra.tsv').read_text().splitlines():i,q=line.split('\t');add(q,i,'business_spec')
for line in (D/'multi_extra.tsv').read_text().splitlines():i,q=line.split('\t');add(q,i,'multi_source')
for line in (D/'followup_extra.tsv').read_text().splitlines():i,p,q=line.split('\t');add(q,i,'followup',p)
for q in (D/'unanswerable_extra.tsv').read_text().splitlines():add(q,[],'unanswerable')
assert len(rows)==300,len(rows);assert len({x['question'] for x in rows})==300
for x in rows:
 assert all(any(k in by[i]['content'] for i in x['gold_ids']) for k in x['key_points']),x
obj={'name':'Jinshu-PE-500 QA subset v1','generated_at_utc':'2026-09-19T01:13:56.398452+00:00','source':'self-authored from existing 68 public summaries/synthetic documents','no_new_users':True,'code_frozen':True,'not_blind_external_eval':True,'not_independent_300_topics':True,'rows':rows}
(D/'questions300.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
print(len(rows),collections.Counter(x['category'] for x in rows));print('unique answerable doc families',len({i for x in rows for i in x['gold_ids']}));
