@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL-AIDER.ps1"
exit /b %ERRORLEVEL%
