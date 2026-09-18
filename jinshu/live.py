"""V4 production adapters. Original app/* modules remain unchanged.

The same Runtime/DAG runs against either the original offline stores or real
MongoDB, Redis, Milvus and an OpenAI-compatible private/approved model endpoint.
No network exception is ever converted into a hash embedding.
"""
from __future__ import annotations
import asyncio, hashlib, json, math, os, time
from dataclasses import dataclass
import httpx
from app.llm.client import LLMClient, LLMError
from app.storage.mongodb import MongoDB
from app.storage.redis_store import RedisSessionStore
from app.retrieval.bm25 import BM25Index
from .context import run_state


def local_models() -> bool:
    return os.getenv('JINSHU_MODEL_SCOPE', 'external') == 'local'


def models_allowed(state=None) -> bool:
    state = run_state.get() if state is None else state
    return bool(state and state.get('models_enabled', state.get('allow_external', False)))


def evidence_allowed(chunks) -> bool:
    return local_models() or all(c.get('external_allowed', False) for c in chunks)


def event(kind, **values):
    state = run_state.get()
    if state is not None:
        state.setdefault('model_calls', []).append({'kind': kind, **values})


class AsyncMongo(MongoDB):
    """Original MongoStore interface, backed by PyMongo Async, not Motor."""
    async def connect(self):
        from pymongo import AsyncMongoClient
        self.client = AsyncMongoClient(self.settings.mongodb_uri,
            serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
            socketTimeoutMS=20000, maxPoolSize=30)
        await self.client.admin.command('ping')
        self.db = self.client[self.settings.mongodb_db]
        await self._ensure_indexes()
        await self.db['document_heads'].create_index([('doc_id', 1)])
        await self.db['pilot_events'].create_index([('created_at', 1)])

    async def close(self):
        if self.client is not None:
            await self.client.close()


class LiveRedis(RedisSessionStore):
    """Only working memory may degrade to single-turn. Jobs never fake ACKs."""
    async def get_session(self, session_id):
        try:
            return await asyncio.wait_for(super().get_session(session_id), 2)
        except Exception as exc:
            event('redis_working_memory', status='single_turn', error=type(exc).__name__)
            return None

    async def set_session(self, session_id, data, ttl=1800):
        try:
            await asyncio.wait_for(super().set_session(session_id, data, ttl), 2)
        except Exception as exc:
            event('redis_working_memory', status='not_saved', error=type(exc).__name__)


class ChatClient(LLMClient):
    """Reusable HTTP pool; real returned token counts are recorded, not estimated."""
    def __init__(self, settings):
        super().__init__(os.getenv('CHAT_BASE_URL', settings.relay_base_url),
            os.getenv('CHAT_API_KEY', settings.relay_api_key),
            os.getenv('CHAT_MODEL', settings.relay_model),
            timeout=float(os.getenv('MODEL_TIMEOUT', '120')),
            max_tokens=int(os.getenv('CHAT_MAX_TOKENS', '384')))
        self.http = httpx.AsyncClient(timeout=self.timeout)

    def name(self):
        return 'private_openai_compatible' if local_models() else 'approved_external'

    async def complete(self, messages, *, temperature=None, max_tokens=None, response_format=None):
        started = time.perf_counter()
        payload = {'model': self.model, 'messages': messages,
                   'temperature': self.temperature if temperature is None else temperature,
                   'max_tokens': self.max_tokens if max_tokens is None else max_tokens, 'stream': False}
        if response_format:
            payload['response_format'] = response_format
        try:
            response = await self.http.post(self._chat_url(), headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise LLMError('empty completion')
            event('chat', model=data.get('model', self.model), status='ok',
                  usage=data.get('usage'), latency_ms=round((time.perf_counter()-started)*1000, 2))
            return content
        except Exception as exc:
            event('chat', model=self.model, status='failed', error=type(exc).__name__)
            raise LLMError('model endpoint failed: '+type(exc).__name__) from exc

    async def close(self):
        await self.http.aclose()


class SemanticEmbeddings:
    provider = 'semantic_http'
    def __init__(self, settings):
        self.model = os.getenv('EMBEDDING_MODEL', settings.embedding_model)
        self.dim = int(os.getenv('EMBEDDING_DIM', str(settings.embedding_dim)))
        self.base = os.getenv('EMBEDDING_BASE_URL', settings.relay_base_url).rstrip('/')
        self.key = os.getenv('EMBEDDING_API_KEY', settings.relay_api_key)
        self.revision = os.getenv('EMBEDDING_REVISION', 'configured')
        self.query_prefix = os.getenv('EMBEDDING_QUERY_PREFIX', '')
        self.fingerprint = hashlib.sha256(f'{self.model}|{self.revision}|{self.dim}|{self.query_prefix}'.encode()).hexdigest()[:12]
        self.http = httpx.AsyncClient(timeout=float(os.getenv('EMBEDDING_TIMEOUT', '120')))
        self.batch_size = int(os.getenv('EMBEDDING_BATCH_SIZE', '16'))

    async def embed(self, texts):
        result = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start+self.batch_size]
            if not batch:
                continue
            res = await self.http.post(self.base+'/embeddings', headers={'Authorization':'Bearer '+self.key},
                json={'model':self.model, 'input':batch, 'encoding_format':'float'})
            res.raise_for_status()
            data = res.json()
            rows = sorted(data['data'], key=lambda r: r['index'])
            if [r['index'] for r in rows] != list(range(len(batch))):
                raise ValueError('missing/duplicate embedding indices')
            for row in rows:
                vector = row['embedding']
                if len(vector) != self.dim or any(not math.isfinite(float(v)) for v in vector):
                    raise ValueError('embedding dimension/finite value mismatch')
                if sum(float(v)**2 for v in vector) == 0:
                    raise ValueError('zero embedding')
                result.append(vector)
            event('embedding', model=self.model, dimension=self.dim, texts=len(batch), status='ok', usage=data.get('usage'))
        return result

    async def embed_query(self, query):
        return (await self.embed([self.query_prefix+query]))[0]

    async def close(self):
        await self.http.aclose()


