@echo off
title Point Break 3.0 Autonomous Workstation Core
color 0A
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
cls
echo ==============================================================================
echo                     POINT BREAK 3.0 -- WORKSTATION AI
echo ==============================================================================
echo.
echo [*] Initializing Workstation Interface...
taskkill /F /IM stockfish.exe >nul 2>nul
python jarvis.py %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Point Break exited with code %errorlevel%.
    pause
)
