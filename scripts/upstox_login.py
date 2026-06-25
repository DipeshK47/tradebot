#!/usr/bin/env python3
"""Upstox daily-token helper — keeps the access token OUT of the chat / shell history.

Upstox access tokens die ~3:30 AM IST every day and there is NO refresh token, so
you re-auth each morning. Two steps:

  1) Print the login URL, open it in a browser, log in (mobile + PIN/TOTP):
         python3 scripts/upstox_login.py
     Upstox redirects to your REDIRECT_URI with  ?code=XXXXXXXX  in the address bar.

  2) Exchange that code for a token and write it straight into .env:
         python3 scripts/upstox_login.py --code XXXXXXXX

It rewrites only the UPSTOX_ACCESS_TOKEN line in .env (creating it if missing) and
prints the token LENGTH only — never the token itself. Then restart the dashboard.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"
AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _load_env() -> dict:
    env: dict[str, str] = {}
    if not ENV.exists():
        return env
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v and v[0] not in "\"'" and " #" in v:   # strip inline comment on unquoted value
            v = v.split(" #")[0].strip()
        env[k.strip()] = v.strip("\"'")
    return env


def _write_token(token: str) -> None:
    """Replace (or append) the UPSTOX_ACCESS_TOKEN line, leaving everything else intact."""
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    out, found = [], False
    for line in lines:
        if line.strip().startswith("UPSTOX_ACCESS_TOKEN="):
            out.append(f"UPSTOX_ACCESS_TOKEN={token}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"UPSTOX_ACCESS_TOKEN={token}")
    ENV.write_text("\n".join(out) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="auth code from the redirect URL (?code=...)")
    args = ap.parse_args()

    env = _load_env()
    api_key = env.get("UPSTOX_API_KEY", "")
    api_secret = env.get("UPSTOX_API_SECRET", "")
    redirect = env.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:3000/callback")
    if not api_key or not api_secret:
        print("ERROR: UPSTOX_API_KEY / UPSTOX_API_SECRET missing in .env", file=sys.stderr)
        return 2

    if not args.code:
        url = (f"{AUTH_URL}?response_type=code&client_id={urllib.parse.quote(api_key)}"
               f"&redirect_uri={urllib.parse.quote(redirect)}")
        print("\n1) Open this URL in a browser and log in to Upstox:\n")
        print("   " + url + "\n")
        print(f"2) You'll be redirected to {redirect}?code=XXXXXXXX  (the page may show an")
        print("   error — that's fine, the browser is not running a server). Copy the code, then:\n")
        print("   python3 scripts/upstox_login.py --code XXXXXXXX\n")
        return 0

    body = urllib.parse.urlencode({
        "code": args.code, "client_id": api_key, "client_secret": api_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json", "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR: token exchange HTTP {e.code}: {e.read().decode(errors='replace')[:300]}",
              file=sys.stderr)
        return 1
    token = data.get("access_token")
    if not token:
        print(f"ERROR: no access_token in response: {str(data)[:300]}", file=sys.stderr)
        return 1
    _write_token(token)
    print(f"OK — wrote UPSTOX_ACCESS_TOKEN to .env (length {len(token)}).")
    print("Now restart the dashboard so it picks up the new token.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
