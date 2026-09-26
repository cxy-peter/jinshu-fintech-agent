"""Validate against the public Vercel schema, without a deployment or account login.

Authorized CLI dry-run and cloud build remain in Manual Vercel Deploy. The
public CI job deliberately has no access to the user's Vercel credentials.
"""
import copy
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
# The upstream document mixes newer keywords in unused experimental branches
# with a draft-04 declaration. Validate the ACTUAL instance without claiming
# that every unused part of the upstream schema passes meta-schema validation.
validator = jsonschema.validators.validator_for(schema)(schema)
validator.validate(config)
negative = copy.deepcopy(config)
negative['functions']['index.py']['excludeFiles'] = 'x' * 257
assert not validator.is_valid(negative), 'overlong exclusion must fail'
negative = copy.deepcopy(config)
negative['functions']['index.py']['maxDuration'] = 'invalid'
assert not validator.is_valid(negative), 'invalid duration type must fail'
negative = copy.deepcopy(config)
negative['framework'] = 'not-a-valid-framework'
assert not validator.is_valid(negative), 'unknown framework must fail'
print(json.dumps({
    'configuration_valid': True,
    'scope': 'official_public_json_schema_only',
    'schema_url': url,
    'negative_controls_passed': 3,
    'upstream_metaschema_conformance': 'not_asserted; unused experimental fields mix dialects',
    'schema_sha256': hashlib.sha256(raw).hexdigest(),
    'cloud_build_tested': False,
    'authenticated_cli_dry_run': 'not_run_in_public_ci_without_credentials',
    'real_model_tested': False,
}, indent=2))
