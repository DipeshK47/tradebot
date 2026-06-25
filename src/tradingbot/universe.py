"""Tradable-universe / segment definitions for the scanner's top-level filter.

Segments map to a list of symbols to scan. The constituent lists below are SEED
data — at runtime they must be refreshed from the Upstox instrument master + the
NSE index-constituent files (memberships change). Marked clearly so we don't ship
a stale hardcoded list to production.
"""
from __future__ import annotations

from enum import Enum


class Segment(str, Enum):
    NIFTY50 = "NIFTY50"
    BANKNIFTY = "BANKNIFTY"
    FNO = "FNO"              # all F&O (futures-eligible) stocks
    ALL_STOCKS = "ALL_STOCKS"
    OPTIONS = "OPTIONS"
    INDEX = "INDEX"          # the indices themselves


# --- SEED constituent lists (refresh from instrument master at runtime) ---
BANKNIFTY_STOCKS = [
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANKBARODA", "PNB", "AUBANK", "FEDERALBNK", "IDFCFIRSTB", "CANBK",
]

# Representative subset only — NOT the full 50. Load the real list at runtime.
NIFTY50_STOCKS_SEED = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "LT", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "AXISBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI",
]

INDICES = ["NIFTY 50", "NIFTY BANK"]


def resolve_universe(segment: Segment,
                     all_stocks: list[str] | None = None,
                     fno_stocks: list[str] | None = None,
                     options: list[str] | None = None) -> list[str]:
    """Resolve a segment to the list of symbols to scan.

    The dynamic lists (all_stocks / fno_stocks / options) come from the live
    instrument master; the index/bank seed lists are fallbacks.
    """
    if segment is Segment.BANKNIFTY:
        return list(BANKNIFTY_STOCKS)
    if segment is Segment.NIFTY50:
        return list(NIFTY50_STOCKS_SEED)
    if segment is Segment.INDEX:
        return list(INDICES)
    if segment is Segment.FNO:
        return list(fno_stocks or [])
    if segment is Segment.OPTIONS:
        return list(options or [])
    if segment is Segment.ALL_STOCKS:
        return list(all_stocks or [])
    return []


# --- Full instrument-master loader (downloads the live Upstox NSE master) ---
import gzip as _gzip          # noqa: E402
import json as _json          # noqa: E402
import urllib.request as _req  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_CACHE = _Path(__file__).resolve().parents[2] / "data" / "cache" / "nse_equities.json"

NIFTY50_FULL = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "LT", "SBIN",
    "BHARTIARTL", "KOTAKBANK", "AXISBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI",
    "SUNPHARMA", "NTPC", "TATAMOTORS", "HCLTECH", "TITAN", "POWERGRID", "ULTRACEMCO",
    "ASIANPAINT", "ONGC", "TATASTEEL", "NESTLEIND", "M&M", "ADANIENT", "JSWSTEEL",
    "WIPRO", "BAJAJFINSV", "COALINDIA", "ADANIPORTS", "GRASIM", "HINDALCO", "TECHM",
    "BPCL", "DRREDDY", "BRITANNIA", "CIPLA", "EICHERMOT", "INDUSINDBK", "DIVISLAB",
    "HEROMOTOCO", "APOLLOHOSP", "BAJAJ-AUTO", "TATACONSUM", "SBILIFE", "HDFCLIFE",
    "LTIM", "SHRIRAMFIN",
]


_CACHE_IDX = _CACHE.parent / "nse_indices.json"
_MASTER_MEMO = None


def _load_master():
    """Download + parse the NSE instrument master once per process."""
    global _MASTER_MEMO
    if _MASTER_MEMO is None:
        raw = _req.urlopen(_req.Request(_MASTER_URL, headers={"User-Agent": _UA}), timeout=90).read()
        _MASTER_MEMO = _json.loads(_gzip.decompress(raw))
    return _MASTER_MEMO


def load_equities(force: bool = False) -> dict:
    """{trading_symbol: instrument_key} for all ~2,400 NSE equities (cached to disk)."""
    if not force and _CACHE.exists():
        try:
            return _json.loads(_CACHE.read_text())
        except Exception:
            pass
    eq = {d["trading_symbol"]: d["instrument_key"] for d in _load_master()
          if d.get("segment") == "NSE_EQ" and d.get("instrument_type") == "EQ"}
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(_json.dumps(eq))
    return eq


