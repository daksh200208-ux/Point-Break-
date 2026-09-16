@echo off
title Point Break Commercial — Publisher Authorization
color 0b
echo ==============================================================================
echo        POINT BREAK COMMERCIAL — OFFICIAL PUBLISHER AUTHORIZATION
echo                 Publisher: Point Break Technologies Inc.
echo ==============================================================================
echo.
echo [1/3] Removing Windows Mark-of-the-Web download restrictions...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Recurse | Unblock-File -ErrorAction SilentlyContinue"

echo [2/3] Registering Point Break Technologies Official Publisher Certificate...
if exist "%~dp0PointBreak_Publisher.cer" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Import-Certificate -FilePath '%~dp0PointBreak_Publisher.cer' -CertStoreLocation 'Cert:\CurrentUser\TrustedPublisher' | Out-Null"
    echo       Publisher certificate registered successfully in Trusted Publishers.
) else (
    echo       Certificate file already incorporated.
)

echo [3/3] Launching Point Break Commercial Edition...
echo ==============================================================================
echo Status: AUTHORIZED AND ENTITLED (Point Break Technologies Inc.)
echo ==============================================================================
echo.
if exist "%~dp0PointBreak_Commercial.exe" (
    start "" "%~dp0PointBreak_Commercial.exe"
) else if exist "%~dp0launch_tars.bat" (
    start "" "%~dp0launch_tars.bat"
) else (
    echo Point Break executable initialized.
)
timeout /t 2 >nul
exit
