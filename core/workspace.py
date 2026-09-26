"""Additive API for the governed workspace; no cloud client at import time."""
from __future__ import annotations
import base64
import io
import os
import secrets
import time
from datetime import date
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from typing import Literal
from . import governance as g
from .store import Store, StoreUnavailable
from .rag import chunk_text,index_chunks,active_documents,search,source_graph,encoder_available,digest,MODEL_ID

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Login(Input):
    username:str=Field(min_length=1,max_length=50)
    password:str=Field(min_length=1,max_length=200)
class Document(Input):
    title:str=Field(min_length=1,max_length=120)
    text:str=Field(min_length=1,max_length=20000)
    topic:str=Field(min_length=1,max_length=100)
    department:Literal['dept_wealth','dept_release','dept_risk','dept_service','shared']='shared'
    version:int=Field(ge=1,le=10000,default=1)
    source_url:str=Field(default='',max_length=1000)
    effective:str=''
    expires:str=''
class Review(Input):
    decision:Literal['approve','reject']
    reason:str=Field(min_length=1,max_length=500)
    external_allowed:StrictBool=False
class Feedback(Input):
    conversation_id:str=Field(max_length=40)
    trace_id:str=Field(max_length=40)
    resolved:StrictBool
    category:Literal['retrieval','intent','generation','knowledge_gap']='generation'
    note:str=Field(default='',max_length=1000)
    expected_docs:list[str]=Field(default_factory=list,max_length=5)
    share_context:StrictBool=False
class Proposal(Input):
    feedback_ids:list[str]=Field(min_length=1,max_length=30)
    terms:list[str]=Field(default_factory=list,max_length=8)
    top_k:int=Field(default=6,ge=2,le=8)
    template:Literal['direct','checklist','compare']='direct'
class Action(Input):
    action:Literal['replay','canary','promote','rollback']
class Preferences(Input):
    language:Literal['zh','en']='zh'
    format:Literal['direct','checklist','compare']='direct'
    remember:StrictBool=False
class Parse(Input):
    name:str=Field(max_length=120)
    data:str=Field(max_length=90000)


