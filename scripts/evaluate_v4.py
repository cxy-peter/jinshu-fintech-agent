"""Execute real retrieval on reviewed mock PDFs; no fabricated benchmark percentages."""
import argparse, asyncio, json, os, statistics, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.v4.metrics import ir_metrics
from jinshu.context import scope,access,run_state
from jinshu.fixtures import WORKFLOWS
from jinshu.runtime import Runtime

async def evaluate(r,output):
    cases=json.loads(Path('evaluation/v4/questions.json').read_text());docs=await r.c.store.list_documents()
    byfile={d['source']['file_name']:d for d in docs if d['status']=='active'};rows=[]
    for case in cases:
        d=byfile.get(case['file'])
        if not d:rows.append({'id':case['id'],'status':'not_indexed'});continue
        all_chunks=await r.c.store.list_chunks_by_doc(d['_id'])
        relevant=[c['_id'] for c in all_chunks if case['anchor'] in c['content']]
        if not relevant:rows.append({'id':case['id'],'status':'label_anchor_unresolved'});continue
        tk=scope.set([d['dept_id']]);ak=access.set({'departments':[d['dept_id']],'clearance':'sensitive'})
        sk=run_state.set({'models_enabled':r.profile=='services','profile':r.profile,'workflow':case['workflow']})
        started=time.perf_counter()
        try:
            chunks=await r.c.retrieval_agent.retrieve([case['question']],[d['dept_id']],top_k=5)
            row={'id':case['id'],'split':case['split'],'status':'executed','latency_ms':round((time.perf_counter()-started)*1000,2),
                 'retrieved_ids':[c['_id'] for c in chunks],'gold_ids':relevant,'metrics':ir_metrics([c['_id'] for c in chunks],relevant),
                 'calls':run_state.get().get('model_calls',[]),'retrieval':run_state.get().get('retrieval',[])}
            rows.append(row)
        finally:scope.reset(tk);access.reset(ak);run_state.reset(sk)
    summary={}
    for split in ['dev','holdout']:
        selected=[r for r in rows if r.get('split')==split and r['status']=='executed']
        summary[split]={'n':len(selected),**{key:statistics.mean(x['metrics'][key] for x in selected) if selected else None for key in ['recall_at_k','hit_at_k','mrr_at_k','ndcg_at_k']}}
    report={'profile':r.profile,'kind':'retrieval_only_on_synthetic_PDF','gold_status':'draft_anchor_labels_not_exhaustive_human_gold',
            'no_user_accuracy_claim':True,'summary':summary,'rows':rows}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str));return report
async def main(a):
    r=await Runtime(a.profile).initialize()
    try:print(json.dumps((await evaluate(r,a.output))['summary'],ensure_ascii=False))
    finally:await r.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profile',choices=['offline','services'],default='services');p.add_argument('--output',type=Path,default=Path('evidence/v4/retrieval_eval.json'))
    asyncio.run(main(p.parse_args()))
