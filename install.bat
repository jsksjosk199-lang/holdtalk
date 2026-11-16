@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   SenseVoice IME - installer
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  echo Install Python 3.10 or newer, and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [1/3] Installing dependencies ...
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [2/3] Downloading model ^(~230 MB^) ...
python download_model.py
if errorlevel 1 goto :fail

echo.
echo [3/3] Checking audio input devices ...
python main.py --devices

echo.
echo --------------------------------------------
echo Done.
echo   start.bat  - run in background (no console)
echo   test.bat   - record 4 seconds and show result
echo   tools\setup_autostart.py  - start with Windows
echo --------------------------------------------
pause
exit /b 0

:fail
echo.
echo [FAILED] See messages above.
pause
exit /b 1
