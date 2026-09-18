# V6｜原ZIP、pi Runtime与视频能力对照

## 1. 对照范围

本轮重新解包用户上传的 `wenshu-project(3).zip`，共231个文件，SHA-256为 `716d2022e4c9c7ecad17ef082921f383aa779ff55bc0e86e07c395ee49ca479d`。与当前public engine比较：218个保留，其中216个字节相同；原有2个V3补丁仍为backend/app/harness/orchestrator.py和backend/app/storage/mongodb.py。13个学校资料和原设计资料未发布，不是新丢失的运行代码。16个pi目录文件全部一致。本轮通过新增overlay扩展，不覆盖原ZIP或engine。

视频为25分21.885秒、1868×1080；本轮按00:45、03:00、07:30、10:00、13:00、16:00、19:30、22:00、24:00、25:00检查10个关键帧并对照源码，未做完整音频逐字转写。视频07:30明确提及没有直接启动多个部门后端容器，因此不把图示拆分或配置当成真实集群效果。

## 2. 能力矩阵

| 参考能力 | 金枢完整服务 | Vercel网站 | 本轮处理/边界 |
|---|---|---|---|
| Intent→Rewrite→Retrieval→Answer→Verify | 复用原Harness并增加金融适配 | 规则路由、改写、检索、原文组装、来源校验 | 五步可观察，网页不声称每步调用模型 |
| pi Agent Runtime | 原16文件保留，兼容服务接口 | 不在浏览器运行pi服务 | 新增超时abort、最终消息选取和严格JSON overlay |
| Mongo事实平面/有效版本 | 文档状态、来源、审核与版本回查 | IndexedDB文档及active启停 | 网页没有服务器多人权限或分布式事实存储 |
| BM25+Milvus+RRF+Reranker | 已有真实服务子链路执行记录 | 中文分词+BM25+标题权重 | 网页未使用语义Embedding；失败不假装模型生成 |
| 父子/跨页证据 | 取决于解析器与原块元数据 | 同文档有界邻块展开 | V5.1已修目录误排和第24—25页说明不完整 |
| 引用/Verify | 来源状态与生成候选验证 | 原文offset、chunk、doc、版本逐字核验 | V6在回答里直接呈现参考资料和原文摘录 |
| 五类Memory | 工作、情景、用户、组织、程序策略 | 对应逻辑视图和本地记录 | 本地视图不是Redis/Mongo真实服务 |
| Execute/Observe/Reflect/Adapt/Deploy | 原LoopEngine配合反馈和受限候选 | 反馈归因选择、候选、真实历史检索回放、确认生效、回滚 | 进化对象是执行策略，不是模型权重 |
| Skill/Hook/Rule | 原模块保留，金融Skill可执行 | 8种业务工具+有限检索策略 | 不把未接入的Hook/Rule学习声称为网页自进化 |
| 异步队列 | Redis Stream/Worker，曾测试ACK | 当前浏览器异步函数 | 网页不冒充跨进程队列或至少一次投递 |
| 多部门 | 服务代码与适配保留，部分网络路径尚待联调 | 三表+周报的受限两个子任务 | 多任务检索合并不等于部署独立部门服务 |
| K8s/HPA/Prometheus | 有配置和采集脚本 | 不适合静态网页运行 | 尚未执行真实集群压测，不引用参考20Pod成绩 |

## 3. pi并不是缺文件，而是还有运行细节需要补

ZIP里的 `agents.ts` 创建真实pi Agent，`server.ts` 用Promise.race限制接口等待。检查发现该等待超时没有调用Agent.abort，底层模型工作可能继续；返回值累计全部text_delta，也不严格区分工具使用前的说明和最终消息；JSON解析存在从混合文本中截取括号的宽松路径。

新增 `services/pi-agent-overlay/`：构建时复制原pi工程，保留上游agents为agents.upstream.ts，再替换构建副本中的运行适配。三项变化是：（1）把请求预算传入执行器并在超时调用abort；（2）从最后一个assistant消息提取文字，不累计中间文本；（3）JSON只接受单个对象/数组，可去代码围栏，但不接受前后夹杂或多个JSON对象。

`contract.mjs`使用真实pi包和可控的测试stream检查运行/中止/输出合同。该测试不是大模型质量验收，也不能消除原V4真实pi端到端验收未完成这一状态。客户端abort也不承诺供应商一定停止计费。

可选本机构建：

```bash
python services/pi-agent-overlay/prepare.py /tmp/jinshu-pi-v6
cd /tmp/jinshu-pi-v6
npm ci
npm run build
node contract.mjs
```

Compose叠加方式（先按V4手册生成.env、配置内部token和私有模型）：

```bash
docker compose --env-file deploy/compose/.env \
  -f deploy/compose/stack.yml -f deploy/compose/pi-v6.yml \
  --profile local-models --profile pi up -d --build
```

PI_AGENT_ENABLED仍需显式开启；未开启不应宣称pi参与答案。Dockerfile为可选部署配方，类型编译和真实包合同测试与真实模型端到端验收分开报告。

## 4. 与材料表述的明确差异

材料的“向量已入库，所以模型整体不可用仍可向量查询”缺少新查询编码这个条件；金枢在查询Embedding不可用时回BM25，不把hash当同空间替代。材料把重排放在正文回填之前；金枢先回事实源确认可读有效正文，再进入可能外部的重排器。材料中的1086份文档、1200题和93.1%是参考叙述，不属于当前项目的实测结果。

## 5. 产品岗如何体现深度

不写“搭了一个聊天网页”就结束，而是说明：为什么把检索与计算拆开、如何决定引用权威性、哪些节点需要确认、失败时保留什么价值、如何证明反馈改变下一轮、如何划分功能验收与真实业务效果。PRD负责把这些决策变成可验收要求；架构和技术术语作为支撑，不应替代产品问题本身。

原文参考：用户Pasted markdown(2).md第96—101行（架构）、229—235行（版本与补偿）、350—358行（Memory）、390—430行（Loop）。pi API参考固定版本：https://github.com/earendil-works/pi-mono/blob/v0.84.2/packages/agent/src/agent.ts 。
