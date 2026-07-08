@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   PageIndex RAG Agent - Dev Mode (Hot Reload)
echo ==================================================
echo.
echo Starting Vite + Electron + Python backend
echo Close Electron window to exit all
echo --------------------------------------------------

set "NODE_OPTIONS="
set "ELECTRON_RUN_AS_NODE="
cd /d "%~dp0frontend"
call npm run electron:dev

endlocal
