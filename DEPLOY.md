# 金枢：一个仓库，手动选择发布

**唯一维护与发布源：`cxy-peter/jinshu-fintech-agent` 的 `main`。**
`jinshu-workbench` 是此前的私有发布镜像，保留作为旧版本备份，不再作为新版本发布来源。此次没有删除或公开它，也没有复制私有资料到公开仓库。Vercel 的**项目名称**仍可叫 `jinshu-workbench`：项目名称和 GitHub 代码仓库不是一回事。

## 方式 A：GitHub 页面点 Run workflow（推荐）

[打开 Manual Vercel Deploy](https://github.com/cxy-peter/jinshu-fintech-agent/actions/workflows/manual-vercel-deploy.yml)

第一次先在 Vercel 选定一个你有权限的项目。建议复用现有 `jinshu-workbench`，保留域名和服务器环境变量，不再建第二套工作台。

在主仓库 **Settings → Secrets and variables → Actions → New repository secret** 配置三个值：

| 名称 | 在哪里取得 | 用途 |
|---|---|---|
| `VERCEL_TOKEN` | Vercel 账号 Tokens，令牌要有目标团队权限 | 工作流发布授权，不是 DeepSeek key |
| `VERCEL_ORG_ID` | 目标 Vercel 团队 ID，或本地 `vercel link` 生成的 `.vercel/project.json` 的 `orgId` | 指定团队 |
| `VERCEL_PROJECT_ID` | 目标项目 Settings 的 Project ID，或上述文件的 `projectId` | 指定项目 |

不要把这些值贴到聊天、README、工作流明文或提交到 Git。

配置后打开 Actions → **Manual Vercel Deploy → Run workflow**：

- Branch 选 **main**。
- `target=preview`：生成预览版，不覆盖现有正式域名；首次建议用这个。
- `target=production`：会替换所选项目的正式版本，必须在 `confirmation` 中输入 **DEPLOY PRODUCTION**。先验收预览再使用。

工作流先测试当前精确提交，再复制完整运行代码，读取所选环境的 Vercel 配置，执行 `vercel build` 和 `vercel deploy --prebuilt`。成功后部署链接在该次运行的 Summary；失败时打开失败步骤看原始错误。不要把“工作流启动”当成“发布成功”。本次新增入口没有真实云端发布验收，也没有调用真实 DeepSeek。

本仓库 `vercel.json` 已设置 `git.deploymentEnabled=false`：普通 push/merge 不会自动替换线上版本。手动 CLI/工作流才发版。以后需要自动发布，可明确改回 true，不必维护第二个仓库。

## 方式 B：你自己的电脑手动发布（不需要 GitHub Actions secrets）

先安装 **Node.js 22 或更高版本**，并在终端用 `npx vercel login` 登录你自己的 Vercel 账号。源码中不包含令牌。

Windows 直接双击根目录 **`deploy_vercel.bat`**；macOS/Linux 执行 **`bash deploy_vercel.sh`**。**默认直接发布 Preview，不再要求输入 `DEPLOY PREVIEW`。** 第一次运行才会让你选择已有 Vercel 项目，之后复用本地 `.vercel/project.json`，不再重复 link。正式版从终端运行 `deploy_vercel.bat production`（macOS/Linux 为 `bash deploy_vercel.sh production`），并且只有正式版要求输入 `DEPLOY PRODUCTION`。

手工等价入口：

```bash
node scripts/manual_deploy.mjs preview   # Preview 无二次确认
# 正式版：要求交互输入 DEPLOY PRODUCTION
node scripts/manual_deploy.mjs production
```

这条路在 Vercel 云端构建，不要求本机安装 Python 或数据库。若还要在本地运行完整工作台，才使用 Python 3.12 的 `start_local.bat` / `start_local.sh`。

部署脚本只打包 `index.py`、Python 配置、`unified`、`jinshu`、`engine/backend/app` 和合成示例，不上传根目录 `.env`、私有文档库、工作目录或本地模型。它从所选 Vercel 项目取服务器配置，不把你的本地 `.env` 自动同步到云端。运行源代码中不得硬编码密钥；过滤不是秘密扫描的替代。

部署前脚本会先执行 Vercel 的项目检查和 `vercel deploy --dry`；配置错误会在真正上传前停止。`vercel.json` 不再使用超长 `excludeFiles`，因为部署目录本身已经是 allowlist 打包。Windows 调用也不再使用 Node 的 `shell:true`，避免之前的 DEP0190 警告。Windows `.bat` 仍只做自动化入口检查，未在本会话执行真实云端发布。

## 项目设置：避免沿用旧网页项目的配置

在 Vercel 中检查目标项目（不能只改 GitHub 仓库名称）：

| 设置 | 统一版使用的值 |
|---|---|
| Git 仓库（使用 Git 关联时） | `cxy-peter/jinshu-fintech-agent` |
| Production Branch | `main` |
| Root Directory | 仓库根目录，留空或 `./`，不是 `lite` / `engine/frontend` |
| Framework Preset | FastAPI |
| Build Command | `python scripts/build_unified.py`（由 vercel.json 提供） |
| Install Command | 关闭旧自定义覆盖，使用 Python 项目自动安装 |
| Output Directory | 关闭旧自定义覆盖，不填 `public` / `dist` / `.next` |
| Python | 3.12，由 `.python-version` 与 pyproject.toml 指定 |

使用现有 Vercel 项目时，在 **Settings → Git** 将旧 `jinshu-workbench` 仓库关联改成主仓库。此操作需要你对该项目的权限。本次没有改掉远端项目的 Git 绑定，也没有切换线上域名。CLI/本工作流不要求 Git 自动部署，但改变旧关联可以避免以后误点旧镜像的 Redeploy。

也可从 [Vercel New Project](https://vercel.com/new) → Import Git Repository 选现有主仓库；这是新建 Vercel 项目，不要求创建新的 GitHub 仓库。常见的 `/new/clone` Deploy Button 会克隆仓库，不适合本次“只保留一个维护源”的目的。

## DeepSeek 和真正可用的区别

在 Vercel 项目的 **Environment Variables** 中配置 `unified/environment.example` 列出的服务端变量，分别设置 Preview 和 Production。DeepSeek 使用 `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` 等；旧 `CHAT_*` 必须为完整的一组，不能混用。

完整工作台还需要 `AUTH_SECRET`、MongoDB、Redis、Milvus、Embedding 和 Reranker。**只填 DeepSeek key 可以完成部分配置，但不保证登录和完整 RAG 能工作。**没有密钥也能构建设置页，不等于服务已配置。

发布后分别核验：首页、`/api/status`、首次账号、真实服务连接、经同意的模型连接测试、公共/合成资料上传与独立审核、带来源问答和工具任务。正式数据需先获得授权。不要把真实机构资料放到公开仓库。

## 关于 private 和原来的失败

Vercel 支持私有 Git 仓库，但对账号权限、提交者身份、Hobby/Pro 及组织仓库有条件要求。此前镜像由 GitHub Actions bot 提交，这属于需要排查的因素，不是已确认根因。

本会话读取旧 Vercel 团队仍返回403，所以没有取得原始构建报错；403是当前连接的读取权限问题，不能直接证明构建为何失败。手动发布需要你自己的有效权限，不能绕过目标团队的授权。

官方参考：
- https://vercel.com/docs/git
- https://vercel.com/docs/deployments/troubleshoot-project-collaboration
- https://vercel.com/docs/cli/deploy
- https://vercel.com/docs/project-configuration/git-configuration
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
