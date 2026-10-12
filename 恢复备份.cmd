@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" "restore_backup.py"
pause
