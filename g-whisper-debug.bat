@echo off
REM Versão com console visível para debug
cd /d "%~dp0"
".venv\Scripts\python.exe" -u -m gwhisper.tray
pause
