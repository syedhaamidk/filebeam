@echo off
setlocal EnableDelayedExpansion
title FileBeam - Cloudflare Tunnel Setup

echo.
echo  ============================================================
echo   ^⚡  FileBeam ^+ Cloudflare Tunnel  ^-  Auto Setup
echo  ============================================================
echo.

:: ── Step 1: Check Python ──────────────────────────────────────────────────
echo  [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ^❌  Python not found!
    echo      Download from: https://www.python.org/downloads/
    echo      Make sure to check "Add Python to PATH" during install.
    pause & exit /b 1
)
echo  ^✅  Python found.

:: ── Step 2: Download cloudflared ─────────────────────────────────────────
echo.
echo  [2/4] Setting up cloudflared...

set CF_DIR=%USERPROFILE%\filebeam
set CF_EXE=%CF_DIR%\cloudflared.exe

if exist "%CF_EXE%" (
    echo  ^✅  cloudflared already downloaded.
) else (
    echo  ^⬇^  Downloading cloudflared...
    mkdir "%CF_DIR%" 2>nul
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CF_EXE%'"
    if errorlevel 1 (
        echo  ^❌  Download failed. Check your internet connection.
        pause & exit /b 1
    )
    echo  ^✅  cloudflared downloaded.
)

:: ── Step 3: Copy fileserver scripts ──────────────────────────────────────
echo.
echo  [3/4] Preparing FileBeam scripts...

if not exist "%CF_DIR%\fileserver.py" (
    if exist "%~dp0fileserver.py" (
        copy "%~dp0fileserver.py" "%CF_DIR%\fileserver.py" >nul
        echo  ^✅  fileserver.py copied.
    ) else (
        echo  ^⚠^   fileserver.py not found next to this script.
        echo      Make sure fileserver.py is in the same folder.
    )
)

if not exist "%CF_DIR%\filesync.py" (
    if exist "%~dp0filesync.py" (
        copy "%~dp0filesync.py" "%CF_DIR%\filesync.py" >nul
        echo  ^✅  filesync.py copied.
    )
)

:: ── Step 4: Create launcher ────────────────────────────────────────────────
echo.
echo  [4/4] Creating launcher...

set LAUNCHER=%CF_DIR%\start_filebeam.bat
(
echo @echo off
echo title FileBeam - Running
echo cd /d "%CF_DIR%"
echo echo.
echo echo  ============================================================
echo echo   ^⚡  FileBeam is starting...
echo echo  ============================================================
echo echo.
echo echo  Starting file server on port 8080...
echo start "FileBeam Server" python "%CF_DIR%\fileserver.py" --port 8080
echo timeout /t 2 /nobreak ^>nul
echo echo  Starting Cloudflare Tunnel...
echo echo  ^(Your public URL will appear below - open it on any device^)
echo echo.
echo "%CF_EXE%" tunnel --url http://localhost:8080
echo pause
) > "%LAUNCHER%"

echo  ^✅  Launcher created at: %LAUNCHER%

:: ── Done ──────────────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   ^✅  Setup Complete!
echo  ============================================================
echo.
echo   FILES SAVED TO: %CF_DIR%
echo.
echo   HOW TO USE:
echo   1. Double-click: %LAUNCHER%
echo   2. A public URL like https://xxxx.trycloudflare.com
echo      will appear in the window
echo   3. Open that URL on your phone from ANYWHERE
echo.
echo   NOTE: The URL changes each time you restart.
echo         For a permanent URL, log in to Cloudflare (free):
echo         https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
echo.
echo  ============================================================
echo.

set /p LAUNCH="  Launch FileBeam now? (y/n): "
if /i "%LAUNCH%"=="y" (
    start "" "%LAUNCHER%"
)

pause
