@echo off
title Step 1 Verification Test - Client Hints
cd /d "%~dp0"
echo ========================================================
echo Running Step 1 Client Hints Verification...
echo ========================================================
py -3.12 test_step1.py
echo.
pause
