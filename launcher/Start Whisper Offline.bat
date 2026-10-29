@echo off
setlocal
cd /d "%~dp0"
set "APP_DIR=%~dp0"
set "TARGET=%APP_DIR%WhisperOffline.exe"

if not exist "%TARGET%" (
  echo WhisperOffline.exe was not found next to this file.
  echo Make sure you extracted the whole WhisperOffline folder from the zip.
  pause
  exit /b 1
)

rem First run only: remove the "downloaded from the internet" flag Windows adds
rem to every extracted file, so it stops showing a security prompt each launch.
if not exist "%APP_DIR%_internal\.unblocked" (
  echo Preparing Whisper Offline for first use, this can take a minute...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%APP_DIR%' -Recurse -File | Unblock-File" 2>nul
  type nul > "%APP_DIR%_internal\.unblocked"
)

rem Create or refresh the desktop shortcut.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $s=$ws.CreateShortcut((Join-Path $desktop 'Whisper Offline.lnk')); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%APP_DIR%'; $s.IconLocation='%TARGET%,0'; $s.Save()" 2>nul

start "" "%TARGET%"
