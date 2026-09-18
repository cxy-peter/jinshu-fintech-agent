# V5｜网页部署、操作与实现对照

## 1. 选择一条部署路径

**最快的正式网址：Vercel。** 在Vercel登录后Import本仓库，Root Directory=`lite`，Framework=`Other`，Build=`npm run build`，Output=`dist`，Node22，Install=`npm ci`。默认不需要模型或数据库。必须完成平台的首次授权与Deploy，才有可分享的网址；本轮没有获得Vercel账号连接，尚未创建该线上项目。

README Deploy按钮使用Vercel支持的Git子目录URL，它复制lite到一个新仓库再部署。要随当前主仓库的后续更新自动发布，使用Import主仓库并指定lite。

另有 `.github/workflows/lite-pages.yml`，需仓库所有者先启用GitHub Pages并选择Actions。不要把准备好的工作流写成Pages已上线。

本机：`cd lite && npm ci && npm run build`，再 `python -m http.server 8795 --directory dist`，打开localhost:8795。

## 2. 九个页面，十一种工作流

页面：学习与问答、资料与上传、业务工具、执行记录、反馈与策略、记忆工作台、回放与评测、体验记录、原理与部署。

工作流：金融学习、FOF研究、理财对标、发行排期、周报质检、材料生成、开户时点、案件核查、特征预检、三表核对、客服。不是11个远程Agent服务。

推荐演示：问商业银行四个职能 → 查看来源 → 上传模拟TXT并本地启用 → 重新提问 → 执行排期并导出Word → 提交顺延相关反馈 → 候选回放与启用 → 再问看top-k → 回滚。

## 3. 资料怎么进入检索

网页原生解析PDF；DOCX读取正文XML；文本和分页JSON保留全部正文；JSONL/ZIP可读取V4的chunks.jsonl。单文件40MB，最多1500页，现成切片包最多25000片。扫描页没有自动OCR，复杂表格仍须原件复核。

上传者选择工作流及公开/内部/敏感标记，系统提供简单敏感词提示；默认pending_review。查看后点击本地启用才成为active。此操作是本浏览器审核流程演示，不是两人审核或企业权限。停用为archived；删除只删除本地副本，不删除原文件。

存储在该网站源的IndexedDB，不上传服务器，不共享给其他访客。浏览器清理、额度、隐私模式可能影响保留；可导出工作区备份。

回答预览不等于全文。来源查看器支持全部提取页/片段的逐页查看和完整文字导出。另行交付的115页金融学习JSON可在本人部署或本机上传；公开内置的是56个重新整理的主题，不是用户笔记全文。上传的历史资料需要保留年份，不作为现行制度。

## 4. 分词、路由与回答

`core.mjs` 使用Intl.Segmenter中文分词，加相邻双字补充与停用词；Index为倒排索引，BM25的k1=1.2、b=0.75，并给标题词项加权。不是hash向量，不是语义Embedding。

自动路由结合任务术语、索引结果和前一工作流；匹配不足时澄清或手选。短追问把上次问题加入检索表达，原话与改写分开保存。

默认Answer组织来源文字；Verify只核对活动来源关联，不声称验证每句金融事实。所有界面明确“分词检索整理”。

## 5. 可选模型接口

`lite/api/answer.mjs`需要服务端环境变量：

|变量|含义|
|---|---|
|LITE_AI_ENABLED|设1启用|
|LITE_ACCESS_CODE|部署者为试用者提供的访问码|
|CHAT_BASE_URL|HTTPS兼容接口根地址，通常以/v1结尾|
|CHAT_API_KEY|服务端密钥，不放前端|
|CHAT_MODEL|实际供应方支持的模型名称|

每次用户确认后才发送问题和最多5条来源；20秒超时；输出标记llm_draft，仅检查来源编号。未配置、超时或失败时保留原文检索结果。此可选路径尚未用真实模型密钥在Vercel验收，不能宣称已完成线上模型联调。

## 6. 工具与反馈

`tools.mjs`真实执行8类等价JS工具，原Python方法留在jinshu。模拟数据来自既有data/synthetic。登记编码保留前导零、缺失不填零、无效日期拒绝、共同净值区间校验、策略候选保持disabled。不处理真实钱款、发信或冻结。

反馈选择intent/retrieval/generation/knowledge_gap。前三类可产生受限候选，回放历史检索后本地启用；知识缺口只生成补资料待办。下一次Trace记录候选与top-k变化。回滚恢复基线。规则归因不是LLM反思，本地启用不是真实用户A/B，词项保留不是质量提升。

## 7. 与参考工程对标

|能力|当前网页|完整工程|
|---|---|---|
|主流程|固定JS步骤与Trace|原Harness/DAG及节点预算|
|检索|中文词项BM25、标题加权|BM25+真实向量+RRF+Reranker|
|事实|本地active资料与来源|Mongo事实记录、版本、哈希回查|
|记忆|IndexedDB中五类逻辑视图|Redis工作记忆与Mongo相关记录|
|工具|等价JS计算与文件导出|Python参数化Skill|
|Loop|规则候选、历史来源回放、本地启停|反馈引擎、模型候选、审核灰度、共享控制|
|部署|Vercel静态页+可选函数|Compose私有模型与数据服务|
|扩容|不实现|K8s/HPA模板，未压测|

原engine未修改。视频在约5、60、180、420、780、1140秒查看抽帧，参考侧栏、Loop阶段与运行内容；不是完整逐秒观看或像素级复刻。

## 8. 实际验收与限制

38条程序测试及真实Chromium交互已通过。浏览器检查覆盖TXT上传启用刷新检索、DOCX、原生PDF、115页模拟JSON、Word导出、8工具、16开发题、反馈回滚、9页面与移动端。PDF试件为英文模拟FAQ；115页试件为模拟内容。不是私有90份资料全部浏览器验收。

运行：https://github.com/cxy-peter/jinshu-fintech-agent/actions/runs/35392921379 。证据在evidence/v5。一次早期失败来自测试在IndexedDB提交完成前刷新，已修正为等待提交后的界面状态，失败历史仍保留。

V4完整服务的部分失败未被V5成功覆盖。提供scripts/run_live_acceptance_v5.py修补评测导入入口，未重跑完整服务。真人用户0，没有K8s/HPA实测。

官方参考：
- https://vercel.com/docs/monorepos
- https://vercel.com/docs/deploy-button/source
- https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
- https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity
