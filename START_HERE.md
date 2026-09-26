# 金枢 V8.1：线上与本地使用同一个完整入口

## 启动完整工作台

需要 Python 3.12。Windows 双击 `start_local.bat`；macOS/Linux 运行 `bash start_local.sh`。二者都运行 `python -m uvicorn index:app --host 127.0.0.1 --port 8766`，不是旧版 `python -m jinshu serve`。打开 http://127.0.0.1:8766 。

启动脚本会建立虚拟环境、安装 requirements.txt，并在根目录有 `.env` 时通过 Uvicorn 加载它。没有配置仍能打开设置页，但不能登录、问答或访问业务数据；不会偷偷退回模拟数据。已有虚拟环境不是 Python 3.12 时，请另建合适环境，脚本不会擅自删除你的环境。

## 本地和 Vercel 配置

以 `unified/environment.example` 为模板：本地复制为根目录 `.env`（已被 Git 忽略），Vercel 则在项目的 Preview / Production 环境变量中分别设置，不把 `.env` 上传。

对话模型支持 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`（默认 `deepseek-flash`）和官方 `DEEPSEEK_BASE_URL`；旧的完整 `CHAT_BASE_URL/CHAT_API_KEY/CHAT_MODEL` 组合仍兼容，不能混用凭据。不要把真实 API key 写进聊天、代码或文档。

完整运行还需要 MongoDB、Redis、Milvus，以及独立的 Embedding / Reranker 配置；仅一个 DeepSeek key 不等于整个 RAG 服务可用。页面会展示缺少的配置名称，不展示密钥。先核验公共/合成资料，不上传未获授权的机构资料。

首次账号通过服务配置页说明的 `/api/setup/user` 一次性授权创建。建立编辑与独立复核账号后移除 `JINSHU_BOOTSTRAP_TOKEN`。完整服务没有默认演示账号。模型连接测试需管理员明确同意；状态区的“已配置”不等于“实际调用成功”。

## Vercel 发布状态

部署入口为 `index.py → unified.app → jinshu.runtime.Runtime`，Python 3.12，FastAPI 框架。必须使用包含 pyproject.toml、.vercelignore、完整 engine/backend、jinshu 和 unified 的版本。

V8.1 已进入发布预览分支；截至本次交接，新预览部署失败，构建错误日志因目标团队授权不足未能读取。**尚未替换原生产站，也未验证真实 DeepSeek 调用**。最终状态以 GitHub PR 与 Vercel 部署记录为准，不把本文当作实时运行状态。

## 历史离线回归保留，但不是默认启动

`python -m jinshu serve --profile offline --port 8767` 专门用于原始离线回归与确定性夹具；它使用旧入口、合成数据和测试账号，不是完整服务，不调用真实 DeepSeek。旧 V7 浏览器实现与证据保留在 `lite/` 及相应历史文档，不作为本次线上版替代品。

资料问答、八类业务工具、独立资料审核、版本化任务/导出、Memory、Trace、反馈与受限迭代仍在完整后端；本项目不执行真实资金、账户或策略平台处置。
