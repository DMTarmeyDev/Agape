@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL-TEST-REPORT.ps1"
exit /b %ERRORLEVEL%
