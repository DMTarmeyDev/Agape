@echo off
setlocal
cd /d "%~dp0"
where python.exe >nul 2>&1
if errorlevel 1 (
  python scripts\run_full_test_process.py
) else (
  python.exe scripts\run_full_test_process.py
)
exit /b %errorlevel%
