"""Validate against the public Vercel schema, without a deployment or account login.

Authorized CLI dry-run and cloud build remain in Manual Vercel Deploy. The
public CI job deliberately has no access to the user's Vercel credentials.
"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
import jsonschema

url = 'https://openapi.vercel.sh/vercel.json'
with urllib.request.urlopen(url, timeout=30) as response:
    raw = response.read(2_000_001)
if len(raw) > 2_000_000:
    raise RuntimeError('schema_too_large')
schema = json.loads(raw)
config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
jsonschema.validate(config, schema)
print(json.dumps({
    'configuration_valid': True,
    'scope': 'official_public_json_schema_only',
    'schema_url': url,
    'schema_sha256': hashlib.sha256(raw).hexdigest(),
    'cloud_build_tested': False,
    'authenticated_cli_dry_run': 'not_run_in_public_ci_without_credentials',
    'real_model_tested': False,
}, indent=2))
