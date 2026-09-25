# 金枢：统一完整运行时

本轮目标是让线上与本地使用同一套实际后端，不把轻量网页改名为完整版。

## 一条执行链

`index.py → unified.app → jinshu.runtime.Runtime(profile=services)`。

网页仅展示和调用HTTP API。问答继续使用原来的Harness、权限与事实校验、BM25/Milvus/RRF/重排、生成和Verifier；五类Memory、反馈Loop、共享灰度/回滚与Trace保持原实现。8类固定工具在服务器执行，可接收用户明确提供的数据；示例数据必须显式选择。

任务、确认和导出通过MongoDB的版本条件写控制，跨请求不以浏览器state为准。资料上传需要独立账号审核；敏感资料不外发，未授权外部编码时明确为BM25-only，不伪造语义向量。外部模型模式不自动上传历史反馈，Loop候选采用本地有界规则；私有模型模式保留原模型反思路径。pi是保留的可选认证服务，需要实际部署其服务端，不能把未配置称为已运行。

## Vercel与持久服务

Vercel负责同一个Python ASGI应用。MongoDB、Redis和Milvus必须是可达的持久服务，不能塞进Function的临时文件系统。模型、Embedding和Reranker必须分别配置可用接口；只配置一个DeepSeek聊天Key并不能同时提供后三类服务。

环境变量名称见`unified/environment.example`。没有配置时，网页展示缺项；业务API返回503，绝不自动进入offline测试模式，也不把公共示例当用户资料。`configured`仅指变量存在，连接测试和真实质量验收另行执行。

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# 在当前终端安全加载配置，不把.env提交到仓库
uvicorn index:app --host 127.0.0.1 --port 8000
```

Vercel从仓库根目录识别`index.py`；使用同一requirements和`vercel.json`，不是root=lite。独立发布仓库必须同步后端源文件，而不再只下载web文件。

## 首次使用

设置随机AUTH_SECRET和JINSHU_BOOTSTRAP_TOKEN后，在“服务与配置”中创建编辑和另一名复核账号，随后删除初始化token。不存在公开默认账号。登录token仅保留当前页面内存，刷新需重新登录，服务器资料仍保存。

上传3.5MB以内原生PDF/Word/TXT/MD/CSV/分页JSON或只包含分页JSON的ZIP。压缩比、路径、解压体积和页数有界；没有自动OCR。大资料需拆分。原V7 IndexedDB不会自动外传或删除；新页面可以在原域名下备份旧工作区，待本人确认后重新上传审核。旧本地启用不转成企业审核。

工具执行：保存输入→执行→检查异常→确认当前版→导出。修改输入撤销旧确认；迟到的计算或导出不覆盖更新版本。Word超过500行或12列时改用CSV/JSON，不静默截掉数据。中断的running任务可编辑为新版本重试。

Loop作业由管理员点击处理一个有界批次（最长180秒、Redis互斥），不在Vercel开启永久后台循环。原始完整服务可以另设外部Worker，但同一队列不能另启动未协调的并行处理器。实际策略发布仍要求回放、版本绑定与审核；没有随机线上用户样本时不声称收益。

## 验收边界

`tests/test_unified_v8.py`通过依赖注入使用测试Runtime和内存CAS仓库。它验证真实函数、HTTP API、权限、输入版本及文件，但不等同于已连接云端Mongo/Redis/Milvus或真实模型。部署不得注入测试Runtime。当前云端授权和凭据需另外核验；真实结果只以发布记录为准。

原V7的500项标签和旧源码保留在历史目录，不把历史489/500直接写成新版完整服务质量。

官方部署依据：
- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/functions/configuring-functions/duration
