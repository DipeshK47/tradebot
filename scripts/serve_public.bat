@echo off
REM ===== Run GARUDA publicly via a FREE Cloudflare tunnel (Windows) =====
REM Double-click this file. Requires: Python on PATH, DASHBOARD_PASS set in .env, and
REM cloudflared (install once:  winget install --id Cloudflare.cloudflared).
REM It runs the dashboard (scans + Telegram alerts) AND prints a public https URL.
setlocal
cd /d "%~dp0.."

where py >nul 2>nul && (set "PY=py") || (set "PY=python")
if not exist .venv ( echo Creating environment (one-time)... & %PY% -m venv .venv )
call .venv\Scripts\activate.bat
echo Installing/updating dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-dashboard.txt

if not exist .env (
  copy .env.example .env >nul
  echo Created .env -- open it in Notepad, fill in your keys, then run this file again.
  pause & exit /b
)

findstr /r /b /c:"DASHBOARD_PASS=..*" .env >nul || (
  echo !! Set DASHBOARD_PASS in .env before exposing the dashboard. Aborting.
  pause & exit /b
)
where cloudflared >nul 2>nul || (
  echo !! cloudflared not installed. Run once:  winget install --id Cloudflare.cloudflared
  pause & exit /b
)

REM free port 8000 if a stale instance holds it
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>nul

set "PYTHONPATH=src"
set "DOTENV_PATH=.env"
echo Starting dashboard in a background window...
start "GARUDA" /min cmd /c "%CD%\.venv\Scripts\python.exe scripts\run_dashboard.py"
timeout /t 6 >nul

echo.
echo Opening a free Cloudflare tunnel -- share the https URL below (password required):
cloudflared tunnel --url http://127.0.0.1:8000
pause
