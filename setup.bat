@echo off
title Point Break Commercial - Setup
color 0b
echo ==============================================================================
echo              POINT BREAK COMMERCIAL — INITIAL SYSTEM SETUP
echo ==============================================================================
echo.
echo [1/3] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ from python.org and check "Add to PATH".
    pause
    exit /b
)

echo.
echo [2/3] Installing required packages...
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [3/3] Initializing environment secrets...
if not exist .env (
    copy .env.example .env
    echo Created .env configuration file.
    echo [IMPORTANT] Please open .env with Notepad and add your GEMINI_API_KEY!
) else (
    echo Existing .env detected. Keeping current configuration.
)

echo.
echo ==============================================================================
echo [SUCCESS] Setup completed successfully!
echo You can now double-click 'run.bat' to start Point Break.
echo ==============================================================================
pause
