"""Launch the command-center dashboard.  ->  http://127.0.0.1:8000"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("DOTENV_PATH", os.path.join(os.path.dirname(__file__), "..", ".env"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("tradingbot.web.server:app", host="127.0.0.1", port=port, log_level="warning")
