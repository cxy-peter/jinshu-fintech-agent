# 从这里开始：金枢 V9

本地和线上都使用 `index:app`，默认是 `core.app`，不要再使用旧 `python -m jinshu serve` 或旧 Workbench 静态网页来验收当前版本。

Windows 本地：根目录 `.env` 设置 `DEEPSEEK_API_KEY`，双击 `start_local.bat`。需要 Python 3.12 / 3.13。浏览器打开 http://127.0.0.1:8766 。无密钥仍能打开页面和计算工具。

Windows 部署：Vercel 项目环境变量设置同一个服务端变量，再双击 `deploy_vercel.bat`。需要 Node.js 22+ 和自己的 Vercel 登录；不需要本机 Python/数据库。已有 `.vercel/project.json` 会复用，不要删除。默认 Preview，正式发布仍需显式确认。

只看“页面可打开”“密钥已配置”不能证明模型可用。发布后在“服务状态与配置”勾选测试授权，再点“实际测试 DeepSeek”，核对返回模型与真实调用标记。

详细说明：[DEPLOY.md](DEPLOY.md)。当前不提供独立审批、共享历史和数据库持久化；这些能力未伪装成已上线。
