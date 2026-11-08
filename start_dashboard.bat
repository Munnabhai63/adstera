@echo off
title Traffic Generator Dashboard
cd /d "%~dp0"
echo ============================================================
echo   Starting Traffic Generator Dashboard on http://localhost:5050
echo ============================================================
echo.
echo Dashboard is running! Open your browser at:
echo http://localhost:5050
echo.
py -3.12 ui.py 5050
pause
