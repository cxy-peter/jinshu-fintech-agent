# 金枢：先跑这三个演示

1. 启动：`python -m jinshu generate-data`、`python -m jinshu.mock_pdfs`、`python -m jinshu serve --port 8766`。
2. 使用editor / demo-editor，选择“发行材料生成”执行，下载真实Word草稿。
3. 在资料页导入模拟PDF，再用reviewer / demo-reviewer审核。查看表格片段的metadata.page与当前版本。
4. 到Loop进化中心运行隔离实验：查看配对回放、5%灰度、top-k 2→8、故障注入后恢复2。

本项目是两段实习场景的个人延伸：统一“查资料—运行工具—交付材料—反馈迭代”的中后台任务，不是两家公司共同生产系统。默认离线；hash向量不等于真实语义模型。
