#!/usr/bin/env python3
"""Run inspectable lexical retrieval diagnostics; never call a language model.

--code-root can point at an old Git worktree for the same-fixture comparison.
The report stores queries, source IDs and page numbers, not source text.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'tests/fixtures/retrieval_diagnostics.json')
    parser.add_argument('--code-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.code_root.resolve()))
    from core.reference_library import ReferenceIndex
    try:
        from core.retrieval_query import resolve_followup
    except ImportError:
        # The V11 baseline's existing bounded-history rule, preserved for a
        # fair full-query preparation comparison. No assistant facts are added.
        def resolve_followup(query, history=()):
            if history and len(query)<35 and any(x in query for x in ('这个','那个','它','继续','上面','为什么','那')):
                prior=next((m['content'] for m in reversed(history) if m['role']=='user'),'')
                query=prior[-400:]+'\n补充问题：'+query
            return {'query':query}
    data = json.loads(args.dataset.read_text())
    started = time.perf_counter();index = ReferenceIndex(data)
    build_ms = round((time.perf_counter()-started)*1000,3)
    cases = []
    for case in data['cases']:
        query=resolve_followup(case['query'],case.get('history',[]))['query']
        started=time.perf_counter();hits=index.search(query)
        elapsed=round((time.perf_counter()-started)*1000,3)
        ids=list(dict.fromkeys(hit['doc_id'] for hit in hits));gold=case['expected_docs']
        cases.append({'id':case['id'],'query':case['query'],'retrieval_query':query,
                      'expected_docs':gold,'returned_docs':ids,
                      'returned_pages':[{'doc_id':hit['doc_id'],'page':hit['page']} for hit in hits],
                      'matched_expected_source':bool(set(ids)&set(gold)) if gold else not ids,
                      'first_source_correct':bool(ids and ids[0] in gold) if gold else not ids,
                      'retrieval_ms':elapsed})
    report={'dataset_id':data['dataset_id'],'scope':data['scope'],
            'documents':len(data['documents']),'chunks':len(index.rows),
            'model_called':False,'semantic_model_called':False,'build_ms':build_ms,
            'cases':cases,'total':len(cases),
            'matched_expected_source':sum(c['matched_expected_source'] for c in cases),
            'first_source_correct':sum(c['first_source_correct'] for c in cases),
            'measurement':'本机单轮离线；延迟不包含网络、MongoDB、鉴权、冷启动或生成模型'}
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text+'\n')
    print(text)


if __name__ == '__main__':main()
