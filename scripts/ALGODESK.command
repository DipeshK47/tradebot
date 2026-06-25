#!/bin/bash
# Double-click this to start ALGODESK and open it in your browser (macOS).
# (First run installs everything; if it creates .env, fill it in and double-click again.)
cd "$(dirname "$0")/.." || exit 1
( sleep 5; open "http://127.0.0.1:8000" >/dev/null 2>&1 ) &   # open the browser once it's up
exec bash scripts/local_run.sh
