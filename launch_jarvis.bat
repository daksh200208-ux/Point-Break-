@echo off
title Point Break Autonomous System
color 0A
cd /d "%~dp0"
cls
echo ==============================================================================
echo                     POINT BREAK 3.0 -- WORKSTATION AI
echo ==============================================================================
echo.
echo [*] Initializing workstation interface...
taskkill /F /IM stockfish.exe >nul 2>nul
python jarvis.py %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Point Break exited with code %errorlevel%.
    pause
)
