@echo off
echo Starting Java Storage Daemons...
echo.

cd /d "%~dp0\..\storage"

echo [1/3] Starting node on port 8001...
start "StorageNode-8001" java -cp out StorageDaemon 8001

echo [2/3] Starting node on port 8002...
start "StorageNode-8002" java -cp out StorageDaemon 8002

echo [3/3] Starting node on port 8003...
start "StorageNode-8003" java -cp out StorageDaemon 8003

echo.
echo All 3 storage daemons launched (ports 8001, 8002, 8003).
echo Close the individual windows to stop them.
