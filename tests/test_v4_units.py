import json
from pathlib import Path
from evaluation.v4.metrics import ir_metrics
from jinshu.corpus import bounded_chunks
from app.pipeline.parser import ParsedDocument,Block

def test_distinct_metrics():
    m=ir_metrics(['a','b','x'],{'a','b','c','d'},k=3)
    assert m['recall_at_k']==.5 and m['hit_at_k']==1 and m['mrr_at_k']==1
    assert m['ndcg_at_k']<1

def test_page_chunk_provenance():
    chunks=bounded_chunks(ParsedDocument('reference',[Block('paragraph',0,'银行基金知识'*110,3),Block('paragraph',0,'另一个段落',4)]))
    assert all(len(c['content'])<=360 for c in chunks)
    assert {c['metadata']['page'] for c in chunks}=={3,4}

def test_holdout_family_disjoint():
    rows=json.loads(Path('evaluation/v4/questions.json').read_text())
    dev={c['family'] for c in rows if c['split']=='dev'};holdout={c['family'] for c in rows if c['split']=='holdout'}
    assert not dev&holdout
