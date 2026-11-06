"""Reuse Mongo connections within one event loop, never across asyncio loops."""
import asyncio
import threading
import weakref

_clients = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def client_for(env):
    from pymongo import AsyncMongoClient
    loop = asyncio.get_running_loop()
    uri = env['MONGODB_URI']
    with _lock:
        clients = _clients.setdefault(loop, {})
        if uri not in clients:
            clients[uri] = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000,
                                           connectTimeoutMS=5000, maxPoolSize=12,
                                           minPoolSize=0, maxIdleTimeMS=60_000)
        return clients[uri]


def collection(env, name):
    return client_for(env)[env.get('MONGODB_DB', 'jinshu')][name]
