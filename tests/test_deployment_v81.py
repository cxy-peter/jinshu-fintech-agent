"""Deployment safety contracts. HTTP model replies are MOCKED, never live inference."""
import json
import os
from types import SimpleNamespace
import httpx
import pytest
from jinshu.model_config import resolve_chat, CHAT_KEYS
from jinshu.context import run_state
from unified import config
from unified.app import create_app
from unified.runtime import RuntimeManager

MODEL_ENV = (*CHAT_KEYS, 'CHAT_PROVIDER', 'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'DEEPSEEK_BASE_URL', 'VERCEL')
@pytest.fixture
def clean_models(monkeypatch):
    for k in MODEL_ENV:
        monkeypatch.delenv(k, raising=False)


def test_missing_key_is_never_connected_or_leaked():
    c = resolve_chat({})
    assert c.provider == 'deepseek' and c.model == 'deepseek-flash'
    assert c.missing == ('DEEPSEEK_API_KEY',)
    assert not c.public()['configured'] and not c.public()['inference_verified']
    configured = resolve_chat({'DEEPSEEK_API_KEY': 'not-a-real-key'})
    assert 'not-a-real-key' not in repr(configured)
    assert 'not-a-real-key' not in json.dumps(configured.public())


def test_blank_generic_variables_do_not_override_deepseek():
    c = resolve_chat({**dict.fromkeys(CHAT_KEYS, '  '), 'DEEPSEEK_API_KEY': 'fake'})
    assert c.base_url == 'https://api.deepseek.com' and c.api_key == 'fake'
    assert c.public()['configured'] and not c.public()['inference_verified']


@pytest.mark.parametrize('url', ['http://api.deepseek.com', 'https://evil.invalid',
    'https://api.deepseek.com.evil.invalid', 'https://api.deepseek.com@evil.invalid',
    'https://api.deepseek.com:1234', 'https://api.deepseek.com/v1?token=secret', 'https://[bad'])
def test_deepseek_key_cannot_be_sent_to_another_endpoint(url):
    assert 'DEEPSEEK_BASE_URL' in resolve_chat({'DEEPSEEK_API_KEY': 'fake', 'DEEPSEEK_BASE_URL': url}).invalid


def test_incomplete_generic_configuration_cannot_borrow_deepseek_key():
    c = resolve_chat({'CHAT_BASE_URL': 'https://other.invalid/v1', 'DEEPSEEK_API_KEY': 'fake'})
    assert c.api_key == '' and 'CHAT_API_KEY' in c.missing


def test_complete_legacy_configuration_remains_supported():
    c = resolve_chat({'CHAT_BASE_URL': 'https://other.invalid/v1', 'CHAT_API_KEY': 'old',
        'CHAT_MODEL': 'old-model', 'DEEPSEEK_API_KEY': 'new'})
    assert (c.provider, c.api_key, c.model) == ('openai_compatible', 'old', 'old-model')


def test_explicit_conflicting_provider_fails_closed():
    c = resolve_chat({'CHAT_PROVIDER': 'deepseek', 'CHAT_BASE_URL': 'https://other.invalid', 'DEEPSEEK_API_KEY': 'fake'})
    assert 'CHAT_PROVIDER_MIXED_CONFIGURATION' in c.invalid


def test_unified_settings_accept_deepseek_alias_without_embedding_alias(monkeypatch, clean_models):
    values = {k: 'fake' for k in config.REQUIRED if k not in CHAT_KEYS}
    values.update(AUTH_SECRET='x'*40, EMBEDDING_DIM='8', MONGODB_URI='mongodb://local', REDIS_ADDR='redis://local',
        MILVUS_URI='http://milvus:19530', EMBEDDING_BASE_URL='http://embedding:9000/v1',
        RERANKER_BASE_URL='http://reranker:9000', DEEPSEEK_API_KEY='fake-deepseek', JINSHU_ALLOW_EXTERNAL='1')
    for k, v in values.items(): monkeypatch.setenv(k, v)
    assert config.problems() == {'missing': [], 'invalid': []}
    settings = config.settings()
    assert settings.relay_api_key == 'fake-deepseek'
    assert settings.relay_model == 'deepseek-flash'
    assert os.environ['EMBEDDING_API_KEY'] == 'fake'
    monkeypatch.delenv('EMBEDDING_API_KEY')
    assert 'EMBEDDING_API_KEY' in config.problems()['missing']


@pytest.mark.parametrize('field,value', [('MODEL_TIMEOUT', '99999'), ('CHAT_MAX_TOKENS', 'abc'), ('CHAT_MAX_TOKENS', '999999')])
def test_bad_budgets_are_reported(field, value):
    assert field in config.problems({field: value})['invalid']


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['deepseek', 'openai_compatible'])
async def test_mocked_protocol_records_actual_model_and_usage(monkeypatch, clean_models, provider):
    from jinshu.live import ChatClient
    if provider == 'deepseek':
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-fake')
    else:
        for k, v in zip(CHAT_KEYS, ('https://other.invalid/v1', 'test-only-fake', 'other-model')):
            monkeypatch.setenv(k, v)
    c = ChatClient(SimpleNamespace(relay_base_url='', relay_api_key='', relay_model=''))
    await c.http.aclose()
    def mock(request):
        payload = json.loads(request.content)
        assert request.headers['authorization'] == 'Bearer test-only-fake'
        assert payload['stream'] is False and payload['max_tokens'] == 2048
        assert ('thinking' in payload) == (provider == 'deepseek')
        if provider == 'deepseek': assert payload['thinking'] == {'type': 'disabled'}
        return httpx.Response(200, json={'model': 'returned-model-id',
            'choices': [{'message': {'content': 'mock answer'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 2}})
    c.http = httpx.AsyncClient(transport=httpx.MockTransport(mock))
    token = run_state.set({'models_enabled': True})
    try:
        assert await c.complete([{'role': 'user', 'content': 'test'}]) == 'mock answer'
        call = run_state.get()['model_calls'][0]
        assert call['model'] == 'returned-model-id' and call['provider'] == provider
        assert call['usage']['completion_tokens'] == 2
    finally:
        run_state.reset(token); await c.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['unauthorized', 'timeout', 'empty', 'truncated', 'redirect'])
async def test_mocked_provider_failures_do_not_become_success(monkeypatch, clean_models, failure):
    from jinshu.live import ChatClient
    from app.llm.client import LLMError
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-fake')
    c = ChatClient(SimpleNamespace(relay_base_url='', relay_api_key='', relay_model=''))
    await c.http.aclose()
    def mock(request):
        if failure == 'timeout': raise httpx.ReadTimeout('private upstream diagnostic', request=request)
        if failure == 'unauthorized': return httpx.Response(401, text='test-only-fake')
        if failure == 'redirect': return httpx.Response(307, headers={'location': 'https://evil.invalid'})
        return httpx.Response(200, json={'choices': [{'message': {'content': '' if failure == 'empty' else 'partial'},
            'finish_reason': 'length' if failure == 'truncated' else 'stop'}]})
    c.http = httpx.AsyncClient(transport=httpx.MockTransport(mock), follow_redirects=False)
    token = run_state.set({})
    try:
        with pytest.raises(LLMError) as exc: await c.complete([{'role': 'user', 'content': 'test'}])
        assert 'test-only-fake' not in str(exc.value)
        assert 'private upstream diagnostic' not in str(exc.value)
        assert run_state.get()['model_calls'][-1]['status'] == 'failed'
    finally:
        run_state.reset(token); await c.close()


@pytest.mark.asyncio
async def test_unauthorized_cold_start_never_opens_databases(monkeypatch, clean_models):
    app = create_app()
    async def forbidden(): raise AssertionError('cold-start initialization was attempted')
    monkeypatch.setattr(app.state.manager, 'get', forbidden)
    monkeypatch.setenv('AUTH_SECRET', 'a'*40)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://localhost') as client:
        for h in ({}, {'Authorization': 'Bearer forged.token'}):
            response = await client.get('/api/tasks', headers=h)
            assert response.status_code == 401 and response.headers['cache-control'] == 'no-store'
        assert (await client.get('/api/status')).status_code == 200
        assert (await client.get('/assets/provider.js')).status_code == 200


def test_runtime_status_never_mislabels_offline_as_deepseek(clean_models):
    state = RuntimeManager(SimpleNamespace(profile='offline')).status()
    assert state['model']['provider'] == 'offline_fixture'
    assert state['model']['inference_verified'] is False


def test_external_deepseek_cannot_be_mislabelled_private():
    assert 'JINSHU_MODEL_SCOPE' in config.problems({'JINSHU_MODEL_SCOPE':'local','DEEPSEEK_API_KEY':'fake'})['invalid']

def test_pyproject_and_pip_dependencies_match():
    from pathlib import Path
    import tomllib
    root=Path(__file__).resolve().parents[1]
    project=tomllib.loads((root/'pyproject.toml').read_text())
    pip=[s for s in (root/'unified/requirements.txt').read_text().splitlines() if s and not s.startswith('#')]
    assert project['project']['dependencies']==pip
    assert project['tool']['vercel']['entrypoint']=='index:app'
