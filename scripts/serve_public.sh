#!/usr/bin/env bash
# Serve GARUDA over a FREE Cloudflare quick-tunnel (macOS/Linux) — no card, no account.
#   bash scripts/serve_public.sh
# Requires: DASHBOARD_PASS set in .env, and cloudflared (macOS: brew install cloudflared).
# Prints an https://….trycloudflare.com URL — open it from any browser, enter the password.
set -euo pipefail
cd "$(dirname "$0")/.."

# venv + deps + .env
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q --upgrade pip >/dev/null 2>&1 || true
pip install -q -r requirements-dashboard.txt
[ -f .env ] || { cp .env.example .env; chmod 600 .env 2>/dev/null || true; }

# never expose without a password (the dashboard has ARM/KILL controls)
if ! grep -qE '^DASHBOARD_PASS=.+' .env; then
  echo "!! Set DASHBOARD_PASS=<strong password> in .env before exposing it. Aborting."
  exit 1
fi
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "!! cloudflared not installed.  macOS:  brew install cloudflared"
  exit 1
fi

# free port 8000 if a stale instance holds it — otherwise the tunnel would point at THAT
# (possibly password-LESS) instance instead of this protected one.
if lsof -ti tcp:8000 >/dev/null 2>&1; then
  echo ">> port 8000 busy — stopping the old instance first"
  lsof -ti tcp:8000 | xargs kill 2>/dev/null || true
  sleep 2
fi

# keep the machine awake (macOS 'caffeinate'); start the dashboard on localhost, backgrounded
CAFF=""; command -v caffeinate >/dev/null 2>&1 && CAFF="caffeinate -i"
echo ">> starting dashboard on 127.0.0.1:8000 (machine kept awake while this runs)"
$CAFF env PYTHONPATH=src DOTENV_PATH=.env python scripts/run_dashboard.py &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT INT TERM

# wait until it actually answers (a 401 from the password gate counts as "up")
for _ in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8000/ && break; sleep 1; done
if ! curl -s -o /dev/null http://127.0.0.1:8000/; then
  echo "!! dashboard failed to start (see errors above) — NOT opening the tunnel."
  exit 1
fi

echo ">> opening a free Cloudflare tunnel — share the https URL below (password required):"
cloudflared tunnel --url http://127.0.0.1:8000
