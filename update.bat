@echo off
title Updating Point Break Commercial...
color 0e
echo ==============================================================================
echo                 POINT BREAK COMMERCIAL — SYSTEM AUTO-UPDATER
echo ==============================================================================
echo.
echo [1/2] Pulling latest updates from GitHub...
git pull origin main
if %errorlevel% neq 0 (
    echo [WARNING] Git pull encountered an issue. Checking local dependencies...
)

echo.
echo [2/2] Updating dependencies...
if exist venv\Scripts\activate (
    call venv\Scripts\activate
    pip install -r requirements.txt --upgrade
)

echo.
echo ==============================================================================
echo [SUCCESS] Point Break is up to date! Run 'run.bat' to launch.
echo ==============================================================================
pause
