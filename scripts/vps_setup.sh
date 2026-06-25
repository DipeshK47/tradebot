#!/usr/bin/env bash
# ALGODESK — one-shot setup on a fresh Ubuntu Oracle Always-Free VM.
# Run as the default user (e.g. 'ubuntu'):
#   curl -fsSLO https://raw.githubusercontent.com/DipeshK47/tradebot/main/scripts/vps_setup.sh
#   bash vps_setup.sh
# The dashboard binds to 127.0.0.1 only — reach it from your laptop via an SSH tunnel
# (no public ports, so your 127.0.0.1 OAuth redirect keeps working unchanged).
set -euo pipefail

REPO="https://github.com/DipeshK47/tradebot.git"
APP="$HOME/tradebot"

echo "==> system packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git

echo "==> clone / update repo"
if [ -d "$APP/.git" ]; then git -C "$APP" pull --ff-only; else git clone "$REPO" "$APP"; fi
cd "$APP"

echo "==> venv + slim dashboard deps"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dashboard.txt

echo "==> .env"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "   created .env (chmod 600)"
fi

echo "==> systemd service (auto-restart, starts on boot)"
sudo tee /etc/systemd/system/algodesk.service >/dev/null <<UNIT
[Unit]
Description=ALGODESK dashboard
After=network-online.target
Wants=network-online.target
[Service]
WorkingDirectory=$APP
Environment=PYTHONPATH=src
Environment=DOTENV_PATH=$APP/.env
ExecStart=$APP/.venv/bin/python scripts/run_dashboard.py
Restart=always
RestartSec=5
User=$USER
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable algodesk

cat <<NEXT

================ DONE — 3 steps left ================
1) Add your Upstox app creds to .env:
     nano $APP/.env      # set UPSTOX_API_KEY and UPSTOX_API_SECRET, save (Ctrl-O, Enter, Ctrl-X)
     (Leave UPSTOX_REDIRECT_URI as http://127.0.0.1:8000/auth/upstox/callback)
2) Start it:
     sudo systemctl restart algodesk
     systemctl status algodesk --no-pager
3) From YOUR LAPTOP (not the VM), open a tunnel and the dashboard:
     ssh -L 8000:127.0.0.1:8000 $USER@<VM_PUBLIC_IP>
     # then browse to  http://127.0.0.1:8000  and click 'Login with Upstox'
=====================================================
NEXT
