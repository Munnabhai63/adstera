@echo off
title Adsterra & Cloudflare Fleet Controller
cd /d "%~dp0"
echo ============================================================
echo   Starting Autonomous Fleet Services
echo ============================================================
echo.

echo 1. Starting Local UI Server (Port 5050)...
start "Adsterra UI Server" /min py -3.12 ui.py 5050

timeout /t 2 /nobreak >nul

echo 2. Starting Cloudflare Tunnel Daemon (10 Domains Bridge)...
start "Cloudflare Tunnel Daemon" /min py -3.12 tunnel_daemon.py

timeout /t 2 /nobreak >nul

echo 3. Starting FreeLLMAPI AI Router (Port 3001)...
start "FreeLLMAPI Watchdog" /min py -3.12 freellmapi_daemon.py

echo.
echo ============================================================
echo   ALL SERVICES ARE ONLINE!
echo   - Local Dashboard:     http://localhost:5050
echo   - Public Admin URL:    https://rechargetak.com/admin
echo   - Public Domain:       https://loanraaj.com
echo   - Free LLM API:        http://localhost:3001
echo ============================================================
echo.
pause