def install(app,authorize,env=None,clock=time.monotonic):
    e=os.environ if env is None else env
    store=Store(e);app.state.workspace_store=store
    from .security import Budget
    auth_limit=Budget(clock)
    @app.exception_handler(StoreUnavailable)
    async def unavailable(request,exc):
        return JSONResponse({'error':{'code':'STORE_UNAVAILABLE','message':str(exc)}},503)
    @app.exception_handler(PermissionError)
    async def denied(request,exc):
        return JSONResponse({'error':{'code':'ROLE_DENIED','message':str(exc)}},403)
    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        return JSONResponse({'error':{'code':'WORKSPACE_INVALID','message':str(exc)[:300]}},409)

    @app.get('/api/workspace/bootstrap')
    async def bootstrap(request:Request,c=Depends(authorize)):
        from jinshu.fixtures import WORKFLOWS
        state=await store.read();who=g.actor(state,request);oid=g.owner(request)
        result={'store':store.kind,'actor':who and {k:who[k] for k in ('username','name','role')},
            'accounts':g.ACCOUNTS if e.get('JINSHU_DEMO_ACCOUNTS')=='1' else [],
            'conversations':[{'id':x['id'],'title':x['title'],'revision':x['revision'],'updated_at':x['updated_at']} for x in state['conversations'].values() if x['owner']==oid],
            'semantic':{'configured':encoder_available(),'model':MODEL_ID,'verified_this_request':False},
            'optional':{k:bool(e.get(v)) for k,v in [('MongoDB','MONGODB_URI'),('Redis','REDIS_ADDR'),('Milvus','MILVUS_URI'),('pi','PI_AGENT_URL')]},
            'department_options':g.DEPARTMENTS,'workflows':{key:row['name'] for key,row in WORKFLOWS.items()}}
        response=JSONResponse(result)
        if not oid:response.set_cookie('jinshu_owner',secrets.token_hex(32),httponly=True,secure=request.url.scheme=='https',samesite='strict',max_age=90*86400)
        return response

    @app.post('/api/workspace/login')
    async def login(d:Login,request:Request,c=Depends(authorize)):
        if not auth_limit.consume(str(request.client.host),model=False,per_minute=10):raise HTTPException(429,'登录过于频繁')
        token,who=await store.mutate(lambda s:g.login(s,d.username,d.password,e))
        response=JSONResponse({'actor':who})
        response.set_cookie('jinshu_session',token,httponly=True,secure=request.url.scheme=='https',samesite='strict',max_age=14400)
        return response

    @app.post('/api/workspace/logout')
    async def logout(request:Request,c=Depends(authorize)):
        await store.mutate(lambda s:s['sessions'].pop(digest(request.cookies.get('jinshu_session','')),None))
        response=JSONResponse({'logged_out':True});response.delete_cookie('jinshu_session');return response

    @app.get('/api/library')
    async def library(request:Request,c=Depends(authorize)):
        s=await store.read();who=g.actor(s,request)
        docs=list(s['documents'].values()) if who else [d for d in active_documents(s) if d['external_allowed']]
        return {'documents':[{k:v for k,v in d.items() if k not in ('chunks',)}|{'chunks':[{k:v for k,v in ch.items() if k!='vector'} for ch in d['chunks']]} for d in docs]}

    @app.post('/api/library')
    async def document(d:Document,request:Request,c=Depends(authorize)):
        s=await store.read();who=g.actor(s,request);g.require(who,'editor','reviewer')
        if not d.text.strip() or not d.title.strip():raise ValueError('标题和正文不能为空')
        if d.effective:date.fromisoformat(d.effective)
        if d.expires:date.fromisoformat(d.expires)
        if d.expires and d.effective and d.expires<d.effective:raise ValueError('失效日期早于生效日期')
        if d.source_url:
            from urllib.parse import urlsplit
            u=urlsplit(d.source_url)
            if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('来源链接须为 https 地址')
        chunks=chunk_text(d.text,d.title)
        if len(chunks)>60:raise ValueError('单份资料最多60个条款，请拆分')
        chunks,model=await index_chunks(chunks,e.get('JINSHU_SEMANTIC','1')!='0')
        record=d.model_dump()|dict(id=g.uid(),author=who['username'],status='pending',chunks=chunks,embedding=model,
            hash=digest(d.text),external_allowed=False,origin='reviewed_library',created_at=g.now())
        def save(s):
            g.require(g.actor(s,request),'editor','reviewer')
            if len(s['documents'])>=80:raise ValueError('演示空间最多80份资料，请使用企业存储归档扩容')
            if any(x['topic']==d.topic and x['department']==d.department and x['version']==d.version for x in s['documents'].values()):raise ValueError('主题版本已存在，请增加版本号')
            s['documents'][record['id']]=record;g.audit(s,'document_submitted',who['username'],doc_id=record['id']);return record
        result=await store.mutate(save)
        from .optional_services import milvus_index
        vector_status=await milvus_index(e,record)
        return {'id':result['id'],'status':result['status'],'chunk_count':len(chunks),'embedding':model,'vector_index':vector_status}

    @app.post('/api/library/{did}/review')
    async def review(did:str,d:Review,request:Request,c=Depends(authorize)):
        row=await store.mutate(lambda s:g.publish(s,did,g.actor(s,request),d.decision,d.reason,d.external_allowed))
        return {k:v for k,v in row.items() if k not in ('chunks','text')}

    @app.post('/api/library/parse/file')
    async def parse_file(d:Parse,request:Request,c=Depends(authorize)):
        g.require(g.actor(await store.read(),request),'editor','reviewer')
        raw=base64.b64decode(d.data,validate=True)
        if len(raw)>65000:raise ValueError('当前内置解析限65KB；大文件请先提取正文')
        if d.name.lower().endswith('.pdf'):
            from pypdf import PdfReader
            pdf=PdfReader(io.BytesIO(raw))
            if pdf.is_encrypted or len(pdf.pages)>30:raise ValueError('仅支持未加密、30页以内的原生文字 PDF')
            text='\n\n'.join(f'## 第{i+1}页\n'+(p.extract_text() or '') for i,p in enumerate(pdf.pages))
        elif d.name.lower().endswith('.docx'):
            import zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist())>2_000_000:raise ValueError('解压内容过大')
            from docx import Document as Word
            document=Word(io.BytesIO(raw));text='\n'.join(p.text for p in document.paragraphs)
            for t in document.tables:
                text+='\n'+'\n'.join('| '+' | '.join(c.text for c in r.cells)+' |' for r in t.rows)
        else:raise ValueError('仅支持 PDF / DOCX；其他文本直接粘贴')
        if len(text)>20000 or len(text.strip())<10:raise ValueError('未提取到有效正文或超过20000字，请人工整理后提交')
        return {'text':text,'notice':'解析预览，请先核对乱码、表格和页码；尚未入库或发布。'}

    @app.get('/api/conversations/{cid}')
    async def conversation(cid:str,request:Request,c=Depends(authorize)):
        s=await store.read();row=s['conversations'].get(cid)
        if not row or row['owner']!=g.owner(request):raise HTTPException(404,'会话不存在')
        return row

    @app.delete('/api/conversations/{cid}')
    async def forget(cid:str,request:Request,c=Depends(authorize)):
        def remove(s):
            row=s['conversations'].get(cid)
            if not row or row['owner']!=g.owner(request):raise PermissionError('无权删除会话')
            s['conversations'].pop(cid)
            for key,f in list(s['feedback'].items()):
                if f['conversation_id']==cid:s['feedback'].pop(key)
            # Removing a replay sample invalidates its binding; no orphaned approved treatment.
            return {'deleted':True}
        return await store.mutate(remove)

    @app.post('/api/conversations/{cid}/preferences')
    async def preferences(cid:str,d:Preferences,request:Request,c=Depends(authorize)):
        def save(s):
            row=s['conversations'].get(cid)
            if not row or row['owner']!=g.owner(request):raise PermissionError('无权修改会话')
            row['preferences']=d.model_dump() if d.remember else {};return row['preferences']
        return await store.mutate(save)

    @app.post('/api/feedback')
    async def feedback(d:Feedback,request:Request,c=Depends(authorize)):
        if not d.share_context:raise ValueError('请先确认将本轮及相关上下文提交给运营复核')
        def save(s):
            row=s['conversations'].get(d.conversation_id)
            if not row or row['owner']!=g.owner(request):raise PermissionError('只能反馈自己的会话')
            at=next((i for i,t in enumerate(row['turns']) if t.get('trace_id')==d.trace_id),None)
            if at is None or row['turns'][at]['role']!='assistant':raise ValueError('回答记录不存在')
            turn=row['turns'][at];labelled=set(d.expected_docs)
            if not labelled<={doc['id'] for doc in active_documents(s,turn['department']) if doc['external_allowed']}:raise ValueError('目标资料不在当前有效资料库')
            feedback_id=digest(d.conversation_id+'|'+d.trace_id)[:32]
            if len(s['feedback'])>=200 and feedback_id not in s['feedback']:raise ValueError('反馈演示上限200，请归档后继续')
            f=d.model_dump()|dict(id=feedback_id,owner=row['owner'],query=row['turns'][at-1]['content'],answer=turn['content'],
                context=[{'role':t['role'],'content':t['content']} for t in row['turns'][max(0,at-5):at+1]],
                sources=turn.get('sources',[]),department=turn['department'],skill_id=turn.get('skill_id'),group=turn.get('group'),created_at=g.now())
            s['feedback'][f['id']]=f
            # Low quality automatically stops an existing experiment; never auto-promotes.
            if f.get('skill_id'):
                skill=s['skills'].get(f['skill_id']);m=g.skill_metrics(s,f['skill_id'])
                if skill and skill['status']=='active' and min(m[x]['n'] for x in ('control','treatment'))>=5 and m['treatment']['rate']+.1<m['control']['rate']:
                    skill.update(status='rolled_back',rollout=0);g.audit(s,'automatic_guardrail_rollback','system',skill_id=skill['id'])
            return {'id':f['id'],'saved':True}
        return await store.mutate(save)

    @app.get('/api/operations')
    async def operations(request:Request,c=Depends(authorize)):
        s=await store.read();g.require(g.actor(s,request),'operator','reviewer','editor');return g.dashboard(s)

    @app.post('/api/skills')
    async def propose(d:Proposal,request:Request,c=Depends(authorize)):
        if any(not t.strip() or len(t)>40 for t in d.terms):raise ValueError('扩展词1至40字')
        return await store.mutate(lambda s:g.propose(s,g.actor(s,request),d.feedback_ids,d.top_k,d.terms,d.template))

    @app.post('/api/skills/{sid}')
    async def skill_action(sid:str,d:Action,request:Request,c=Depends(authorize)):
        return await store.mutate(lambda s:g.replay(s,sid,g.actor(s,request)) if d.action=='replay' else g.release(s,sid,g.actor(s,request),d.action))
    return store


