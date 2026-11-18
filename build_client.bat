@echo off
rem Build a portable Windows client: dist\QwertyBar.zip
rem Classmates unzip and double-click QwertyBar.exe — no Python install.
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
where py.exe >nul 2>nul && set "PY=py.exe"
if not defined PY where python.exe >nul 2>nul && set "PY=python.exe"

if not defined PY (
  echo [!] Python not found. Install Python 3.10+ and tick "Add to PATH".
  pause
  exit /b 1
)

echo [1/4] Installing PyInstaller...
%PY% -m pip install -q "pyinstaller>=6.0"
if errorlevel 1 (
  echo [!] pip install pyinstaller failed
  pause
  exit /b 1
)

if not exist "data\catalog.json" (
  echo [2/4] Downloading dictionary catalog...
  %PY% "%~dp0fetch_dicts.py"
  if errorlevel 1 (
    echo [!] fetch_dicts.py failed — check the network and retry.
    pause
    exit /b 1
  )
) else (
  echo [2/4] catalog.json already present
)

echo [3/4] Building QwertyBar.exe ...
%PY% -m PyInstaller --noconfirm --clean "%~dp0QwertyBar.spec"
if errorlevel 1 (
  echo [!] PyInstaller failed
  pause
  exit /b 1
)

set "OUT=%~dp0dist\QwertyBar"
if not exist "%OUT%\QwertyBar.exe" (
  echo [!] dist\QwertyBar\QwertyBar.exe was not created
  pause
  exit /b 1
)

copy /y "%~dp0LICENSE" "%OUT%\LICENSE.txt" >nul
copy /y "%~dp0使用说明.txt" "%OUT%\使用说明.txt" >nul

echo [4/4] Zipping...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -LiteralPath '%OUT%' -DestinationPath '%~dp0dist\QwertyBar.zip' -Force"
if errorlevel 1 (
  echo [!] zip failed
  pause
  exit /b 1
)

echo.
echo Done. Send this file to classmates:
echo   %~dp0dist\QwertyBar.zip
echo.
echo They unzip the folder and double-click QwertyBar.exe
echo No Python install needed.
echo.
pause
