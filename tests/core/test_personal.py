import json
import httpx
import pytest
from fastapi.testclient import TestClient
from core.app import create_app
from test_governed import env,make,login,publish


def test_acceptance_document_does_not_crowd_out_real_evidence(env):
    with make(env) as c:
        c.get('/api/workspace/bootstrap');login(c,'editor')
        did=c.post('/api/library',json={'title':'发行排期复核示例（合成）','topic':'v10-acceptance-test','text':'第一条 发行排期是验收合成示例，不是制度。'}).json()['id']
        publish(c,did)
        base={'query':'发行排期是什么','consent':True,'use_library':True}
        assert c.post('/api/chat',json=base).json()['sources']==[]
        assert c.post('/api/chat',json=base|{'include_examples':True}).json()['sources']


def test_personal_page_preserved_and_not_published(env):
    with make(env) as c:
        c.get('/api/workspace/bootstrap')
        passage={'title':'研究报告.pdf','text':'基金经理评价涉及收益、风险和风格的一致性。','page':39,'chunk_id':'original:19','origin':'personal_local'}
        result=c.post('/api/chat',json={'query':'基金经理评价是什么','consent':True,'personal_passages':[passage]}).json()
        assert result['sources'][0]['page']==39
        assert result['sources'][0]['origin']=='personal_local'
        assert c.get('/api/library').json()['documents']==[]
        assert result['persistence']=='not_stored_server_side'
        invalid=passage|{'origin':'reviewed_library'}
        assert c.post('/api/chat',json={'query':'问题','consent':True,'personal_passages':[invalid]}).status_code==422
        assert c.post('/api/chat',json={'query':'问题','personal_passages':[passage]}).status_code==403


@pytest.mark.parametrize('cloud,host',[(True,'localhost'),(False,'attacker.example')])
def test_personal_corpus_cannot_be_exposed_in_cloud_or_dns_rebinding(env,tmp_path,cloud,host):
    pack=tmp_path/'private.json';pack.write_text('{"documents":[]}')
    cfg=env|{'JINSHU_PERSONAL_PACK':str(pack)}
    if cloud:cfg['VERCEL']='1'
    with TestClient(create_app(env=cfg),base_url='http://'+host,client=('127.0.0.1',5000)) as c:
        assert c.get('/api/local-materials').status_code==404


def test_local_pack_loads_only_on_loopback(env,tmp_path):
    pack=tmp_path/'private.json';pack.write_text('{"documents":[]}')
    with TestClient(create_app(env=env|{'JINSHU_PERSONAL_PACK':str(pack)}),base_url='http://localhost',client=('127.0.0.1',5000)) as c:
        assert c.get('/api/local-materials').json()=={'documents':[]}
