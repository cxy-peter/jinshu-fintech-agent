"""Business acceptance, not a security test suite or an LLM accuracy benchmark."""
import asyncio,copy,json,os,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from jinshu.runtime import Runtime
from jinshu.mock_pdfs import generate,OUT
from jinshu.operations import RecoveryController,TicketOutbox
from jinshu.context import scope,access,run_state
from jinshu.fixtures import DEPARTMENTS
from jinshu.demo import run_loop_lab
from jinshu.python_skills import execute

async def validate():
    os.environ['JINSHU_INSTANCE_ID']='acceptance-'+uuid.uuid4().hex[:10]
    r=await Runtime().initialize();staged=[];hits=[]
    try:
        for d in generate():
            item=await r.c.documents.stage_file(OUT/d['file'],d['dept_id'],'pdf-uploader',d['topic'],1,d['manual_sensitivity'])
            assert item['status']=='pending_review' and item['vector_status']=='not_indexed'
            suggested=item['detection']['suggested_level']
            final='sensitive' if d['file'].startswith('08_') else d['manual_sensitivity']
            published=await r.c.documents.review_and_publish(item['_id'],'pdf-reviewer',list(DEPARTMENTS),final,reason='确认合成样例和资料范围')
            chunks=await r.c.store.list_chunks_by_doc(item['_id'])
            staged.append({'file':d['file'],'doc_id':item['_id'],'manual':d['manual_sensitivity'],'suggested':suggested,'final':final,'chunks':len(chunks),'tables':sum(c['metadata'].get('has_table',False) for c in chunks),'vector_status':published['vector_status'],'pages':published['page_count']})
        tests=[('资产总计 2025 1020250','dept_wealth','01_balance_sheet.pdf','1020250'),('净利润 2025 102025','dept_wealth','02_income_statement.pdf','102025'),('期末现金 2025 92025','dept_wealth','03_cashflow_statement.pdf','92025'),('SIM0001 产品编码 持有期限','dept_wealth','04_wealth_products.pdf','SIM0001'),('拟成立日 调整后成立日 顺延原因','dept_release','05_issuance_sop.pdf','顺延原因'),('怎样转人工 用户主动请求','dept_service','06_public_faq.pdf','用户主动请求')]
        for query,dept,filename,term in tests:
            tk=scope.set([dept]);ak=access.set({'departments':[dept],'clearance':'sensitive'});sk=run_state.set({})
            try:
                cs=await r.c.retrieval_agent.retrieve([query],[dept],top_k=8)
                target=next(d['doc_id'] for d in staged if d['file']==filename)
                hit=any(c['doc_id']==target and term in c['content'] for c in cs)
                hits.append({'query':query,'expected_source':filename,'hit':hit,'returned':len(cs),'mode':'BM25 + local hash test vectors, not learned semantic embeddings'})
                assert hit,(query,[c['content'] for c in cs])
            finally:scope.reset(tk);access.reset(ak);run_state.reset(sk)
        # Same actual Skill path used by API, not a fake diagram-only function.
        material=await r.ask('生成Word发行材料',user_id='operations',workflow='material_fill',params={'product_name':'模拟月月稳A'})
        first=material['tool_results'][0];repeat=execute('material_fill',{'product_name':'模拟月月稳A'})
        assert first['result']['output_file']==repeat['result']['output_file']
        assert (ROOT/'workspace/outputs'/first['result']['output_file']).exists()
        candidate=copy.deepcopy(await r.c.store.get_skill('base_issuance'))
        candidate.update(_id='candidate-recovery-demo',version=2,experiment_id='exp-recovery-demo',gray_percent=1)
        for step in candidate['action']['steps']:
            if step['action']=='retrieve':step['params']['top_k']=8
        await r.c.store.upsert_skill(candidate)
        before=await r.ask('发行排期',user_id='operations',workflow='issuance')
        async def broken():raise ConnectionError('injected control API failure')
        failed=await r.recovery.rollback('issuance',candidate['_id'],broken,'演示回滚控制请求失败')
        after=await r.ask('发行排期',user_id='operations',workflow='issuance')
        restarted=RecoveryController(r.recovery.path.parent)
        assert before['execution']['skill_plan']['top_k']==8 and after['execution']['skill_plan']['top_k']==2 and restarted.frozen('issuance')
        assert failed['status']=='local_baseline_remote_unconfirmed'
        draft=r.outbox.draft('u:s','模拟工单');pending=await r.outbox.submit(draft)
        again=r.outbox.draft('u:s','模拟工单')
        assert pending['status']=='pending_submission' and draft['id']==again['id']
        report={'mode':'offline business acceptance; all data and failures synthetic','pdf_files':len(staged),'pdf_chunks':sum(x['chunks'] for x in staged),'pdf_table_chunks':sum(x['tables'] for x in staged),'documents':staged,'retrieval_cases':hits,'retrieval_passed':sum(h['hit'] for h in hits),'python_material':first,'rollback_control_failure':{'before_top_k':8,'after_top_k':2,'restart_keeps_freeze':True,'result':failed},'ticket_outbox':{'status':pending['status'],'same_id_on_retry':True},'live_models':False,'live_services':False}
    finally:await r.close()
    lab=await run_loop_lab()
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    (evidence/'loop_lab_v3.json').write_text(json.dumps(lab,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    report['loop']={'replay_pairs':lab['candidate']['replay']['sample_count'],'promoted_to':lab['promoted_to'],'rolled_back':lab['automatic_rollback']['rolled_back'],'after_top_k':lab['after_rollback']['plan']['top_k'],'financial_results_unchanged':lab['unchanged_financial_results']}
    (evidence/'v3_pdf_and_failure_evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['documents','retrieval_cases','python_material']},ensure_ascii=False,indent=2))
    return report
if __name__=='__main__':asyncio.run(validate())
