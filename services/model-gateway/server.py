"""Small self-hosted *real model* gateway; no canned answers / hash vectors.
Loads approved Hugging Face weights; downloaded models remain in mounted cache.
CPU defaults are integration baselines, not claimed financial-grade models.
"""
from __future__ import annotations
import asyncio, json, os, time, uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

app=FastAPI(title='Jinshu private model gateway',version='4.0')
CHAT=os.getenv('LOCAL_CHAT_MODEL','Qwen/Qwen2.5-0.5B-Instruct')
EMBED=os.getenv('LOCAL_EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5')
RERANK=os.getenv('LOCAL_RERANKER_MODEL','BAAI/bge-reranker-base')
loaded={}; serial=asyncio.Semaphore(1)

def auth(value):
    token=os.getenv('MODEL_GATEWAY_TOKEN','')
    if not token or value != 'Bearer '+token:
        raise HTTPException(401,'Configure MODEL_GATEWAY_TOKEN and use its bearer token')

def load(kind):
    if kind not in loaded:
        import torch
        from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM, AutoModelForSequenceClassification
        torch.set_num_threads(int(os.getenv('MODEL_THREADS','2')))
        name={'chat':CHAT,'embedding':EMBED,'rerank':RERANK}[kind]
        cls={'chat':AutoModelForCausalLM,'embedding':AutoModel,'rerank':AutoModelForSequenceClassification}[kind]
        options={'trust_remote_code':False}
        revision=os.getenv('LOCAL_'+{'chat':'CHAT','embedding':'EMBEDDING','rerank':'RERANKER'}[kind]+'_REVISION')
        if revision:options['revision']=revision
        tokenizer=AutoTokenizer.from_pretrained(name,**options)
        model=cls.from_pretrained(name,**options).eval()
        device=os.getenv('MODEL_DEVICE','cpu'); model.to(device)
        loaded[kind]=(tokenizer,model)
    return loaded[kind]

@app.get('/health')
def health():
    return {'status':'ready','loaded':list(loaded),'kind':'real_transformers','lazy_load':True}

@app.get('/v1/models')
def models():
    return {'object':'list','data':[{'id':n,'object':'model'} for n in [CHAT,EMBED,RERANK]]}

@app.get('/provenance')
def provenance(authorization:str=Header(default='')):
    auth(authorization)
    return {kind:{'model':model.config._name_or_path,'revision':getattr(model.config,'_commit_hash',None),'architecture':model.__class__.__name__,'device':str(model.device)} for kind,(_,model) in loaded.items()}

class EmbeddingRequest(BaseModel):
    model:str
    input:list[str]|str
    encoding_format:str='float'

@app.post('/v1/embeddings')
async def embedding(req:EmbeddingRequest,authorization:str=Header(default='')):
    auth(authorization)
    if req.model!=EMBED:raise HTTPException(422,'embedding model mismatch')
    texts=[req.input] if isinstance(req.input,str) else req.input
    if not 1<=len(texts)<=32:raise HTTPException(422,'1..32 texts per batch')
    def work():
        import torch
        tok,model=load('embedding')
        enc=tok(texts,padding=True,truncation=False,return_tensors='pt')
        if enc['input_ids'].shape[1]>512:raise ValueError('chunk exceeds embedding window; split smaller, never silently truncate')
        enc={k:v.to(model.device) for k,v in enc.items()}
        with torch.inference_mode():
            vectors=torch.nn.functional.normalize(model(**enc).last_hidden_state[:,0],p=2,dim=1).cpu().tolist()
        return {'object':'list','model':EMBED,'data':[{'object':'embedding','index':i,'embedding':v} for i,v in enumerate(vectors)],'usage':{'prompt_tokens':int(enc['attention_mask'].sum()),'total_tokens':int(enc['attention_mask'].sum())}}
    try:
        async with serial:return await asyncio.to_thread(work)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

class RerankRequest(BaseModel):
    model:str
    query:str
    documents:list[str]=Field(max_length=80)
    top_n:int=Field(default=5,ge=1,le=80)

@app.post('/v1/rerank')
async def rerank(req:RerankRequest,authorization:str=Header(default='')):
    auth(authorization)
    if req.model!=RERANK:raise HTTPException(422,'reranker model mismatch')
    def work():
        import torch
        tok,model=load('rerank');scores=[]
        for start in range(0,len(req.documents),8):
            enc=tok([[req.query,d] for d in req.documents[start:start+8]],padding=True,truncation=True,max_length=512,return_tensors='pt')
            enc={k:v.to(model.device) for k,v in enc.items()}
            with torch.inference_mode():scores.extend(model(**enc).logits.view(-1).float().cpu().tolist())
        ranked=sorted(range(len(scores)),key=lambda i:scores[i],reverse=True)[:req.top_n]
        return {'model':RERANK,'results':[{'index':i,'relevance_score':scores[i]} for i in ranked],'pair_max_tokens':512}
    async with serial:return await asyncio.to_thread(work)

class ChatRequest(BaseModel):
    model:str
    messages:list[dict]
    max_tokens:int|None=None
    max_completion_tokens:int|None=None
    temperature:float=0.0
    stream:bool=False

@app.post('/v1/chat/completions')
async def chat(req:ChatRequest,authorization:str=Header(default='')):
    auth(authorization)
    if req.model!=CHAT:raise HTTPException(422,'chat model mismatch')
    def work():
        import torch
        tok,model=load('chat')
        text=tok.apply_chat_template(req.messages,tokenize=False,add_generation_prompt=True)
        enc=tok([text],return_tensors='pt')
        if enc['input_ids'].shape[1]>int(os.getenv('CHAT_INPUT_LIMIT','6000')):
            raise ValueError('context exceeds configured budget')
        enc={k:v.to(model.device) for k,v in enc.items()}
        budget=min(req.max_tokens or req.max_completion_tokens or 256,int(os.getenv('CHAT_OUTPUT_LIMIT',os.getenv('MODEL_MAX_OUTPUT','256'))))
        with torch.inference_mode():
            ids=model.generate(**enc,max_new_tokens=budget,do_sample=False,pad_token_id=tok.eos_token_id)
        count=enc['input_ids'].shape[1]; generated=ids[0,count:]
        output=tok.decode(generated,skip_special_tokens=True)
        usage={'prompt_tokens':count,'completion_tokens':len(generated),'total_tokens':count+len(generated)}
        return output,usage
    try:
        async with serial:content,usage=await asyncio.to_thread(work)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    common={'id':'chatcmpl-'+uuid.uuid4().hex,'created':int(time.time()),'model':CHAT}
    if not req.stream:return common|{'object':'chat.completion','choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],'usage':usage}
    # Buffered SSE compatibility for the original pi client, not token-by-token inference.
    async def stream():
        for delta in [{'role':'assistant'},{'content':content}]:
            yield 'data: '+json.dumps(common|{'object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':None}]},ensure_ascii=False)+'\n\n'
        yield 'data: '+json.dumps(common|{'object':'chat.completion.chunk','choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':usage})+'\n\n'
        yield 'data: [DONE]\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream')
