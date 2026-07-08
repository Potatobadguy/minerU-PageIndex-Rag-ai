@echo off
cd /d c:\Work
git push --force work dev
echo.
echo Exit code: %ERRORLEVEL%
pause
