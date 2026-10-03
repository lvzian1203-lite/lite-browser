@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 lite browser ...
start "" pythonw lite_browser.py
exit /b 0
