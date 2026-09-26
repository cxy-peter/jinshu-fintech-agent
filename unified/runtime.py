"""Original complete Runtime, initialized once per process, never as a web demo."""
from __future__ import annotations
import asyncio,os,tempfile,uuid
from pathlib import Path
from . import config
class RuntimeUnavailable(Exception):
 def __init__(self,code='services_unavailable'):self.code=code
class RuntimeManager:
 def __init__(self,runtime=None):self.runtime=runtime;self.lock=asyncio.Lock();self.failure=None
 async def get(self):
  if self.runtime is not None:return self.runtime
  if any(config.problems().values()):raise RuntimeUnavailable('configuration_required')
  async with self.lock:
   if self.runtime is not None:return self.runtime
   from jinshu.runtime import Runtime
   from .tools import dispatch
   settings=config.settings();runtime=None
   try:
    runtime=await asyncio.to_thread(Runtime,profile='services',settings=settings,instance_id=str(Path(tempfile.gettempdir())/('jinshu-'+uuid.uuid4().hex)),bootstrap_documents=False)
    await asyncio.wait_for(runtime.initialize(),35)
    runtime.c.skill_executor.tool_runner=dispatch
    from jinshu.skills import seed_skills
    from jinshu.hooks import seed_controls
    await seed_skills(runtime.c.store);await seed_controls(runtime.c.store)
    # Clustering hash vectors are NOT document embeddings and never enter Milvus.
    # Historical feedback is not automatically transmitted to external models.
    if os.getenv('JINSHU_MODEL_SCOPE','external')!='local':
     from app.llm.embeddings import EmbeddingClient
     from app.loop.skill_miner import SkillMiner
     from app.config import Settings
     from jinshu.agents import DisabledLLM
     disabled=DisabledLLM();runtime.c.loop_engine.llm=disabled;runtime.c.loop_engine.pi_runtime=None
     runtime.c.loop_engine.embeddings=EmbeddingClient(Settings(_env_file=None,embedding_provider='hash',embedding_dim=128),None)
     runtime.c.loop_engine.skill_miner=SkillMiner(runtime.c.store,disabled,min_cluster=settings.skill_min_cluster)
    self.runtime=runtime;self.failure=None;return runtime
   except Exception as exc:
    self.failure=type(exc).__name__
    try:await runtime.close()
    except Exception:pass
    raise RuntimeUnavailable() from None
 def status(self):
  p=config.problems()
  return {'version':'8.0.0','runtime':'jinshu.runtime.Runtime','mode':'complete_server','same_local_and_vercel_entrypoint':True,
   'configured':not any(p.values()),'connected':self.runtime is not None,'required_configuration':p,'last_error_type':self.failure,
   'model_inference_verified':'not_asserted_by_health_check','note':'configured仅表示必需配置存在；连接与真实模型质量另行验证。',
   'policy_proposals':'private_model' if os.getenv('JINSHU_MODEL_SCOPE')=='local' else 'bounded_rules_no_external_feedback_upload'}
