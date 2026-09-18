# 金枢｜金融产品中后台自进化 Agent

**可信知识、可执行 Python Skill、分层 Memory 与反馈自进化。**

金枢是基于既有理财产品自动化方法、客服/核查需求及用户提供的行政助手工程进行的 **AI 辅助个人改造原型**。统一场景是：中后台人员收到问题或材料任务，找对资料、执行已有工具、交付可核对结果，并让失败进入可回放的迭代闭环。

它不是 Bitget 与施罗德交银共同上线的系统，也没有虚构学校/企业委托。所有业务数据、政策与日历均为模拟。

## 快速运行

Python 3.11+；本次本地验收使用 Python 3.13.5。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m jinshu.mock_pdfs
.venv\Scripts\python.exe -m jinshu serve --port 8766
```

macOS/Linux 激活虚拟环境后使用 `python -m ...`。打开 `http://127.0.0.1:8766`；也可运行 `start_local.bat` / `start_local.sh`。默认只监听本机。

演示用户 `editor / demo-editor` 上传，`reviewer / demo-reviewer` 独立审核。analyst、risk、operations、service 的示例密码为 `demo-用户名`。**公开的演示账号只能本机使用，不能直接部署公网。**

## 本轮增加的可验证链路

- **8 份实际模拟 PDF**：三大报表、理财产品、发行日历、公共FAQ、开户SOP、敏感交接案例。
- **上传者初判 → 本地检测 → 独立复核 → 索引 → 发布**：审核前不外发 Embedding，不进入共享检索。
- **33 个 PDF 切片，5 个表格切片**：表头、公司、年度、单位、合并口径和物理页码保留；6 个固定 PDF 检索问题命中来源。这不是模型准确率。
- **9 类业务工作流**：对标、排期、周报、开户时点、案件核查、策略预检、模拟三表、客服、材料生成。四个理财入口明确绑定 Python 函数和 Schema。
- **原 Loop 继续执行**：20 条配对回放、5% 灰度、20% 扩量、合成故障自动回滚；下一轮 top-k 确实从 2→8→2，财务工具结果不变。
- **回滚接口失败仍先停候选**：本机持久化冻结，状态 `local_baseline_remote_unconfirmed`，下一轮只用稳定基线；重启仍保持冻结。
- **界面恢复原深绿/金色侧栏风格**：新增敏感审核、原生 PDF、故障中心和流程图。原 Next.js 文件继续保留，没有冒称已完整联调原前端。

## 工作流与可执行 Skill

|工作流|用途|边界|
|---|---|---|
|wealth_benchmark|同口径产品、共同净值区间的收益与回撤|不把所有产品直接排名|
|issuance|日历、频率、合同期限生成排期|草案，不自动发行|
|weekly_report|数字、主键、缺失和重复检查|不覆盖原数据|
|material_fill|产品参数生成真实 Word 草稿|不发邮件；幂等文件名|
|onboarding|字段在决策时点是否存在|不填补尚未产生的数据|
|kep|编号匹配和歧义分类|未找到不等于业务漏回|
|strategy|事件、状态、字段候选预检|disabled 候选，无生产推送|
|statements|模拟两年三表勾稽|不替代审计|
|service|有效 FAQ/SOP 和人工接续|不查询真实客户账户|

`jinshu/python_skills.py` 注册函数、输入Schema和方法来源；没有执行用户上传任意 Python 的入口。Skill动作与财务计算分开，Loop不能改账本、密级、真实风控处置或付款。

## 可信 PDF / RAG

```text
原生 PDF → 本地解析与敏感性提示 → 隔离切片
→ 独立审核等级/部门/外发许可
→ BM25 + 获准向量化 → 索引就绪 → 有效版本切换
→ 召回候选 → 回查权威源/权限/版本 → 回答或原文 → Verify
```

![PDF审核与索引](diagrams/02_document.svg)