def load_indices(force: bool = False) -> dict:
    """{trading_symbol: instrument_key} for NSE indices (Nifty 50, Nifty Bank, ...)."""
    if not force and _CACHE_IDX.exists():
        try:
            return _json.loads(_CACHE_IDX.read_text())
        except Exception:
            pass
    idx = {d["trading_symbol"]: d["instrument_key"] for d in _load_master()
           if d.get("segment") == "NSE_INDEX"}
    _CACHE_IDX.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_IDX.write_text(_json.dumps(idx))
    return idx


_MASTER_URL_BSE = "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz"
_CACHE_BSE_IDX = _CACHE.parent / "bse_indices.json"
# Used only if the BSE master download fails — the keys are verified-working (public history).
_BSE_IDX_FALLBACK = {"SENSEX": "BSE_INDEX|SENSEX", "BANKEX": "BSE_INDEX|BANKEX"}
_BSE_MASTER_MEMO = None


def _load_bse_master():
    """Download + parse the BSE instrument master once per process (BSE indices + BSE F&O)."""
    global _BSE_MASTER_MEMO
    if _BSE_MASTER_MEMO is None:
        raw = _req.urlopen(_req.Request(_MASTER_URL_BSE, headers={"User-Agent": _UA}),
                           timeout=90).read()
        _BSE_MASTER_MEMO = _json.loads(_gzip.decompress(raw))
    return _BSE_MASTER_MEMO


def load_bse_indices(force: bool = False) -> dict:
    """{trading_symbol: instrument_key} for BSE indices (SENSEX, BANKEX, ...). The NSE
    master has no BSE names, so SENSEX is invisible without this. Cached to disk."""
    if not force and _CACHE_BSE_IDX.exists():
        try:
            return _json.loads(_CACHE_BSE_IDX.read_text())
        except Exception:
            pass
    try:
        idx = {d["trading_symbol"]: d["instrument_key"] for d in _load_bse_master()
               if d.get("segment") == "BSE_INDEX" and d.get("trading_symbol")}
    except Exception:
        idx = {}
    if idx:                                  # cache ONLY a real, successful download
        try:
            _CACHE_BSE_IDX.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_BSE_IDX.write_text(_json.dumps(idx))
        except Exception:
            pass
        return idx
    return dict(_BSE_IDX_FALLBACK)           # transient failure -> serve fallback, never persist it


def segment_symbols(segment: str, equities: dict) -> list:
    """Resolve a dashboard segment label to the list of equity symbols to scan."""
    if segment == "All stocks":
        return sorted(equities)
    if segment == "Bank Nifty":
        return [s for s in BANKNIFTY_STOCKS if s in equities]
    # "Nifty 50" (also the fallback for F&O / Options / Indices until those land)
    return [s for s in NIFTY50_FULL if s in equities]


_CACHE_FO = _CACHE.parent / "nse_fo_recs4.json"   # v4: now includes BSE index F&O (SENSEX etc.)
_CACHE_FNO = _CACHE.parent / "nse_fno.json"
_FO_MEMO = None


def _bse_index_fo() -> list:
    """BSE index F&O — SENSEX / BANKEX / SENSEX50 options (CE/PE) + futures — as standard
    records, so they flow into the options universe (e.g. SENSEX options in Index Options ATM).
    underlying_type forced to 'INDEX' (these are all index derivatives)."""
    try:
        return [[d["trading_symbol"], d["instrument_key"], d["instrument_type"], d.get("expiry"),
                 d.get("underlying_symbol"), "INDEX", d.get("underlying_key"), d.get("strike_price")]
                for d in _load_bse_master()
                if d.get("segment") == "BSE_FO" and d.get("instrument_type") in ("CE", "PE", "FUT")
                and str(d.get("underlying_key", "")).startswith("BSE_INDEX|")]
    except Exception:
        return []


def _fo_records(force: bool = False) -> list:
    """[[symbol, key, instrument_type, expiry_ms, underlying, underlying_type, underlying_key,
    strike], ...] for NSE_FO + BSE index F&O options (CE/PE) + futures (FUT). Cached with ALL
    expiries (stable); the current-expiry filter is applied at read time so it rolls forward."""
    global _FO_MEMO
    if _FO_MEMO is not None and not force:
        return _FO_MEMO
    if not force and _CACHE_FO.exists():
        try:
            _FO_MEMO = _json.loads(_CACHE_FO.read_text())
            return _FO_MEMO
        except Exception:
            pass
    nse = [[d["trading_symbol"], d["instrument_key"], d["instrument_type"], d.get("expiry"),
            d.get("underlying_symbol"), d.get("underlying_type"), d.get("underlying_key"),
            d.get("strike_price")]
           for d in _load_master()
           if d.get("segment") == "NSE_FO" and d.get("instrument_type") in ("CE", "PE", "FUT")]
    _FO_MEMO = nse + _bse_index_fo()        # fold in SENSEX/BANKEX/SENSEX50 options
    _CACHE_FO.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FO.write_text(_json.dumps(_FO_MEMO))
    return _FO_MEMO


