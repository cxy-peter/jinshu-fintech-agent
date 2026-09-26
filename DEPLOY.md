# 金枢 V9：不用数据库，先把真实对话跑起来

## 你已正确关联的项目不需要再更换

代码仓库：`cxy-peter/jinshu-fintech-agent/main`。Vercel 项目可以继续是 `cxy-peters-projects/jinshu-workbench`。原 private GitHub Workbench 不参与新版本发布。

覆盖新源码时保留本机 `.vercel/project.json` 与 `.env`。发布器不会上传本地 `.env`、私人资料或模型权重。

## 必需配置只有一个模型密钥

在 Vercel 项目 **Settings → Environment Variables** 设置 `DEEPSEEK_API_KEY`，选择要使用的 Preview / Production 环境。保存后重新部署。不要把密钥发到聊天或提交到 GitHub。

默认模型 `deepseek-flash`，默认接口 `https://api.deepseek.com`；可选 `DEEPSEEK_MODEL`。在默认 `auto` 选择下，存在有效的 DeepSeek key 时优先用它，忽略旧 `CHAT_*`，不会把这个 key 拼到别的提供商接口。

不需要设置 `MONGODB_URI`、`REDIS_ADDR`、`MILVUS_URI`、Embedding 或 Reranker。旧环境变量即使残留，也不会启动这些服务。

公开分享前建议设置 `JINSHU_ACCESS_CODE`（12–200位），页面会要求输入这个访问码。访问码不是模型 API key。默认开放聊天；不设置访问码意味着其他能访问页面的人也可能消耗你的额度。单实例限流不是全局费用上限，请另设 Vercel 费用限制。

## 直接发布 Preview

Node.js 22+，终端 `npx vercel login` 登录后，在当前项目根目录双击 `deploy_vercel.bat`。macOS/Linux：`bash deploy_vercel.sh`。

已有项目关联会直接复用，不再询问 `DEPLOY PREVIEW`。日志应包含 `金枢 V9 core`；打包中有 `core/` 和少量共享工具，不再安装 NumPy/Milvus 等重型栈。Vercel 的 dry-run 只检查配置与上传文件，不代替云端安装、启动或真实模型验收。

正式版：`deploy_vercel.bat production`，再输入 `DEPLOY PRODUCTION`。先检查预览。

GitHub 手动入口仍是 **Actions → Manual Vercel Deploy → Run workflow**，选 main 和 preview。使用这条路径才需要 Actions secrets：`VERCEL_TOKEN`、`VERCEL_ORG_ID`、`VERCEL_PROJECT_ID`；模型密钥仍保存在目标 Vercel 项目环境变量里。

## 发布后只做这三项验收

1. 首页打开，页头显示 V9，而不是旧 V7/V8 页面。
2. “服务状态与配置”只列模型相关配置问题；不能再要求数据库全部就绪才能聊天。
3. 勾选一次公开测试授权，点“实际测试 DeepSeek”。检查实际响应、返回模型、`inference_verified: true`，再发送自己的问题。只有真实提供商正常响应才标为 true；HTTP 模拟端点不会。

失败信息会分别说明：密钥无效、模型不存在、余额不足、限流、网络错误、超时、空回答、截断。系统不会把固定话术当模型成功。

## 本地使用同一版本

Python 3.12 或 3.13。复制 `unified/environment.example` 为根目录 `.env`，填写密钥；双击 `start_local.bat`，或运行 `bash start_local.sh`。打开 http://127.0.0.1:8766 。Uvicorn 和 Vercel 都导入 `index:app`。

## 当前边界

核心版保留实际聊天、轻量资料检索和原八类计算工具；原企业审核/持久化/灰度 Loop 不启用。资料与历史不自动保存到服务器，不跨设备同步，刷新页面即清除。导出只是本人复核确认，不等同独立审批。只读取文本文件，不处理 PDF/Word。

此改版没有将 private 仓库公开、没有迁移机构资料、没有自动替换正式域名。真实部署及模型结果以运行日志和实际测试为准，不以历史 README 的通过数字代替。
