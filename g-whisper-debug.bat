@echo off
REM Debug mode with visible console
cd /d "%~dp0"
".venv\Scripts\python.exe" -u -m gwhisper.tray
pause
