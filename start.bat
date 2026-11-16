@echo off
setlocal
cd /d "%~dp0"

set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"

if defined PYW (
  start "" "%PYW%" main.py %*
) else (
  start "" python main.py %*
)
exit /b 0
