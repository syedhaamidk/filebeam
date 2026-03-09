@echo off
:: FileBeam PC Sync — rclone → Cloudflare R2
:: Run this on your PC to keep a folder synced with R2

setlocal
set RCLONE_REMOTE=filebeam-r2
set R2_BUCKET=filebeam
set LOCAL_FOLDER=%USERPROFILE%\FileBeamSync

echo.
echo  ============================================================
echo   ⚡  FileBeam PC Sync  ^|  Folder → Cloudflare R2
echo  ============================================================

:: Check rclone
where rclone >nul 2>&1
if errorlevel 1 (
    echo  ❌  rclone not found.
    echo      Download from: https://rclone.org/downloads/
    echo      Then run: rclone config  and follow the R2 setup
    pause & exit /b 1
)

:: Create folder if missing
if not exist "%LOCAL_FOLDER%" mkdir "%LOCAL_FOLDER%"

echo  📁  Syncing: %LOCAL_FOLDER%
echo  ☁️   To:      r2:%R2_BUCKET%
echo  🔄  Mode:    Two-way (bisync)
echo.

:: First run — use --resync to initialise bisync state
if not exist "%USERPROFILE%\.config\rclone\bisync_%R2_BUCKET%.db" (
    echo  First run — initialising sync...
    rclone bisync "%LOCAL_FOLDER%" "%RCLONE_REMOTE%:%R2_BUCKET%" --resync --verbose
) else (
    rclone bisync "%LOCAL_FOLDER%" "%RCLONE_REMOTE%:%R2_BUCKET%" --verbose
)

echo.
echo  ✅  Sync complete!
echo  📂  Open %LOCAL_FOLDER% to add/remove files.
echo      Re-run this script any time to sync changes.
echo.
pause
