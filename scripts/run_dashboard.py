"""Launch the command-center dashboard.  ->  http://127.0.0.1:8000

HOST=127.0.0.1 (default) = local only. To open it from ANOTHER machine (LAN or via a
tunnel) set HOST=0.0.0.0 — allowed ONLY when DASHBOARD_PASS is set, since the dashboard
has ARM/KILL/scan controls and must not be exposed unauthenticated.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("DOTENV_PATH", os.path.join(os.path.dirname(__file__), "..", ".env"))

from tradingbot.config import load_dotenv  # noqa: E402

load_dotenv()                                # so HOST / DASHBOARD_PASS from .env are visible here

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    if host != "127.0.0.1" and not os.environ.get("DASHBOARD_PASS"):
        raise SystemExit(
            f"Refusing to bind {host} without DASHBOARD_PASS set — the dashboard has "
            "ARM/KILL controls. Add DASHBOARD_USER + DASHBOARD_PASS to .env first.")
    uvicorn.run("tradingbot.web.server:app", host=host, port=port, log_level="warning")
