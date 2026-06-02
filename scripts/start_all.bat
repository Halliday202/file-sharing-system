@echo off
echo ============================================
echo   Distributed File Sharing System Launcher
echo ============================================
echo.

REM --- 1. Compile Java (if not already) ---
echo [Step 1] Compiling Java Storage Daemons...
cd /d "%~dp0\..\storage"
if not exist "out\StorageDaemon.class" (
    call build.bat
    if %ERRORLEVEL% neq 0 (
        echo Java compilation failed. Aborting.
        pause
        exit /b 1
    )
) else (
    echo Already compiled, skipping.
)
echo.

REM --- 2. Start Java storage nodes ---
echo [Step 2] Launching 3 Storage Daemons...
start "StorageNode-8001" java -cp out StorageDaemon 8001
start "StorageNode-8002" java -cp out StorageDaemon 8002
start "StorageNode-8003" java -cp out StorageDaemon 8003
timeout /t 2 /nobreak >nul
echo.

REM --- 3. Start Python manager ---
echo [Step 3] Launching Python Manager (port 9000)...
cd /d "%~dp0\..\manager"
start "PythonManager" python server.py
timeout /t 1 /nobreak >nul
echo.

REM --- 4. Start Streamlit dashboard ---
echo [Step 4] Launching Streamlit Dashboard...
start "Dashboard" streamlit run dashboard.py
echo.

echo ============================================
echo   All components launched!
echo   - Storage nodes: ports 8001, 8002, 8003
echo   - Manager:       port 9000
echo   - Dashboard:     http://localhost:8501
echo ============================================
echo.
echo Close this window or press any key to exit.
pause >nul
