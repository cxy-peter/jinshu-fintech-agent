# 历史资料索引

当前运行入口、简历与面试材料以根README和V11文档为准。升级前完整快照保留在 [archive/pre-v11-20261105](https://github.com/cxy-peter/jinshu-fintech-agent/tree/archive/pre-v11-20261105)，对应主线44321c6。Git历史未重写、数据库未删除。

22份旧版本指南及2个一次性补丁从当前目录移除，避免把历史实现或验收数字当现状。完整文件均可在该归档分支原路径取得：

- docs/V6_RESUME_PRODUCT.md
- docs/PRODUCT_SPEC_V5.md
- docs/CORE_V9_AUDIT.md
- docs/README_V7_HISTORY.md
- docs/V4_GUIDE.md
- docs/V7_PRODUCTION.md
- docs/V5_GUIDE.md
- docs/V6_README_ARCHIVE.md
- docs/V6_ACCEPTANCE_AND_PRODUCT.md
- docs/UNIFIED_V8.md
- docs/V7_RESUME_PUBLIC.md
- docs/V5_INTERVIEW.md
- docs/VERCEL_AUDIT_V81.md
- docs/V7_READABLE_GUIDE.md
- docs/CORE_V9_ACCEPTANCE_NOTES.md
- docs/README_V9_ARCHIVE.md
- docs/V7_ARCHITECTURE.md
- docs/V7_RELEASE.md
- docs/V6_SOURCE_ALIGNMENT.md
- docs/V5_1_READING.md
- docs/V7_ACCEPTANCE.md
- docs/UNIFIED_V8_RELEASE.md
- patches/01_mongodb.patch
- patches/02_orchestrator.patch

旧简历与面试稿也在同一归档分支的docs目录。`engine/`保留上游参考源码及来源，`jinshu/`与`unified/`仍被业务工具复用，没有因看似旧而删除。`lite/`及历史验收数据保留用于历史回归，不进入Vercel发布包。仅清理明确过时说明和一次性补丁。

本轮用于提取源码的一次性CI以及已应用的集成补丁脚本也移除；保留常规只读验收工作流，不在生产构建时修改代码。
