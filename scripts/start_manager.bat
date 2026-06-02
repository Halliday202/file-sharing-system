@echo off
echo Starting Python Manager Server...
echo.

cd /d "%~dp0\..\manager"

python server.py
