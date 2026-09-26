# 金枢 V9 统一正式发布

2026-09-26 发布的运行代码来自 main 的 `d9bddd4a45e0633971433a491096ed14ca7d5cbd`。该版本已合并普通对话、资料问答与八类 Workbench 工具。本次不重写业务逻辑，保留 V9 的权限、输入限制、模型提示、引用校验、工具确认和旧企业模块。

## 唯一发布源与入口

- 代码仓库：`cxy-peter/jinshu-fintech-agent`。
- Vercel 项目：现有 `jinshu-workbench`，项目 ID `prj_sR3xgvfkKwtLIDEPE33a41S0Eb3f`。
- 已把 Vercel Git 关联从旧 workbench 仓库改为当前仓库；框架设为 FastAPI，构建命令为 `python scripts/build_unified.py`。
- 正式入口：https://jinshu-workbench.vercel.app/
- https://jinshu-fintech-agent-cxy-peters-projects.vercel.app/ 与 https://unified-cxy-peters-projects.vercel.app/ 已作为同一项目的生产域名，访问相同部署，后续生产发布一起更新。
- 历史项目和仓库保留，没有删除。Git 自动发布仍按 vercel.json 关闭；合并新代码后需显式正式部署。

正式部署 ID：`dpl_DATDSRnu8JoDycZaHVcovzjLc79N`。服务端配置了 DEEPSEEK_API_KEY，源码、浏览器和验收记录均不包含该密钥。

## 验收事实

1. Vercel 构建和发布均 READY；三个地址返回 V9.0.0、core 模式、模型已配置。
2. `/api/model-check` 收到真实 deepseek-flash 回复“连接成功。”，21 tokens；随后公开合成的产品对标问题返回实际模型回答，809 tokens。不是 HTTP 模拟或预设答案。
3. 发行排期、材料填充、产品对标、报表、开户、策略、周报、KEP 八类工具均在线执行合成示例成功，返回 trace 与本人复核提示；未执行真实业务操作。
4. 来源版本的 Core V9 Linux、Windows 与浏览器 CI 已通过。本机生产浏览器自动打开被权限策略拒绝，因此本次新增生产证据是实际 API 调用，不冒充生产 UI 验收。

脱敏记录：[production verification](../../evidence/v9-production/2026-09-26.json)。本次真实模型检查只证明连接与两次响应，不代表所有金融答案已做专业审查。当前历史仍仅保留在当前页面；旧企业审批和持久化 Loop 不在 core 模式中启用。
