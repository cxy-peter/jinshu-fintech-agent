"""V4 shared publication/stop controls and human-pilot collection.
Public routes expose no credentials. The pilot table starts empty.
"""
from __future__ import annotations
import asyncio, hashlib, os, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from .ingestion import DraftIndexer
from .operations import RecoveryController, save, timestamp
from .live import ping_runtime

class SharedPublisher(DraftIndexer):
    @classmethod
    def from_indexer(cls, idx, mongo):
        instance=cls.__new__(cls); instance.__dict__=dict(idx.__dict__); instance.mongo=mongo
        return instance

    async def publish(self, did, actor, allowed_depts):
        """Serialize per-topic publishers; compare-and-swap a single authoritative head.
        Index cleanup is compensating, not a cross-store transaction.
        """
        from pymongo import ReturnDocument
        from pymongo.errors import DuplicateKeyError
        document=await self.store.get_document(did)
        if not document or document['dept_id'] not in allowed_depts:
            raise PermissionError('文档不在审核部门')
        key=document['topic_key']; owner=uuid.uuid4().hex; now=datetime.now(timezone.utc)
        locks=self.mongo.collection('publish_leases')
        try:
            lock=await locks.find_one_and_update({'_id':key,'expires_at':{'$lte':now}},
                {'$set':{'owner':owner,'expires_at':now+timedelta(seconds=45)}},upsert=True,return_document=ReturnDocument.AFTER)
        except DuplicateKeyError as exc:
            raise ValueError('该主题正在发布，请稍后重试') from exc
        try:
            if document['source']['uploaded_by']==actor or document['status']!='pending_review':
                raise ValueError('需要独立审核且资料处于待发布状态')
            today=now.date().isoformat()
            if document.get('effective_date') and document['effective_date']>today:
                raise ValueError('尚未生效')
            if document.get('expiry_date') and document['expiry_date']<today:
                raise ValueError('已过有效期')
            head_coll=self.mongo.collection('document_heads')
            old=await self.store.get('document_heads',key)
            if old and float(old['version'])>=float(document['version']):
                raise ValueError('不允许隐式覆盖更高或同版本')
            await self.store.update_document(did,{'status':'active','reviewed_by':actor})
            head={'_id':key,'doc_id':did,'version':document['version']}
            try:
                if old:
                    result=await head_coll.replace_one({'_id':key,'doc_id':old['doc_id'],'version':old['version']},head)
                    if result.modified_count!=1:raise ValueError('版本已被其它发布者改变')
                else:
                    await head_coll.insert_one(head)
            except Exception:
                await self.store.update_document(did,{'status':'pending_review'});raise
            await self.store.increment('corpus_revisions',document['dept_id'],'value')
            if old:
                await self.store.update_document(old['doc_id'],{'status':'archived','superseded_by':did})
                try:await self._remove_from_runtime_indexes(old['doc_id'])
                except Exception:
                    await self.store.upsert('index_cleanup_pending',{'_id':old['doc_id'],'status':'pending'})
                if self.organization_memory:
                    await self.organization_memory.invalidate_document(old['doc_id'],'document_superseded')
            await self.store.upsert('publish_audit',{'_id':uuid.uuid4().hex,'doc_id':did,'actor':actor,'previous':old,'created_at':timestamp()})
            return await self.store.get_document(did)
        finally:
            await locks.delete_one({'_id':key,'owner':owner})

class SharedRecovery(RecoveryController):
    def __init__(self,directory,store):
        super().__init__(directory);self.store=store

    async def refresh(self,family):
        try:
            row=await self.store.get('strategy_controls',family)
        except Exception as exc:
            self.state['families'][family]={'frozen':True,'status':'authority_unavailable'}
            raise ConnectionError('策略权威状态不可读，暂停该请求') from exc
        if row:
            self.state['families'][family]=row
            save(self.path,self.state)

    async def rollback(self,family,skill_id,remote,reason):
        async def shared_then_remote():
            row={'_id':family,'frozen':True,'candidate':skill_id,'reason':reason,
                 'status':'shared_freeze_confirmed','at':timestamp()}
            await self.store.upsert('strategy_controls',row)
            await remote()
            row['status']='remote_rollback_confirmed'
            await self.store.upsert('strategy_controls',row)
        result=await super().rollback(family,skill_id,shared_then_remote,reason)
        result['scope']='shared MongoDB control read at each new request; already-running requests may finish'
        return result

    async def resume_shared(self,family,actor):
        await self.refresh(family)
        row=super().resume(family,actor)
        await self.store.upsert('strategy_controls',{'_id':family,**row})
        return row

