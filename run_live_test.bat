@echo off
title Traffic Generator - Head-On Live Window Test
cd /d "%~dp0"
echo ============================================================
echo   Launching Chromium in Visible Head-On Mode on your Monitor
echo ============================================================
echo.
py -3.12 main.py
pause