class HTTPReranker:
    def __init__(self, settings):
        self.model = os.getenv('RERANKER_MODEL', settings.reranker_model)
        self.base = os.getenv('RERANKER_BASE_URL', settings.relay_base_url).rstrip('/')
        self.key = os.getenv('RERANKER_API_KEY', settings.relay_api_key)
        self.http = httpx.AsyncClient(timeout=float(os.getenv('RERANKER_TIMEOUT', '60')))

    async def rerank(self, query, candidates, top_k=5):
        if not candidates:
            return []
        res = await self.http.post(self.base+'/rerank', headers={'Authorization':'Bearer '+self.key},
            json={'model':self.model,'query':query,'documents':[c['content'] for c in candidates],'top_n':top_k})
        res.raise_for_status()
        rows = res.json()['results']
        indices = [r['index'] for r in rows]
        if len(indices)!=len(set(indices)) or any(type(i) is not int or not 0<=i<len(candidates) for i in indices):
            raise ValueError('invalid reranker indices')
        event('rerank', model=self.model, status='ok', candidates=len(candidates))
        return [candidates[r['index']]|{'rerank_score':float(r['relevance_score'])} for r in rows[:top_k]]

    async def close(self):
        await self.http.aclose()


class RevisionBM25(BM25Index):
    """Reuse original BM25; refresh per-department index on authoritative revision.
    This improves coherence but is not an Elasticsearch-scale shared index.
    """
    def __init__(self, store):
        super().__init__(); self.store=store; self.revisions={}; self.indices={}; self.lock=asyncio.Lock()

    async def search(self, query, top_k=10, dept_id=None):
        if not dept_id:
            return []
        revision = await self.store.get('corpus_revisions', dept_id) or {'value':0}
        value = revision['value']
        async with self.lock:
            if self.revisions.get(dept_id) != value:
                rows = await self.store.list_active_chunks(dept_id)
                idx=BM25Index(); idx.index(rows)
                self.indices[dept_id]=idx; self.revisions[dept_id]=value
            return self.indices[dept_id].search(query, top_k, dept_id)


def configure_clients(c, settings):
    """Called before original agent assembly, so all agents share the same clients."""
    c.mongo=AsyncMongo(settings); c.store.mongo=c.mongo
    c.session_store=LiveRedis(settings)
    c.llm=ChatClient(settings)
    c.live_embeddings=SemanticEmbeddings(settings)
    c.live_reranker=HTTPReranker(settings)
    c.user_memory.llm=c.llm
    c.dept_memory.llm=c.llm
    if hasattr(c.episodic_memory,'llm'):c.episodic_memory.llm=c.llm
    c.bm25=RevisionBM25(c.store)
    c.retrieval_agent.hybrid.bm25=c.bm25
    c.retrieval_agent.hybrid.reranker=c.live_reranker


async def ping_runtime(runtime):
    if runtime.profile == 'offline':
        return {'mode':'offline','services':{},'semantic_embeddings':False,'real_llm':False}
    c=runtime.c; checks={}
    for name, call in [('mongo',lambda:c.mongo.client.admin.command('ping')),
                       ('redis',lambda:c.session_store.redis.ping()),
                       ('milvus',lambda:asyncio.to_thread(c.vector_store.client.list_collections))]:
        try:
            await asyncio.wait_for(call(),5); checks[name]='ok'
        except Exception as exc:
            checks[name]='unavailable:'+type(exc).__name__
    return {'mode':'services','model_scope':os.getenv('JINSHU_MODEL_SCOPE','external'),
            'services':checks,'embedding_model':c.embeddings.model,'embedding_dimension':c.embeddings.dim,
            'collection':c.vector_store.collection,'chat_model':c.llm.model,
            'note':'Connectivity only; model quality requires evaluation. No secrets returned.'}