点击“资料与切片 → 导入8份模拟PDF（待审核）”，换 `reviewer` 审核后发布。待审、旧版、超出当前用户可读级别或部门范围的资料不能进答案。自动检测仅为规则提示，有误报漏报可能；不将其称为DLP或合规认证。

默认仍为原内存存储、hash向量、BM25/RRF及规则/原文回退。**hash不是语义Embedding。**真实Milvus/Embedding/模型Reranker/pi接口保留，尚无真实服务联调和模型效果结果。生成及模型外发默认关闭，受请求许可与资料许可共同约束。

## 自进化与回滚

```text
Execute → Observe → Reflect → Adapt → 配对Replay
→ 审核 → 稳定哈希Canary → Monitor → 扩量 / Rollback
```

![Loop及控制故障](diagrams/03_loop.svg)

这轮调用原 `LoopEngine.run_cycle`、原SkillMiner与原Harness；不是用待办清单替代Loop。离线实验反馈、流量与故障为合成，验证的是“下一轮行为真的改变”，不声称真实用户效果提升。

回滚先持久化本机停止候选标志，再请求远端控制。失败返回 `local_baseline_remote_unconfirmed`，不伪造成功；稳定基线接续且重启保留冻结。它是**单机保护**，不保证全体Pod同步。整个API不可达时，需要独立网关/监管层停流，客户端不能声称已写入冻结。

权威状态库失败时暂停受保护答案，不用旧权限缓存。Milvus/查询Embedding失败回退BM25；生成失败返回原文。工单只有外部确认ID才算已提交；当前实现本地幂等草稿与可注入接口测试，未接真实Zendesk。

## 原工程保留与公开范围

完整本地包保留原231个文件，其中229个字节不变、2个已有显式补丁。原ZIP/RAR不改动。新增适配在 `jinshu/`，`engine/web` 保留原Next.js布局，`engine/services` 保留pi服务，部署文件保留。

公开仓库排除学校原始业务PDF/Word、设计原图、公司截图、视频、个人简历、真实密钥和运行库。`evidence/public_exclusions.json` 逐文件记录公开排除范围。原始校验与公开校验不要混用。保留上游作者标注，不擅自给未知许可的参考代码增加MIT等许可证；不继承原文章的用户数、准确率、压测或团队身份。

## 本轮验证

```bash
python -m pytest -q
python scripts/validate_v3.py
python scripts/verify_source.py --public  # GitHub公开包；完整本地包可不加参数
python scripts/build_diagrams.py  # 需要 Graphviz / Noto CJK
```

本地当前 **123通过、2跳过**（原测试依赖pymongo未安装）。`evidence/v3_pdf_and_failure_evidence.json` 保存8PDF与回滚故障；`evidence/loop_lab_v3.json` 保存原Loop完整实验。本轮补充PDF、材料Skill、控制故障、工单和Loop主流程验收，不扩展安全测试专项。最终复测见 `evidence/v3_validation_summary.json`。

UI检查方式见evidence/v3_ui_checks.json；不把本机界面验证当作公网部署验收。未进行真实大模型/Embedding调用、真实Mongo/Redis/Milvus服务部署、K8s/HPA压测或真实用户试点。

## 阅读地图

- [产品、结构和运行手册](docs/PRODUCT_MANUAL.md)
- [32道面试问答与29个名词](docs/INTERVIEW_MANUAL.md)
- [故障回退操作说明](docs/FAILURE_PLAYBOOK.md)
- [PDF审核与测试记录](docs/PDF_PIPELINE.md)
- [来源、保留和新增差异](docs/SOURCE_REVIEW.md)
- [简历定位与三条项目文案](docs/RESUME_POSITIONING.md)
- [六张流程图与可编辑源文件](diagrams/)

生产部署前至少补真实服务联调、数据外发审计、身份集成、跨节点停流/恢复、版本CAS、备份和独立评测。不能用本地演示代替这些验收。
