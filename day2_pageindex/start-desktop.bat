@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   PageIndex RAG Agent - Desktop Launcher
echo ==================================================
echo.

REM Clear env vars that may interfere with electron
set "NODE_OPTIONS="
set "ELECTRON_RUN_AS_NODE="

REM ---- 1. Build frontend if not already built ----
if not exist "frontend\dist\index.html" (
    echo [1/3] First run: building frontend (~30s)...
    pushd frontend
    call npm install --no-audit --no-fund --loglevel=error
    if errorlevel 1 (
        echo [ERROR] npm install failed. Check Node.js environment.
        popd
        pause
        exit /b 1
    )
    call npm run build
    if errorlevel 1 (
        echo [ERROR] Frontend build failed.
        popd
        pause
        exit /b 1
    )
    popd
    echo [1/3] Frontend build complete.
) else (
    echo [1/3] Frontend already built, skip.
)

REM ---- 2. Check electron deps ----
if not exist "electron\node_modules\electron\dist\electron.exe" (
    echo [2/3] Installing electron dependencies...
    pushd electron
    call npm install --no-audit --no-fund --loglevel=error
    popd
) else (
    echo [2/3] Electron deps ready.
)

REM ---- 3. Launch desktop client (electron auto-starts python backend) ----
echo [3/3] Launching desktop client...
echo.
echo Tip: Close the window to exit. Backend will stop automatically.
echo --------------------------------------------------

cd /d "%~dp0electron"
set ELECTRON_PROD=1
".\node_modules\electron\dist\electron.exe" main.js

cd /d "%~dp0"
endlocal
