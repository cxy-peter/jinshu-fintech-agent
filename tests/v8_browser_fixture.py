"""CI ONLY. Excluded from Vercel. Never import this module from index.py."""
from contextlib import asynccontextmanager
from unified.app import create_app
from jinshu.runtime import Runtime
from test_unified_v8 import MemoryTasks
runtime=Runtime();app=create_app(runtime,MemoryTasks())
@asynccontextmanager
async def lifespan(app):
 await runtime.initialize()
 yield
 await runtime.close()
app.router.lifespan_context=lifespan
