@echo off
title Point Break Commercial Console
color 0a
echo ==============================================================================
echo                      LAUNCHING POINT BREAK COMMERCIAL
echo ==============================================================================
echo.
if exist venv\Scripts\activate (
    call venv\Scripts\activate
)
python jarvis.py
if %errorlevel% neq 0 (
    echo.
    echo [NOTICE] Point Break terminated with an exit code.
    pause
)
