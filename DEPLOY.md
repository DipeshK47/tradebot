# Deploying ALGODESK

## ⚠️ Not GitHub Pages
This is a **live FastAPI (Python) backend** — it scans markets, holds an Upstox
websocket, exchanges OAuth tokens server-side, and keeps secrets in `.env`.
**GitHub Pages serves only static files and cannot run any of this.** GitHub is for
source control; deploy the running app to a host that executes Python.

## Recommended: Oracle Cloud Always-Free VPS (ap-mumbai-1)
Always-on, ₹0, low latency to NSE — the original plan.

1. Create an **Always-Free** VM (Ampere/A1, Ubuntu), reserve a static public IP.
2. SSH in, then:
   ```bash
   sudo apt update && sudo apt install -y python3-venv git
   git clone https://github.com/DipeshK47/tradebot.git && cd tradebot
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env && chmod 600 .env   # then fill in API key/secret
   ```
3. **Upstox app console** → set the Redirect URI to your server's callback and put the
   SAME value in `.env`:
   ```
   UPSTOX_REDIRECT_URI=http://<your-static-ip>:8000/auth/upstox/callback
   ```
   (Use `https://yourdomain/...` once you add a domain + TLS.)
4. Run it (foreground test):
   ```bash
   PYTHONPATH=src DOTENV_PATH=.env python3 scripts/run_dashboard.py
   ```
   Open `http://<ip>:8000`, click **Login with Upstox** — the token is captured and
   saved to `.env` automatically (no daily `--code` step).

### Keep it always-on (systemd)
`/etc/systemd/system/algodesk.service`:
```ini
[Unit]
Description=ALGODESK dashboard
After=network-online.target
[Service]
WorkingDirectory=/home/ubuntu/tradebot
Environment=PYTHONPATH=src
Environment=DOTENV_PATH=/home/ubuntu/tradebot/.env
ExecStart=/home/ubuntu/tradebot/.venv/bin/python scripts/run_dashboard.py
Restart=always
User=ubuntu
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now algodesk
```
Lock the firewall to your IP (or front it with Caddy/Nginx + TLS + basic auth — the
dashboard has no user login of its own).

## Alternatives
- **Railway / Fly.io** — connect the GitHub repo, set env vars in their dashboard,
  deploy. Pick an *always-on* plan (a sleeping free tier drops the websocket).
- Any ₹400–600/mo micro-VPS (DigitalOcean/Linode) as a rock-solid fallback.

## Security reminders
- **Never commit `.env`** (it's gitignored). Secrets live only on the server.
- `chmod 600 .env`. The token write is atomic + 0600 already.
- Personal + immediate-family accounts only; broker-side stops; arm-live OFF by default.
