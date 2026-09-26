@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Please install Node.js 22 or newer first.
  pause
  exit /b 1
)
node scripts\manual_deploy.mjs %*
set "RESULT=%errorlevel%"
pause
exit /b %RESULT%
