# V4｜私有服务、知识库与评测指南

## 1. 状态先读

实际 GitHub run 35383830099 已启动真实 MongoDB、Redis、Milvus 和本地权重网关，并完成8PDF/34切片向量入库、模型生成、DAG重排、跨Runtime读写和共享冻结。随后因脚本包导入冲突失败，24题评测与原pi最终验收没有完成。仓库修补写入被工具拦截，本地交付中的修补也未作全量真实服务复测。不要把子检查通过写成整套生产系统验收通过。

小模型在DAG中参与生成，但结构化验证失败时结果显示 `verification_blocked`，此前尝试保存在 `attempted_answer_mode`；真实推理不等于足够好的金融回答。

## 2. 保持原工程，切换依赖

原 `engine/backend`、`engine/web`、`engine/services/pi-agent` 不变；金融适配复用原Harness固定主流程、SkillMiner和LoopEngine。主线仍是 Intent、Rewrite、Retrieval、Answer、Verify，最多两次定向重写。Memory仍按工作、情景、用户语义、组织知识、程序策略区分，而不是全部塞入同一向量库。

离线使用内存、hash测试向量与原文，保留深绿/金色工作台。服务模式使用 PyMongo Async、Redis会话与Stream、Milvus及实际模型HTTP客户端。BM25仍是进程内索引，只补Mongo版本计数刷新，不声称已迁移OpenSearch。

默认模型：Qwen/Qwen2.5-0.5B-Instruct、BAAI/bge-small-zh-v1.5、BAAI/bge-reranker-base。CPU模型网关是串行集成基线，不用于推断生产吞吐或金融质量。三者可分别换成合适的私有服务。

## 3. 自己服务器使用Docker Compose

安装Docker Engine和Compose插件后，仓库根目录执行：

```bash
python scripts/init_deployment.py
dc() { docker compose --env-file deploy/compose/.env -f deploy/compose/stack.yml --profile local-models "$@"; }
dc up -d --build
dc run --rm manage python scripts/manage_services.py user editor --role admin
dc run --rm manage python scripts/manage_services.py user reviewer --role admin
dc run --rm manage python scripts/manage_services.py user analyst --department dept_wealth
dc run --rm manage python scripts/manage_services.py synthetic --uploader editor
```

密码隐藏输入，服务模式不使用演示口令。模拟材料先进入待审核，换reviewer在工作台确认等级/部门后发布。工程试跑可从4核、16GB内存、40GB空闲磁盘规划，这是容量规划起点而非最低配置承诺。

API只映射127.0.0.1:8766，数据库/模型无公网映射；远程访问可使用：

```bash
ssh -N -L 8766:127.0.0.1:8766 your-user@your-server
```

首次下载镜像和模型需网络，模型缓存及数据库留在服务器卷中。停机 `dc stop`，更新先备份。**不要在需保留数据的服务器运行CI清理用的 `down -v`。** 单机Compose不等于高可用。

原pi可用额外 `--profile pi` 启动；`.env` 的 PI_AGENT_ENABLED 默认false。启用后原DEEPSEEK环境变量映射到兼容私有网关，但本轮原pi路径尚未确认通过，直接模型路径已有实际调用证据。监控另启 `--profile monitoring`。

修改CHAT/EMBEDDING/RERANKER地址、名称和口令可连接已有推理平台；API兼容性需实测。向量模型、维度、查询前缀或版本改变需重建独立索引：

```bash
dc run --rm manage python scripts/manage_services.py reindex DOC_ID
```

建议固定LOCAL_*_REVISION与EMBEDDING_REVISION到实际权重版本；默认main不保证未来重复下载相同权重。外部模型模式需要scope=external、JINSHU_ALLOW_EXTERNAL=1，以及请求和资料许可；后台Loop默认不外发跨文档材料。

## 4. 新资料、chunk和可信RAG

FOF与基金产品RAR加学习笔记共有92份输入；90份唯一文档完成原生解析，共3,859页/19,032片，2份重复。私有包保留原件、manifest、chunks.jsonl及默认approved=false的审核模板。90份资料尚未进入共享检索/语义索引。

```bash
python -m jinshu.corpus /path/FOF.rar /path/基金产品.rar /path/学习笔记.pdf --out private_corpus
```

复制 approvals.template.json 为 approvals.json，真实上传者与另一位复核人审核后填写approved、密级和理由，再导入：

```bash
dc run --rm manage python scripts/manage_services.py import-reviewed --corpus /app/private_corpus --approvals /app/private_corpus/approvals.json
```

私有目录只读挂载；写入的是Mongo/Milvus。没有把真实资料自动批准。Web上传仍需另留原文件，系统保存提取内容/哈希不等于原件归档。

批量研报采用原生页块、360字符上限和45字符重叠，保留文件、哈希、页、父块和来源类型。它不是学习式语义切片；复杂表格/扫描页可能需要人工处理，没有全量OCR或声称表格已全部还原。三表模拟PDF单独使用表格感知解析。

