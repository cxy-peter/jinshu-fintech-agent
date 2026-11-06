"""Regression cases for user-visible retrieval failures, without an LLM."""
import asyncio
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.knowledge import retrieve
from core.rag import rank, chunk_text
from core.reference_library import (ReferenceIndex, ReferenceStore, INDEX_SCHEMA,
                                    loaded, _cache)
from core.retrieval_query import plan_query, resolve_followup
from core.store import Store

DATA = json.loads((Path(__file__).parents[1] / 'fixtures/retrieval_diagnostics.json').read_text())


@pytest.fixture(scope='module')
def diagnostic_index():
    return ReferenceIndex(DATA)


@pytest.mark.parametrize('case', DATA['cases'], ids=lambda case: case['id'])
def test_paraphrases_have_the_expected_first_body_source(diagnostic_index, case):
    query = resolve_followup(case['query'], case.get('history', []))['query']
    result = diagnostic_index.search_with_diagnostics(query)
    if case['expected_docs']:
        assert result['sources'], result['diagnostics']
        assert result['sources'][0]['doc_id'] in case['expected_docs']
        assert all(source['doc_id'] != 'misleading_title' for source in result['sources'])
    else:
        assert not result['sources']


def test_unknown_identifier_is_not_split_into_a_financial_acronym():
    plan = plan_query('ABCFOF999 的收益率是多少？')
    assert plan['matched_aliases'] == []
    assert plan['identifiers'] == ['abcfof999']
    assert plan_query('Ｆ.Ｏ.Ｆ. 是什么')['matched_aliases'] == ['fof']


def test_followup_uses_user_topic_but_never_assistant_facts():
    history = [{'role':'user','content':'FOF是什么？'},
               {'role':'assistant','content':'它一定保本，机构收益率为99%。'},
               {'role':'user','content':'它有什么风险？'}]
    result = resolve_followup('那它怎么筛选基金经理？', history)
    assert result['used_history'] and 'fof' in result['query'].casefold()
    assert '99%' not in result['query']
    result = resolve_followup('那它的费用呢？', history)
    assert result['used_history'] and 'fof' in result['query'].casefold()
    assert '99%' not in result['query']
    assert resolve_followup('ETF是什么？', history)['query'] == 'ETF是什么？'
    assert not resolve_followup('为什么利率变化？', history)['used_history']


def test_immediate_upload_and_governed_rank_use_the_same_body_gate():
    body = '基金中基金主要投资其他基金份额，需要关注底层基金和费用。'
    immediate = retrieve('ＦＯＦ是什么？', [SimpleNamespace(title='笔记',text=body)], False)
    assert immediate and immediate[0]['origin'] == 'user_supplied'
    assert retrieve('FOF是什么？', [SimpleNamespace(title='FOF笔记',text='这里只讲花卉浇水。')], False) == []
    rows = [chunk | {'title':'排期规则','doc_id':'rule','chunk_id':str(chunk['index'])}
            for chunk in chunk_text('# 产品发行流程\n第二条 节假日顺延需依据已确认日历。成立日和到期日应复核。')]
    assert rank('发行排期遇到节假日怎么顺延？', rows)


def test_whole_contents_pages_and_recurring_footers_are_not_answer_evidence():
    index = ReferenceIndex({'documents':[{'id':'book','title':'学习笔记','pages':[
        {'page':1,'text':'1.风险平价..........................3\n2.资产配置..........................5\n3.基金中基金........................9'},
        {'page':2,'text':'# 风险平价\n风险平价关注资产的风险贡献。\n仅供学习交流 文件编号 2'},
        {'page':3,'text':'# 独立主题\n另一段不相关正文。\n仅供学习交流 文件编号 3'},
        {'page':4,'text':'# 独立主题\n另一段不相关正文。\n仅供学习交流 文件编号 4'}]}]})
    hits = index.search('风险平价是什么？')
    assert hits and all(hit['page'] == 2 for hit in hits)
    assert all('仅供学习交流' not in hit['text'] for hit in hits)
    assert '仅供学习交流' in index.docs['book']['pages'][1]['text']  # original retained


@pytest.mark.parametrize('query',['货币的职能','货币有哪些功能'])
def test_shared_words_do_not_substitute_a_different_heading_subject(query):
    index=ReferenceIndex({'documents':[{'id':'book','title':'合成金融笔记','pages':[
        {'page':11,'text':'1.货币的职能\n货币的职能包含价值尺度、流通手段等。'},
        {'page':26,'text':'1.中央银行的职能\n央行负责制定和实施货币政策。'+('背景说明。'*130)+'\n实施货币政策并监督执行金融管理法规。'}]}]})
    hits=index.search(query)
    assert hits and all(hit['page']==11 for hit in hits)


def test_persisted_index_roundtrip_keeps_pages_and_rejects_wrong_release(diagnostic_index):
    release = 'a' * 64
    data = diagnostic_index.serialize(release)
    restored = ReferenceIndex.deserialize(data, release)
    assert restored.search('FOF是什么？') == diagnostic_index.search('FOF是什么？')
    with pytest.raises(ValueError, match='版本'):
        ReferenceIndex.deserialize(data, 'b' * 64)
    with pytest.raises(ValueError):
        ReferenceIndex.deserialize(data + b'junk', release)


