# 金枢｜金融产品中后台智能助手

把**金融资料问答、理财工具、发行支持和反馈复盘**放进同一个工作台。基于既有 Agent 参考工程与 Python 方法的个人 AI 辅助改造项目，不是实习公司的正式上线系统，也不是学校委托项目。

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fcxy-peter%2Fjinshu-fintech-agent%2Ftree%2Fmain%2Flite&project-name=jinshu-workbench&repository-name=jinshu-workbench)

**先体验主要功能，再按需要部署完整服务。** 上面的按钮复制 `lite` 子目录并进入 Vercel 建项目流程；需要登录并确认，完成后使用平台返回的网址。要持续跟随本仓库更新，在 Vercel Import 本仓库并把 **Root Directory 设为 `lite`**。当前没有自动创建 Vercel 线上项目，不提供猜测的 `vercel.app` 地址。

[部署与操作](docs/V5_GUIDE.md) · [产品方案与验收](docs/PRODUCT_SPEC_V5.md) · [产品面试问答](docs/V5_INTERVIEW.md) · [实际浏览器验收](https://github.com/cxy-peter/jinshu-fintech-agent/actions/runs/35392921379)

## 可以做什么

| 功能 | 可操作内容 |
|---|---|
| 金融学习与自动路由 | 56个原创学习主题、11类任务入口；中文分词、术语扩展、来源展示和短追问 |
| 文档上传与查阅 | PDF / DOCX / TXT / MD / CSV / JSON / JSONL / 切片ZIP；页码、切片、启停、全文查看 |
| 理财与发行工具 | 产品对标、发行排期、周报质检、材料生成；实际计算并导出CSV / JSON / Word |
| 风险与运营辅助 | 开户字段时点、案件邮件匹配、禁用策略候选、模拟三表核对；不执行真实资金或账户操作 |
| 执行与反馈 | Trace、记忆视图、反馈分类、受限候选、历史检索回放、本地启用和回滚 |
| 评测与体验记录 | 16题开发回归、真实浏览器测试；体验表单默认标记测试数据 |

默认网页使用**词项检索与原文整理**，不需要模型密钥，也不把它说成语义Embedding或LLM生成。上传资料和反馈存在访问者自己的IndexedDB，不进入公共知识库。可选模型接口须由部署者配置，并由访问者确认发送当前问题及片段。

## 一次部署

Vercel设置：**Root `lite` / Framework `Other` / Build `npm run build` / Output `dist` / Node 22**。不需要为默认模式配置数据库或模型。

本机运行：

```bash
cd lite
npm ci
npm run build
python -m http.server 8795 --directory dist
# 浏览器：http://localhost:8795
```

完整服务仍在仓库根目录，保留原工程：

```bash
python scripts/init_deployment.py
docker compose --env-file deploy/compose/.env -f deploy/compose/stack.yml --profile local-models up -d --build
```

账户创建、资料审核和私有模型见 [V4部署指南](docs/V4_GUIDE.md)。单机Compose不等于高可用。

## 工作流与反馈闭环

点击小图查看原尺寸；下图是完整工程结构，网页使用可操作的简化实现。

<a href="diagrams/01_architecture.svg"><img src="diagrams/01_architecture.svg" width="430" alt="完整工程的固定DAG、事实检索与业务工作流"></a>
<a href="diagrams/03_loop.svg"><img src="diagrams/03_loop.svg" width="430" alt="反馈、候选、回放、灰度与回滚"></a>

```text
任务 → 路由 → 改写 → 检索 / 工具 → 答案与来源 → 校验 → Trace
反馈 → 失败归因 → 受限候选 → 历史回放 → 确认 → 生效 / 回滚
```

自进化改变查询词、top-k及模板等执行策略，不自动训练模型，不改财务公式，不擅自批准真实风险处置。

## 实际验证范围

**V5轻量路径已通过实际执行：38条程序测试；Chromium问答、上传、刷新保留、PDF/Word解析、115页模拟导入、8类工具、Word导出、反馈回放启用及回滚、移动端布局。** [查看JSON](evidence/v5/browser-results.json)。16题是自编开发回归，不能当成独立金融准确率；真实用户为0。

<details>
<summary>V4完整服务的历史状态与原工程保留范围</summary>

V4实际接通过Mongo/Redis/Milvus，8份模拟PDF形成34个服务切片并向量入库；Qwen2.5-0.5B、BGE512与Reranker有实际调用记录。完整CI随后因评测脚本包冲突失败，pi最终验收与24题评测没有完成，生成候选也曾被Verifier阻止。V5提供显式导入修补入口 `scripts/run_live_acceptance_v5.py`，但没有重新宣称完整服务全部通过。[历史原始证据](evidence/v4/live_acceptance.json)

K8s/HPA/k6是待执行的容量工具，不是已完成20Pod压测。用户私有90份资料/19032片的预处理结果不随公共网页发布。公开engine保留原ZIP中的218个文件，216个字节一致，另外2个是已声明的V3补丁；V5没有修改engine。原署名和目录保留。

</details>

## 目录

`lite/` 可部署网页；`jinshu/` 金融适配；`engine/` 原参考工程；`services/model-gateway/` 私有模型接口；`deploy/` Compose及K8s；`docs/` 产品与技术文档；`evidence/` 实际执行结果。

用户原始PDF、公司截图、私人切片、密钥、字体文件及模型权重不进入公共网页包。网页里的金融内容用于资料学习与模拟，历史笔记不是现行政策或投资建议。