async def prepare(store,d,request):
    """Only opt-in persisted chats load history; client history cannot override it."""
    state=await store.read();oid=g.owner(request)
    if d.persist and not oid:raise ValueError('请先初始化工作空间，再启用持久化对话')
    conversation=state['conversations'].get(d.conversation_id) if d.conversation_id else None
    if d.conversation_id and (not conversation or conversation['owner']!=oid):raise PermissionError('会话不属于当前浏览器')
    if conversation and conversation['revision']!=d.conversation_revision:raise ValueError('会话已更新，请重新加载后发送')
    history=[{'role':t['role'],'content':t['content'][:2500]} for t in conversation['turns'][-8:]] if conversation else [m.model_dump() for m in d.history]
    from .optional_services import working_history,pi_rewrite
    history,working_mode=await working_history(store.env,conversation,history)
    prefs=conversation.get('preferences',{}) if conversation else {}
    query=d.query
    # Conservative pronoun expansion; material is not substituted for the question.
    if history and len(query)<35 and any(x in query for x in ('这个','那个','它','继续','上面','为什么','那')):
        prior=next((m['content'] for m in reversed(history) if m['role']=='user'),'')
        query=prior[-400:]+'\n补充问题：'+query
    skill,group=g.policy(state,oid or 'anonymous',d.department)
    top_k=4;instructions=[]
    if skill and group=='treatment':query+=' '+' '.join(skill['terms']);top_k=skill['top_k'];instructions.append(g.TEMPLATES[skill['template']])
    if prefs.get('remember'):
        instructions.append(g.TEMPLATES[prefs['format']]);instructions.append('请用英文回答。' if prefs['language']=='en' else '请用中文回答。')
    docs=[x for x in active_documents(state,d.department) if x['external_allowed']] if d.use_library else []
    query,rewrite_mode=await pi_rewrite(store.env,query)
    sources,mode=await search(query,docs,top_k,env=store.env)
    return {'state':state,'owner':oid,'conversation':conversation,'history':history,'query':query,'sources':sources,
            'retrieval_mode':mode,'working_mode':working_mode,'rewrite_mode':rewrite_mode,'instructions':instructions,'skill':skill,'group':group,'graph':source_graph(docs,sources)}


