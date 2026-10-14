@echo off
setlocal
cd /d "%~dp0"
if not defined GIE_CORE_PYTHON set "GIE_CORE_PYTHON=%CD%\.venv\Scripts\python.exe"
"%GIE_CORE_PYTHON%" -B src\gie_panel\launch.py
if errorlevel 1 pause
endlocal
