# 原工程来源与V3差异

## 资料基础
- 用户提供的wenshu-project(1).zip、行政助手说明文字、XMind和运行视频。
- 用户GitHub：Intern-Python4WealthProduct、财报清洗、年报提取、数字资产风控原型。
- 用户提供CoinTR chatbot登录、自助服务、AI客服、Zendesk与知识库PRD截图。截图不公开。

原说明的主线是Harness、可信RAG、五个记忆平面、可执行Skill与Execute→Observe→Reflect→Adapt→Deploy。保留这些组织方式；不继承其高校身份、1,086文档、1,200题或效果/压测数字。

## 文件保留
完整本地包231个原文件，229个字节相同，2个V2已有补丁。本轮新增内容在jinshu等适配目录，engine未继续改动。原ZIP/RAR未更改。公开包有单独逐文件排除清单，排除学校原始资料和设计图片；不能把公开排除误写为原文件篡改。

## 原材料、原代码与本次实现的区分
|项目|参考/原有|V3处理|
|---|---|---|
|DAG和Loop|原Orchestrator、LoopEngine、SkillMiner|保留调用，增加金融任务与控制故障门槛|
|表格切片|参考文字承认附表不足|真实PDF表格转结构片段，附上下文与源页|
|审核与敏感|原部门鉴权与文档状态|上传者声明、本地检测、独立审级、审核前禁外发|
|回滚API故障|原正常回滚路径|先本机持久化freeze，再更新远端；失败显示pending|
|工单对接|PRD保留Zendesk|本地幂等草稿和契约测试；未调用真实接口|
|理财程序|既有对标、排期、数字整理思路|显式Python注册、Schema、来源哈希和Word草稿|
|UI|原Next.js深绿/金色布局|原页面保留，金融工作台恢复相近风格并接新API|

## 视频阅读范围
上一轮沿时间轴核对51个画面，对照LoopPanel、Orchestrator、Verifier、入库、Memory与loop_engine.py讲解位置。没有完成完整音轨逐字转录。本轮以原源码、已提供完整文字、截图和实际测试为改造依据，不声称重新完整听录了视频。

## 已知不足不静默抹去
原材料关于“模型全部不可用时仍可无条件向量检索”的说法不能直接用于本版本：在线问题通常仍需query embedding。版本发布仍有跨进程CAS/补偿需求；本机冻结不是集群容灾。规则检测不是正式DLP。hash向量和原文回退不是大模型推理。

## 参考链接
- https://github.com/cxy-peter/Intern-Python4WealthProduct
- https://github.com/cxy-peter/simple-data-cleaning-about-three-financial-statement
- https://github.com/cxy-peter/information-extraction-from-an-enterprise-annual-report
- https://github.com/cxy-peter/digital-asset-cex-risk-strategy-ai-copilot
- https://fastapi.tiangolo.com/tutorial/request-files/
- https://milvus.io/docs/milvus_lite.md
- https://redis.io/docs/latest/commands/xautoclaim/

原代码保留出处，本次成果为AI辅助个人适配，不重新授权未知许可上游代码。
