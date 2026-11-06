"""Explicit, loopback-only folder library. No cloud file-system access.

Manual scans parse changed files once and persist page text and retrieval indexes.
Queries only load cached indexes; stale/deleted files are withheld until a scan.
The configured directory is a read whitelist, never a path supplied to search.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time
import zlib
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .private_library import EXTENSIONS, MAX_FILE, parse_document, combine_indexes
from .reference_library import INDEX_SCHEMA, ReferenceIndex

MAX_DOCUMENTS = 200
MAX_FOLDER_BYTES = 300_000_000


def _loopback(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def assert_local(request, env):
    """Do not trust forwarded headers or arbitrary DNS names resolving locally."""
    if env.get('VERCEL') or env.get('JINSHU_LOCAL_FOLDER_ENABLED') != '1':
        raise HTTPException(404, '本地文件夹服务未启用；请在本机运行 START_LOCAL_FOLDER.bat。')
    peer = request.client.host if request.client else ''
    try:
        host = request.headers.get('host', '')
        parsed = urlsplit('http://' + host)
        host_ok = (parsed.hostname in {'localhost', '127.0.0.1', '::1'}
                   and not parsed.username and not parsed.password
                   and not parsed.path and not parsed.query and not parsed.fragment)
        # Force validation of the port; urlsplit postpones this check.
        parsed.port
        origin = request.headers.get('origin')
        source = urlsplit(origin) if origin else None
        origin_ok = not source or (source.scheme in {'http', 'https'} and source.netloc == host
                                   and not source.path and not source.query and not source.fragment)
    except ValueError:
        host_ok = origin_ok = False
    if not _loopback(peer) or not host_ok or not origin_ok or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '本地资料仅允许从本机同源工作台访问。')


def _linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def validate_root(value):
    root = Path(value).expanduser()
    if not root.is_absolute() or not root.is_dir() or root == Path(root.anchor):
        raise ValueError('请选择已存在的绝对路径资料文件夹，不可选择整个磁盘。')
    if any(_linked(p) for p in (root, *root.parents)):
        raise ValueError('资料文件夹及其父目录不可使用符号链接或目录联接。')
    return root.resolve(strict=True)


class LocalFolder:
    def __init__(self, cache_path, env):
        self.path = Path(cache_path)
        self.env = env
        self.lock = threading.RLock()
        self.indexes = OrderedDict()
        self.merged_indexes = OrderedDict()

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, root TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
            size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, pages TEXT NOT NULL,
            warnings TEXT NOT NULL, location_kind TEXT NOT NULL, error TEXT NOT NULL,
            index_schema TEXT NOT NULL, search_index BLOB)''')
        return db

    def root(self):
        with self._db() as db:
            row = db.execute('SELECT root FROM settings WHERE id=1').fetchone()
        # Environment sets the initial root. A later explicit UI choice persists.
        return row['root'] if row else self.env.get('JINSHU_LOCAL_FOLDER_ROOT', '')

    def configure(self, value):
        root = str(validate_root(value))
        with self.lock, self._db() as db:
            if root != self.root():
                db.execute('DELETE FROM documents')
                self.indexes.clear()
                self.merged_indexes.clear()
            db.execute('INSERT INTO settings VALUES (1,?) ON CONFLICT(id) DO UPDATE SET root=excluded.root', (root,))
        return self.status()

    def _safe_path(self, root, relative):
        path = root / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('无效相对路径。')
        if any(_linked(p) for p in (path, *path.parents) if p != root and root in p.parents):
            raise ValueError('跳过符号链接或目录联接。')
        path.resolve(strict=True).relative_to(root)
        if not path.is_file():
            raise ValueError('仅支持普通文件。')
        return path

    def _read_file(self, root, relative):
        path = self._safe_path(root, relative)
        descriptors = []
        try:
            # POSIX: no-follow each path component, including directories. This
            # closes the parent-symlink race left by a resolve-then-open check.
            if os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'):
                parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                descriptors.append(parent)
                parts = Path(relative).parts
                for part in parts[:-1]:
                    parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    descriptors.append(parent)
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            else:
                fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
            descriptors.append(fd)
            before = os.fstat(fd)
            checked = self._safe_path(root, relative).stat()
            if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (checked.st_dev, checked.st_ino):
                raise ValueError('文件在扫描中改变，已跳过。')
            if before.st_size > MAX_FILE:
                raise ValueError('单文件最多12MB，请拆分。')
            with os.fdopen(os.dup(fd), 'rb') as handle:
                data = handle.read(MAX_FILE + 1)
            after = os.fstat(fd)
            if len(data) > MAX_FILE or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('文件在扫描中改变，已跳过。')
            return data, after
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _current(self, root, row):
        try:
            info = self._safe_path(root, row['relative_path']).stat()
            return info.st_size == row['size'] and info.st_mtime_ns == row['mtime_ns']
        except (OSError, ValueError):
            return False

    @staticmethod
    def _record(row):
        pages = json.loads(row['pages'])
        return {'id': row['id'], 'title': Path(row['relative_path']).name,
                'relative_path': row['relative_path'], 'sha256': row['sha256'],
                'version': row['sha256'], 'pages': len(pages),
                'characters': sum(len(p['text']) for p in pages),
                'location_kind': row['location_kind'], 'warnings': json.loads(row['warnings']),
                'status': 'error' if row['error'] else 'indexed', 'error': row['error']}

    def status(self):
        with self.lock, self._db() as db:
            docs = [self._record(r) for r in db.execute('SELECT * FROM documents ORDER BY relative_path')]
        return {'enabled': True, 'root': self.root(), 'documents': docs,
                'indexed_documents': sum(d['status'] == 'indexed' for d in docs),
                'supported_extensions': sorted(EXTENSIONS), 'max_file_bytes': MAX_FILE,
                'max_documents': MAX_DOCUMENTS, 'storage': 'local_sqlite',
                'uploads_automatically': False, 'scan_required_after_changes': True,
                'message': '扫描与检索分离；查询只读取已建索引。扫描PDF须先OCR。'}

    def scan(self):
        with self.lock:
            root = validate_root(self.root())
            with self._db() as db:
                previous = {r['id']: dict(r) for r in db.execute('SELECT * FROM documents')}
            prepared, skipped, count_bytes = [], [], 0
            counts = {'added': 0, 'changed': 0, 'unchanged': 0, 'errors': 0}
            for directory, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not _linked(Path(directory) / d))
                for name in sorted(files):
                    path = Path(directory) / name
                    if path.suffix.lower() not in EXTENSIONS or name.startswith('.'):
                        continue
                    relative = path.relative_to(root).as_posix()
                    if len(prepared) >= MAX_DOCUMENTS:
                        skipped.append({'path': relative, 'reason': '超过200份资料上限。'})
                        continue
                    identifier = hashlib.sha256(relative.encode()).hexdigest()[:32]
                    old = previous.get(identifier)
                    try:
                        data, info = self._read_file(root, relative)
                        count_bytes += len(data)
                        if count_bytes > MAX_FOLDER_BYTES:
                            raise ValueError('单次扫描总量超过300MB，请选择更小的目录。')
                        sha = hashlib.sha256(data).hexdigest()
                        if old and old['sha256'] == sha and old['index_schema'] == INDEX_SCHEMA and not old['error']:
                            old.update(size=info.st_size, mtime_ns=info.st_mtime_ns)
                            prepared.append(old)
                            counts['unchanged'] += 1
                            continue
                        pages, warnings, location = parse_document(data, name)
                        pack = {'documents': [{'id': identifier, 'title': name, 'status': 'active', 'pages': pages}]}
                        index = ReferenceIndex(pack)
                        prepared.append(dict(id=identifier, relative_path=relative, sha256=sha,
                            size=info.st_size, mtime_ns=info.st_mtime_ns, pages=json.dumps(pages, ensure_ascii=False),
                            warnings=json.dumps(warnings, ensure_ascii=False), location_kind=location,
                            error='', index_schema=INDEX_SCHEMA, search_index=index.serialize(sha)))
                        counts['changed' if old else 'added'] += 1
                    except Exception as exc:
                        # Failed replacements must invalidate old searchable text.
                        counts['errors'] += 1
                        reason = str(exc)[:300] if isinstance(exc, ValueError) else '文件读取或解析失败，请检查格式、权限或依赖。'
                        if path.suffix.lower() == '.pdf' and 'OCR' not in reason:
                            reason += ' 如为扫描PDF，请先在本机OCR；未建立可检索正文。'
                        skipped.append({'path': relative, 'reason': reason})
                        prepared.append(dict(id=identifier, relative_path=relative, sha256='', size=0, mtime_ns=0,
                            pages='[]', warnings='[]', location_kind='', error=reason, index_schema=INDEX_SCHEMA, search_index=None))
            present = {r['id'] for r in prepared}
            counts['removed'] = len(set(previous) - present)
            with self._db() as db:
                db.execute('DELETE FROM documents')
                db.executemany('INSERT INTO documents VALUES (:id,:relative_path,:sha256,:size,:mtime_ns,:pages,:warnings,:location_kind,:error,:index_schema,:search_index)', prepared)
            self.indexes.clear()
            self.merged_indexes.clear()
            return self.status() | {'scan': counts, 'skipped': skipped, 'scanned_bytes': count_bytes}

    def search(self, query, limit=6):
        started = time.perf_counter()
        with self.lock:
            root_value = self.root()
            if not root_value:
                return [], {'status': 'unconfigured', 'documents': 0, 'model_called': False}
            try:
                root = validate_root(root_value)
            except (ValueError, OSError):
                return [], {'status': 'root_unavailable', 'documents': 0, 'model_called': False}
            with self._db() as db:
                # Warm queries read metadata only, not all cached page/index blobs.
                docs = [dict(r) for r in db.execute("SELECT id,relative_path,sha256,size,mtime_ns,location_kind,index_schema FROM documents WHERE error='' ORDER BY relative_path")]
                current = [r for r in docs if r['index_schema'] == INDEX_SCHEMA and self._current(root, r)]
                stale = len(docs) - len(current)
                corpus_key = tuple((r['id'], r['sha256'], r['index_schema']) for r in current)
                merged = self.merged_indexes.get(corpus_key)
                if merged is None:
                    indexes = []
                    corrupt = False
                    for row in current:
                        key = (row['id'], row['sha256'], row['index_schema'])
                        index = self.indexes.get(key)
                        if index is None:
                            try:
                                payload = db.execute('SELECT search_index FROM documents WHERE id=?', (row['id'],)).fetchone()[0]
                                index = ReferenceIndex.deserialize(bytes(payload), row['sha256'])
                            except (ValueError, TypeError, KeyError, zlib.error):
                                stale += 1
                                corrupt = True
                                continue
                            self.indexes[key] = index
                            while len(self.indexes) > 16:
                                self.indexes.popitem(last=False)
                        self.indexes.move_to_end(key)
                        indexes.append(index)
                    merged = combine_indexes(indexes)
                    if not corrupt:
                        self.merged_indexes[corpus_key] = merged
                        while len(self.merged_indexes) > 2:
                            self.merged_indexes.popitem(last=False)
            metadata = {r['id']: r for r in current}
            hits = []
            for result in merged.search(query, limit):
                row = metadata[result['doc_id']]
                hits.append(result | {'origin': 'local_folder', 'version': row['sha256'], 'department': 'private',
                    'location_kind': row['location_kind'], 'external_allowed': True,
                    'authority': '用户本机资料；非机构已审核制度'})
            return hits, {'status': 'matched' if hits else 'scan_required' if stale else 'no_matches' if docs else 'empty',
                'documents': len(docs), 'stale_documents': stale, 'hits': len(hits),
                'elapsed_ms': round((time.perf_counter() - started) * 1000),
                'mode': 'local_combined_page_bm25_alias', 'model_called': False}

    def verify(self, sources):
        with self.lock, self._db() as db:
            try:
                root = validate_root(self.root())
            except (ValueError, OSError):
                raise ValueError('本地资料目录在回答过程中改变，请重新扫描后提问。') from None
            for source in sources:
                row = db.execute('SELECT * FROM documents WHERE id=?', (source['doc_id'],)).fetchone()
                if (not row or row['error'] or row['sha256'] != source['version']
                        or row['index_schema'] != INDEX_SCHEMA or not self._current(root, row)):
                    raise ValueError('本地资料在回答过程中更改、移走或删除，请重新扫描后提问。')

    def page(self, identifier, number):
        with self.lock, self._db() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone()
            if not row or row['error']:
                raise HTTPException(404, '资料不存在或未成功解析。')
            try:
                root = validate_root(self.root())
            except (ValueError, OSError):
                raise HTTPException(409, '资料文件夹不可用，请重新设置并扫描。') from None
            if not self._current(root, row):
                raise HTTPException(409, '文件已改变、移走或删除，请重新扫描。')
            pages = json.loads(row['pages'])
            found = next((p for p in pages if p['page'] == number), None)
            if found is None:
                raise HTTPException(404, '页码不存在。')
            return {'id': identifier, 'title': Path(row['relative_path']).name, 'version': row['sha256'],
                'page': number, 'pages': [p['page'] for p in pages], 'text': found['text'],
                'location_kind': row['location_kind'], 'warnings': json.loads(row['warnings'])}

    def export(self):
        with self.lock, self._db() as db:
            root = validate_root(self.root())
            docs = [{'id': r['id'], 'title': Path(r['relative_path']).name, 'status': 'active',
                     'sha256': r['sha256'], 'pages': json.loads(r['pages'])}
                    for r in db.execute("SELECT * FROM documents WHERE error='' ORDER BY relative_path")
                    if self._current(root, r)]
            if not docs:
                raise ValueError('没有可导出的已索引资料，请先扫描。')
            return gzip.compress(json.dumps({'documents': docs}, ensure_ascii=False).encode(), mtime=0)


class FolderInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    root: str = Field(min_length=1, max_length=2000)


def install(app, store, authorize, env=None):
    env = store.env if env is None else env
    library = LocalFolder(store.path.parent / 'local_folder.sqlite', env)
    app.state.local_library = library

    async def access(request: Request, c=Depends(authorize)):
        assert_local(request, env)
        return library

    @app.get('/api/local-folder')
    async def catalog(local=Depends(access)):
        return await asyncio.to_thread(local.status)

    @app.post('/api/local-folder/config')
    async def configure(d: FolderInput, local=Depends(access)):
        return await asyncio.to_thread(local.configure, d.root)

    @app.post('/api/local-folder/scan')
    async def scan(local=Depends(access)):
        return await asyncio.to_thread(local.scan)

    @app.get('/api/local-folder/search')
    async def search(q: str = '', local=Depends(access)):
        if not 1 <= len(q.strip()) <= 6000:
            raise HTTPException(422, '问题需为1至6000字。')
        sources, diagnostics = await asyncio.to_thread(local.search, q)
        return {'sources': sources, 'diagnostics': diagnostics}

    @app.get('/api/local-folder/documents/{identifier}/page/{page}')
    async def page(identifier: str, page: int, local=Depends(access)):
        return await asyncio.to_thread(local.page, identifier, page)

    @app.get('/api/local-folder/export')
    async def export(local=Depends(access)):
        data = await asyncio.to_thread(local.export)
        return Response(data, media_type='application/gzip',
            headers={'Content-Disposition': 'attachment; filename="jinshu-local-private-pack.json.gz"'})
    return library


async def search_for_chat(app, request, query):
    library = getattr(app.state, 'local_library', None)
    if library is None:
        return [], {'status': 'disabled', 'model_called': False}
    assert_local(request, library.env)
    return await asyncio.to_thread(library.search, query)


async def verify_for_chat(app, request, sources):
    local_sources = [s for s in sources if s.get('origin') == 'local_folder']
    if not local_sources:
        return
    library = getattr(app.state, 'local_library', None)
    if library is None:
        raise ValueError('本地资料服务不可用，请重新提问。')
    assert_local(request, library.env)
    await asyncio.to_thread(library.verify, local_sources)
