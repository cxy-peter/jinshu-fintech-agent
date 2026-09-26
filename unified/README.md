# 统一完整运行时

本地和 Vercel 都以 `index:app` 启动完整 Python 后端，不使用浏览器模拟来替代原功能。

本地默认启动已统一：Windows `start_local.bat`，macOS/Linux `bash start_local.sh`。手工命令是 `python -m uvicorn index:app --host 127.0.0.1 --port 8766`，有本地 `.env` 时添加 `--env-file .env`。需要 Python 3.12；密钥只放本地忽略文件或 Vercel 私密环境变量。

完整依赖、DeepSeek、独立 Embedding/Reranker、数据库、首次账号与当前发布边界见 [START_HERE](../START_HERE.md)。无配置只显示设置页，不自动使用离线测试账号或虚构模型结果。
