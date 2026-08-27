@echo off
title T.A.R.S. 2.5 — Commercial Edition
color 0B
cd /d "%~dp0"
echo.
echo   ====================================================
echo     T.A.R.S. 2.5  //  STARK SYSTEMS COMMERCIAL EDITION
echo   ====================================================
echo.
echo   [1] Auto-Detecting Python Runtime & Repairing Environment...

set PYCMD=
set PYWCMD=

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYCMD=py -3
    set PYWCMD=pyw -3
)

if "%PYCMD%"=="" (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set PYCMD=python
        set PYWCMD=pythonw
    )
)

rem Search standard user AppData and Program Files installation directories automatically!
if "%PYCMD%"=="" (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" (
            set "PYCMD=%%D\python.exe"
            set "PYWCMD=%%D\pythonw.exe"
            rem Auto-fix CMD PATH permanently!
            setx PATH "%PATH%;%%D;%%D\Scripts" >nul 2>nul
        )
    )
)

if "%PYCMD%"=="" (
    for /d %%D in ("%ProgramFiles%\Python*") do (
        if exist "%%D\python.exe" (
            set "PYCMD=%%D\python.exe"
            set "PYWCMD=%%D\pythonw.exe"
            setx PATH "%PATH%;%%D;%%D\Scripts" >nul 2>nul
        )
    )
)

if "%PYCMD%"=="" (
    if exist "C:\Python311\python.exe" (
        set "PYCMD=C:\Python311\python.exe"
        set "PYWCMD=C:\Python311\pythonw.exe"
    ) else if exist "C:\Python38\python.exe" (
        set "PYCMD=C:\Python38\python.exe"
        set "PYWCMD=C:\Python38\pythonw.exe"
    )
)

if "%PYCMD%"=="" (
    echo.
    echo   [!] Python is not installed yet. Launching auto-installer...
    echo.
    winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements
    for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" (
            set "PYCMD=%%D\python.exe"
            set "PYWCMD=%%D\pythonw.exe"
        )
    )
)

if "%PYCMD%"=="" (
    echo.
    echo   [!] Could not auto-detect Python. Please run Python installer and check "Add to PATH".
    pause
    exit /b
)

echo   [+] Python runtime active!

echo.
echo   [2] Verifying Core AI Libraries...
"%PYCMD%" -m pip install -q -r requirements.txt 2>nul

echo.
echo   [3] Launching T.A.R.S. 2.5 Monolith Core...
echo.
start "" "%PYWCMD%" jarvis.py %*
