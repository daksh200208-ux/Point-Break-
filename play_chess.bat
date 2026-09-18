@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

:: Terminate any runaway Stockfish engine and reset stop flags
taskkill /F /IM stockfish.exe >nul 2>nul
if exist chess_stop.flag del /F /Q chess_stop.flag >nul 2>nul

:: Launch Point Break Autonomous Chess Titan completely MINIMIZED to taskbar
:: Zero giant black CMD window covering the chessboard or desktop!
start "" /min python pointbreak_chess.py --auto %*

exit
