@echo off
title Point Break -- 1-Click TARS Cloud Voice Deployer
color 0B
chcp 65001 >nul
cd /d "%~dp0"
cls
echo ==============================================================================
echo        POINT BREAK -- 1-CLICK CLOUD GPU VOICE DEPLOYMENT
echo ==============================================================================
echo.
python deploy_cloud_tars.py
echo.
pause
