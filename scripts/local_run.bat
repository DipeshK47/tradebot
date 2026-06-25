@echo off
REM ===== Run ALGODESK on Windows =====
REM Requires Python (python.org, tick "Add python.exe to PATH" during install).
REM Just DOUBLE-CLICK this file. First run builds everything + makes .env; edit .env
REM (add your Upstox key/secret), then double-click again to launch.
setlocal
cd /d "%~dp0.."

where py >nul 2>nul && (set "PY=py") || (set "PY=python")

if not exist .venv (
  echo Creating virtual environment ^(one-time^)...
  %PY% -m venv .venv || (echo Could not create venv. Is Python installed + on PATH? & pause & exit /b 1)
)

call .venv\Scripts\activate.bat
echo Installing/updating dependencies ^(first run takes a minute^)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-dashboard.txt || (echo pip install failed. & pause & exit /b 1)

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo ============================================================
  echo  Created .env  --  now open it in Notepad and fill in:
  echo     UPSTOX_API_KEY=your_key
  echo     UPSTOX_API_SECRET=your_secret
  echo  Save it, then DOUBLE-CLICK this file again to start.
  echo  ^(Or copy your .env from your other laptop into this folder.^)
  echo ============================================================
  echo.
  pause
  exit /b 0
)

set "PYTHONPATH=src"
set "DOTENV_PATH=.env"
echo.
echo  Dashboard starting at  http://127.0.0.1:8000
echo  Open that in your browser. Close this window to stop.
echo.
python scripts\run_dashboard.py
pause