def verify_current_sources(state, sources, department):
    active={d['id']:d for d in active_documents(state,department) if d['external_allowed']}
    for source in sources:
        if source.get('origin')!='reviewed_library':continue
        doc=active.get(source['doc_id'])
        if not doc or doc['version']!=source['version'] or not any(c['hash']==source['hash'] and digest(c['text'])==source['hash'] for c in doc['chunks']):
            raise ValueError('回答生成期间资料版本或权限已变，请重新提问')


async def save_answer(store,d,request,context,result):
    cid=d.conversation_id or g.uid();tid=result['trace_id']
    def save(s):
        row=s['conversations'].get(cid)
        if row and (row['owner']!=context['owner'] or row['revision']!=d.conversation_revision):raise ValueError('会话有新内容，请刷新；迟到回答未覆盖新记录')
        if not row:
            if sum(c['owner']==context['owner'] for c in s['conversations'].values())>=20 or len(s['conversations'])>=100:raise ValueError('会话数量达到演示上限，请删除旧会话再保存')
            row=dict(id=cid,owner=context['owner'],title=d.query[:32],revision=0,turns=[],preferences={})
        if len(row['turns'])>=40:raise ValueError('本会话已达20轮，请新建对话')
        # Re-check the exact source hashes after the model call; retired facts cannot
        # be persisted/presented as current reviewed sources.
        verify_current_sources(s,result['sources'],d.department)
        row['turns'].extend([{'role':'user','content':d.query}, {'role':'assistant','content':result['answer'],
            'trace_id':tid,'sources':result['sources'],'trace':result['trace'],'department':d.department,
            'skill_id':context['skill']['id'] if context['skill'] else None,'group':context['group'],
            'verification':result['verification'],'model_call':result['model_call']}])
        row.update(revision=row['revision']+1,updated_at=g.now());s['conversations'][cid]=row
        return {'conversation_id':cid,'conversation_revision':row['revision'],'persistence':store.kind}
    return await store.mutate(save)
