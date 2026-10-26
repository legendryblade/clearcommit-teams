@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM ClearCommit Teams — local demo (no cloud services needed)
REM
REM Starts the team API and the web UI on this machine, then opens the browser.
REM The desktop app is a separate window and can be running at the same time.
REM ---------------------------------------------------------------------------

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [ClearCommit] Creating virtual environment...
    py -3 -m venv ".venv"
    "%VENV_PY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
    "%VENV_PY%" -m pip install --disable-pip-version-check --quiet -r requirements-server.txt
)

REM The API talks to the same Supabase project the app uses. Everything else
REM (UI, sessions, permissions) runs on this machine.
set "CLEARCOMMIT_ALLOWED_ORIGINS=http://127.0.0.1:8765,http://localhost:8765,null"

echo [ClearCommit] Starting API on http://127.0.0.1:8770 ...
start "ClearCommit API" /min "%VENV_PY%" -m server

echo [ClearCommit] Starting web UI on http://127.0.0.1:8765 ...
start "ClearCommit Web" /min "%VENV_PY%" -m clearcommit_teams --web --port 8765

timeout /t 6 /nobreak >nul
start "" "http://127.0.0.1:8765/"

echo.
echo   Team workspace : http://127.0.0.1:8765/
echo   API            : http://127.0.0.1:8770/health
echo.
echo   Close the two minimised console windows to stop the services.
echo.
pause
