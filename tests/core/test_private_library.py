import base64
import hashlib
import json
import httpx
from fastapi.testclient import TestClient
from core.app import create_app


def upload(client, body, name='规则说明.txt'):
    start=client.post('/api/private-library/uploads',json={'name':name,'size':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    assert start.status_code==200,start.text
    row=start.json()
    if row.get('existing'):return row['existing']
    for part in range(row['parts']):
        raw=body[part*row['part_size']:(part+1)*row['part_size']]
        assert client.put(f"/api/private-library/uploads/{row['id']}/parts/{part}",json={'data':base64.b64encode(raw).decode()}).status_code==200
    end=client.post(f"/api/private-library/uploads/{row['id']}/finish",json={})
    assert end.status_code==200,end.text
    return end.json()['document']


def test_owner_isolation_deduplication_handoff_and_restart(tmp_path):
    env={'JINSHU_DATA_DIR':str(tmp_path),'JINSHU_SEMANTIC':'0'}
    with TestClient(create_app(env=env)) as first,TestClient(create_app(env=env)) as other:
        first.get('/api/workspace/bootstrap');other.get('/api/workspace/bootstrap')
        body='货币的职能包括价值尺度、流通手段、支付手段。'.encode()
        doc=upload(first,body)
        assert upload(first,body)['id']==doc['id']
        assert other.get('/api/private-library').json()['documents']==[]
        assert other.get(f"/api/private-library/{doc['id']}/page/1").status_code==404
        assert other.get(f"/api/private-library/{doc['id']}/original").status_code==404
        assert first.get(f"/api/private-library/{doc['id']}/original").content==body
        assert first.get('/api/private-library/search',params={'q':'货币的职能'}).json()['sources']
        token=first.post('/api/private-library/handoff',json={}).json()['token']
        assert other.post('/api/private-library/claim',json={'token':token}).json()['claimed']==1
        assert first.get('/api/private-library/search',params={'q':'货币的职能'}).json()['sources']==[]
        assert first.post('/api/private-library/claim',json={'token':token}).status_code==409
        cookies=other.cookies
    with TestClient(create_app(env=env)) as restored:
        restored.cookies.update(cookies)
        assert restored.get('/api/private-library').json()['documents'][0]['id']==doc['id']
        assert restored.delete('/api/private-library/'+doc['id']).status_code==200
        assert restored.get('/api/private-library/search',params={'q':'货币的职能'}).json()['sources']==[]


def test_private_document_enters_model_context_and_retrieval_has_no_model_call(tmp_path):
    requests=[]
    def model(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'model':'mock','choices':[{'message':{'content':'支付手段用于延期支付。[S1]'},'finish_reason':'stop'}]})
    env={'JINSHU_DATA_DIR':str(tmp_path),'JINSHU_SEMANTIC':'0','DEEPSEEK_API_KEY':'test-only'}
    with TestClient(create_app(env=env,transport=httpx.MockTransport(model))) as c:
        c.get('/api/workspace/bootstrap');upload(c,'支付手段是货币作为价值的独立形式进行延期支付。'.encode())
        payload={'query':'支付手段是什么','use_private_library':True,'answer_mode':'grounded'}
        r=c.post('/api/retrieve',json=payload)
        assert r.status_code==200 and r.json()['sources'] and not requests
        result=c.post('/api/chat',json=payload|{'consent':True})
        assert result.status_code==200,result.text
        assert result.json()['sources'][0]['origin']=='private_cloud'
        assert '延期支付' in requests[0]['messages'][-1]['content']


def test_grounded_missing_evidence_and_stream_failures_are_explicit(tmp_path):
    with TestClient(create_app(env={'JINSHU_DATA_DIR':str(tmp_path)})) as c:
        c.get('/api/workspace/bootstrap')
        response=c.post('/api/chat/stream',json={'query':'未知机构的内部上限','answer_mode':'grounded','consent':True})
        events=[json.loads(x[6:]) for x in response.text.strip().split('\n\n')]
        assert [x['event'] for x in events]==['retrieval','answer']
        assert events[-1]['data']['model_call']['status']=='not_called'
        r=c.post('/api/private-library/uploads',json={'name':'../secret.txt','size':1,'sha256':'a'*64})
        assert r.status_code==409


def test_private_corpus_uses_one_score_scale_for_short_definition_and_large_log():
    from core.private_library import combine_indexes
    from core.reference_library import ReferenceIndex
    definition=ReferenceIndex({'documents':[{'id':'definition','title':'基金学习','pages':[{'page':1,'text':'FOF（基金中基金）是指以其他基金为主要投资对象的基金。'}]}]})
    log=ReferenceIndex({'documents':[{'id':'log','title':'运营台账','pages':[{'page':i+1,'text':('FOF页面更新记录，附录待核对。' if i==0 else '台账中的资源巡检和发布记录。')} for i in range(100)]}]})
    hits=combine_indexes([definition,log]).search('FOF是什么？')
    assert hits[0]['doc_id']=='definition'
