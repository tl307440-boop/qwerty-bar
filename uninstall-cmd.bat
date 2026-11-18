@echo off
rem Remove the global `qwerty` command installed by install-cmd.bat
setlocal EnableExtensions

set "SHIM_DIR=%LOCALAPPDATA%\qwerty-bar"
set "SHIM=%SHIM_DIR%\qwerty.cmd"

if exist "%SHIM%" (
  del /f /q "%SHIM%"
  echo [ok] removed %SHIM%
) else (
  echo [..] shim not found
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = $env:LOCALAPPDATA + '\qwerty-bar';" ^
  "$userPath = [Environment]::GetEnvironmentVariable('Path','User');" ^
  "if ([string]::IsNullOrEmpty($userPath)) { Write-Host '[..] user PATH empty'; exit 0 };" ^
  "$parts = $userPath -split ';' | Where-Object { $_ -ne '' -and $_.TrimEnd('\') -ne $dir.TrimEnd('\') };" ^
  "$newPath = $parts -join ';';" ^
  "[Environment]::SetEnvironmentVariable('Path', $newPath, 'User');" ^
  "Write-Host '[ok] removed from user PATH:' $dir;" ^
  "if ((Test-Path $dir) -and -not (Get-ChildItem $dir -Force -ErrorAction SilentlyContinue)) { Remove-Item $dir -Force }"

echo.
echo Open a NEW terminal for PATH changes to take effect.
echo.
pause
