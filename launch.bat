@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ClearCommit Teams] Creating isolated virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv ".venv"
    ) else (
        python -m venv ".venv"
    )
    if errorlevel 1 goto :error
)

"%VENV_PY%" -c "import webview" >nul 2>nul
if errorlevel 1 (
    echo [ClearCommit Teams] Installing desktop dependencies...
    "%VENV_PY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
    if errorlevel 1 goto :error
)

"%VENV_PY%" -m clearcommit_teams %*
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo [ClearCommit Teams] Startup failed. See README.md for troubleshooting.
pause
exit /b 1