来源分 research_reference、learning_reference、institutional_document、synthetic。2022笔记是历史学习资料，研报是机构观点；不当作当前监管规则或本单位制度。基金/FOF查询和基础学习新增两个工作流，合计11个入口。

文档审核后向量化，查询时同模型编码；BM25与Milvus召回、RRF融合、Mongo回填正文/有效版本，再Reranker和回答验证。没有模型时返回原文；索引是候选，不是事实真源。

## 5. 自进化和故障

反馈→Observe→Reflect→Adapt→配对Replay→人工审核→稳定哈希灰度→Monitor→扩量/回滚。自进化改变查询、top-k和模板，不更新模型权重，也不改财务计算、真实客户风险处置和付款。

V3合成20条回放仍是离线软件实验，不转成真实用户效果。服务版可接模型生成候选；小模型输出不满足Schema不能直接发布。

向量或查询Embedding失败→BM25；Reranker失败→RRF序；生成失败→原文；Redis工作记忆失败→单轮；Mongo事实状态不可用→暂停受保护答案。共享停候选先保留本机冻结，再写Mongo供各实例下一请求读取；远端失败保留未确认状态，已开始请求可能完成。全API不可达仍依赖外部网关停流。

文档头CAS/租约与补偿清理不是跨Mongo/Milvus的分布式ACID。`/api/ask/multi`是进程内并行子DAG和部分失败展示，不能称为所有部门已独立网络服务化。

## 6. 评测与K8s/HPA

24题在evaluation/v4/questions.json，12dev/12holdout按问题家族分离；标签是anchor草稿，需独立人工补齐相关chunk。它不是24个独立场景，更不是说明中的1,200题成绩。本轮评测脚本在完整CI中尚未运行到，可单独运行并检查结果：

```bash
dc run --rm manage python scripts/evaluate_v4.py --profile services
```

Recall@5是命中相关片数/相关片总数；Hit@5是是否至少命中；MRR@5首个相关排名倒数；nDCG@5有位置折损。生成质量还需关键点、引用支撑和人工评审，不拿ROUGE或HTTP200替代。

K8s目录提供客服Deployment、Service、HPA、Prometheus采集和Adapter映射；loadtest/jinshu-v4.js请求实际/api/ask而非健康页。配置maxReplicas=20不证明曾扩到20Pod。需要已有测试集群、镜像、Pod可达的模型/数据库和jinshu-runtime Secret；地址不能照搬Compose服务名。

```bash
kubectl create namespace jinshu
# 先配置 Secret、镜像、Prometheus/Adapter；仅用于自己的测试集群。
kubectl -n jinshu apply -f deploy/k8s/department.yaml
kubectl -n jinshu set image deployment/jinshu-service api=YOUR_REGISTRY/jinshu:YOUR_TAG
kubectl -n jinshu apply -f deploy/k8s/hpa.yaml
bash scripts/collect_hpa.sh jinshu 300 evidence/v4/hpa
BASE_URL=http://127.0.0.1:8766 TOKEN=YOUR_TEST_TOKEN VUS=2 DURATION=60s k6 run loadtest/jinshu-v4.js
```

先1用户1Pod基线再递增。容量对照固定副本与HPA，保持模型/语料/缓存条件一致，记录真实生成率、验证率、错误、P95和副本时间线。此模板针对客服只读路径，材料/工单共享文件和全局部署需另外设计。**本轮未跑真实K8s/HPA压测。**

## 7. 真人试点和GitHub

服务与试点页支持同意、任务编号、人工/Agent耗时、完成与评分、Trace关联、测试标记和撤回删除。默认测试标记勾选，不预置成功案例；当前真实参与者0。招募后让参与者做同难度任务并交叉安排顺序，独立评审复核正确性，保存失败。模拟表单提交只能证明入口能用。

GitHub保存源码；Actions可以临时启动容器执行检查，任务结束即清理；Pages只托管静态页面，不能承载FastAPI/Mongo/Milvus/LLM。长期私有化用自己的服务器；后续可接Actions和自托管Runner做交付，但本轮没有执行远程服务器部署。

## 8. 面试叙述

“我把原Agent参考工程适配为金融产品中后台助手，保留离线展示，并增加真实私有模型、Mongo/Redis/Milvus路径；完成模拟PDF实际向量入库与核心服务验证，用版本和来源治理连接理财工具与反馈Loop。完整自动验收还有脚本修补待复测，尚未做真人试点和集群压测。”

不要宣称自己训练了基础模型、独立原创全部原工程，或使用原说明的准确率/用户数。后续优先完善评测标签和模型质量，再扩大语料及并发，而不是堆更多技术栈。

官方参考：
- Docker: https://docs.docker.com/compose/how-tos/production/
- GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- Kubernetes HPA: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
