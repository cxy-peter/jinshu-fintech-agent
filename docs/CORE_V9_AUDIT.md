# 金枢：默认运行链路复查（V9）

基线：主仓库 `50fa0c88c285d309e8b5f9f1c44879bb214d2c8e`。参考：Visit China `5c8fab9c0f8bcc47bf72002b81564dbf9413a36c` 的 `api/chat.js` 与 `v5/cloud-chat.js`，其公开聊天与持久化运营后台分离。没有修改 Visit China，也未复制其密钥或私有数据。

## 实际复现的根因

1. 旧 `unified.config.problems`：只设置 DeepSeek key 仍缺12项，包括 MongoDB/Redis/Milvus、Embedding/Reranker 和全局外传开关。本次在本机复现首页200、未登录问答401、登录503。此前宣称“同一入口”没有解决运行就绪问题。
2. 旧登录与模型检查均调用整个 RuntimeManager；模型连通性被数据库/向量库/账号初始化绑定。构建修好了也不等于能问答。
3. 历史浏览器验收显式注入 offline Runtime，隔离服务用受控模型HTTP返回。它们能证明对应契约，不能证明仅有真实 DeepSeek key 的默认部署可运行。过去汇总措辞过强。
4. 依赖清单包含 NumPy/scikit-learn/PyMuPDF/Milvus 等；构建诊断曾依赖未声明 packaging。旧 V7 CI 还用 Python3.11 安装要求3.12的 NumPy，出现环境错配。
5. 存在多个历史发布工作流及旧默认入口，容易反复构建/验收不同版本。当前默认只保留核心验收与手动 Vercel 发布；旧工作流源文件移到 docs/legacy-workflows，不删除历史。

## 本次改法

- 默认 `index:app → core.app`，本地/Vercel/Docker共用。没有数据库连接、持久后台循环或模型调用的导入副作用。
- 仅4个直接生产依赖：FastAPI、Uvicorn、HTTPX、python-dotenv。模型检查独立于数据库、账号库和向量索引。
- 无key可以打开页面和使用业务工具。有key时以一次有总时限和输出预算的真实HTTP调用回答，不做5次模型串行调度。
- 文本资料与历史按本次请求传递；关键词检索只选择当前资料及用户勾选的合成示例；不伪装向量检索。引用检查只保证编号存在，不声称全部事实校验。
- 复用原8类确定性工具，保留显式数据、合成示例标志、数据哈希和本人复核导出。数据编辑使旧结果失效；不自动对外执行。
- 可选访问码、跨站请求拒绝、体积/长度/预算/并发限制、密钥不回传、错误不回传上游正文、HTML以文字显示。限流为每实例保护，非分布式费用上限。
- 浏览器清空后迟到响应不得恢复旧对话；停止等待明确提示请求可能已产生费用。浏览器内容刷新即清，不声称有持久化。

## 被主动延后的能力（未悄悄冒充“全功能”）

独立账号审核、共享知识库、跨设备记忆、MongoDB任务/Trace存储、Redis作业队列、Milvus/Embedding/Reranker、pi服务、持久化反馈Loop/灰度回滚、PDF/Word解析与Word导出。不在当前默认运行链路验收。原代码和企业依赖保留可供后续逐项接回；不能将V9核心测试当作上述能力验收。

## 验收方法与诚实边界

- 本机实际API测试覆盖默认入口、仅key配置、无key、旧变量、8工具、模型协议/错误、权限、请求边界、引用和导出；Node测试用真实子进程加stub CLI验证发布控制与Windows调用路径。
- 本机浏览器访问被环境的 ERR_BLOCKED_BY_ADMINISTRATOR 拒绝，不绕过环境策略；独立GitHub CI执行真实Chromium/HTTP界面测试。
- 新CI先创建空虚拟环境，只装生产依赖并启动真正的 index:app/实际发布目录，再安装pytest/浏览器，避免测试工具隐式补齐部署依赖。
- HTTP mock 与真实模型调用字段严格分开。当前环境没有真实模型密钥，Vercel目标团队读取返回403，因此本次不能仅凭代码测试断言真实DeepSeek已连接或正式站已更新。

## 参考的官方接口

DeepSeek 官方首次调用： https://api-docs.deepseek.com/zh-cn/ （当前示例 deepseek-flash；Chat Completions兼容格式）
Vercel Python运行时： https://vercel.com/docs/functions/runtimes/python

生产部署/模型验收必须以实际构建结果、首页版本、服务端状态和一次经同意的真实模型响应为准。
