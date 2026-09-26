# 金枢 V8.1｜统一完整工作台（发布验证中）

**查得到依据，算得清结果，改得动流程。**

个人 AI 辅助工程项目，面向金融资料查询、理财对标、发行排期、周报核查和合规支持，不是机构正式上线系统。

## 手动 Deploy：以后只用这一个仓库

**维护与发布源：本仓库 `main`；不再同步到另一个私有仓库发版。** 原 `jinshu-workbench` 私有仓库保留作旧版本备份，不删除、不公开。Vercel 项目名仍可保留 `jinshu-workbench`，不影响使用本仓库代码。

[▶ 打开手动发布（GitHub Actions）](https://github.com/cxy-peter/jinshu-fintech-agent/actions/workflows/manual-vercel-deploy.yml) · [首次配置与步骤](DEPLOY.md)

点击 **Run workflow**，选 `main`，再选 `preview` 或 `production`。默认预览；正式版需输入 **DEPLOY PRODUCTION**。首次配置三个 GitHub Actions secrets：`VERCEL_TOKEN`、`VERCEL_ORG_ID`、`VERCEL_PROJECT_ID`。业务/模型密钥仍在 Vercel 服务端环境变量中设置。

也可在自己的电脑双击 **deploy_vercel.bat**（Windows）或运行 **bash deploy_vercel.sh**（macOS/Linux），用自己的 Vercel 登录手动选择项目发版。普通 Git push 的自动部署默认关闭，代码合并不等于已替换线上版本。没有创建会再次克隆仓库的 Deploy Button。

## 一个完整入口

本地启动与 Vercel 都运行 `index.py → unified.app → jinshu.runtime.Runtime(profile=services)`。前端展示和调用服务端 API，不再另跑一套浏览器 RAG 或业务计算。保留原 Harness、BM25/Milvus/RRF/重排、生成/验证、Memory、Trace、反馈与受限迭代、八类工具、资料独立审核以及版本化任务和导出。

**开始使用：[完整启动与配置](START_HERE.md)。** Windows 使用 `start_local.bat`；macOS/Linux 使用 `bash start_local.sh`。需要 Python 3.12。无配置时仅展示设置页，不启用默认测试账号，也不自动退回离线模式。

## DeepSeek 与服务边界

DeepSeek 通过服务端 `DEEPSEEK_API_KEY` 等配置接入；完整的旧 `CHAT_*` 组合仍兼容。页面区分“待配置”“配置存在”和真实调用结果；离线夹具不冒充 DeepSeek。密钥不放前端或 GitHub。

完整服务还需要 MongoDB、Redis、Milvus 和独立 Embedding / Reranker 配置；一个对话模型 key 不等于整个 RAG 已可用。真实机构资料需先获得授权。本项目不执行真实资金、账户或策略平台处置。

## 发布与验证状态

V8.1 应用已通过代码、浏览器及隔离服务验证；DeepSeek 协议用受控 HTTP 测试，不是实际模型质量验收。最新 Vercel 预览失败，目标团队的构建日志读取被403权限拒绝，根因尚未确定。原生产站尚未切换。

当前进展见 [V8.1 修复 PR](https://github.com/cxy-peter/jinshu-fintech-agent/pull/3)、[单仓库发布说明](DEPLOY.md) 和 [部署审计](docs/VERCEL_AUDIT_V81.md)。文档不是实时状态接口。

## 历史资料保留

原 V7 README 完整保留在 [历史说明](docs/README_V7_HISTORY.md)，浏览器实现仍在 `lite/`。其中旧网站、默认离线账号、运行方式和历史测试数字只适用于相应旧版本，不代表 V8.1 已部署成功。原 CLI 离线模式只用于显式选择的测试与回归。
