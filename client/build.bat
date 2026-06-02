@echo off
REM Build script for the C++ client using MinGW-w64 (scoop) and OpenSSL (scoop)
REM Adjust paths if your installations differ.

set MINGW_BIN=%USERPROFILE%\scoop\apps\mingw\current\bin
set OPENSSL_ROOT=%USERPROFILE%\scoop\apps\openssl\current

echo Compiling C++ client...
"%MINGW_BIN%\g++.exe" -std=c++17 -o client.exe ^
    src\main.cpp src\crypto.cpp src\packet.cpp src\network.cpp ^
    -I"%OPENSSL_ROOT%\include" -L"%OPENSSL_ROOT%\lib" ^
    -lssl -lcrypto -lws2_32

if %ERRORLEVEL% neq 0 (
    echo Build failed.
    exit /b 1
)

REM Copy OpenSSL DLLs next to the executable
copy /Y "%OPENSSL_ROOT%\libcrypto-4-x64.dll" . >nul
copy /Y "%OPENSSL_ROOT%\libssl-4-x64.dll" . >nul

echo Build successful: client.exe
