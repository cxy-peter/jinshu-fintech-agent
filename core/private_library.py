"""Browser-owned cloud documents; originals never enter Git or the public library.

Uploads are bounded parts, parsing happens once, and query-time uses immutable
page text. The unguessable HttpOnly owner cookie is the capability, independently
of the public demonstration role. A single-use handoff transfers that capability
to another browser without exposing a corpus in a URL or granting a shared role.
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import io
import json
import math
import secrets
import time
import uuid
import zipfile
import zlib
from collections import OrderedDict, defaultdict
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from . import governance as g
from .reference_library import INDEX_SCHEMA, ReferenceIndex, ReferenceStore
from .security import Budget

PART_SIZE = 50_000
MAX_FILE = 12_000_000
MAX_TEXT = 6_000_000
MAX_DOCUMENTS = 25
EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.csv', '.json'}
_indexes = OrderedDict()
_combined_indexes = OrderedDict()


def parse_document(data: bytes, name: str):
    """Native text only. PDF page numbers are physical pages, not guessed folios."""
    extension = '.' + name.rsplit('.', 1)[-1].lower()
    if extension not in EXTENSIONS or not data or len(data) > MAX_FILE:
        raise ValueError('支持 PDF、DOCX、TXT、MD、CSV、JSON，单文件最多12MB。')
    warnings = []
    if extension == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('请先在本机解密有权使用的PDF。')
        if len(reader.pages) > 1500:
            raise ValueError('单份PDF最多1500页，请拆分。')
        pages = []
        characters = 0
        for number, page in enumerate(reader.pages, 1):
            body = (page.extract_text(extraction_mode='layout') or '') if page.get('/Contents') else ''
            characters += len(body)
            if characters > MAX_TEXT:
                raise ValueError('提取正文过长，请拆分文件。')
            pages.append({'page': number, 'text': body})
        empty = sum(len(p['text'].strip()) < 15 for p in pages)
        if empty:
            warnings.append(f'{empty}页未提取到足够正文，可能需要本地OCR；这些页面不会被假称为已识别。')
        location = 'physical_pdf_page'
    elif extension == '.docx':
        from docx import Document
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 60_000_000:
                raise ValueError('DOCX解压内容过大。')
        doc = Document(io.BytesIO(data))
        body = '\n'.join(p.text for p in doc.paragraphs)
        body += '\n' + '\n'.join('| ' + ' | '.join(c.text.replace('\n', ' ') for c in r.cells) + ' |'
                                   for table in doc.tables for r in table.rows)
        pages = [{'page': 1, 'text': body}]
        location = 'logical_text_section'
        warnings.append('Word未计算排版页码；“第1段”表示提取文本，不是原文件页码。')
    else:
        try:
            body = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            body = data.decode('gb18030')
        if extension == '.csv':
            import csv
            rows = list(csv.reader(io.StringIO(body)))
            body = '\n'.join('| ' + ' | '.join(cell.replace('\n', ' ') for cell in row) + ' |' for row in rows)
        pages = [{'page': 1, 'text': body}]
        location = 'logical_text_section'
    if sum(len(p['text']) for p in pages) > MAX_TEXT:
        raise ValueError('提取正文超过600万字，请拆分。')
    if not any(p['text'].strip() for p in pages):
        raise ValueError('没有可检索正文。扫描PDF需先OCR，未建立空索引。')
    warnings.append('PDF/Word表格为原生文本提取，关键金额与列对应关系请对照原文件。')
    return pages, warnings, location


def owner(request):
    oid = g.owner(request)
    if not oid:
        raise HTTPException(409, '请先初始化工作空间，再导入个人资料。')
    return oid


def visible(state, oid):
    return [d for d in state.get('private_documents', {}).values() if d['owner'] == oid]


def public_record(row):
    return {k: v for k, v in row.items() if k not in {'owner', 'blob', 'original_blob'}}


async def document_index(store, row):
    key = INDEX_SCHEMA + ':' + row['id'] + ':' + row['revision']
    if key in _indexes:
        _indexes.move_to_end(key)
        return _indexes[key]
    ref = ReferenceStore(store)
    index_key = 'private_index:' + key
    persisted = await ref.get(index_key)
    if persisted is not None:
        try:
            result = await asyncio.to_thread(ReferenceIndex.deserialize, persisted, row['revision'])
        except (ValueError, TypeError, KeyError, zlib.error):
            result = None
        if result is not None:
            _indexes[key] = result
            while len(_indexes) > 16:
                _indexes.popitem(last=False)
            return result
    compressed = await ref.get(row['blob'])
    if not compressed or hashlib.sha256(compressed).hexdigest() != row['revision']:
        raise ValueError('个人资料完整性校验失败。')
    def build():
        pack = json.loads(gzip.decompress(compressed))
        return ReferenceIndex(pack)
    result = await asyncio.to_thread(build)
    # Indexes are derived data, prepared during upload. Cold instances load the
    # serialized postings; a schema change or corrupt cache rebuilds from text.
    if store.env.get('JINSHU_STORE_READ_ONLY') != '1':
        try:
            payload = await asyncio.to_thread(result.serialize, row['revision'])
            await ref.put(index_key, payload)
        except Exception:
            # A cache write failure does not invalidate the verified source.
            pass
    _indexes[key] = result
    while len(_indexes) > 16:
        _indexes.popitem(last=False)
    return result


async def search(store, query, request, limit=6, state=None):
    started = time.perf_counter()
    oid = g.owner(request)
    if not oid:
        return [], {'status': 'not_initialized', 'documents': 0, 'elapsed_ms': 0}
    state = state if state is not None else await store.read()
    docs = visible(state, oid)
    if not docs:
        return [], {'status': 'empty', 'documents': 0, 'hits': 0,
                    'elapsed_ms': round((time.perf_counter() - started) * 1000), 'model_called': False}
    gate = asyncio.Semaphore(3)
    async def lookup(doc):
        async with gate:
            return await document_index(store, doc)
    key = INDEX_SCHEMA + ':' + hashlib.sha256(json.dumps(sorted((d['id'], d['revision']) for d in docs)).encode()).hexdigest()
    if key not in _combined_indexes:
        indexes = await asyncio.gather(*(lookup(d) for d in docs))
        _combined_indexes[key] = await asyncio.to_thread(combine_indexes, indexes)
        while len(_combined_indexes) > 4:
            _combined_indexes.popitem(last=False)
    _combined_indexes.move_to_end(key)
    rows = await asyncio.to_thread(_combined_indexes[key].search, query, limit)
    metadata = {d['id']: d for d in docs}
    hits = []
    for result in rows:
        doc = metadata[result['doc_id']]
        hits.append(result | {'origin': 'private_cloud', 'version': doc['revision'],
                     'location_kind': doc['location_kind'], 'department': 'private',
                     'authority': '当前浏览器授权的个人参考；非机构已审核制度', 'external_allowed': True})
    return hits[:limit], {'status': 'matched' if hits else 'no_matches' if docs else 'empty',
                          'documents': len(docs), 'hits': min(len(hits), limit),
                          'elapsed_ms': round((time.perf_counter() - started) * 1000),
                          'mode': 'private_combined_page_index', 'model_called': False}


def combine_indexes(indexes):
    """One authorized corpus gives every BM25 candidate the same IDF scale."""
    merged = ReferenceIndex.__new__(ReferenceIndex)
    merged.docs, merged.rows, merged.lengths = {}, [], []
    merged.postings = defaultdict(list)
    for index in indexes:
        offset = len(merged.rows)
        merged.docs.update(index.docs)
        merged.rows.extend(index.rows)
        merged.lengths.extend(index.lengths)
        for term, postings in index.postings.items():
            merged.postings[term].extend((position + offset, frequency) for position, frequency in postings)
    merged.avg = sum(merged.lengths) / max(1, len(merged.rows)) or 1
    return merged


async def verify(store, sources, request):
    private = [s for s in sources if s.get('origin') == 'private_cloud']
    if not private:
        return
    current = {d['id']: d for d in visible(await store.read(), owner(request))}
    if any(s['doc_id'] not in current or current[s['doc_id']]['revision'] != s['version'] for s in private):
        raise ValueError('个人资料在回答过程中已删除或转移，请重新提问。')


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Upload(Input):
    name: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    size: int = Field(ge=1, le=MAX_FILE)


class Part(Input):
    data: str = Field(min_length=1, max_length=68000)


class Claim(Input):
    token: str = Field(min_length=40, max_length=100)


def install(app, store, authorize):
    ref = ReferenceStore(store)
    budget = Budget()

    @app.get('/api/private-library')
    async def catalog(request: Request, c=Depends(authorize)):
        docs = visible(await store.read(), owner(request))
        return {'documents': [public_record(d) for d in docs], 'scope': 'current_browser_private',
                'max_file_bytes': MAX_FILE, 'shared_with_demo_accounts': False}

    @app.post('/api/private-library/uploads')
    async def start(d: Upload, request: Request, c=Depends(authorize)):
        oid = owner(request)
        if not budget.consume(oid, model=False, per_minute=10):
            raise HTTPException(429, '导入过于频繁，请稍后重试。')
        if any(ch in d.name for ch in ['/', '\\', '\x00']) or '.' + d.name.rsplit('.', 1)[-1].lower() not in EXTENSIONS:
            raise ValueError('无效文件名或文件类型。')
        state = await store.read()
        existing = next((x for x in visible(state, oid) if x['sha256'] == d.sha256), None)
        if existing:
            return {'existing': public_record(existing), 'deduplicated': True}
        if len(visible(state, oid)) >= MAX_DOCUMENTS or len(state.get('private_documents', {})) >= 300:
            raise ValueError('个人资料数量达到当前原型上限，请先移除不需要的资料。')
        identifier = uuid.uuid4().hex
        row = d.model_dump() | {'id': identifier, 'owner': oid, 'expires': time.time() + 3600,
                                'parts': math.ceil(d.size / PART_SIZE)}
        await ref.put('private_upload:' + identifier, row, temporary=True)
        return {'id': identifier, 'parts': row['parts'], 'part_size': PART_SIZE}

    async def upload_record(identifier, request):
        row = await ref.get('private_upload:' + identifier)
        if not row or row['owner'] != owner(request) or row['expires'] < time.time():
            raise HTTPException(404, '导入任务不存在或已过期。')
        return row

    @app.put('/api/private-library/uploads/{identifier}/parts/{number}')
    async def part(identifier: str, number: int, d: Part, request: Request, c=Depends(authorize)):
        row = await upload_record(identifier, request)
        if not 0 <= number < row['parts']:
            raise ValueError('分片编号无效。')
        try:
            raw = base64.b64decode(d.data, validate=True)
        except ValueError:
            raise ValueError('文件分片不是有效编码。') from None
        if len(raw) != min(PART_SIZE, row['size'] - number * PART_SIZE):
            raise ValueError('分片大小不匹配。')
        key = f'private_part:{identifier}:{number}'
        previous = await ref.get(key)
        if previous is not None and previous != raw:
            raise ValueError('重复分片内容冲突，未覆盖。')
        await ref.put(key, raw, temporary=True)
        return {'part': number, 'bytes': len(raw)}

    @app.post('/api/private-library/uploads/{identifier}/finish')
    async def finish(identifier: str, request: Request, c=Depends(authorize)):
        row = await upload_record(identifier, request)
        gate = asyncio.Semaphore(4)
        async def read_part(n):
            async with gate:
                return await ref.get(f'private_part:{identifier}:{n}')
        parts = await asyncio.gather(*(read_part(n) for n in range(row['parts'])))
        if any(p is None for p in parts):
            raise ValueError('文件分片不完整，原资料未改变。')
        raw = b''.join(parts)
        if len(raw) != row['size'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('文件SHA256校验失败。')
        pages, warnings, location = await asyncio.to_thread(parse_document, raw, row['name'])
        did = 'private_' + identifier
        pack = {'documents': [{'id': did, 'title': row['name'], 'status': 'active', 'pages': pages}]}
        compressed = gzip.compress(json.dumps(pack, ensure_ascii=False).encode(), mtime=0)
        revision = hashlib.sha256(compressed).hexdigest()
        if len(compressed) > 8_000_000:
            raise ValueError('资料压缩后超过8MB，请拆分。')
        record = {'id': did, 'owner': row['owner'], 'title': row['name'], 'sha256': row['sha256'],
                  'revision': revision, 'blob': 'private_text:' + did, 'pages': len(pages),
                  'original_blob': 'private_original:' + did, 'original_available': True,
                  'characters': sum(len(p['text']) for p in pages), 'location_kind': location,
                  'warnings': warnings, 'imported_at': g.now(), 'origin': 'private_cloud'}
        await ref.put(record['blob'], compressed)
        await ref.put(record['original_blob'], raw)
        def save(state):
            docs = state.setdefault('private_documents', {})
            old = next((d for d in docs.values() if d['owner'] == row['owner'] and d['sha256'] == row['sha256']), None)
            if old:
                return old
            if len(visible(state, row['owner'])) >= MAX_DOCUMENTS or len(docs) >= 300:
                raise ValueError('个人资料数量达到当前原型上限。')
            docs[did] = record
            return record
        saved = await store.mutate(save)
        await document_index(store, saved)
        return {'document': public_record(saved), 'model_called': False, 'shared': False}

    @app.delete('/api/private-library/{did}')
    async def remove(did: str, request: Request, c=Depends(authorize)):
        oid = owner(request)
        def drop(state):
            record = state.get('private_documents', {}).get(did)
            if not record or record['owner'] != oid:
                raise HTTPException(404, '个人资料不存在。')
            state['private_documents'].pop(did)
            return {'removed_from_retrieval': True, 'original_local_file_changed': False}
        return await store.mutate(drop)

    @app.get('/api/private-library/search')
    async def lookup(request: Request, q: str = '', c=Depends(authorize)):
        if not 1 <= len(q.strip()) <= 6000:
            raise ValueError('请输入有效检索词。')
        hits, diagnostics = await search(store, q, request)
        return {'sources': hits, 'diagnostics': diagnostics, 'model_called': False}

    @app.get('/api/private-library/{did}/page/{page}')
    async def page(did: str, page: int, request: Request, c=Depends(authorize)):
        row = next((d for d in visible(await store.read(), owner(request)) if d['id'] == did), None)
        if not row:
            raise HTTPException(404, '个人资料不存在。')
        index = await document_index(store, row)
        pages = index.docs[did]['pages']
        found = next((p for p in pages if p['page'] == page), None)
        if not found:
            raise HTTPException(404, '原文页不存在。')
        return {'id': did, 'title': row['title'], 'version': row['revision'],
                'pages': [p['page'] for p in pages], 'location_kind': row['location_kind'],
                'original_available': row.get('original_available', False), **found}

    @app.get('/api/private-library/{did}/original')
    async def original(did: str, request: Request, c=Depends(authorize)):
        row = next((d for d in visible(await store.read(), owner(request)) if d['id'] == did), None)
        if not row or not row.get('original_blob'):
            raise HTTPException(404, '原文件不存在。')
        raw = await ref.get(row['original_blob'])
        if not raw or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('原文件完整性校验失败。')
        return Response(raw, media_type='application/octet-stream', headers={
            'Content-Disposition': 'attachment; filename="jinshu-document"; filename*=UTF-8\'\'' + quote(row['title'], safe='')})

    @app.post('/api/private-library/handoff')
    async def handoff(request: Request, c=Depends(authorize)):
        oid = owner(request)
        token = secrets.token_urlsafe(32)
        def issue(state):
            docs = visible(state, oid)
            if not docs:
                raise ValueError('没有可转移的个人资料。')
            claims = state.setdefault('private_claims', {})
            for key in list(claims):
                if claims[key]['expires'] < time.time() or claims[key]['owner'] == oid:
                    claims.pop(key)
            if len(claims) >= 100:
                raise ValueError('转移请求已满，请稍后重试。')
            claims[g.digest(token)] = {'owner': oid, 'documents': [d['id'] for d in docs], 'expires': time.time() + 86400}
        await store.mutate(issue)
        return {'token': token, 'expires_in_seconds': 86400, 'single_use': True,
                'notice': '在另一个浏览器认领后，本浏览器不再拥有这些资料。不要公开此链接。'}

    @app.post('/api/private-library/claim')
    async def claim(d: Claim, request: Request, c=Depends(authorize)):
        oid = owner(request)
        def transfer(state):
            claims = state.setdefault('private_claims', {})
            row = claims.get(g.digest(d.token))
            if not row or row['expires'] < time.time():
                raise ValueError('认领链接无效、已使用或已过期。')
            records = state.get('private_documents', {})
            docs = [records[i] for i in row['documents'] if i in records and records[i]['owner'] == row['owner']]
            if row['owner'] != oid and len(visible(state, oid)) + len(docs) > MAX_DOCUMENTS:
                raise ValueError('资料数量超过当前浏览器上限。')
            for record in docs:
                record['owner'] = oid
            claims.pop(g.digest(d.token))
            return {'claimed': len(docs), 'documents': [public_record(r) for r in docs]}
        return await store.mutate(transfer)

