@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0TEST-AFTER-PATCH.ps1"
exit /b %ERRORLEVEL%
