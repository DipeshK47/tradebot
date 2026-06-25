#!/usr/bin/env bash
# Run ALGODESK on ANY Mac/Linux laptop. First time on a new machine:
#   git clone https://github.com/DipeshK47/tradebot.git && cd tradebot
#   bash scripts/local_run.sh          # builds venv + deps, creates .env (then edit it)
#   bash scripts/local_run.sh          # runs the dashboard
# Open http://127.0.0.1:8000 and click "Login with Upstox".
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only 2>/dev/null || true        # stay up to date if it's a clone

if [ ! -d .venv ]; then
  echo ">> creating venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements-dashboard.txt

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env 2>/dev/null || true
  echo ""
  echo ">> Created .env — edit it to add your UPSTOX_API_KEY and UPSTOX_API_SECRET,"
  echo "   then run this script again to launch. (Or copy your .env from another laptop.)"
  exit 0
fi

echo ">> starting dashboard at http://127.0.0.1:8000  (Ctrl-C to stop)"
exec env PYTHONPATH=src DOTENV_PATH=.env python3 scripts/run_dashboard.py
