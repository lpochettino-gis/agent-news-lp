@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0install_agent_news_task.ps1"
pause
endlocal
