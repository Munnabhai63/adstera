@echo off
title AutoPublish 24/7 Autonomous Daemon
cd /d "%~dp0"
echo ============================================================
echo   Starting AutoPublish 24/7 Autonomous Daemon (10 Domains)
echo ============================================================
echo.
echo Daemon is running in background! It will automatically:
echo  - Write SEO articles (1200+ words)
echo  - Deploy to Cloudflare Pages
echo  - Submit to Google & Bing IndexNow
echo.
if exist .venv\Scripts\python.exe (
    .\.venv\Scripts\python.exe autopublish_daemon.py
) else (
    py -3.12 autopublish_daemon.py
)
pause