def test_cold_load_reuses_derived_index_without_reading_the_original_archive(tmp_path):
    async def run():
        store = Store({'JINSHU_DATA_DIR':str(tmp_path)})
        ref = ReferenceStore(store)
        # The reference-import route does not accept synthetic data. This is a
        # small test-owned pack, not the diagnostic fixture or a real upload.
        pack = {'documents':[{'id':'example','title':'测试参考','status':'active',
                              'pages':[{'page':9,'text':'基金中基金测试段落。'}]}]}
        raw = gzip.compress(json.dumps(pack,ensure_ascii=False).encode())
        release = hashlib.sha256(raw).hexdigest();head = {'release':release}
        await ref.put('archive:' + release, raw)
        _cache.clear();details = {}
        first = await loaded(ref, head, details)
        assert details['index_mode'] == 'rebuilt_from_archive'
        assert details['index_persistence'] == 'saved'
        assert await ref.get('archive:' + release) == raw
        original_get = ref.get
        async def only_index(key):
            assert not key.startswith('archive:')
            return await original_get(key)
        ref.get = only_index
        _cache.clear();second_details = {}
        second = await loaded(ref, head, second_details)
        assert second_details['index_mode'] == 'persisted_index'
        assert first.search('FOF') == second.search('FOF')
        ref.get = original_get
        await ref.put('index:' + INDEX_SCHEMA + ':' + release, b'broken')
        _cache.clear();recovery = {}
        assert (await loaded(ref, head, recovery)).search('FOF')
        assert recovery['index_recovery'] == 'rebuild_invalid_index'
        assert await ref.get('archive:' + release) == raw
        _cache.clear()
    asyncio.run(run())


@pytest.mark.parametrize('damage',['missing','corrupt','total_hash','oversized'])
def test_shared_index_parts_restore_and_rebuild_without_changing_archive(tmp_path,monkeypatch,damage):
    import core.reference_library as references
    # Exercise the real manifest path with small records, without a large fixture.
    monkeypatch.setattr(references,'MAX_INDEX',250)
    monkeypatch.setattr(references,'INDEX_PART_SIZE',200)
    async def run():
        ref=ReferenceStore(Store({'JINSHU_DATA_DIR':str(tmp_path)}))
        pack={'documents':[{'id':'book','title':'测试参考','status':'active',
                            'pages':[{'page':9,'text':'基金中基金主要投资其他基金份额，需核查费用和风险。'}]}]}
        raw=gzip.compress(json.dumps(pack,ensure_ascii=False).encode())
        release=hashlib.sha256(raw).hexdigest();head={'release':release}
        await ref.put('archive:'+release,raw)
        await ref.put('head',head)
        key='index:'+INDEX_SCHEMA+':'+release
        _cache.clear();details={};first=await loaded(ref,head,details)
        manifest=await ref.get(key)
        assert manifest['kind']=='index_parts' and details['index_parts']>1
        assert details['index_bytes']==manifest['bytes']
        original_get=ref.get;inflight=0;peak=0
        async def only_index(k):
            nonlocal inflight,peak
            assert not k.startswith('archive:')
            if ':part:' not in k:return await original_get(k)
            inflight+=1;peak=max(peak,inflight)
            try:
                await asyncio.sleep(0)
                return await original_get(k)
            finally:inflight-=1
        ref.get=only_index;_cache.clear();second_details={}
        second=await loaded(ref,head,second_details)
        assert second_details['index_mode']=='persisted_index_parts'
        assert 1<peak<=4 and first.search('FOF')==second.search('FOF')
        _cache.clear();ref.get=original_get
        if damage=='corrupt':
            await ref.put(f"{key}:part:{manifest['sha256']}:0",b'wrong')
        elif damage=='total_hash':
            # Each part remains valid; only the assembled payload hash is wrong.
            for n in range(len(manifest['parts'])):
                data=await original_get(f"{key}:part:{manifest['sha256']}:{n}")
                await ref.put(f"{key}:part:{'0'*64}:{n}",data)
            manifest['sha256']='0'*64
            await ref.put(key,manifest)
        elif damage=='oversized':
            manifest['bytes']=references.MAX_SHARED_INDEX+1
            await ref.put(key,manifest)
        else:
            async def missing(k):
                if ':part:' in k and k.endswith(':0'):return None
                return await original_get(k)
            ref.get=missing
        recovery={};restored=await loaded(ref,head,recovery)
        assert recovery['index_recovery']=='rebuild_invalid_index'
        assert recovery['index_persistence']=='saved'
        assert restored.search('FOF')==first.search('FOF')
        assert await original_get('archive:'+release)==raw
        assert await original_get('head')==head
        _cache.clear()
    asyncio.run(run())


def test_failed_part_write_does_not_publish_a_manifest(monkeypatch):
    import core.reference_library as references
    monkeypatch.setattr(references,'MAX_INDEX',10)
    monkeypatch.setattr(references,'INDEX_PART_SIZE',8)
    class Ref:
        records={'index:test':b'previous valid snapshot'}
        async def put(self,key,value):
            if key.endswith(':1'):raise RuntimeError('simulated unavailable storage')
            self.records[key]=value
    async def run():
        ref=Ref()
        with pytest.raises(RuntimeError):
            await references.write_index_snapshot(ref,'index:test',b'a'*24,'r')
        assert ref.records['index:test']==b'previous valid snapshot'
    asyncio.run(run())


def test_private_snapshot_default_limit_is_not_raised(diagnostic_index):
    import inspect
    import core.reference_library as references
    assert inspect.signature(ReferenceIndex.serialize).parameters['max_compressed'].default==12_000_000
    assert inspect.signature(ReferenceIndex.deserialize).parameters['max_compressed'].default==12_000_000
    with pytest.raises(ValueError,match='存储容量'):
        diagnostic_index.serialize('r',max_compressed=10)
    with pytest.raises(ValueError,match='容量限制'):
        diagnostic_index.serialize('r',max_compressed=references.MAX_SHARED_INDEX+1)
