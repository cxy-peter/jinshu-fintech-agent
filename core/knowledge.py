"""Small, inspectable keyword retrieval. No embeddings, external index or hidden uploads."""
from __future__ import annotations
from collections import Counter
import re
from jinshu.fixtures import DOCS

STOP = set('的是了在和与及或请我你它这个什么如何一下')
def terms(text: str) -> Counter:
    text = text.casefold()
    latin = re.findall(r'[a-z0-9_]{2,}', text)
    chinese = []
    for run in re.findall(r'[\u4e00-\u9fff]+', text):
        chinese.extend(run[i:i + 2] for i in range(len(run)-1)
                       if not (run[i] in STOP and run[i+1] in STOP))
    return Counter(latin + chinese)

def retrieve(query: str, documents: list, include_examples: bool):
    candidates = []
    if include_examples:
        for topic, dept, title, version, status, body in DOCS:
            if status == 'active':
                candidates.append({'title': title + '（项目合成示例）', 'text': body,
                    'origin': 'synthetic_example', 'version': version})
    for doc in documents:
        candidates.append({'title': doc.title, 'text': doc.text, 'origin': 'user_supplied', 'version': None})
    q = terms(query)
    chunks = []
    for doc in candidates:
        text = doc['text']
        # Bounded overlapping passages; only the selected excerpts leave the server.
        for start in range(0, len(text), 850):
            passage = text[start:start+1100]
            index = terms(doc['title'] + ' ' + passage)
            score = sum(min(count, index[t]) for t, count in q.items())
            if score:
                chunks.append({**doc, 'text': passage, 'score': score, 'offset': start})
    ranked = sorted(chunks, key=lambda x: (-x['score'], x['title'], x['offset']))[:4]
    return [dict(source_id=f'S{i+1}', **row) for i, row in enumerate(ranked)]

def citation_check(answer: str, sources: list):
    cited = set(re.findall(r'\[(S\d+)\]', answer))
    known = {s['source_id'] for s in sources}
    unknown = sorted(cited - known)
    if unknown:
        # Reject fabricated reference identifiers; don't silently bless the answer.
        return {'status': 'invalid_source_ids', 'unknown_ids': unknown,
                'scope': '仅检查引用编号，不验证全部事实'}, False
    return {'status': 'references_present' if cited else 'no_citations',
            'cited_ids': sorted(cited), 'scope': '仅检查引用编号与本次检索结果一致，不等于事实全部正确'}, True
