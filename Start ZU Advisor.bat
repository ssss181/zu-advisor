@echo off
rem Double-click to start the ZU Advisor site, then it opens in your browser.
rem Close this window to stop the site.
cd /d "%~dp0"
title ZU Advisor - running at http://localhost:5178
start "" /min cmd /c "timeout /t 2 >nul & start http://localhost:5178"
".venv\Scripts\python.exe" server.py
pause
