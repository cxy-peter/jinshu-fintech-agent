# API不可用时怎样退回 / V3.1

本轮只补必要的业务失败处理，不建立额外的安全测试平台。

|故障位置|当前执行或设计状态|业务人员看到什么|
|---|---|---|
|查询Embedding / Milvus|关键词检索继续，仍回查有效原文|Trace记录embedding/vector不可用|
|Reranker|回到RRF候选顺序|记录重排回退，不假装模型重排完成|
|Answer / Verify|有界重写或返回原文、依据不足|原文摘录与未生成说明|
|权威事实库|不把旧缓存当成最新权限或制度|服务异常，不作确定答复；统一可用性层仍待建设|
|回滚控制调用|先本地落盘停候选，再发回滚请求|失败是local_baseline_remote_unconfirmed，下次使用稳定基线|
|整个API或进程不可达|本机处理可能根本没执行|需要独立网关或运维停流，当前未实现|
|外部工单服务|本地保存幂等草稿|pending_submission；无外部编号不显示成功|
|Redis/Mongo服务|原服务接口、消费组与作业状态保留|真实服务需联调，不默默替成内存后宣称持久化|

## 本轮实际回滚实验
先让一个候选将发行检索top-k从2改到8，然后注入回滚控制调用失败。RecoveryController先以文件原子替换保存冻结，再调用控制操作。操作失败记录ConnectionError和local_baseline_remote_unconfirmed。下一次Skill执行跳过此family的实验候选，稳定base仍执行，因此top-k恢复2。重建控制器仍可读取冻结。

这个开关覆盖当前实例，不保证全体Pod一致，也未做fsync断电恢复承诺。解除冻结应在远端状态确认后由管理员操作；不支持未经确认的自动恢复。

## 已实现API
- GET `/api/operations`：冻结状态与本地工单。
- POST `/api/operations/rollback`：skill_id、reason；离线模式可用simulate_failure演示故障。
- POST `/api/operations/resume/{family}`：管理员显式恢复。
- POST `/api/tickets`：session_id、summary；保存草稿，当前没有真实Zendesk地址。

源码入口：jinshu/operations.py、jinshu/skills.py、jinshu/api.py。现场演示不必把所有异常都做一遍，展示一次正常执行、一次回滚失败、一次基线继续服务即可。
