"""Upstox market-data adapter (read-only).

Fetches historical candles via the Upstox v2 REST API using only the stdlib, so it
runs without extra dependencies once a daily access token is present in the env.

UNVERIFIED until run against a live token — endpoint shapes follow the documented
v2 API and will be validated on the first real fetch.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

from ..strategies.base import Candle

BASE = "https://api.upstox.com/v2"
BASE_V3 = "https://api.upstox.com/v3"
VALID_INTERVALS = {"1minute", "30minute", "day", "week", "month"}  # Upstox v2

# Browser User-Agent — Upstox sits behind Cloudflare, which 1010-blocks the
# default python-urllib agent.
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Our timeframe label -> Upstox v3 (unit, interval). v3 supports per-minute and
# hourly candles (the v2 historical API only offers 1minute/30minute/day).
TIMEFRAME_MAP = {
    "1min": ("minutes", 1), "5min": ("minutes", 5), "15min": ("minutes", 15),
    "30min": ("minutes", 30), "1hour": ("hours", 1), "day": ("days", 1),
}

# --- client-side throttle: Upstox allows 50/sec, 500/min, 2000/30min per user.
# Stay well under the first two gates; the 30-min budget is protected by caching.
_MAX_PER_SEC = 8
_MAX_PER_MIN = 400
_rate_lock = threading.Lock()
_req_times: deque = deque()          # monotonic timestamps of the last minute's requests


def _throttle():
    while True:
        with _rate_lock:
            now = time.monotonic()
            while _req_times and now - _req_times[0] > 60:
                _req_times.popleft()
            in_last_sec = sum(1 for t in _req_times if now - t < 1)
            if in_last_sec < _MAX_PER_SEC and len(_req_times) < _MAX_PER_MIN:
                _req_times.append(now)
                return
        time.sleep(0.1)


# --- disk cache: historical candles can't change during the day (today's bars come
# from the intraday endpoint), so re-scans shouldn't re-download 14-80 days of data.
_CACHE_DIR = Path(os.environ.get(
    "CANDLE_CACHE_DIR",
    Path(__file__).resolve().parents[3] / "data" / "cache" / "candles"))
_HIST_TTL = 6 * 3600      # seconds; keys include from/to dates, so they roll daily anyway
_INTRA_TTL = 90           # forming bars: absorb back-to-back scans, stay near-live


def _cache_key(*parts) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", "_".join(str(p) for p in parts))


def _cache_get(key: str, ttl: float):
    p = _CACHE_DIR / f"{key}.json"
    try:
        if time.time() - p.stat().st_mtime < ttl:
            return json.loads(p.read_text())
    except (OSError, ValueError):
        pass
    return None


def _cache_put(key: str, rows: list) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_DIR / f".{key}.tmp"
        tmp.write_text(json.dumps(rows))
        tmp.replace(_CACHE_DIR / f"{key}.json")
    except OSError:
        pass


class UpstoxData:
    def __init__(self, access_token: str = "", timeout: float = 20.0):
        # Historical candle endpoints are PUBLIC (no token needed); a valid token
        # is only required for quotes / live feed / trading.
        self._token = access_token
        self._timeout = timeout

    def _get(self, url: str) -> dict:
        headers = {"Accept": "application/json", "User-Agent": _UA}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(url, headers=headers)
        for attempt in range(3):
            _throttle()
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:      # rate limited -> back off and retry
                    try:
                        wait = float(e.headers.get("Retry-After", ""))
                    except (TypeError, ValueError):
                        wait = 2.0 * (attempt + 1)
                    time.sleep(min(wait, 15.0))
                    continue
                body = e.read().decode(errors="replace")
                raise RuntimeError(f"Upstox HTTP {e.code}: {body[:300]}") from e
        raise RuntimeError("Upstox HTTP 429: rate limited")

    @staticmethod
    def _parse_candles(rows: list) -> list[Candle]:
        out: list[Candle] = []
        for c in rows:
            # row = [timestamp, open, high, low, close, volume, open_interest]
            out.append(Candle(datetime.fromisoformat(c[0]),
                              float(c[1]), float(c[2]), float(c[3]),
                              float(c[4]), float(c[5])))
        out.reverse()   # Upstox returns newest-first -> make chronological
        return out

    def candles(self, instrument_key: str, timeframe: str,
                from_date: str, to_date: str) -> list[Candle]:
        """v3 historical candles on our timeframe labels (1min/5min/15min/30min/
        1hour/day). instrument_key e.g. 'NSE_EQ|INE002A01018'; dates 'YYYY-MM-DD'."""
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAME_MAP)}")
        unit, interval = TIMEFRAME_MAP[timeframe]
        key = _cache_key("hist", instrument_key, unit, interval, from_date, to_date)
        rows = _cache_get(key, _HIST_TTL)
        if rows is None:
            ik = urllib.parse.quote(instrument_key, safe="")
            url = f"{BASE_V3}/historical-candle/{ik}/{unit}/{interval}/{to_date}/{from_date}"
            rows = self._get(url).get("data", {}).get("candles", [])
            _cache_put(key, rows)
        return self._parse_candles(rows)

    def ltp(self, instrument_keys: list[str]) -> dict:
        """Batch last-traded-price: {instrument_key: last_price}. Needs a valid token.
        Off-market this returns the previous close (still the 'current price')."""
        out: dict = {}
        for i in range(0, len(instrument_keys), 400):     # API caps keys per request
            chunk = instrument_keys[i:i + 400]
            q = urllib.parse.quote(",".join(chunk))
            try:
                data = self._get(f"{BASE}/market-quote/ltp?instrument_key={q}").get("data", {})
            except Exception:
                continue
            for v in data.values():
                tok, lp = v.get("instrument_token"), v.get("last_price")
                if tok is not None and lp is not None:
                    out[tok] = lp
        return out

    def intraday(self, instrument_key: str, timeframe: str) -> list[Candle]:
        """Today's (current-session) intraday candles (v3) — the latest forming bars."""
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAME_MAP)}")
        unit, interval = TIMEFRAME_MAP[timeframe]
        key = _cache_key("intra", instrument_key, unit, interval)
        rows = _cache_get(key, _INTRA_TTL)
        if rows is None:
            ik = urllib.parse.quote(instrument_key, safe="")
            url = f"{BASE_V3}/historical-candle/intraday/{ik}/{unit}/{interval}"
            rows = self._get(url).get("data", {}).get("candles", [])
            _cache_put(key, rows)
        return self._parse_candles(rows)

    def historical_candles(self, instrument_key: str, interval: str,
                           from_date: str, to_date: str) -> list[Candle]:
        """instrument_key e.g. 'NSE_EQ|INE002A01018'; dates 'YYYY-MM-DD'.

        Returns candles in chronological order (Upstox sends newest-first).
        """
        if interval not in VALID_INTERVALS:
            raise ValueError(f"interval must be one of {sorted(VALID_INTERVALS)}")
        ik = urllib.parse.quote(instrument_key, safe="")
        url = f"{BASE}/historical-candle/{ik}/{interval}/{to_date}/{from_date}"
        data = self._get(url)
        rows = data.get("data", {}).get("candles", [])
        out: list[Candle] = []
        for c in rows:
            # row = [timestamp, open, high, low, close, volume, open_interest]
            out.append(Candle(datetime.fromisoformat(c[0]),
                              float(c[1]), float(c[2]), float(c[3]),
                              float(c[4]), float(c[5])))
        out.reverse()
        return out
