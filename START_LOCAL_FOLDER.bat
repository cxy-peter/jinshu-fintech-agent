@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_local_folder.py %*
) else (
  python scripts\run_local_folder.py %*
)
if errorlevel 1 (
  echo 请确认已安装项目 Python 依赖，可使用 --root "F:\JinshuData" 设置资料目录。
  pause
)
