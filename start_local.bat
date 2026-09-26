@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3.12 -m venv .venv
  )
)
if errorlevel 1 goto failed
.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 'Python 3.12 or 3.13 is required. Create a Python 3.12 .venv before starting.')"
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Jinshu V9: shared core backend at http://127.0.0.1:8766
echo Missing settings are shown on the setup page; no offline fallback.
if exist .env (
  .venv\Scripts\python.exe -m uvicorn index:app --host 127.0.0.1 --port 8766 --env-file .env
) else (
  .venv\Scripts\python.exe -m uvicorn index:app --host 127.0.0.1 --port 8766
)
exit /b %errorlevel%
:failed
echo Startup failed. Check the Python version and dependency errors above.
pause
exit /b 1
