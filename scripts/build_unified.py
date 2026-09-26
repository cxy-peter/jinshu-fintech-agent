"""Fail the build for missing full-runtime assets or a broken ASGI import.

This intentionally does not connect to production services or call paid models.
"""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from compileall import compile_dir

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REQUIRED = ("index.py", "unified/web/index.html", "unified/web/app.js",
            "unified/web/provider.js", "unified/web/style.css",
            "engine/backend/app/main.py", "jinshu/runtime.py",
            "data/synthetic/documents.json", "data/synthetic/calendar.json")
for name in REQUIRED:
    if not (ROOT / name).is_file():
        raise RuntimeError("missing_runtime_asset:" + name)
for folder in ("unified", "jinshu", "engine/backend/app"):
    if not compile_dir(str(ROOT / folder), quiet=1):
        raise RuntimeError("python_compile_failed:" + folder)
from index import app
from fastapi import FastAPI
assert isinstance(app, FastAPI)
assert app.state.manager.runtime is None, "build must not initialize production services"
import httpx
async def smoke():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://build.local") as c:
        for path in ("/", "/api/status", "/assets/app.js", "/assets/provider.js", "/assets/style.css"):
            response = await c.get(path)
            assert response.status_code == 200, (path, response.status_code)
        assert (await c.get("/api/tasks")).status_code == 401
asyncio.run(smoke())
source = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
          for folder in ("unified", "jinshu", "engine/backend/app")
          for p in sorted((ROOT/folder).rglob("*")) if p.suffix in {".py", ".js", ".css", ".html"}}
# Diagnostic footprint of direct project dependencies only.
# This must use the Python standard library exclusively: a clean Vercel build
# should never fail because an optional build-diagnostic parser is absent.
from importlib.metadata import distribution, PackageNotFoundError
import re
import tomllib
declared = tomllib.loads((ROOT/"pyproject.toml").read_text())["project"]["dependencies"]
files, packages, unavailable = set(), {}, []
for raw in declared:
    # Project dependencies are pinned simple requirements in this repository.
    # Strip extras/version/marker syntax without importing third-party packaging.
    name = re.split(r"[<>=!~;\[\s]", raw, maxsplit=1)[0].strip()
    normalized = name.lower().replace("_", "-")
    if not normalized or normalized in packages:
        continue
    try:
        dist = distribution(normalized)
    except PackageNotFoundError:
        unavailable.append(normalized)
        continue
    size = 0
    for entry in dist.files or []:
        path = Path(dist.locate_file(entry))
        if path in files or not path.is_file() or path.suffix == ".pyc":
            continue
        files.add(path)
        size += path.stat().st_size
    packages[normalized] = {"version": dist.version, "bytes": size}
footprint = {"installed_direct_dependency_bytes": sum(d["bytes"] for d in packages.values()),
             "missing_direct_dependencies": unavailable, "packages": packages,
             "scope": "diagnostic only; direct project dependencies, not the Vercel function artifact"}
print("Runtime dependency footprint:", json.dumps(footprint, sort_keys=True))
info = {"version": "8.1.0", "entrypoint": "index.py", "runtime": "jinshu.runtime.Runtime",
        "git_commit": os.getenv("VERCEL_GIT_COMMIT_SHA"), "source_hashes": source,
        "build_import_verified": True, "route_smoke_verified": True,
        "runtime_configuration_checked": False, "paid_model_called": False}
(ROOT/"unified/web/build-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
print("Complete backend import and static/API routes passed. No paid models or cloud services called.")
