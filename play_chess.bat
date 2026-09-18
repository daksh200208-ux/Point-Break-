@echo off
cd /d "%~dp0"
taskkill /F /IM stockfish.exe >nul 2>nul
if exist chess_stop.flag del /F /Q chess_stop.flag >nul 2>nul
start "" wscript.exe "%~dp0Play_Chess_Silent.vbs"
exit