class PilotConsent(BaseModel):
    consent:bool
    purpose:str='金融产品中后台助手可用性试点'
class PilotResult(BaseModel):
    task_id:str=Field(min_length=1,max_length=80)
    phase:str=Field(pattern='^(manual|agent)$')
    trace_id:str|None=None
    seconds:float=Field(gt=0,le=86400)
    completed:bool
    rating:int=Field(ge=1,le=5)
    correctness:bool|None=None
    note:str=Field(default='',max_length=500)
    is_test:bool=False
class Fanout(BaseModel):
    query:str=Field(min_length=1,max_length=2000)
    workflows:list[str]=Field(min_length=1,max_length=4)
    allow_external:bool=False

def install_routes(app,rt,auth,admin,depts):
    @app.get('/api/services')
    async def services(u=Depends(auth)):
        return await ping_runtime(rt())

    @app.get('/ready')
    async def ready():
        data=await ping_runtime(rt())
        if any(v!='ok' for v in data['services'].values()):
            raise HTTPException(503,'Required data services unavailable')
        return {'status':'ready','mode':rt().profile}

    @app.get('/api/jobs/{job_id}')
    async def job(job_id:str,u=Depends(admin)):
        row=await rt().c.store.get('async_jobs',job_id)
        if not row:raise HTTPException(404,'作业不存在')
        return row

    @app.post('/api/ask/multi')
    async def multi(d:Fanout,u=Depends(auth)):
        from .fixtures import WORKFLOWS
        allowed=depts(u); timeout=float(os.getenv('DEPARTMENT_TIMEOUT','150'))
        if any(w not in WORKFLOWS or WORKFLOWS[w]['dept'] not in allowed for w in d.workflows):
            raise HTTPException(403,'含未授权或未知工作流')
        async def one(w):
            try:
                answer=await asyncio.wait_for(rt().ask(d.query,user_id=u['id'],workflow=w,allowed=allowed,
                    allow_external=d.allow_external,clearance='sensitive' if u['role']=='admin' else 'internal'),timeout)
                return {'workflow':w,'status':'completed','result':answer}
            except Exception as exc:
                return {'workflow':w,'status':'unavailable','error':type(exc).__name__}
        results=await asyncio.gather(*(one(w) for w in dict.fromkeys(d.workflows)))
        return {'results':results,'partial':any(r['status']!='completed' for r in results),
            'merge_mode':'parallel governed sub-DAG results, not an invented cross-department conclusion'}

    @app.post('/api/pilot/consent')
    async def consent(d:PilotConsent,u=Depends(auth)):
        await rt().c.store.upsert('pilot_consents',{'_id':u['id'],**d.model_dump(),'at':timestamp()})
        return {'consent':d.consent,'note':'记录仅用于本次试点评估；参与者可撤回'}

    @app.post('/api/pilot/result')
    async def pilot(d:PilotResult,u=Depends(auth)):
        c=await rt().c.store.get('pilot_consents',u['id'])
        if not c or not c.get('consent'):raise HTTPException(422,'请先确认试点同意')
        if d.phase=='agent':
            t=await rt().c.store.get('traces',d.trace_id or '')
            if not t or t['user_id']!=u['id']:raise HTTPException(422,'需要自己的真实任务Trace')
        record={'_id':uuid.uuid4().hex,**d.model_dump(),'participant':hashlib.sha256(u['id'].encode()).hexdigest()[:20],'created_at':timestamp()}
        await rt().c.store.upsert('pilot_events',record)
        return {'id':record['_id'],'status':'recorded','source':'participant_submitted_not_independent_label'}

    @app.get('/api/pilot/results')
    async def results(u=Depends(admin)):
        rows=await rt().c.store.find('pilot_events')
        real=[r for r in rows if not r.get('is_test')]
        return {'rows':rows,'non_test_events':len(real),'participants':len(set(r['participant'] for r in real)),
                'claim_boundary':'Uploaded forms do not themselves prove external recruitment or independent correctness.'}
