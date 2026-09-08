@echo off
cd /d "%~dp0"
if not exist ".venv-demo\Scripts\python.exe" (
 echo Crie .venv-demo e instale requirements-demo.txt antes de iniciar.
 pause
 exit /b 1
)
set PYTHONDONTWRITEBYTECODE=1
".venv-demo\Scripts\python.exe" -m streamlit run demo\app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false --theme.base dark
