@echo off
setlocal
cd /d "%~dp0"
echo Recording for 4 seconds - please speak now.
echo.
python main.py --test
echo.
pause
