# 从这里开始：金枢 V11

> **跨对话接续：** [新对话交接导航（无需 ZIP）](docs/handoff/README.md) · [完整交接](docs/handoff/V11_FULL_CONTEXT.md) · [一段可复制的续聊 Prompt](docs/handoff/NEW_CHAT_PROMPT.md) · [历史索引](docs/handoff/HISTORY_INDEX.md)


当前入口只有 `index.py → core.app`。线上与本地使用同一代码；不要用企业参考Runtime或旧静态页面替代当前验收。

先读 [README](README.md)，再看 [部署说明](DEPLOY.md) 和 [V11改造与边界](docs/V11_UPGRADE.md)。

演示新增能力：页面底部登录编辑账号 → “可恢复业务流程” → “周报质检＋同业对标” → 填入合成示例 → 保存输入 → 逐批执行 → 刷新恢复 → 切换独立审核账号 → 打开待审任务 → 核对并导出。仅使用脱敏示例，不执行真实金融操作。

现有资料审核、引用问答、Memory与反馈Loop保留。无模型密钥时仍可计算；共享资料和可恢复任务需要持久化服务。不要把“配置存在”当服务可达或模型效果合格。

本地：Python3.12/3.13，安全加载服务端配置后运行 `uvicorn index:app --host 127.0.0.1 --port 8000`，或沿用原启动脚本。Windows/macOS启动脚本保留，不删除本机`.env`或`.vercel/project.json`。

[简历项目片段](docs/RESUME_PROJECT.md) · [面试准备](docs/INTERVIEW_MANUAL.md) · [历史快照](docs/history/README.md)
