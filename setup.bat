@echo off
rem Refresh the dictionary catalog and download the default word lists.
setlocal
cd /d "%~dp0"

set "PY="
where py.exe >nul 2>nul && set "PY=py.exe"
if not defined PY where python.exe >nul 2>nul && set "PY=python.exe"

if not defined PY (
  echo [!] Python not found. Install Python 3.10+ and tick "Add to PATH".
  pause
  exit /b 1
)

%PY% "%~dp0fetch_dicts.py" %*