def _current_expiry(recs: list) -> list:
    """Keep only each underlying's NEAREST upcoming expiry (records: expiry@3, underlying@4)."""
    import datetime as _dt
    ist = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
    cutoff = int(_dt.datetime.now(ist).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    nearest: dict = {}
    for r in recs:
        exp, und = r[3], r[4]
        if exp is None or exp < cutoff:
            continue
        if und not in nearest or exp < nearest[und]:
            nearest[und] = exp
    return [r for r in recs if r[3] is not None and r[3] >= cutoff and nearest.get(r[4]) == r[3]]


def load_fo(kind: str, current_expiry_only: bool = True, force: bool = False) -> dict:
    """{trading_symbol: instrument_key}. kind: 'options' | 'index_options' |
    'stock_options' | 'futures'. Current (nearest upcoming) expiry by default."""
    recs = _fo_records(force)
    if kind == "futures":
        sel = [r for r in recs if r[2] == "FUT"]
    elif kind == "index_options":
        sel = [r for r in recs if r[2] in ("CE", "PE") and r[5] == "INDEX"]
    elif kind == "stock_options":
        sel = [r for r in recs if r[2] in ("CE", "PE") and r[5] != "INDEX"]
    else:  # all options
        sel = [r for r in recs if r[2] in ("CE", "PE")]
    if current_expiry_only:
        sel = _current_expiry(sel)
    return {r[0]: r[1] for r in sel}


def load_options(force: bool = False, current_expiry_only: bool = True) -> dict:
    """All option contracts (CE/PE), current expiry by default."""
    return load_fo("options", current_expiry_only, force)


def load_fno_underlyings(force: bool = False) -> list:
    """Underlying symbols that have futures (the F&O tradable stock/index list, ~220)."""
    if not force and _CACHE_FNO.exists():
        try:
            return _json.loads(_CACHE_FNO.read_text())
        except Exception:
            pass
    unds = sorted({d.get("underlying_symbol") for d in _load_master()
                   if d.get("segment") == "NSE_FO" and d.get("instrument_type") == "FUT"
                   and d.get("underlying_symbol")})
    _CACHE_FNO.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FNO.write_text(_json.dumps(unds))
    return unds


def option_underlying_map() -> dict:
    """{option trading_symbol: underlying instrument_key} for all CE/PE — used to
    pair an option with its underlying for the dual-RSI options screen."""
    return {r[0]: r[6] for r in _fo_records() if r[2] in ("CE", "PE") and r[6]}


def option_underlying_keys() -> list:
    """Distinct underlying instrument keys across all options (for spot LTP lookup)."""
    return sorted({r[6] for r in _fo_records() if r[2] in ("CE", "PE") and r[6]})


def atm_options(spots: dict, n_strikes: int = 5, kind: str = "options",
                current_expiry_only: bool = True) -> dict:
    """{option symbol: key} for strikes within ±n_strikes of the at-the-money strike
    per underlying. spots = {underlying_key: spot_price}. kind: options|index_options|
    stock_options. Shrinks the option universe to the near-the-money, current-expiry set."""
    recs = [r for r in _fo_records() if r[2] in ("CE", "PE")]
    if kind == "index_options":
        recs = [r for r in recs if r[5] == "INDEX"]
    elif kind == "stock_options":
        recs = [r for r in recs if r[5] != "INDEX"]
    if current_expiry_only:
        recs = _current_expiry(recs)
    by_und: dict = {}
    for r in recs:
        by_und.setdefault(r[6], []).append(r)
    out: dict = {}
    for uk, rs in by_und.items():
        spot = spots.get(uk)
        if spot is None:
            continue
        strikes = sorted({r[7] for r in rs if r[7] is not None})
        if not strikes:
            continue
        atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
        keep = set(strikes[max(0, atm - n_strikes): atm + n_strikes + 1])
        for r in rs:
            if r[7] in keep:
                out[r[0]] = r[1]
    return out
