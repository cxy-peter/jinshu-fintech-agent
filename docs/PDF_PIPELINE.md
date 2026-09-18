# 原生PDF → 审核 → 切片索引 → 检索验证

## 复现
```bash
python -m jinshu generate-data
python -m jinshu.mock_pdfs
python scripts/validate_v3.py
```

8份PDF位于data/mock_pdf，包含三大报表、产品要素、发行日历、新旧FAQ与敏感个案。均由模拟CSV或模拟规则生成，重新用PyMuPDF读取PDF，而不是把生成前的文本冒充解析结果。

## 数据流
POST `/api/documents/pdf` 接收PDF、dept_id、topic、version、manual_sensitivity。本机读取文字及表格并切片，文档状态为pending_review，vector_status=not_indexed。上传者初判和规则提示独立保留，原文此时不进入共享检索。

另一位管理员通过 POST `/api/documents/{id}/review` 提交final_sensitivity、allowed_depts、external_allowed和reason。审核通过后准备BM25/向量索引并发布；restricted与sensitive资料不允许外部向量化。离线hash向量只在本机计算。向量服务失败明确降为BM25-only，不把失败写成向量索引成功。

原生表格以完整行切片，保留表头与页码，长表按8行拆分并重复表头。本轮8PDF产生16切片，其中4个表格片段。正式财务计算仍读取结构化CSV；新PDF不会自动改写财务账本。

## 实测口径
固定现金流查询返回的结果中有5个来自这些PDF的片段；同时执行18个工作流任务并检查来源。FAQ v2发布后v1归档。以上是固定合成样例的工程验收，不是Recall@k或真实语义问答准确率。默认hash向量不等于学习得到的Embedding。

详情见evidence/v3_pdf_and_failure_evidence.json。扫描PDF、特殊版式和真实模型服务仍需后续适配；当前不自动OCR。
