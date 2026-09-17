@echo off
title Point Break Grandmaster Chess (Stockfish 16 NNUE)
color 0B
cd /d "%~dp0"
cls
echo ==============================================================================
echo    POINT BREAK 3.0 -- AUTONOMOUS GRANDMASTER CHESS TITAN (3500+ ELO)
echo ==============================================================================
echo.
echo [*] Clearing stale background locks...
taskkill /F /IM stockfish.exe >nul 2>nul
echo [*] Launching Autonomous Chess Controller...
echo.
python pointbreak_chess.py --auto %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Chess controller finished or exited with code %errorlevel%.
    pause
)
