@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0START-AGAPE-LATEST.ps1" -Root "%~dp0"
if errorlevel 1 pause
