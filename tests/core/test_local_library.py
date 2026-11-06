import asyncio
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from core.local_library import LocalFolder, install, search_for_chat
from core.reference_library import unpack


def library(tmp_path):
    root = tmp_path / 'documents'
    root.mkdir()
    local = LocalFolder(tmp_path / 'cache' / 'local.sqlite', {'JINSHU_LOCAL_FOLDER_ENABLED': '1'})
    local.configure(str(root))
    return local, root


def test_incremental_parse_restart_rename_delete_and_changed_files(tmp_path, monkeypatch):
    local, root = library(tmp_path)
    file = root / '基金知识.txt'
    file.write_text('FOF是指基金中基金，主要以基金作为投资对象。', encoding='utf-8')
    first = local.scan()
    assert first['scan']['added'] == 1
    doc = first['documents'][0]
    assert local.search('什么是FOF')[0][0]['origin'] == 'local_folder'
    assert local.page(doc['id'], 1)['text'].startswith('FOF')
    from core import local_library
    original = local_library.parse_document
    monkeypatch.setattr(local_library, 'parse_document', lambda *a: (_ for _ in ()).throw(AssertionError('reparsed')))
    assert local.scan()['scan']['unchanged'] == 1
    restored = LocalFolder(local.path, local.env)
    assert restored.search('FOF投资什么')[0]
    evidence = restored.search('FOF投资什么')[0]
    restored.verify(evidence)
    assert restored.page(doc['id'], 1)['pages'] == [1]
    file.write_text('货币具有价值尺度和流通手段的职能。', encoding='utf-8')
    with pytest.raises(ValueError):
        restored.verify(evidence)
    assert local.search('FOF是什么')[0] == []
    with pytest.raises(Exception) as error:
        local.page(doc['id'], 1)
    assert error.value.status_code == 409
    monkeypatch.setattr(local_library, 'parse_document', original)
    assert local.scan()['scan']['changed'] == 1
    file.rename(root / '货币知识.txt')
    assert local.search('货币职能')[0] == []
    changes = local.scan()['scan']
    assert changes['added'] == changes['removed'] == 1
    (root / '货币知识.txt').unlink()
    assert local.scan()['scan']['removed'] == 1
    assert local.search('货币职能')[0] == []


