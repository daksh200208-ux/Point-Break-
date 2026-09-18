@echo off
title Point Break Grandmaster Chess Titan (3500+ ELO)
color 0B
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
cls
echo ==============================================================================
echo    POINT BREAK 3.0 -- AUTONOMOUS GRANDMASTER CHESS TITAN (3500+ ELO)
echo ==============================================================================
echo.
echo [*] Terminal Encoding: UTF-8 Activated
echo [*] Stockfish 16 NNUE Engine: Armed (Depth 16-20)
echo [*] Mode: 100%% Silent Tournament Execution
echo [*] Target Speed: 3.0s - 3.8s per move
echo.
taskkill /F /IM stockfish.exe >nul 2>nul
python pointbreak_chess.py --auto %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Process exited with code %errorlevel%.
    pause
)
