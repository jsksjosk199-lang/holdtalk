@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   HoldTalk - installer
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  echo Install Python 3.10 or newer, and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

python bootstrap.py
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [FAILED] exit code %RC% - see the message above.
) else (
  echo  Done. Hold the middle mouse button and speak.
)
echo.
echo   start.bat  - run in background ^(no console^)
echo   test.bat   - record 4 seconds and show the result
pause
exit /b %RC%
