@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
".venv-demo\Scripts\python.exe" -m streamlit run demo\high_autonomy_v2\app.py --server.address 127.0.0.1 --server.port 8503 --browser.gatherUsageStats false --theme.base dark
