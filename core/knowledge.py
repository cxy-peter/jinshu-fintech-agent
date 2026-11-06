"""Small, inspectable keyword retrieval. No embeddings, external index or hidden uploads."""
from __future__ import annotations
import re
from jinshu.fixtures import DOCS
from .retrieval_query import terms

def retrieve(query: str, documents: list, include_examples: bool):
    from .rag import chunk_text, rank
    candidates = []
    if include_examples:
        for topic, dept, title, version, status, body in DOCS:
            if status == 'active':
                candidates.append({'title': title + '（项目合成示例）', 'text': body,
                    'origin': 'synthetic_example', 'version': version})
    for doc in documents:
        candidates.append({'title': doc.title, 'text': doc.text, 'origin': 'user_supplied', 'version': None})
    chunks = []
    for i, doc in enumerate(candidates):
        for ch in chunk_text(doc['text'], doc['title']):
            chunks.append(doc | ch | {'doc_id': 'temporary-' + str(i),
                                     'chunk_id': f'temporary-{i}:{ch["index"]}'})
    return rank(query, chunks, top_k=4)

def citation_check(answer: str, sources: list):
    blocks=re.findall(r'\[(S\d+(?=[\s,，;；\]])[^\]\r\n]{0,160})\]',answer)
    cited={identifier for block in blocks for identifier in re.findall(r'\bS\d+\b',block)}
    known = {s['source_id'] for s in sources}
    unknown = sorted(cited - known)
    if unknown:
        # Reject fabricated reference identifiers; don't silently bless the answer.
        return {'status': 'invalid_source_ids', 'unknown_ids': unknown,
                'scope': '仅检查引用编号，不验证全部事实'}, False
    by_id={s['source_id']:s for s in sources}
    for block in blocks:
        ids=re.findall(r'\bS\d+\b',block)
        pages=re.findall(r'(?:原文页码|page|p\.)\s*(\d+)|(?:原文)?第\s*(\d+)\s*页',block,re.I)
        if len(ids)==1 and any(int(a or b)!=by_id[ids[0]].get('page') for a,b in pages):
            return {'status':'invalid_source_pages','source_id':ids[0],
                    'scope':'引用括号内的页码与本次原文不一致'},False
    return {'status': 'references_present' if cited else 'no_citations',
            'cited_ids': sorted(cited), 'scope': '仅检查引用编号与本次检索结果一致，不等于事实全部正确'}, True
