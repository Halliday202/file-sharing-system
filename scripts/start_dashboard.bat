@echo off
echo Starting Streamlit Dashboard...
echo.

cd /d "%~dp0\..\manager"

streamlit run dashboard.py
