# 金枢 V11｜同一入口、受控部署

## 发布目标
仓库 `cxy-peter/jinshu-fintech-agent`；Vercel团队 `cxy-peters-projects`，项目 `jinshu-workbench`；正式地址 https://jinshu-workbench.vercel.app/ 。不要新建另一套业务版本。

`index.py → core.app`，框架FastAPI，根目录构建 `python scripts/build_unified.py`。`vercel.json`关闭自动Git发布，代码合并不等于生产切换。先验证指定提交，再发布预览/正式环境；保留上一部署与Git回退点。

## 配置职责
- Chat：服务端`DEEPSEEK_API_KEY`，可选`DEEPSEEK_MODEL`；不在客户端放Key。
- 持久状态：本地SQLite；云端显式`JINSHU_STORE=mongo`及已有`MONGODB_URI`/`MONGODB_DB`，或私有Blob。云端不回退到/tmp冒充持久化。
- 身份：`JINSHU_DEMO_ACCOUNTS=1`只供公开脱敏演示，真实工作区须关闭并配置独立授权账号。`JINSHU_ACCESS_CODE`可作为额外入口限制，不代替细粒度权限。
- CPU语义模型：`JINSHU_BUILD_EMBEDDINGS=1`构建下载固定模型；获取失败应明确BM25降级。Milvus、Redis、pi为可选服务，不是新任务流程必需依赖。

保留Vercel部署保护。不得为了测试关掉SSO、公开密钥或把私有资料写入GitHub。当前空间有共享演示角色；不要上传真实机构内部数据。

## 验收顺序
1. 指定Git提交跑Python、Node、浏览器及干净依赖冷启动检查。
2. 发布预览，检查`/api/status`的版本、实际存储类型及新接口。
3. 用合成数据验证重复创建返回同一任务、步骤保存、独立审核、版本绑定导出、输入改动失效及越权拒绝。
4. 模型连通须另经明确同意，用公开测试文字检查真实返回；不能用协议模拟回答代替真实模型，也不能把一次连通当质量评测。
5. 验收通过才切换正式域名，记录部署ID/URL/提交；保留回滚。旧数据库记录不迁走、不删除。

新流程一次HTTP只执行一个有界批次；45秒租约、每节点最多3次尝试。持久状态记录在数据库；服务重启后要后续请求触发恢复。没有常驻Worker、没有全链路LLM exactly-once声明。详细失败语义见V11说明。

原型事实文档上限8MB。任务输入最多180KB、每浏览器最多20个、全局最多100个（实际还受总容量限制）。超过上限明确拒绝，不覆盖旧数据。扩容需拆任务/节点集合并补压测。

本机原发布器和GitHub手动发布入口保留。账号凭据由用户直接在服务端配置；不要求在聊天中提供。当前已配置的Mongo和模型凭据不需要重新复制给AI。
