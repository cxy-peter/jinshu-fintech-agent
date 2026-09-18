# 金枢｜金融产品中后台自进化 Agent

可信 RAG、可执行理财 Python Skill、五层 Memory、反馈 Loop；保留离线展示，并增加私有模型与数据库运行模式。

个人 AI 辅助改造作品，来源于实习场景与用户提供的参考工程；不是两家实习公司共同上线的系统，也不是学校委托项目。原工程署名及目录保留。

## V4 当前状态（2026-09-18）

**真实服务子链路已执行，完整验收尚未通过。** [查看实际运行](https://github.com/cxy-peter/jinshu-fintech-agent/actions/runs/35383830099)。

- MongoDB、Redis、Milvus 实际容器与客户端接通；8 份模拟 PDF、34 个服务模式切片实际向量化并写入 Milvus。
- Qwen2.5-0.5B-Instruct 实际生成；bge-small-zh-v1.5 生成512维语义向量；bge-reranker-base 在实际 DAG 中重排。
- 已验证 Mongo/Redis 跨 Runtime 读写、Redis Stream 消费确认、共享停候选标记。两 Runtime 不等于两个 Kubernetes Pod。
- 小模型校验未通过时，最终输出为 verification_blocked；实际调用模型不代表答案正确。
- 完整 CI 随后因 `scripts.evaluate_v4` 导入与上游同名包冲突而失败。24题评测、最终 pi 验收、后续容器回归阶段没有完成。最后一次上传评测脚本修补被工具拦截，仓库仍保留真实失败状态；下载交付包中的本地修补也尚未完成全量服务复测。
- K8s/HPA/k6 清单已提供，未执行集群扩缩容压测。真实参与者为0；试点表单不等于用户试点已经完成。

详见 [V4部署、材料、评测与边界](docs/V4_GUIDE.md) 和 [原始执行证据](evidence/v4/live_acceptance.json)。V3手册为旧版基线，当前状态以本节和V4指南为准。

## 两种运行方式

离线展示（无需模型密钥）：

```bash
python -m venv .venv
# 激活虚拟环境后：
pip install -r requirements.txt
python -m jinshu.mock_pdfs
python -m jinshu serve --port 8766
```

浏览器打开 `http://127.0.0.1:8766`。演示账户 `editor / demo-editor`、`reviewer / demo-reviewer`；普通用户 analyst、risk、operations、service 的密码为 `demo-用户名`。演示账号仅本机使用。

私有服务器（Docker Engine + Compose；真实本地模型）：

```bash
python scripts/init_deployment.py
docker compose --env-file deploy/compose/.env -f deploy/compose/stack.yml --profile local-models up -d --build
```

服务模式不自动创建公开演示账户。用户创建、PDF审核和模型配置见V4指南。首次拉镜像和模型需要网络；不把单机Compose称为高可用集群。

## 业务与核心结构

11个工作流入口：产品对标、发行排期、周报质检、材料生成、开户时点、案件核查、策略预检、模拟三表、客服、基金/FOF研究资料、金融基础学习。后两个需要导入相应资料，不会凭空得到知识。

```text
身份与资料范围 → MemoryContextBuilder
→ Intent → Rewrite → Retrieval → Answer → Verify → Trace/反馈
                     ↓
            BM25 + 语义向量 → RRF → 回查Mongo → Reranker
反馈 → Observe → Reflect → Adapt → 配对回放 → 审核 → 灰度 → 扩量/回滚
```

`engine/` 保留原后端、Next.js和pi服务；`jinshu/` 是金融适配；`services/model-gateway/` 是真实权重网关；`deploy/compose/` 是私有化配置；`deploy/k8s/` 和 `loadtest/` 是待执行容量测试工具。

![原DAG与工作流](diagrams/01_architecture.svg)
![反馈Loop](diagrams/03_loop.svg)

## 资料与发布范围

上传 → 本地解析/敏感性提示 → 待审 → 独立复核 → 索引 → 发布有效版本。文档及查询向量必须同模型同空间；真实模式失败回BM25，不静默换hash。

新金融资料在私有包完成92份输入、90份去重解析、3,859页、19,032切片，尚待审核和语义向量化。原文和切片不进入公共仓库。研报、2022学习笔记、内部制度、模拟材料分开来源类别，历史资料不是现行政策。

原ZIP231文件中，公开engine保留218个，216个逐字节一致；2个是V3已声明补丁。13份原校内资料或设计图未公开。V4不修改engine。字体、模型权重、公司截图、私人语料、密钥均不随代码发布。

## 验证与阅读

```bash
python -m pytest -q
python scripts/evaluate_v4.py --profile services
```

本地离线回归记录为126通过、2跳过；不能与失败CI的跳过阶段混为一谈。评测输出必须实际运行后读取，不能沿用原说明中的93.1%、1,200题或20Pod吞吐。

- [V4综合指南](docs/V4_GUIDE.md)
- [真实服务执行结果（包含失败）](evidence/v4/live_acceptance.json)
- [V3产品手册（历史）](docs/PRODUCT_MANUAL.md)
- [V3面试问答（历史）](docs/INTERVIEW_MANUAL.md)
- [原工程来源说明](docs/SOURCE_REVIEW.md)

GitHub保存源码并可运行临时CI；GitHub Pages不能承载FastAPI、数据库或模型服务。持续运行应放在自己的服务器。当前无生产上线、真人试点或全量金融质量保证。
