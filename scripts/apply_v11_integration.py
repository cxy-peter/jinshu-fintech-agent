"""One-time, hash-verified transport of already-tested source edits.

CI applies these exact edits before tests; after success it commits normal source
and removes the transport JSON. This never runs in the deployed application.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / '.github/v11-integration.json'
if source.exists():
    changes = json.loads(source.read_text())
    allowed = {'core/__init__.py','core/app.py','core/security.py','core/web/index.html',
               'core/web/style.css','jinshu/tools.py','scripts/build_unified.py'}
    assert set(changes) == allowed
    prepared = {}
    for name, spec in changes.items():
        value = (root / name).read_text()
        assert hashlib.sha256(value.encode()).hexdigest() == spec['before'], name
        for start, end, replacement in reversed(spec['edits']):
            value = value[:start] + replacement + value[end:]
        assert hashlib.sha256(value.encode()).hexdigest() == spec['after'], name
        prepared[name] = value
    for name, value in prepared.items():
        (root / name).write_text(value)
    source.unlink()
    print('Applied verified source changes:', ', '.join(prepared))
