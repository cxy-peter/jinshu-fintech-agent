"""Bounded prototype fact plane: SQLite locally, private Blob or Mongo CAS in cloud.

Never use Vercel's ephemeral filesystem as durable storage. No model call runs in
a mutation: compare-and-swap retries must be side-effect free.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
import sqlite3
import httpx
from pathlib import Path


def initial():
    return dict(revision=0, documents={}, conversations={}, feedback={}, skills={}, audit=[], sessions={})


def encoded(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(data.encode()) > 8_000_000:
        raise ValueError('演示存储达到 8MB 上限，请归档资料或切换企业存储；未覆盖旧数据。')
    return data


class StoreUnavailable(Exception):
    pass


class Store:
    def __init__(self, env=None):
        self.env = os.environ if env is None else env
        e = self.env
        # Explicit choice avoids a stale optional URI breaking working chat.
        self.kind = e.get('JINSHU_STORE') or ('private-blob' if e.get('BLOB_STORE_ID') or e.get('BLOB_READ_WRITE_TOKEN') else 'unconfigured' if e.get('VERCEL') else 'sqlite')
        self.path = Path(e.get('JINSHU_DATA_DIR', 'workspace/governed')) / 'state.sqlite'
        self.lock = asyncio.Lock()

    async def read(self):
        try:
            value, _ = await self._read()
            return copy.deepcopy(value or initial())
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise StoreUnavailable('持久化服务暂不可用，原对话通道仍可使用。') from exc

    async def _read(self):
        if self.kind == 'sqlite':
            return await asyncio.to_thread(self._sql_read), None
        if self.kind == 'private-blob':
            token, store_id = self._blob_auth()
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                row = await client.get(f'https://{store_id}.private.blob.vercel-storage.com/governance/state-v1.json?cache=0',
                    headers={'authorization':'Bearer '+token,'accept-encoding':'identity'})
                if row.status_code == 404:
                    return None, None
                etag=row.headers.get('etag','')
                if row.status_code != 200 or not etag or etag.startswith('W/'):
                    raise StoreUnavailable('存储版本校验失败，未继续写入。')
                return row.json(), etag
        if self.kind == 'mongo':
            from pymongo import AsyncMongoClient
            async with AsyncMongoClient(self.env['MONGODB_URI'], serverSelectionTimeoutMS=5000) as client:
                row = await client[self.env.get('MONGODB_DB', 'jinshu')]['governed_state'].find_one({'_id': 'v1'})
                return (row['value'], row['revision']) if row else (None, None)
        raise StoreUnavailable('请连接私有 Blob 或 MongoDB；云端不会用临时磁盘冒充持久化。')

    def _blob_auth(self):
        # Static server-side token supplied by the project's Blob connection.
        # Protocol mirrors @vercel/blob 2.7 conditional puts. Python SDK 0.9
        # lacks ifMatch, so it must NOT be used for governance writes.
        token=self.env.get('BLOB_READ_WRITE_TOKEN','')
        parts=token.split('_')
        if len(parts)<5 or parts[:3]!=['vercel','blob','rw']:
            raise StoreUnavailable('请连接此项目的私有 Blob 读写令牌。')
        return token,parts[3].lower()

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        return db

    def _sql_read(self):
        with self._db() as db:
            row = db.execute('SELECT value FROM state WHERE id=1').fetchone()
            return json.loads(row[0]) if row else None

    def _sql_mutate(self, fn):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM state WHERE id=1').fetchone()
            value = json.loads(row[0]) if row else initial()
            result = fn(value)
            value['revision'] += 1
            db.execute('INSERT INTO state(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (encoded(value),))
            return copy.deepcopy(result)

    async def mutate(self, fn):
        if self.env.get('JINSHU_STORE_READ_ONLY') == '1':
            raise StoreUnavailable('资料存储正在只读迁移，稍后可继续保存；现有数据未改变。')
        async with self.lock:
            if self.kind == 'sqlite':
                return await asyncio.to_thread(self._sql_mutate, fn)
            for _ in range(5):
                value, version = await self._read()
                value = value or initial()
                result = fn(value)
                value['revision'] += 1
                data = encoded(value)
                if self.kind == 'private-blob':
                    token,store_id=self._blob_auth()
                    headers={'authorization':'Bearer '+token,'x-api-version':'12','x-vercel-blob-store-id':store_id,
                        'x-vercel-blob-access':'private','x-content-type':'application/json','x-add-random-suffix':'0',
                        'x-allow-overwrite':'1' if version is not None else '0','x-cache-control-max-age':'0',
                        'x-content-length':str(len(data.encode()))}
                    if version is not None:headers['x-if-match']=version
                    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
                        response=await client.put('https://vercel.com/api/blob/?pathname=governance%2Fstate-v1.json',headers=headers,content=data.encode())
                    if response.is_success:return copy.deepcopy(result)
                    if response.status_code not in (409,412):
                        code=response.json().get('error',{}).get('code','') if response.headers.get('content-type','').startswith('application/json') else ''
                        if code not in ('precondition_failed','blob_already_exists'):
                            raise StoreUnavailable('共享存储写入失败；本次操作未确认保存。')
                elif self.kind == 'mongo':
                    from pymongo import AsyncMongoClient
                    from pymongo.errors import DuplicateKeyError
                    async with AsyncMongoClient(self.env['MONGODB_URI'], serverSelectionTimeoutMS=5000) as client:
                        col = client[self.env.get('MONGODB_DB', 'jinshu')]['governed_state']
                        try:
                            if version is None:
                                await col.insert_one({'_id': 'v1', 'revision': value['revision'], 'value': value})
                                return copy.deepcopy(result)
                            changed = await col.replace_one({'_id': 'v1', 'revision': version}, {'_id': 'v1', 'revision': value['revision'], 'value': value})
                            if changed.modified_count:
                                return copy.deepcopy(result)
                        except DuplicateKeyError:
                            pass
            raise StoreUnavailable('并发更新冲突，请刷新后重试。')
