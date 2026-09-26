# 金枢 V9｜同一套本地与线上运行代码

金融中后台助手：真实 DeepSeek 对话、当前资料问答、八类确定性业务工具。

**本次目标是先可靠运行，而不是要求先搭好数据库、向量库和审批平台。** 默认入口统一为 `index.py → core.app`，本地与 Vercel 完全相同。旧 V8 企业服务模块保留，但不在默认入口中启动，也不冒充已运行的功能。

## 先运行

- Vercel：设置服务端 `DEEPSEEK_API_KEY`（Preview 与 Production 分别配置），双击根目录 `deploy_vercel.bat` 发布预览；或在 GitHub Actions 的 **Manual Vercel Deploy** 手动发布。
- 本地：Python 3.12 / 3.13，在根目录 `.env` 写入密钥，双击 `start_local.bat`。macOS/Linux 用 `bash start_local.sh`。打开 `http://127.0.0.1:8766`。
- 无密钥也能打开页面、查看配置并使用业务计算工具；模型问答会明确提示缺少配置，不输出假答案。

首次设置和部署见 [DEPLOY.md](DEPLOY.md)。密钥不能写进前端、GitHub 或聊天。公开分享前建议设置 `JINSHU_ACCESS_CODE`，并在 Vercel 设置费用限制。

## 当前确实提供什么

当前文字/Markdown/CSV/JSON → 小规模关键词检索 → 一次有预算的 DeepSeek 调用 → 引用编号检查 → 本次执行记录。

八类工具复用原 `jinshu.tools` / `unified.tools`：理财对标、发行排期、材料要素预览、周报质检、开户字段时点、案件邮件匹配、策略候选预检、三表核对。计算在服务器执行，不靠 LLM 猜数。示例必须显式选择；导出需要用户本人复核。输入更新后旧结果不再可导出。

聊天历史及本次资料只留在当前浏览器内存，刷新即清除；服务器不把它们存到共享知识库。支持 JSON / CSV 导出，不宣称有持久化、独立审批或真实业务处置。

## 当前未启用的内容

MongoDB、Redis、Milvus、Embedding、Reranker、共享资料独立审核、持久化 Memory/反馈 Loop、灰度发布及原 pi 服务，不是本次核心版的运行前提，也不在后台偷偷启用。PDF/Word 解析和 Word 成品导出暂不提供；可以复制文字进行本次问答。

原代码位于 `unified/`、`jinshu/`、`engine/`，重型依赖另存 `requirements-enterprise.txt`。旧工作流移至 `docs/legacy-workflows`，避免点错后重新发布旧网页。历史内容保留不代表 V9 验收了全部企业能力。

## 一个维护仓库

只维护 `cxy-peter/jinshu-fintech-agent/main`。原 private `jinshu-workbench` 是旧版本备份；现有 Vercel 项目仍可叫 `jinshu-workbench`，名字不影响代码运行。Git 自动发布默认关闭，源码合并不等于已替换正式网站。

## 验证

`python -m pytest` 默认只验证当前核心运行模式；`node --test tests/manual_deploy.test.mjs` 验证部署打包与启动器。

**Core V9 runtime acceptance** 在独立虚拟环境中先仅安装四个生产直接依赖，验证真实默认入口和实际发布目录，再安装测试工具，执行 API、Windows 启动器及浏览器验收。协议模拟测试明确标注，不计为真实 DeepSeek 调用。真实账户连通性要在“服务状态与配置”页点“实际测试 DeepSeek”。

详见 [本次复查与运行边界](docs/CORE_V9_AUDIT.md)。这是个人工程项目，不执行资金、账户冻结、监管报送或策略发布。
