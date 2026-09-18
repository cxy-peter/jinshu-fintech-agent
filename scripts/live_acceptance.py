"""Real services acceptance, suitable for an isolated CI database only.
Does not drop databases, fabricate people or assert learned-answer correctness.
"""
import asyncio, json, os, secrets, sys, time, traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jinshu.runtime import Runtime
from jinshu.mock_pdfs import generate,OUT
from jinshu.context import scope,access,run_state
from jinshu.skills import seed_skills
from jinshu.live import ping_runtime
from app.llm.client import ChatMessage

async def main():
    evidence=Path('evidence/v4');evidence.mkdir(parents=True,exist_ok=True)
    report={'test_scope':'real local weights + MongoDB + Redis + Milvus, synthetic tasks; not a user study',
            'checks':{},'real_users':0,'k8s_load_test':False,'errors':[]}
    r=None;r2=None
    try:
        r=await Runtime('services',instance_id='live-acceptance').initialize()
        report['services']=await ping_runtime(r)
        assert all(v=='ok' for v in report['services']['services'].values())
        for name in ['ci-author','ci-reviewer']:
            if not await r.c.store.get('users',name):
                await r.c.store.upsert_user(r.c.auth._to_user({'username':name,'name':name,'password':secrets.token_hex(24),'role':'admin','dept_id':''}))
        await seed_skills(r.c.store)
        imported=[]
        for d in generate():
            existing=next((x for x in await r.c.store.list_documents() if x.get('source',{}).get('file_name')==d['file'] and x.get('status')=='active'),None)
            if existing:imported.append(existing);continue
            staged=await r.c.documents.stage_file(OUT/d['file'],d['dept_id'],'ci-author',d['topic'],d['version'],d['manual_sensitivity'])
            level=staged['detection']['suggested_level']
            published=await r.c.documents.review_and_publish(staged['_id'],'ci-reviewer',[d['dept_id']],level,external_allowed=False,reason='Automated synthetic-fixture review; not an independent human decision')
            imported.append(published)
        report['documents']=[{'file':d['source']['file_name'],'status':d['status'],'vector_status':d['vector_status'],'chunks':d['chunk_count']} for d in imported]
        assert all(d['vector_status']=='ready' for d in imported),'Some fixtures did not obtain genuine vectors'
        report['checks']['pdf_to_milvus']=True
        state={};st=run_state.set(state)
        try:
            vectors=await r.c.embeddings.embed(['基金分散配置有助于降低集中风险。','投资组合不应过度集中在一个标的。','机器人正在修理电梯。'])
            dot=lambda a,b:sum(x*y for x,y in zip(a,b))
            report['semantic_probe']={'dimension':len(vectors[0]),'related_cosine':dot(vectors[0],vectors[1]),'unrelated_cosine':dot(vectors[0],vectors[2]),'kind':'descriptive sanity check; not domain accuracy'}
            assert len(vectors[0])==r.c.settings.embedding_dim
            report['completion']=await r.c.llm.complete([ChatMessage.system('请用一句中文回答，不要补充无关内容。'),ChatMessage.user('根据材料：工单接口不可用时保留待提交草稿。现在接口不可用，应该怎么做？')],max_tokens=80)
            assert report['completion'].strip()
            report['checks']['llm_inference']=True;report['model_calls']=state.get('model_calls',[])
        finally:run_state.reset(st)
        await r.c.session_store.set_session('ci-v4-shared',{'fixture':True,'value':'真实Redis读写'},ttl=120)
        r2=await Runtime('services',instance_id='live-second-instance').initialize()
        report['checks']['redis_cross_instance']=(await r2.c.session_store.get_session('ci-v4-shared'))['fixture'] is True
        report['checks']['mongo_cross_instance']=(await r2.c.store.count('documents'))>=8
        from jinshu.queue import RecoverableJobQueue
        q=RecoverableJobQueue(r.c.store,r.c.session_store,'jinshu:v4:acceptance-only')
        job=await q.enqueue('acceptance_probe',{'fixture':True});jobs=await q.next_jobs(count=1,block_ms=100)
        assert jobs and jobs[0]['_id']==job['_id'];await q.finish(jobs[0],'completed',{'fixture_checked':True})
        pending=await r.c.session_store.redis.xpending(q.stream_name,'workers')
        report['checks']['redis_stream_ack']=pending['pending']==0
        answer=await r.ask('用户要求转人工，工单接口不可用时应当怎么做？',user_id='ci-reviewer',workflow='service',allowed=['dept_service'],clearance='sensitive')
        report['dag']={'answer':answer.get('answer'),'trace_id':answer['trace_id'],'execution':answer['execution']}
        assert answer['trace_id'] and any(c.get('kind')=='chat' and c.get('status')=='ok' for c in answer['execution'].get('model_calls',[]))
        report['checks']['dag_real_model_call']=True
        async def fail_remote():raise ConnectionError('controlled_remote_control_failure')
        result=await r.recovery.rollback('service','ci-synthetic-candidate',fail_remote,'acceptance')
        await r2.recovery.refresh('service')
        report['shared_rollback']={'result':result,'second_instance_frozen':r2.recovery.frozen('service')}
        report['checks']['shared_freeze']=r2.recovery.frozen('service')
        from scripts.evaluate_v4 import evaluate
        ev=await evaluate(r,evidence/'retrieval_eval.json');report['retrieval_eval_summary']=ev['summary']
        report['checks']['reranker_inference']=any(any(c.get('kind')=='rerank' and c.get('status')=='ok' for c in row.get('calls',[])) for row in ev['rows'])
        assert report['checks']['reranker_inference']
        import httpx
        async with httpx.AsyncClient(timeout=30) as c:
            res=await c.get(os.getenv('CHAT_BASE_URL').removesuffix('/v1')+'/provenance',headers={'Authorization':'Bearer '+os.environ['CHAT_API_KEY']})
            res.raise_for_status();report['model_provenance']=res.json()
        if os.getenv('V4_TEST_PI')=='1':
            r.c.pi_runtime.settings.pi_agent_enabled=True
            try:
                text=await r.c.pi_runtime.run_text('answer','只返回一句中文。','根据材料：接口失败时保留草稿。现在接口失败，怎么办？',allowed_tools=[],timeout_seconds=120)
                report['pi_runtime']={'status':'passed' if text else 'failed','text':text,'uses_original_source':True}
                if not text:
                    async with httpx.AsyncClient(timeout=130) as diagnostic:
                        response=await diagnostic.post(os.environ.get('PI_AGENT_URL','http://pi-agent:8100')+'/v1/agent/run',headers={'X-Internal-Token':os.environ['INTERNAL_API_TOKEN']},json={'agentType':'answer','systemPrompt':'只返回一句中文。','prompt':'根据材料：接口失败时保留草稿。现在接口失败，怎么办？','outputMode':'text','allowedTools':[],'timeoutMs':120000})
                        report['pi_runtime']['diagnostic_http_status']=response.status_code
                        report['pi_runtime']['diagnostic_body']=response.text[:2000]
            finally:r.c.pi_runtime.settings.pi_agent_enabled=False
        if os.getenv('V4_TEST_PI')=='1' and report.get('pi_runtime',{}).get('status')!='passed':raise AssertionError('pi did not return model output; see diagnostic')
        report['status']='passed'
    except Exception as exc:
        report['status']='failed';report['errors'].append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
        raise
    finally:
        (evidence/'live_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
        if r2:await r2.close()
        if r:await r.close()
if __name__=='__main__':asyncio.run(main())
