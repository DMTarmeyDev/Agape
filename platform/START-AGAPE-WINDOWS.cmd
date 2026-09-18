@echo off
setlocal
cd /d "%~dp0\.."
where py >nul 2>nul && (py -3 main.py %* & exit /b %errorlevel%)
python main.py %*
