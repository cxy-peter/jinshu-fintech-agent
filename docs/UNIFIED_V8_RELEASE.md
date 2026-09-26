# 金枢 V8｜统一运行时验收与部署交接

记录日期：2026-09-26（UTC）。**统一代码已上传，隔离服务联调通过；Vercel预览构建未成功，生产站点尚未切换。**

## 一、代码与执行范围

公开源码：[PR #2](https://github.com/cxy-peter/jinshu-fintech-agent/pull/2)，分支 `upgrade/unified-v8-runtime`。

本次已验证应用提交：`92e68aa47eda024c03c260c596e3086db0110a5a`。

统一入口为 `index.py → unified.app → jinshu.runtime.Runtime(profile=services)`。本地和Vercel使用相同ASGI应用；前端负责展示与HTTP请求，不再自行执行另一套BM25、财务计算或策略发布。

复用原有Harness、事实校验、BM25/Milvus/RRF/重排、回答生成、Verifier、Memory、Trace与Loop。任务状态、结果确认与导出增加服务器所有权检查和MongoDB版本条件写。原生资料上传、独立复核、停用和索引版本刷新通过同一后端。示例数据必须显式选择；配置不足返回503，部署不会静默注入测试Runtime。

本轮没有把Visit China的Node实现或稀疏检索冒充金枢的Milvus服务。借鉴的是共享后端和可核验的产品流程，而不是假定两个项目的基础设施相同。

## 二、已执行的验收

[GitHub Actions 36203717804](https://github.com/cxy-peter/jinshu-fintech-agent/actions/runs/36203717804) 已完成，所有步骤成功。

| 层次 | 结果 | 证明范围 |
|---|---:|---|
| Python回归 | 196项通过 | 包含原有及统一版HTTP、权限、任务版本和文件检查；有1条依赖弃用警告 |
| 历史网页回归 | 116项通过 | 原V7网页代码的保留检查，不是V8实际云端检索效果 |
| 浏览器 | 29项通过，页面异常0 | Chromium访问真实本机HTTP，注入明确的测试Runtime；覆盖登录、问答、8工具及导出、修改输入失效、9入口和移动端 |
| 完整服务联调 | 10项通过 | 隔离Docker中的真实MongoDB、Redis、Milvus；模型协议端点是受控测试服务 |

真实持久服务检查包括：
1. 三项数据服务连接。
2. 不自动播种演示账号或文档。
3. Redis限流下的登录。
4. 独立审核与真实Milvus写入。
5. 完整Harness经受控HTTP执行Embedding、Reranker、Chat和Verifier。
6. MongoDB条件写拒绝并发旧版本修改。
7. Redis Stream与MongoDB作业状态处理。
8. 新建第二个Runtime后恢复Trace、任务与工作记忆。
9. 停用资料后另一实例刷新部门索引。
10. 已停用来源不能继续支撑问答。

工件名 `jinshu-unified-v8`，ID `10893207155`，SHA-256：`11b6043d945a7e5b545357337c1bdffae56d655734ad38c93bed1d5b17efef90`。保留源码、依赖版本、测试记录、导出样例及截图。

**这些结果不是：真实模型回答准确率、Vercel实站通过、真实用户试点，或金融业务提效成绩。** 旧489/500不挪用为V8完整服务质量。

## 三、失败记录与修复

早先CI因shell heredoc缩进失败，随后修正。真实服务联调首次因MinIO镜像拉取未授权而未执行；改用Milvus官方提供的embedded-etcd/local-storage拓扑进行隔离测试，仍运行真实Milvus server，没有改成内存替身。生产存储方案未因此改变。

分页JSON ZIP现按成员保留独立文档身份和页码；资料停用更新正确的部门语料版本。两项修复已包含在上述已验收应用提交。

## 四、Vercel尚未完成的部分

私有发布仓库 `cxy-peter/jinshu-workbench` 的 `preview/unified-v8` 已包含完整后端源文件，不再只是复制web资产。其应用源固定到 `1ff0a2412926971fd4517e8304c37c3c3f71cf67`；随后 `92e68aa` 只修改测试用Compose拓扑，不改变预览应用逻辑。

预览提交 `4611088338ff198e7c560f93940dc216aa0debd1` 的Vercel状态仍为failure；部署ID为 `dpl_86nVZ6S3sJF3VGAiWL8EVmCs86Sc`。之前读取项目日志返回403；本次连接器重试又返回工具不存在、参数契约不匹配。**未读到构建错误正文，不能断言构建失败由权限、依赖体积或某个配置造成。**

生产发布仓库main仍为 `3dbef47dacdbb428696a5c4dc3c8050764e847a4`。未用缺配置或失败的V8替换原V7站点，也未开启付费云资源、修改账号权限或读取生产密钥。

## 五、恢复部署的检查顺序

先恢复Vercel连接并授权 `cxy-peters-projects / jinshu-workbench`，再读取上述部署日志。不能为了绕过工具访问拒绝而公开部署日志或关闭鉴权。

核对项目根目录为仓库根、框架为FastAPI、入口为index.py，移除旧静态构建设置的冲突。根据实际日志处理构建失败，不凭猜测启用套餐或更换依赖。

在Preview环境安全配置 `unified/environment.example` 列出的服务：MongoDB、Redis、Milvus及Chat/Embedding/Reranker接口。地址和凭据仅放Vercel环境变量。凭据是否已存在目前未核验；不要求用户在聊天中发送。Vercel临时文件不能作为持久数据库。

预览构建成功后，先检查版本和配置名称，再验证真实服务连接，创建编辑与独立复核账号并撤掉初始化口令。仅在明确授权后，用公开测试文字和公开测试资料调用真实模型，保留实际返回和错误，不复用受控响应冒充成功。

完成资料上传审核、问答引用、用户输入工具、修改失效、导出、反馈、候选回放及恢复检查后，才考虑合并和切换生产。原V7浏览器数据先主动备份，不自动迁出、删除或视为已审核。

## 六、部署依据

Vercel官方FastAPI文档支持index.py入口；数据服务需独立持久化，Function文件系统只有/tmp可写。2026-06-29的Large Functions公告提供部分场景下的大包选项，但必须先看到实际体积错误并确认适用条件，不能把它当成本次失败的已知原因。

- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/functions/runtimes
- https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size
- https://vercel.com/docs/agent-resources/vercel-mcp
