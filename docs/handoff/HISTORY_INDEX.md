# 金枢及关联项目｜历史版本与文件索引

**索引时间：2026-11-06。** 优先级：**当前 GitHub main / 当前站点 > V11 验收文档 > 升级前归档 > 旧简历或课程参考稿**。仅保留可稳定定位的公开仓库地址和精确历史路径，不将原私人交付 ZIP 的内部路径误当成 GitHub 文件。

## A. 当前版本与交付

| 资源 | GitHub/地址 | 用途 |
|---|---|---|
| 主仓库 | [cxy-peter/jinshu-fintech-agent](https://github.com/cxy-peter/jinshu-fintech-agent) | 最新源码；`main` 会随以后改动更新 |
| 在线工作台 | https://jinshu-workbench.vercel.app/ | V11 于2026-11-06完成生产发布；后续需重新核对 |
| V11 PR | [#13](https://github.com/cxy-peter/jinshu-fintech-agent/pull/13) | 改动和合并历史 |
| V11 应用 SHA | [fe3eb326](https://github.com/cxy-peter/jinshu-fintech-agent/commit/fe3eb3261cd7feda9dc2e5c55b52e622009041ab) | 定位实际 V11 上线应用源，区别后续 docs-only 提交 |
| 架构说明 | [docs/V11_UPGRADE.md](../V11_UPGRADE.md) | 文枢/差旅机制融合及准确边界 |
| 发布记录 | [docs/V11_RELEASE.md](../V11_RELEASE.md) | CI、Vercel、真实 DeepSeek 冒烟、未验收项 |
| 简历项目文字 | [docs/RESUME_PROJECT.md](../RESUME_PROJECT.md) | 单项目版四条/三条，保留真实责任边界 |
| 面试 20 问 | [docs/INTERVIEW_MANUAL.md](../INTERVIEW_MANUAL.md) | 60秒中英介绍、技术追问、实战演示 |
| 部署说明 | [DEPLOY.md](../../DEPLOY.md) | 当前统一入口、环境变量与测试步骤 |
| CI 原始记录 | [Actions 42166970120](https://github.com/cxy-peter/jinshu-fintech-agent/actions/runs/42166970120) | Python/Node/浏览器验收；数字不可当模型准确率 |
| 旧文档目录 | [docs/history/README.md](../history/README.md) | 清理的22份过时说明及2份补丁完整列表 |

## B. 恢复点与旧版本

**完整升级前快照：** [archive/pre-v11-20261105](https://github.com/cxy-peter/jinshu-fintech-agent/tree/archive/pre-v11-20261105)，原应用主线为 `44321c6`。此分支保存旧源码、旧文档路径和历史实验；数据库与真实运行版本须分开考虑。

- **V10 / V9：** 归档中 `README.md`、`docs/README_V9_ARCHIVE.md`、`docs/CORE_V9_AUDIT.md`、`docs/CORE_V9_ACCEPTANCE_NOTES.md`。
- **V8：** `docs/UNIFIED_V8.md`、`docs/UNIFIED_V8_RELEASE.md`。旧版曾涉及 FastAPI + Mongo / Redis / Milvus 的完整服务联调，**不表示它们都在 V11 默认网页调用**。
- **V7：** `docs/V7_ARCHITECTURE.md`、`docs/V7_ACCEPTANCE.md`、`docs/V7_RELEASE.md`、`docs/V7_PRODUCTION.md`、`docs/V7_RESUME_PUBLIC.md`、`docs/V7_READABLE_GUIDE.md`；旧网页位于 `lite/`。
- **V6：** `docs/V6_README_ARCHIVE.md`、`docs/V6_RESUME_PRODUCT.md`、`docs/V6_SOURCE_ALIGNMENT.md`、`docs/V6_ACCEPTANCE_AND_PRODUCT.md`。
- **V5 / V4：** `docs/V5_GUIDE.md`、`docs/V5_INTERVIEW.md`、`docs/V5_1_READING.md`、`docs/V4_GUIDE.md` 等。
- **旧临时补丁：** `patches/01_mongodb.patch`、`patches/02_orchestrator.patch`，当前 main 删除但归档分支保留。旧版文档已整理，未改变 Git 历史。

## C. 关联工程及内容边界

| 资源 | 地址或索引 | 可参考的内容 | 不能照搬的内容 |
|---|---|---|---|
| 文枢参考 Agent | 当前聊天中此前提供过其长篇技术/面试参考资料；当次来源原件另有附件 | Harness、可信 RAG、Memory、反馈 Loop 的总体设计 | 参考稿中 1,086 份文档、1,200 题、93.1%、20 Pod 等数据，以及虚构学校合作或两人/三人分工 |
| 差旅助手 V2 | [用户此前提供的参考介绍](https://t.zsxq.com/QvkcT)；课程 Feishu/百度/夸克链接在原聊天 | 输入门控、按依赖批次、持久检查点、请求防重、规则校验 | 课程源码、500题/91%/86%/13.4秒等未经当前金枢验证的成绩 |
| 理财产品业务脚本 | [Intern-Python4WealthProduct](https://github.com/cxy-peter/Intern-Python4WealthProduct) | `数据月报.ipynb`；`业绩比较-五只产品对比+市场业绩对标.ipynb`；`文本转二维码+产品发行排期日期要素+按照模板批量生成文件并修改word内容.ipynb`；`产品发行书excel参数转word固定位置材料文字替换.ipynb` | 企业内部文件、用户数据、模板、敏感路径 |
| Visit China AI | [visit-china-ai-agent](https://github.com/cxy-peter/visit-china-ai-agent) | 入境服务交互、运营评测、标准知识库、反馈与约束改写 | 5,000 URL、旅游场景 12,000 问题/175条召回等不属于金枢 |
| Graph/Harness/Loop 讨论 | 历史聊天及当前 `V11_FULL_CONTEXT.md`；如需要重新研究请核对现有代码 | DAG 组织本次任务，Loop 优化后续执行，Graph 不等于知识图谱 | 未实现的 LangGraph/ADK/K8s 能力 |

文枢与差旅的原课程压缩包**没有上传此公开仓库**；如用户新对话要求审查课程原代码，需要其主动提供可读取的授权附件。此前总结明确：参考 RAR 未完成逐行审计。

## D. 旧简历、私人附件与原 ZIP 的索引（不在 public GitHub 中）

上一轮私有交付中有：
- 金枢 V11 单项目一页简历 PDF、DOCX；
- 同项目 LaTeX 可替换片段；
- 六页架构交接＋20问面试手册 PDF、DOCX；
- V11 已验收源码 ZIP、CI 证据与合成导出；
- V11 完整续聊 Prompt、超短 Prompt、历史索引；
- 旧版 V8 交接、V7/V8 评测、金枢/Visit China 双项目与产品运营简历稿。

**这些文件仍属于之前的聊天附件或本地备份，不存在本 GitHub 当前目录。** 本仓库已经有可公开的项目简历文字 [RESUME_PROJECT.md](../RESUME_PROJECT.md) 和 [INTERVIEW_MANUAL.md](../INTERVIEW_MANUAL.md) 供无附件续聊；要实际修改完整姓名、联系方式和照片的简历，请在新聊天中上传私有 PDF/DOCX。

## E. 使用流程与核对顺序

1. 新聊天先发 [NEW_CHAT_PROMPT.md](NEW_CHAT_PROMPT.md) 的文字，注明 GitHub 可直接阅读。
2. 读取 [V11_FULL_CONTEXT.md](V11_FULL_CONTEXT.md) 定位项目真实能力与未验收边界。
3. 具体改源码前确认当前 `main` SHA、对应 `docs/V11_RELEASE.md`、发布 SHA、实际服务状态、最新单元/浏览器回归。
4. 回退或复盘时用精确 Git SHA 和归档分支，不要直接用历史 ZIP 覆盖更新代码，也不要删除数据库。
5. 简历和面试引用必须精确到哪次运行、哪个数据集和自己实际贡献。不存在证据的数据留空或写作计划。
