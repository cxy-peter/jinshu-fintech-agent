"""Production-only boot/route checks. No pytest, packaging, database or model requests."""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
required = ('index.py', 'core/app.py', 'core/config.py', 'core/provider.py',
            'core/web/index.html', 'core/web/app.js', 'core/web/style.css',
            'jinshu/tools.py', 'jinshu/fixtures.py', 'jinshu/model_config.py',
            'unified/tools.py', 'data/synthetic/calendar.json')
for name in required:
    if not (ROOT / name).is_file():
        raise RuntimeError('missing_runtime_asset:' + name)
modules_before_boot = set(sys.modules)
from index import app
from core import VERSION
import httpx
assert app.version == VERSION
for forbidden in ('pymongo', 'pymilvus', 'redis', 'numpy', 'sklearn', 'app.main', 'jinshu.runtime'):
    assert forbidden not in (set(sys.modules) - modules_before_boot), 'default runtime imported optional dependency: ' + forbidden
async def smoke():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://build.local') as client:
        for route in ('/', '/api/status', '/api/tools', '/assets/app.js', '/assets/style.css'):
            response = await client.get(route)
            assert response.status_code == 200, (route, response.status_code)
        status = (await client.get('/api/status')).json()
        assert status['entrypoint'] == 'index:app' and status['mode'] == 'core'
        assert status['capabilities']['mongodb_required'] is False
        assert status['model']['inference_verified'] is False
asyncio.run(smoke())
info = {'version': VERSION, 'entrypoint': 'index:app', 'mode': 'core',
        'source_commit': os.getenv('VERCEL_GIT_COMMIT_SHA'),
        'build_import_verified': True, 'route_smoke_verified': True,
        'cloud_services_contacted': False, 'paid_model_called': False,
        'source_hashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in required}}
(ROOT/'core/web/build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
print('Jinshu V9 production-only build passed: same index:app; zero database/ML imports; zero model calls.')