def test_symlinks_whitelist_and_root_change(tmp_path):
    local, root = library(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('FOF secret external contents', encoding='utf-8')
    (root / 'link.txt').symlink_to(outside / 'secret.txt')
    (root / 'outside').symlink_to(outside, target_is_directory=True)
    result = local.scan()
    assert not local.search('FOF')[0]
    assert result['scan']['errors'] == 1
    with pytest.raises(ValueError):
        local.configure(str(root / 'outside'))
    with pytest.raises(ValueError):
        local.configure('/')
    with pytest.raises(ValueError):
        local.configure('../')
    with pytest.raises(ValueError):
        local._safe_path(root, '../outside/secret.txt')
    local.configure(str(outside))
    assert local.status()['documents'] == []
    assert local.scan()['scan']['added'] == 1
    assert local.search('FOF')[0]


def test_scan_failure_invalidates_previous_index_and_export_roundtrip(tmp_path):
    local, root = library(tmp_path)
    doc = root / '基金.txt'
    doc.write_text('FOF是指基金中基金，主要投资基金。', encoding='utf-8')
    local.scan()
    pack, catalog, pages = unpack(local.export())
    assert len(catalog) == pages == 1
    assert pack['documents'][0]['pages'][0]['text'].startswith('FOF')
    doc.write_bytes(b'')
    result = local.scan()
    assert result['scan']['errors'] == 1
    assert not local.search('FOF')[0]
    assert result['documents'][0]['status'] == 'error'


def make_app(tmp_path, env=None):
    env = env or {'JINSHU_LOCAL_FOLDER_ENABLED': '1'}
    app = FastAPI()
    async def authorize():
        return True
    store = SimpleNamespace(path=tmp_path / 'state.sqlite', env=env)
    install(app, store, authorize)
    @app.get('/chat-search')
    async def chat(request: Request):
        sources, diagnostics = await search_for_chat(app, request, 'FOF是什么')
        return {'sources': sources, 'diagnostics': diagnostics}
    return app


def test_local_endpoints_and_chat_search(tmp_path):
    root = tmp_path / 'docs'
    root.mkdir()
    (root / 'notes.md').write_text('# FOF\nFOF是指基金中基金，投资对象为基金。', encoding='utf-8')
    with TestClient(make_app(tmp_path), base_url='http://127.0.0.1', client=('127.0.0.1', 1000)) as client:
        assert client.get('/api/local-folder').status_code == 200
        assert client.post('/api/local-folder/config', json={'root': str(root)}).status_code == 200
        scanned = client.post('/api/local-folder/scan', json={}).json()
        doc = scanned['documents'][0]
        assert client.get('/api/local-folder/search', params={'q': 'FOF是什么'}).json()['sources']
        assert client.get('/chat-search').json()['sources']
        page = client.get(f"/api/local-folder/documents/{doc['id']}/page/1").json()
        assert page['pages'] == [1] and page['location_kind'] == 'logical_text_section'
        assert len(json.loads(gzip.decompress(client.get('/api/local-folder/export').content))['documents']) == 1
        assert client.post('/api/local-folder/config', json={'root': str(root)}, headers={'origin': 'https://evil.example'}).status_code == 403
        assert client.get('/api/local-folder', headers={'host': 'evil.example'}).status_code == 403
        assert client.get('/api/local-folder', headers={'host': 'localhost.evil.example'}).status_code == 403


@pytest.mark.parametrize('env,peer,host,status', [
    ({'JINSHU_LOCAL_FOLDER_ENABLED': '1', 'VERCEL': '1'}, '127.0.0.1', '127.0.0.1', 404),
    ({'JINSHU_LOCAL_FOLDER_ENABLED': '0'}, '127.0.0.1', '127.0.0.1', 404),
    ({'JINSHU_LOCAL_FOLDER_ENABLED': '1'}, '192.0.2.1', '127.0.0.1', 403),
    ({'JINSHU_LOCAL_FOLDER_ENABLED': '1'}, '127.0.0.1', 'server.example', 403),
])
def test_cloud_remote_host_and_forwarded_headers_cannot_read_files(tmp_path, env, peer, host, status):
    with TestClient(make_app(tmp_path, env), base_url='http://' + host, client=(peer, 2000)) as client:
        assert client.get('/api/local-folder', headers={'x-forwarded-for': '127.0.0.1'}).status_code == status
        assert client.get('/chat-search').status_code == status
    assert not (tmp_path / 'local_folder.sqlite').exists()


def test_scanned_pdf_is_not_reported_as_parsed(tmp_path):
    from pypdf import PdfWriter
    local, root = library(tmp_path)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with (root / 'scan.pdf').open('wb') as file:
        writer.write(file)
    result = local.scan()
    assert result['scan']['errors'] == 1
    assert 'OCR' in result['documents'][0]['error']
    assert result['indexed_documents'] == 0


def test_warm_combined_index_avoids_document_cache_churn(tmp_path, monkeypatch):
    local, root = library(tmp_path)
    (root / 'definition.txt').write_text('FOF是指基金中基金，以基金作为投资对象。', encoding='utf-8')
    for n in range(18):
        (root / f'ledger-{n}.txt').write_text(f'第{n}份运营清单，记录请求编号和工作安排。', encoding='utf-8')
    local.scan()
    first, diagnostics = local.search('FOF是什么')
    assert first[0]['title'] == 'definition.txt'
    assert diagnostics['documents'] == 19
    from core.reference_library import ReferenceIndex
    monkeypatch.setattr(ReferenceIndex, 'deserialize', lambda *a: (_ for _ in ()).throw(AssertionError('warm query reloaded index')))
    assert local.search('什么是基金中基金')[0][0]['title'] == 'definition.txt'
