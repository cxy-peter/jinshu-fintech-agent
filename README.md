# 金枢 V11.1｜金融业务与个人知识工作台

[打开工作台](https://jinshu-workbench.vercel.app/) · [本轮架构与边界](docs/V11_UPGRADE.md) · [简历表述](docs/RESUME_PROJECT.md) · [面试准备](docs/INTERVIEW_MANUAL.md) · [历史资料索引](docs/history/README.md)

基于文枢参考工程的个人AI辅助改造。保留可信RAG、Memory、可执行Skill和受控反馈Loop；借鉴差旅V2的可靠执行思想，不更换项目业务定位、不训练模型。

## V11.1 新增

同一线上工作台支持个人 PDF/Word 上传、文件夹选择、页码原文、先检索后回答、显式知识缺口和单次跨设备认领。前后端统一金融术语与追问处理，检索索引预计算，数据库连接复用。3 秒是证据返回目标，实际时间见执行记录，不作为完整答案承诺。

[本轮知识库、业务与部署说明](docs/V11_1_KNOWLEDGE.md) · [业务能力目录](docs/BUSINESS_CAPABILITIES.md)

## 现在可以演示

**知识与运营：** 上传资料、独立审核、版本与有效性管理；BM25+CPU中文语义向量/RRF及重排；DeepSeek引用回答；反馈形成受限候选，经回放和人工审核进入灰度、可回滚。

**可恢复业务流程（V11）：** “周报质检＋同业对标”复核包，以及八类原有工具的单任务流程。显式输入快照、请求防重、节点检查点、局部重试和复用、独立审核、服务器版本化JSON/CSV导出。KEEP/REVIEW/REWRITE来自规则，不是模型置信度。

**规则而非猜测：** 发行排期检查日历范围、工作日例外、日期顺序与批次冲突。模型不负责计算金额或决定发行。

## 本地与线上同一个入口

```bash
pip install -r requirements.txt
# 密钥只放服务端.env / Vercel环境变量，不提交GitHub
uvicorn index:app --host 127.0.0.1 --port 8000
```

本地SQLite；线上连接已有MongoDB或私有Blob，不能用/tmp冒充持久数据库。DeepSeek需要`DEEPSEEK_API_KEY`；无密钥仍可使用确定性工具。语义模型通过`python scripts/fetch_embedding.py`获取固定版本。

`JINSHU_DEMO_ACCOUNTS=1`仅用于公开脱敏演示。新任务需要登录；编辑账号提交，另一审核账号复核。真实数据必须关闭演示账号并配置独立授权账号。不要在公共演示空间提交机构内部文件。

Vercel仍为`index.py → core.app`。一批工作完成后即保存，不运行永久后台循环；中断恢复需后续请求。新机制只覆盖白名单纯计算任务，不宣称全部模型调用可恢复、跨系统exactly-once或真实业务自动化。

## 验证与源代码组织

```bash
python -m pytest -q tests/core
node --test tests/manual_deploy.test.mjs tests/personal_materials.test.mjs
python scripts/build_unified.py
python tests/core/browser_check.py
python tests/core/browser_workflows.py
```

`core/`为当前工作台；`jinshu/`与`unified/`含业务工具及既有完整服务；`engine/`保留原参考实现与来源。历史设计和补丁统一归档，不与当前简历/运行说明混用。数据库、浏览器身份、真实文档、模型密钥及字体不进入公开源码包。

测试通过、部署READY、实际模型返回、真实用户效果分别记录。历史489/500不可当本轮新版准确率。未实施压测、K8s/HPA验收或真实生产业务试点。
