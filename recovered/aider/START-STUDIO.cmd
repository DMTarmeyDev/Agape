@echo off
setlocal
cd /d "%~dp0"
python -m agape_studio.server
