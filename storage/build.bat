@echo off
echo Compiling Java Storage Daemon...
javac -d out src\StorageDaemon.java src\ConnectionHandler.java src\PacketParser.java src\CryptoUtil.java src\PathSanitizer.java
if %ERRORLEVEL% neq 0 (
    echo Compilation failed.
    exit /b 1
)
echo Build successful. Run with: java -cp out StorageDaemon ^<port^>
