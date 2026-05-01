@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.13+ and try again.
  pause
  exit /b 1
)

python -c "import pokercli" >nul 2>nul
if errorlevel 1 (
  echo Installing local project dependencies...
  python -m pip install -e .[dev]
  if errorlevel 1 (
    echo Installation failed.
    pause
    exit /b 1
  )
)

if "%~1"=="" (
  python -m pokercli play
  goto :done
)

set "command=%~1"
shift

if /i "%command%"=="play" (
  python -m pokercli play %*
  goto :done
)

if /i "%command%"=="setup" (
  python -m pokercli setup %*
  goto :done
)

if /i "%command%"=="simulate" (
  python -m pokercli simulate %*
  goto :done
)

if /i "%command%"=="replay" (
  python -m pokercli replay %*
  goto :done
)

echo Unknown command: %command%
echo.
echo Usage:
echo   play_poker.bat
echo   play_poker.bat play [options]
echo   play_poker.bat setup
echo   play_poker.bat simulate [options]
echo   play_poker.bat replay [options]
exit /b 1

:done
if errorlevel 1 (
  echo.
  echo The command exited with an error.
)

pause
exit /b %errorlevel%
