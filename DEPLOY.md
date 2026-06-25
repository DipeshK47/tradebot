# Deploying ALGODESK

## ⚠️ Not GitHub Pages
This is a **live FastAPI (Python) backend** — it scans markets, holds an Upstox
websocket, exchanges OAuth tokens server-side, and keeps secrets in `.env`.
**GitHub Pages serves only static files and cannot run any of this.** GitHub is for
source control; deploy the running app to a host that executes Python.

## Recommended: Oracle Cloud Always-Free VPS (Mumbai/Hyderabad)
Always-on, ₹0, low latency to NSE. **Access model: SSH tunnel** — the server binds to
`127.0.0.1` only, so NO public port is exposed and your `http://127.0.0.1:8000/...`
OAuth redirect keeps working unchanged. The bot runs 24/7 on the VM; you tunnel in
from your laptop only to view the dashboard / log in.

### A. Create the VM (Oracle console)
1. Sign up at cloud.oracle.com (card for ID check only; Always-Free = ₹0). **Region:
   ap-mumbai-1** (or ap-hyderabad-1).
2. **Compute → Instances → Create**. Image **Canonical Ubuntu 22.04**. Shape:
   **VM.Standard.A1.Flex** (ARM, free up to 4 OCPU/24 GB — best) or, if A1 capacity is
   unavailable, **VM.Standard.E2.1.Micro** (1 OCPU/1 GB — always available; enough for
   the dashboard).
3. **SSH keys**: on your laptop `ssh-keygen -t ed25519 -f ~/.ssh/algodesk`, upload
   `~/.ssh/algodesk.pub`. Create the instance.
4. **Networking → Reserve a static public IP** (convert the ephemeral IP to reserved).
5. Leave the firewall CLOSED (only SSH/22). No need to open 8000 — we tunnel.

### B. Configure the app (one command on the VM)
SSH in: `ssh -i ~/.ssh/algodesk ubuntu@<VM_IP>`, then:
```bash
curl -fsSLO https://raw.githubusercontent.com/DipeshK47/tradebot/main/scripts/vps_setup.sh
bash vps_setup.sh
```
This installs Python, clones the repo, makes a venv with the slim deps
(`requirements-dashboard.txt`), creates `.env` (chmod 600), and installs a systemd
service. Then:
```bash
nano ~/tradebot/.env          # set UPSTOX_API_KEY + UPSTOX_API_SECRET (leave redirect as-is)
sudo systemctl restart algodesk
systemctl status algodesk --no-pager
```

### C. Open the dashboard (from your laptop)
```bash
ssh -i ~/.ssh/algodesk -L 8000:127.0.0.1:8000 ubuntu@<VM_IP>
```
Browse to `http://127.0.0.1:8000` → **Login with Upstox** (the token is captured and
saved to `.env` on the VM automatically). Make sure `http://127.0.0.1:8000/auth/upstox/callback`
is registered in your Upstox app console (it already is).

Notes: token expires ~3:30 AM IST daily → re-open the tunnel and click Login (the
public historical/intraday scans keep working token-free meanwhile). Autorun is OFF
after a restart — turn it on in the UI each session (persistent autostart is a TODO).

## Alternatives
- **Railway / Fly.io** — connect the GitHub repo, set env vars in their dashboard,
  deploy. Pick an *always-on* plan (a sleeping free tier drops the websocket).
- Any ₹400–600/mo micro-VPS (DigitalOcean/Linode) as a rock-solid fallback.

## Security reminders
- **Never commit `.env`** (it's gitignored). Secrets live only on the server.
- `chmod 600 .env`. The token write is atomic + 0600 already.
- Personal + immediate-family accounts only; broker-side stops; arm-live OFF by default.
