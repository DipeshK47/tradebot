# GARUDA — Setup (Windows)

Get the dashboard running and open it in a browser. Everything else (scanning, watchlist,
autorun, live feed) you do inside the dashboard.

---

## 1. Install Python
[python.org/downloads](https://python.org/downloads) → run the installer →
**tick “Add python.exe to PATH”** → Install Now.

## 2. Get the code
**github.com/DipeshK47/tradebot** → green **Code** → **Download ZIP** → right-click →
**Extract All** (e.g. to `C:\tradebot`).

## 3. Make your `.env`
In the folder, copy **`.env.example`** to a file named exactly **`.env`** and fill in:
```
UPSTOX_API_KEY=your_key
UPSTOX_API_SECRET=your_secret
UPSTOX_REDIRECT_URI=http://127.0.0.1:8000/auth/upstox/callback
DASHBOARD_USER=user
DASHBOARD_PASS=your_password
TRADING_MODE=paper
```
*(In Notepad, save as type “All Files”, name it `.env`. Register that redirect URI in your
Upstox app.)*

## 4. Open the site
Open the `scripts` folder → **double-click `local_run.bat`**. First run installs everything
(~1–2 min). When it says *“Dashboard starting at http://127.0.0.1:8000”*, open that in your
browser → **Login with Upstox**. Done — scan / autorun / watchlist are all in the UI.

## 5. (Optional) Open it from another device
Install the tunnel once: `winget install --id Cloudflare.cloudflared`, then
**double-click `scripts\serve_public.bat`** → it prints a public `https://…trycloudflare.com`
link → open it from any browser, enter your `DASHBOARD_USER` / `DASHBOARD_PASS`.

---

### On a Mac instead
```bash
git clone https://github.com/DipeshK47/tradebot.git && cd tradebot
bash scripts/local_run.sh        # run + open http://127.0.0.1:8000
```

### Notes
- Keep the laptop **on + plugged in** while you want it running (market hours: 9:15 AM–3:30 PM IST).
- Token expires 3:30 AM IST daily → re-open the site and **Login with Upstox** (scans work token-free).
- Never commit `.env` (it's git-ignored).
