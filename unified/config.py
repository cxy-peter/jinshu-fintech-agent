"""Deployment configuration; never disclose credentials or silently select offline mode."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
REQUIRED = {
 'AUTH_SECRET':'账号签名密钥（至少32字符）','MONGODB_URI':'MongoDB事实、任务与审核存储',
 'REDIS_ADDR':'Redis工作记忆与作业队列','MILVUS_URI':'Milvus/Zilliz向量索引',
 'CHAT_BASE_URL':'对话模型兼容接口','CHAT_API_KEY':'对话模型凭据','CHAT_MODEL':'对话模型名称',
 'EMBEDDING_BASE_URL':'Embedding兼容接口','EMBEDDING_API_KEY':'Embedding凭据','EMBEDDING_MODEL':'Embedding模型名称','EMBEDDING_DIM':'Embedding向量维度',
 'RERANKER_BASE_URL':'Reranker兼容接口','RERANKER_API_KEY':'Reranker凭据','RERANKER_MODEL':'Reranker模型名称'}
def problems(env=None):
 env=os.environ if env is None else env
 missing=[k for k in REQUIRED if not env.get(k,'').strip()];invalid=[]
 if env.get('AUTH_SECRET') and len(env['AUTH_SECRET'])<32:invalid.append('AUTH_SECRET')
 try:
  if env.get('EMBEDDING_DIM') and not 1<=int(env['EMBEDDING_DIM'])<=16384:invalid.append('EMBEDDING_DIM')
 except ValueError:invalid.append('EMBEDDING_DIM')
 for k in ['CHAT_BASE_URL','EMBEDDING_BASE_URL','RERANKER_BASE_URL','MILVUS_URI']:
  if env.get(k):
   u=urlsplit(env[k]);local=u.hostname in {'127.0.0.1','localhost','::1'}
   if u.scheme not in {'http','https'} or not u.hostname or u.username or u.password:invalid.append(k)
   elif env.get('VERCEL') and (u.scheme!='https' or local):invalid.append(k)
 if env.get('VERCEL'):
  if env.get('MONGODB_URI') and not env['MONGODB_URI'].startswith(('mongodb://','mongodb+srv://')):invalid.append('MONGODB_URI')
  if env.get('REDIS_ADDR') and not env['REDIS_ADDR'].startswith('rediss://'):invalid.append('REDIS_ADDR')
  if env.get('MILVUS_URI') and not env.get('MILVUS_TOKEN'):missing.append('MILVUS_TOKEN')
 if env.get('PI_AGENT_ENABLED','false').lower()=='true':
  for k in ['PI_AGENT_URL','INTERNAL_API_TOKEN']:
   if not env.get(k):missing.append(k)
  if env.get('VERCEL') and not env.get('PI_AGENT_URL','').startswith('https://'):invalid.append('PI_AGENT_URL')
 if env.get('JINSHU_MODEL_SCOPE','external')!='local' and env.get('JINSHU_ALLOW_EXTERNAL')!='1':missing.append('JINSHU_ALLOW_EXTERNAL')
 return {'missing':missing,'invalid':sorted(set(invalid))}
def settings():
 from app.config import Settings
 p=problems()
 if p['missing'] or p['invalid']:raise ValueError('deployment_configuration_incomplete')
 return Settings(_env_file=None,storage_mode='mongo',vector_backend='milvus',app_name='金枢｜统一金融中后台工作台',seed_demo_users=False,
  auth_secret=os.environ['AUTH_SECRET'],mongodb_uri=os.environ['MONGODB_URI'],mongodb_db=os.getenv('MONGODB_DB','jinshu'),redis_addr=os.environ['REDIS_ADDR'],
  embedding_provider='relay',embedding_dim=int(os.environ['EMBEDDING_DIM']),embedding_model=os.environ['EMBEDDING_MODEL'],reranker_enabled=True,
  relay_base_url=os.environ['CHAT_BASE_URL'],relay_api_key=os.environ['CHAT_API_KEY'],relay_model=os.environ['CHAT_MODEL'],deepseek_api_key='',
  pi_agent_enabled=os.getenv('PI_AGENT_ENABLED','false').lower()=='true',pi_agent_url=os.getenv('PI_AGENT_URL',''),internal_api_token=os.getenv('INTERNAL_API_TOKEN',''),
  timeout_intent=10,timeout_retrieval=25,timeout_answer=60,timeout_verify=25,
  pi_runtime_timeout_intent=8,pi_runtime_timeout_rewrite=10,pi_runtime_timeout_answer=45,pi_runtime_timeout_verify=20,
  upload_storage_dir='/tmp/jinshu-uploads',async_stream_name='jinshu:jobs:v8',dept_agents_enabled=False,auth_token_ttl_hours=4)
