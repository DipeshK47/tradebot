"""Configuration & secret loading.

Secrets come from environment variables (optionally seeded from a gitignored .env
file). They are NEVER hard-coded and never logged in full. Create your .env by
editing the file directly — do not paste secrets into chat.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | None = None) -> None:
    """Minimal .env loader (stdlib). Does NOT override already-set env vars."""
    p = Path(path or os.environ.get("DOTENV_PATH", ".env"))
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip()
        if val[:1] not in ("'", '"'):          # strip inline comment on unquoted values
            h = val.find(" #")
            if h != -1:
                val = val[:h]
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _mask(secret: str) -> str:
    if not secret:
        return "<unset>"
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}…{secret[-2:]}"


@dataclass
class UpstoxConfig:
    api_key: str = ""
    api_secret: str = ""
    redirect_uri: str = "http://127.0.0.1:8000/auth/upstox/callback"
    access_token: str = ""

    @classmethod
    def from_env(cls) -> "UpstoxConfig":
        load_dotenv()
        return cls(
            api_key=os.environ.get("UPSTOX_API_KEY", ""),
            api_secret=os.environ.get("UPSTOX_API_SECRET", ""),
            redirect_uri=os.environ.get("UPSTOX_REDIRECT_URI",
                                        "http://127.0.0.1:8000/auth/upstox/callback"),
            access_token=os.environ.get("UPSTOX_ACCESS_TOKEN", ""),
        )

    @property
    def has_token(self) -> bool:
        return bool(self.access_token)

    def __repr__(self) -> str:  # safe: never prints full secrets
        return (f"UpstoxConfig(api_key={_mask(self.api_key)}, "
                f"api_secret={_mask(self.api_secret)}, "
                f"access_token={_mask(self.access_token)}, "
                f"redirect_uri={self.redirect_uri!r})")
