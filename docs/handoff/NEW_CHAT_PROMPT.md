# 复制以下内容，在新 Chat 直接发送

请继续我之前的 **金枢 Jinshu Fintech Agent V11** 项目，不要从头重新设计或重复已经做过的工作。

这是可公开阅读的项目交接材料，无需下载 ZIP：

- 导航：https://github.com/cxy-peter/jinshu-fintech-agent/blob/main/docs/handoff/README.md
- **完整上下文**：https://github.com/cxy-peter/jinshu-fintech-agent/blob/main/docs/handoff/V11_FULL_CONTEXT.md
- **历史文件和版本索引**：https://github.com/cxy-peter/jinshu-fintech-agent/blob/main/docs/handoff/HISTORY_INDEX.md
- **当前源码**：https://github.com/cxy-peter/jinshu-fintech-agent
- **演示站点**：https://jinshu-workbench.vercel.app/

请先读取完整上下文、历史索引、最新 README、docs/V11_RELEASE.md 与 docs/V11_UPGRADE.md；涉及具体功能则查看实际源码，并检查 GitHub 当前 main 与 Vercel 实际状态，勿只依赖交接文件的旧版本号。

项目是基于**文枢参考 Agent 工程**进行的金融中后台个人项目、AI 辅助工程实现；不是从零原创整个 Harness，不是直接把差旅助手换名，不涉及模型权重训练。保留知识治理/RAG、Memory、Skill、Bad Case 归因与受控反馈 Loop；借鉴差旅 V2 的结构化门控、DAG、规则约束、请求防重和持久检查点，并结合 Intern-Python4WealthProduct 的周报、同业对标和发行排期业务。

V11 新增「周报质检＋同业对标」复合流程和八类单工具流程的受控执行，含服务器节点检查点、请求去重、局部重试和结果复用、版本绑定、独立审核及 JSON/CSV 导出。恢复只覆盖白名单纯计算节点，需要后续请求继续，不保证跨系统 exactly-once。线上默认入口是 `index.py → core.app`；运行组件与保留的企业参考实现必须分清。

我要继续围绕 **Agent 架构/工程改造、产品运营可用性、简历精准表述、面试准备、GitHub 仓库维护与 Vercel 部署** 提问。优先提供能验证、能演示的实际交付。**不要虚构公司上线、真实用户提效、模型训练、团队分工、评测分数或 K8s/Milvus/pi 等可选组件在线上全部运行。** 若需编辑我的完整私人简历，请让我在当前新对话提供文件，勿从公开仓库推断个人信息。
