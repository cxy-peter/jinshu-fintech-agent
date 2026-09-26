import asyncio
import base64
import gzip
import hashlib
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from core.app import create_app
from core.reference_library import ReferenceStore, ReferenceIndex, unpack, MAX_TEXT
from core.store import Store

@pytest.fixture
def env(tmp_path):
    return {'DEEPSEEK_API_KEY':'test-only-key','JINSHU_DATA_DIR':str(tmp_path),'JINSHU_DEMO_ACCOUNTS':'1','JINSHU_SEMANTIC':'0'}

def pack(text='风险平价让各资产风险贡献相等，不是资金权重相等。'):
    return gzip.compress(json.dumps({'documents':[{'id':'personal_test','title':'真实研究示例.pdf','status':'active','synthetic':False,'sha256':'a'*64,
        'pages':[{'page':1,'text':'封面'}, {'page':10,'text':text}]}]},ensure_ascii=False).encode(),mtime=0)

def login(c,user='editor'):
    assert c.post('/api/workspace/login',json={'username':user,'password':'demo-'+user}).status_code==200

def stage(c,raw):
    r=c.post('/api/reference-imports',json={'sha256':hashlib.sha256(raw).hexdigest(),'compressed_bytes':len(raw)})
    assert r.status_code==200,r.text
    row=r.json()
    for n in range(row['parts']):
        b=raw[n*row['part_size']:(n+1)*row['part_size']]
        r=c.put(f"/api/reference-imports/{row['id']}/parts/{n}",json={'data':base64.b64encode(b).decode()})
        assert r.status_code==200,r.text
    return row['id']

def publish(c,identifier,**kw):
    return c.post('/api/reference-imports/'+identifier+'/publish',json={'sharing_confirmed':True,'expected_documents':1,'expected_pages':2,**kw})

def test_authenticated_shared_library_survives_restart_and_automatic_rag(env):
    received=[]
    def model(req):
        received.append(json.loads(req.content))
        return httpx.Response(200,json={'model':'mock','choices':[{'message':{'content':'风险平价比较风险贡献。[S1]'},'finish_reason':'stop'}]})
    with TestClient(create_app(env=env,transport=httpx.MockTransport(model))) as c:
        assert c.get('/api/library/reference-catalog').status_code==403
        login(c);identifier=stage(c,pack())
        assert c.get('/api/library').json()['documents']==[]
        assert publish(c,identifier).status_code==200
        assert publish(c,identifier).status_code==200 # retry is idempotent
        assert len(asyncio.run(Store(env).read())['audit'])==1
    with TestClient(create_app(env=env,transport=httpx.MockTransport(model))) as other:
        anon=other.get('/api/library').json()
        assert anon['documents']==[] and anon['reference_locked'] and anon['reference_count']==1
        assert other.get('/api/library/reference/personal_test/page/10').status_code==403
        assert other.get('/api/library/reference-search?q=风险平价').status_code==403
        other.get('/api/workspace/bootstrap');login(other,'operations')
        doc=other.get('/api/library').json()['documents'][0]
        assert doc['status']=='active_reference' and doc['reviewer'] is None
        page=other.get('/api/library/reference/personal_test/page/10').json()
        assert '风险贡献相等' in page['text'] and page['page']==10
        hits=other.get('/api/library/reference-search?q=风险平价').json()
        assert hits['sources'][0]['page']==10 and hits['model_called'] is False
        answer=other.post('/api/chat',json={'query':'风险平价是什么','consent':True,'use_library':True,'persist':True})
        assert answer.status_code==200,answer.text
        assert answer.json()['sources'][0]['origin']=='shared_reference'
        assert '原文页码：10' in received[0]['messages'][-1]['content']
        assert other.post('/api/reference-imports',json={'sha256':'a'*64,'compressed_bytes':1}).status_code==403
        assert other.get('/api/library/reference-search?q=发行排期复核规则').json()['sources']==[]

def test_publish_requires_complete_matching_authorized_pack(env):
    with TestClient(create_app(env=env)) as c:
        login(c);identifier=stage(c,pack())
        assert publish(c,identifier,sharing_confirmed=False).status_code==409
        assert publish(c,identifier,expected_documents=2).status_code==409
        assert c.get('/api/library').json()['documents']==[]
        assert c.put(f'/api/reference-imports/{identifier}/parts/0',json={'data':base64.b64encode(b'x'*len(pack())).decode()}).status_code==409
        incomplete=c.post('/api/reference-imports',json={'sha256':'a'*64,'compressed_bytes':1}).json()['id']
        assert publish(c,incomplete).status_code==409
        assert publish(c,identifier).status_code==200
        assert c.get('/api/library/reference/personal_test/page/99').status_code==404

def test_optimistic_publish_does_not_overwrite_newer_release(env):
    with TestClient(create_app(env=env)) as c:
        login(c);a=stage(c,pack());b=stage(c,pack('这是另一个风险平价版本。'))
        assert publish(c,a).status_code==200
        assert publish(c,b).status_code==409
        assert '风险贡献相等' in c.get('/api/library/reference/personal_test/page/10').json()['text']

def test_concurrent_source_change_blocks_model_answer(env):
    async def model(req):
        ref=ReferenceStore(Store(env));head=await ref.get('head');old=head['release'];head['release']='b'*64
        await ref.activate(head,old)
        return httpx.Response(200,json={'model':'mock','choices':[{'message':{'content':'风险贡献相等。[S1]'},'finish_reason':'stop'}]})
    with TestClient(create_app(env=env,transport=httpx.MockTransport(model))) as c:
        login(c);assert publish(c,stage(c,pack())).status_code==200
        r=c.post('/api/chat',json={'query':'风险平价','consent':True,'use_library':True})
        assert r.status_code==409 and '版本已更新' in r.text

def test_read_only_and_invalid_archive(env):
    env['JINSHU_STORE_READ_ONLY']='1'
    with pytest.raises(Exception,match='只读'):asyncio.run(ReferenceStore(Store(env)).put('x',b'1'))
    with pytest.raises(ValueError):unpack(pack()+b'junk')
    with pytest.raises(ValueError):unpack(gzip.compress(b'x'*(MAX_TEXT+1)))

@pytest.mark.parametrize('query',[
    '风险平价是什么？请结合共享资料简明解释，注明原文页码。',
    '请根据资料解释一下风险平价是什么，并标注页码。',
    '根据原文，简单说明风险平价的定义，给出出处。',
])
def test_format_instructions_do_not_dilute_the_retrieval_topic(query):
    idx=ReferenceIndex(unpack(pack())[0])
    assert idx.search(query)[0]['page']==10
    assert idx.search('发行排期是什么？请结合共享资料简明解释，注明原文页码。')==[]
