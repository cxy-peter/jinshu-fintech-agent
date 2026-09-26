"""Bounded request bodies and per-process abuse protection; no durable billing claims."""
from __future__ import annotations
from collections import deque
import hashlib
import threading
import time
from starlette.responses import JSONResponse

class BodyLimit:
    def __init__(self, app, limit=128_000):
        self.app, self.limit = app, limit
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        size, messages = 0, []
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            size += len(event.get('body', b''))
            if size > self.limit:
                return await JSONResponse({'error': {'code': 'REQUEST_TOO_LARGE', 'message': '请求最多 128 KB；请减少资料或历史内容。'}}, 413)(scope, receive, send)
            messages.append(event)
            if not event.get('more_body', False):
                break
        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()
        await self.app(scope, replay, send)

class Budget:
    def __init__(self, clock=time.monotonic):
        self.clock, self.lock = clock, threading.Lock()
        self.global_calls = deque()
        self.clients = {}
        self.active = 0
    def consume(self, identity, *, hourly_limit=30, per_minute=6, model=True):
        now = self.clock()
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        with self.lock:
            self.clients = {k: v for k, v in self.clients.items() if v and now-v[-1] < 60}
            queue = self.clients.setdefault(digest, deque())
            while queue and now-queue[0] >= 60:
                queue.popleft()
            if len(queue) >= per_minute or len(self.clients) > 2000:
                return False
            while self.global_calls and now-self.global_calls[0] >= 3600:
                self.global_calls.popleft()
            if model and (len(self.global_calls) >= hourly_limit or self.active >= 2):
                return False
            queue.append(now)
            if model:
                self.global_calls.append(now)
                self.active += 1
            return True
    def release(self):
        with self.lock:
            self.active = max(0, self.active-1)
