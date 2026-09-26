# 金枢 V10｜资料、业务工具与治理工作台

[统一工作台](https://jinshu-workbench.vercel.app/) · [恢复说明与免费配置](docs/V10_RESTORATION.md) · [V9历史边界](docs/README_V9_ARCHIVE.md)

恢复绿色 V7 工作台的学习与问答、资料与上传、业务工具、执行记录、反馈与策略、记忆工作台、回放与评测、体验记录、原理与部署。保留 V9 的真实 DeepSeek 接入、输入校验和八类业务工具补丁。

资料切片 → CPU中文语义Embedding + BM25 → RRF/重排 → 有引用的 DeepSeek 回答。共享资料需要另一账号审核；反馈定位上下文，受限 Skill 经过回放和人工审核后灰度，可回滚。

## 运行

Python3.12/3.13，`pip install -r requirements.txt`；服务端配置 `DEEPSEEK_API_KEY`。`python scripts/fetch_embedding.py` 准备固定版本模型，然后运行原 `start_local.bat` / `start_local.sh`。本地默认SQLite，无密钥仍能使用业务工具。

公开脱敏演示启用 `JINSHU_DEMO_ACCOUNTS=1`，界面列出编辑、审核、运营账号。真实私有资料应关闭演示账号，配置独立用户。每轮模型外发需同意；不执行真实金融业务。

Vercel 使用同一 `index:app`。`JINSHU_BUILD_EMBEDDINGS=1` 在构建时下载模型。资料和历史必须有私有持久化后端，不能用Vercel临时盘。MongoDB免费版、Redis、Milvus、原pi的接入与迁移见恢复说明；未配置的服务不标为已连接。

## 验证

`python -m pytest tests/core`，`node --test tests/manual_deploy.test.mjs`。GitHub CI 在干净生产依赖环境执行程序和Chromium交互验收。协议模拟、真实CPU向量、真实DeepSeek线上请求分别记录，不混成准确率。

原 `engine/`、`jinshu/`、`unified/` 企业实现仍保留。只维护本仓库；普通金枢和workbench共用一个正式部署。代码合并与线上发布分开验收。
