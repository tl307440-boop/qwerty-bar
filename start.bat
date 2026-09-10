@echo off
rem Launch Qwerty Bar without a console window.
setlocal
cd /d "%~dp0"

set "LAUNCH="
where pyw.exe >nul 2>nul && set "LAUNCH=pyw.exe"
if not defined LAUNCH where pythonw.exe >nul 2>nul && set "LAUNCH=pythonw.exe"

if not defined LAUNCH (
  echo [!] Python not found. Install Python 3.10+ and tick "Add to PATH".
  pause
  exit /b 1
)

if not exist "data\catalog.json" (
  echo First run: downloading dictionaries...
  call "%~dp0setup.bat"
)

start "" %LAUNCH% "%~dp0run.pyw"
