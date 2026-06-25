"""FastAPI dashboard — the trading command center.

Run:  PYTHONPATH=src DOTENV_PATH=.env python3 scripts/run_dashboard.py
then open http://127.0.0.1:8000

Charts + scans use Upstox PUBLIC history (no token needed) with DYNAMIC IST dates,
so data is always current. Universe = the full NSE instrument master (~2,400
equities + indices). The "live" toggle re-scans on an interval (the right cadence
for 15m/1h bar strategies). Controls (arm / kill) are wired to the real RiskEngine.
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import secrets
import tempfile
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..brokers.paper import PaperBroker
from ..config import UpstoxConfig
from ..data.upstox import UpstoxData
from ..indicators import Bollinger, RSI
from ..risk.limits import RiskEngine, RiskLimits
from ..scanners.bollinger_breakout import BollingerBreakoutScanner
from ..scanners.bollinger_outside import BollingerOutsideScanner
from ..scanners.prev_day_break import PrevDayBreakScanner
from ..scanners.rsi_momentum import RsiMomentumScanner
from ..data.upstox_feed import UpstoxFeed
from ..live import LiveScanEngine
from ..universe import (BANKNIFTY_STOCKS, NIFTY50_FULL, atm_options, load_bse_indices,
                        load_equities, load_fo, load_fno_underlyings, load_indices, load_options,
                        option_underlying_keys, option_underlying_map)

IST = timezone(timedelta(hours=5, minutes=30))
STATIC = Path(__file__).parent / "static"
SEGMENT_LABELS = ["Nifty 50", "Bank Nifty", "F&O", "Futures",
                  "Index Options ATM", "Stock Options ATM",
                  "Options", "Index Options", "Stock Options", "Indices", "All stocks"]
LIVE_INTERVAL_SEC = 60
SCAN_MAX = 5000         # cap symbols per REST scan (rate limit); full breadth needs the websocket
OPTION_SEGMENTS = {"Options", "Index Options", "Stock Options",
                   "Index Options ATM", "Stock Options ATM"}
OPT_RSI_THRESHOLD = 60.0   # alert options where BOTH the option's and its underlying's RSI >= this
OPT_RSI_NEAR = 58.0        # early "approaching 60" pre-alert (RSI in [NEAR, 60) and RISING) so you
                           # can enter just before the cross instead of after it
SCAN_TFS = ("5min", "15min", "30min", "1hour", "day")   # selectable scanner timeframes

# --- Upstox OAuth (login button -> auto access token) ---
_UPSTOX_AUTH = "https://api.upstox.com/v2/login/authorization/dialog"
_UPSTOX_TOKEN = "https://api.upstox.com/v2/login/authorization/token"
_OAUTH_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _scan_tf(tf):
    """Validate a requested scanner timeframe; fall back to 15min."""
    return tf if tf in SCAN_TFS else "15min"


def now_ist() -> datetime:
    return datetime.now(IST)


def date_window():
    """(to, from_15m, from_1h) as YYYY-MM-DD, always current (IST)."""
    to = now_ist().date()
    # NB: Upstox caps HOURLY history at ~1 quarter (90 days) per request -> keep 1h < 90.
    return (to.isoformat(),
            (to - timedelta(days=14)).isoformat(),
            (to - timedelta(days=80)).isoformat())


# --- "Live" recency: a fresh run shows only signals from the last bar or two ---
LIVE_WINDOW_MIN = 30        # base freshness for 15-min signals (≈ last closed bar + forming bar)
_TF_MIN = {"1min": 1, "5min": 5, "15min": 15, "30min": 30, "1hour": 60, "day": 1440}


def _live_window_min(tf: str) -> float:
    """How fresh (minutes) an alert counts as live: ~2 bars of its OWN timeframe, so the
    window scales WITH the timeframe (5min->10, 15min->30, 30min->60, 1h->120). A bar closes
    up to one bar-width after its open ts, so 2 bars keeps the last CONFIRMED signal + forming."""
    return 2 * _TF_MIN.get(tf, 15)


def _alert_age_min(ts_str: str, now: datetime | None = None) -> float | None:
    """Minutes between an alert's signal-bar timestamp ('YYYY-MM-DD HH:MM', IST) and now."""
    if not ts_str:
        return None
    try:
        ts = datetime.strptime(ts_str[:16], "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    except ValueError:
        return None
    return ((now or now_ist()) - ts).total_seconds() / 60.0


def _is_live(d: dict, now: datetime | None = None) -> bool:
    """Fresh enough for the live feed: within this timeframe's live window (small negative
    slack tolerates clock skew on the just-formed bar)."""
    age = _alert_age_min(d.get("ts", ""), now)
    return age is not None and -2.0 <= age <= _live_window_min(d.get("tf", "15min"))


class AppState:
    def __init__(self) -> None:
        self.cfg = UpstoxConfig.from_env()
        self.data = UpstoxData(self.cfg.access_token)
        self.token_live: bool | None = None     # cached real-validity probe (None=unchecked)
        self.oauth_state = ""                    # CSRF nonce for the in-progress Upstox login
        self.mode = os.environ.get("TRADING_MODE", "paper")
        self.armed = False
        self.broker = PaperBroker(starting_cash=100_000)
        self.limits = RiskLimits(
            max_risk_per_trade_pct=1.0, max_position_value=50_000,
            max_total_exposure_value=100_000, max_daily_loss=2_000,
            max_open_positions=5, max_orders_per_day=50,
            instrument_whitelist=frozenset(), arm_live=False)
        self.risk = RiskEngine(self.limits, mode=self.mode)
        self.merged: dict[str, str] = {}        # symbol -> instrument_key (equities + indices)
        self.segments: dict[str, list] = {}
        self.opt_underlying: dict = {}          # option symbol -> underlying instrument_key
        self.segment = "Nifty 50"
        self.alerts: list[dict] = []
        self.last_scan: str | None = None
        self.scanning = False
        self.scan_done = 0
        self.scan_total = 0
        self.scan_cancel = False
        self.scan_errors = 0                    # symbols whose fetch failed (usually rate-limit)
        self.live = False
        self.live_feed = None
        self.live_engine = None
        self.live_thread = None
        self.live_count = 0
        self.live_tf = "15min"                   # timeframe the live websocket aggregates into
        self.loop = None
        self.autorun = False
        self.autorun_task = None
        self.autorun_interval = 900
        self.ws_clients: set[WebSocket] = set()

    def probe_token(self) -> bool:
        """Is the daily token ACTUALLY valid (not just present)? One cached LTP probe.
        Upstox tokens die 3:30 AM IST daily, so validity is stable within a session."""
        if not self.cfg.access_token:
            self.token_live = False
        elif self.token_live is None:
            try:
                self.token_live = bool(self.data.ltp(["NSE_EQ|INE002A01018"]))
            except Exception:
                self.token_live = False
        return bool(self.token_live)

    def ensure_loaded(self) -> None:
        if self.merged:
            return
        eq, idx = load_equities(), load_indices()
        bse_idx = load_bse_indices()            # SENSEX, BANKEX, ... (BSE master)
        opt = load_options()                    # all options, current expiry
        idx_opt = load_fo("index_options")
        stk_opt = load_fo("stock_options")
        fut = load_fo("futures")
        fno = load_fno_underlyings()
        all_idx = {**idx, **bse_idx}
        # equities LAST: a few BSE index names collide with NSE equity tickers
        # (ENERGY/INFRA/METAL/MID150) — the real equity must win the symbol.
        self.merged = {**all_idx, **opt, **fut, **eq}   # chart any equity/index/option/future
        self.segments = {
            "All stocks": sorted(eq),
            "Nifty 50": [s for s in NIFTY50_FULL if s in eq],
            "Bank Nifty": [s for s in BANKNIFTY_STOCKS if s in eq],
            "Indices": sorted(all_idx),
            "F&O": [s for s in fno if s in self.merged],
            "Futures": sorted(fut),
            "Options": sorted(opt),
            "Index Options": sorted(idx_opt),
            "Stock Options": sorted(stk_opt),
        }
        self.opt_underlying = option_underlying_map()
        try:                                    # ATM (current-price) option segments
            spots = self.data.ltp(option_underlying_keys())
            self.segments["Index Options ATM"] = sorted(atm_options(spots, 5, "index_options"))
            self.segments["Stock Options ATM"] = sorted(atm_options(spots, 5, "stock_options"))
        except Exception:
            self.segments["Index Options ATM"] = []
            self.segments["Stock Options ATM"] = []


state = AppState()
app = FastAPI(title="Trading Command Center")


@app.on_event("startup")
async def _startup() -> None:
    state.loop = asyncio.get_running_loop()
    asyncio.create_task(asyncio.to_thread(state.ensure_loaded))


def _alert_dict(a, tf: str) -> dict:
    return {"ts": a.ts.strftime("%Y-%m-%d %H:%M"), "symbol": a.symbol, "kind": a.kind,
            "direction": a.direction, "action": a.meta.get("action", a.direction.upper()),
            "message": a.message, "tf": tf}


def _chart_time(ts) -> int:
    """Epoch seconds shifted by the bar's UTC offset, so lightweight-charts (which renders
    timestamps in UTC) displays the IST wall-clock time the candle actually belongs to."""
    off = ts.utcoffset()
    return int(ts.timestamp() + (off.total_seconds() if off else 0))


def _marker_text(a) -> str:
    k = a.kind
    if k == "bollinger_breakout":
        return a.meta.get("action", "")
    if k == "rsi_momentum":
        return "RSI60" if a.meta.get("stage") == "cross60" else "RSI50"
    if k == "prev_day_break":
        return "PDH" if a.direction == "up" else "PDL"
    if k == "bollinger_outside":
        return "BBo"
    return ""


def _chart_markers(symbol: str, tf: str, cs: list) -> list[dict]:
    """Run the timeframe's scanners over the chart's candles and return signal
    markers (arrows) for lightweight-charts — alerts drawn ON the chart."""
    # run the SAME scanner set as _scan_symbols at this tf, so chart markers match the feed
    scanners = [BollingerBreakoutScanner(timeframe=tf), RsiMomentumScanner(timeframe=tf),
                PrevDayBreakScanner(timeframe=tf), BollingerOutsideScanner(timeframe=tf)]
    # markers only for the current + previous trading day (scanners still see all bars for warmup)
    recent = set(sorted({c.ts.date() for c in cs}, reverse=True)[:2])
    marks = []
    for c in cs:
        in_recent = c.ts.date() in recent
        for s in scanners:
            a = s.feed(symbol, c)
            if a and in_recent:
                up = a.direction == "up"
                marks.append({"time": _chart_time(c.ts), "kind": a.kind,
                              "position": "belowBar" if up else "aboveBar",
                              "color": "#3fb950" if up else "#f85149",
                              "shape": "arrowUp" if up else "arrowDown",
                              "text": _marker_text(a)})
    marks.sort(key=lambda m: m["time"])
    return marks


def _candles(ik: str, tf: str) -> list:
    """Historical candles + TODAY's intraday session appended — i.e. live current-day
    data during market hours (the intraday tail is what makes a scan 'live')."""
    to_d, from15, from1h = date_window()
    frm = from1h if tf in ("1hour", "day") else from15
    cs = state.data.candles(ik, tf, frm, to_d)
    if tf != "day":                          # append today's forming bars for any intraday tf
        try:
            intra = state.data.intraday(ik, tf)
            if intra:
                last = cs[-1].ts if cs else None
                cs = cs + [c for c in intra if last is None or c.ts > last]
        except Exception:
            pass
    return cs


def _scan_symbols(symbols: list, tf: str, set_done, enabled=None, emit=None) -> list[dict]:
    """Run the selected equity/index scanners on candles at timeframe `tf`. Every scanner
    honours the chosen tf (driven by the dashboard's timeframe selector)."""
    def _on(k):
        return enabled is None or k in enabled
    classes = [(k, c) for k, c in (("bollinger_breakout", BollingerBreakoutScanner),
                                   ("rsi_momentum", RsiMomentumScanner),
                                   ("prev_day_break", PrevDayBreakScanner),
                                   ("bollinger_outside", BollingerOutsideScanner)) if _on(k)]
    want_rsi_threshold = _on("rsi_threshold")    # state-based RSI >= 60 snapshot (like options)

    def fetch(sym):
        ik = state.merged.get(sym)
        if not ik:
            return sym, []
        try:
            return sym, _candles(ik, tf)
        except Exception:
            return sym, None               # None = fetch FAILED (rate-limit etc.), not "no data"

    found: list[dict] = []
    done = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=5) as ex:   # gentle: avoid tripping the rate limiter
        for sym, cs in ex.map(fetch, symbols):
            if state.scan_cancel:          # stop requested -> keep partial results, bail out
                break
            if cs is None:                 # fetch error -> count it so "0 alerts" isn't ambiguous
                errors += 1
                done += 1
                set_done(done)
                continue
            for k, cls in classes:
                s = cls(timeframe=tf)
                for c in cs:
                    x = s.feed(sym, c)
                    if x:
                        d = _alert_dict(x, tf)
                        found.append(d)
                        if emit:
                            emit(d)
            if want_rsi_threshold and cs:            # snapshot: alert if the LATEST bar's RSI >= 60
                rv = _latest_rsi(cs)
                if rv is not None and rv >= OPT_RSI_THRESHOLD:
                    d = {"ts": cs[-1].ts.strftime("%Y-%m-%d %H:%M"), "symbol": sym,
                         "kind": "rsi_threshold", "direction": "up",
                         "action": f"RSI≥{int(OPT_RSI_THRESHOLD)}",
                         "message": f"RSI {rv:.1f} ≥{int(OPT_RSI_THRESHOLD)} ({tf})", "tf": tf}
                    found.append(d)
                    if emit:
                        emit(d)
            done += 1
            set_done(done)
    state.scan_errors = errors
    found.sort(key=lambda x: x["ts"], reverse=True)
    return found


def _latest_rsi(candles, period: int = 14):
    r = RSI(period)
    v = None
    for c in candles:
        v = r.update(c.close)
    return v


def _rsi_last2(candles, period: int = 14):
    """(prev, last) RSI — `last` is current, `prev` is the bar before, so we can tell if
    RSI is RISING toward the threshold (the 'about to touch 60' signal)."""
    r = RSI(period)
    prev = last = None
    for c in candles:
        v = r.update(c.close)
        if v is not None:
            prev, last = last, v
    return prev, last


def _scan_options_rsi(option_syms: list, set_done, threshold: float = OPT_RSI_THRESHOLD,
                      enabled=None, emit=None, tf: str = "15min") -> list[dict]:
    """Options RSI confluence: alert options whose OWN RSI >= threshold AND whose UNDERLYING's
    RSI >= threshold, on timeframe `tf`. Underlying-first to bound REST calls under the rate limit."""
    if enabled is not None and "option_rsi_confluence" not in enabled:
        return []
    to_d, from15, _ = date_window()
    by_und: dict = {}
    for s in option_syms:
        uk = state.opt_underlying.get(s)
        if uk:
            by_und.setdefault(uk, []).append(s)
    und_keys = list(by_und.keys())                     # every underlying in the selection

    def und_fetch(uk):
        try:
            return uk, _rsi_last2(_candles(uk, tf)), False  # (prev, last) — need direction too
        except Exception:
            return uk, (None, None), True

    errors = 0
    und_rsi: dict = {}                                  # underlying_key -> (prev, last)
    with ThreadPoolExecutor(max_workers=5) as ex:
        for uk, pl, failed in ex.map(und_fetch, und_keys):
            und_rsi[uk] = pl
            errors += failed

    # scan options whose UNDERLYING is AT or APPROACHING the threshold (>= NEAR), so we can
    # also catch the "about to touch 60" cases, not just the already-crossed ones.
    opts: list = []
    for uk in und_keys:
        if (und_rsi.get(uk, (None, None))[1] or 0) >= OPT_RSI_NEAR:
            opts.extend(by_und[uk])
    state.scan_total = len(opts)

    def opt_fetch(s):
        try:
            cs = _candles(state.merged[s], tf)
            prev, last = _rsi_last2(cs)
            return s, prev, last, (cs[-1].ts if cs else None), False
        except Exception:
            return s, None, None, None, True

    def _toward(level, prev, last):
        """A leg supports an imminent cross if it's already >= level, or it's below level
        but RISING toward it (NOT flat/falling away)."""
        if last is None:
            return False
        return last >= level or (prev is not None and last > prev)

    found: list[dict] = []
    done = 0
    th = int(threshold)
    with ThreadPoolExecutor(max_workers=5) as ex:
        for s, prev_orv, orv, ts, failed in ex.map(opt_fetch, opts):
            if state.scan_cancel:
                break
            done += 1
            set_done(done)
            errors += failed
            if orv is None or orv < OPT_RSI_NEAR:
                continue
            prev_urv, urv = und_rsi.get(state.opt_underlying.get(s), (None, None))
            urv = urv or 0
            crossed = orv >= threshold and urv >= threshold
            # approaching: not yet crossed, both legs in/above the band, and whichever leg is
            # still BELOW 60 is rising toward it (so a leg decaying away is excluded).
            approaching = (not crossed and orv >= OPT_RSI_NEAR and urv >= OPT_RSI_NEAR
                           and _toward(threshold, prev_orv, orv)
                           and _toward(threshold, prev_urv, urv))
            if crossed:
                action, near = f"RSI≥{th}", False
                msg = f"Option RSI {orv:.1f} ≥{th}  &  underlying RSI {urv:.1f} ≥{th}"
            elif approaching:
                action, near = f"RSI→{th}", True
                lag = "underlying" if (urv < threshold and orv >= threshold) else \
                      "option" if (orv < threshold and urv >= threshold) else "both"
                msg = f"⏳ approaching {th} ({lag} lagging) — option {orv:.1f}, underlying {urv:.1f}"
            else:
                continue                                # in band but not converging -> not actionable
            d = {
                "ts": ts.strftime("%Y-%m-%d %H:%M") if ts else "",
                "symbol": s, "kind": "option_rsi_confluence", "direction": "up",
                "action": action, "message": msg, "near": near, "tf": tf}
            found.append(d)
            if emit:
                emit(d)
    state.scan_errors = errors
    found.sort(key=lambda x: x["ts"], reverse=True)
    return found


async def broadcast(msg: dict) -> None:
    for ws in list(state.ws_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            state.ws_clients.discard(ws)


async def _do_scan(segment: str, enabled=None, tf: str = "15min"):
    state.ensure_loaded()
    state.scanning = True
    state.scan_cancel = False
    state.scan_done = 0
    state.scan_errors = 0
    state.segment = segment
    syms_all = state.segments.get(segment, [])
    is_opt = segment in OPTION_SEGMENTS
    syms = syms_all                      # scan exactly the selected filter — no arbitrary cap
    state.scan_total = len(syms)         # (options screener narrows to qualifying underlyings)
    prev_keys = {(a.get("symbol"), a.get("kind"), a.get("ts")) for a in state.alerts}
    state.alerts = []                    # fresh feed; alerts stream in as they're found
    await broadcast({"type": "state"})
    await broadcast({"type": "alerts"})

    now = now_ist()                      # 'live' = signals fresh within the last bar or two

    def _is_new(d):                      # not present in the PREVIOUS scan/autorun cycle
        return (d.get("symbol"), d.get("kind"), d.get("ts")) not in prev_keys

    def emit(d):                         # called from the scan thread as each alert is found
        if _is_live(d, now):             # only stream genuinely fresh (live) signals
            d["new"] = _is_new(d)
            d["age_min"] = round(_alert_age_min(d.get("ts", ""), now) or 0)
            state.alerts = sorted([d] + state.alerts,    # keep feed newest -> oldest while streaming
                                  key=lambda a: a.get("ts", ""), reverse=True)[:400]

    async def prog():
        while state.scanning:
            await broadcast({"type": "progress", "done": state.scan_done, "total": state.scan_total})
            await broadcast({"type": "alerts"})          # push the accumulating alerts live
            await asyncio.sleep(0.8)

    pt = asyncio.create_task(prog())
    set_done = lambda d: setattr(state, "scan_done", d)  # noqa: E731
    try:
        if is_opt:
            found = await asyncio.to_thread(_scan_options_rsi, syms, set_done,
                                            OPT_RSI_THRESHOLD, enabled, emit, tf)
        else:
            found = await asyncio.to_thread(_scan_symbols, syms, tf, set_done, enabled, emit)
        found = [a for a in found if _is_live(a, now)]   # finalize: keep only live (fresh) signals
        found.sort(key=lambda a: a.get("ts", ""), reverse=True)   # newest -> oldest
        for a in found:
            a["new"] = _is_new(a)
            a["age_min"] = round(_alert_age_min(a.get("ts", ""), now) or 0)
        state.alerts = found[:400]
        scanned = state.scan_total
        note = f" · {scanned} relevant options" if is_opt and len(syms_all) > scanned else ""
        note += f" · {tf}"
        if state.scan_errors:                # don't let failed fetches masquerade as "no signals"
            note += f" · ⚠ {state.scan_errors} fetches failed (rate-limit? retry in a min)"
        state.last_scan = now_ist().strftime("%H:%M:%S IST") + note
        return len(found), scanned
    finally:
        state.scanning = False
        pt.cancel()
        await broadcast({"type": "alerts"})
        await broadcast({"type": "state"})


def _live_on_alert(a, tf: str) -> None:
    """Called from the websocket thread when a live bar produces an alert."""
    d = _alert_dict(a, tf)
    d["new"] = True                                  # a fresh tick-driven bar -> always live/new
    d["age_min"] = round(_alert_age_min(d.get("ts", "")) or 0)
    # Single atomic rebind (no in-place insert): keeps newest->oldest order AND can't be
    # clobbered by a concurrent _do_scan reassignment. Bars emit per-symbol out of ts order,
    # so we must re-sort, not just prepend. Drop anything no longer fresh.
    merged = sorted([d] + state.alerts, key=lambda x: x.get("ts", ""), reverse=True)
    state.alerts = [x for x in merged if _is_live(x)][:400]
    if state.loop:
        try:
            asyncio.run_coroutine_threadsafe(broadcast({"type": "alerts"}), state.loop)
        except Exception:
            pass


def _seed_live(engine, symbols: list, tf: str = "15min") -> None:
    """Warm up the live scanners with recent history at the live timeframe (throttled, capped)."""
    for s in symbols:
        ik = state.merged.get(s)
        if ik:
            try:
                cs = _candles(ik, tf)
                engine.seed(s, cs)
                if cs:
                    engine.agg.prime(s, cs[-1])     # so prices[s] exists before its first tick
            except Exception:
                pass


def _stop_live() -> None:
    if state.live_feed:
        try:
            state.live_feed.disconnect()
        except Exception:
            pass
    state.live_feed = None
    state.live_engine = None
    state.live_count = 0


def _start_live(segment: str, tf: str = "15min") -> bool:
    _stop_live()
    state.ensure_loaded()
    if not state.cfg.access_token:
        return False
    tf = _scan_tf(tf)
    state.live_tf = tf
    syms = state.segments.get(segment, [])[:5000]      # one websocket connection cap
    k2s = {state.merged[s]: s for s in syms if s in state.merged}
    if not k2s:
        return False
    feed = UpstoxFeed(state.cfg.access_token, list(k2s.keys()), mode="ltpc")
    engine = LiveScanEngine(k2s, _live_on_alert, tf)
    feed.on_tick(engine.on_message)
    state.live_feed, state.live_engine, state.live_count = feed, engine, len(k2s)
    threading.Thread(target=_seed_live, args=(engine, syms[:150], tf), daemon=True).start()
    state.live_thread = threading.Thread(target=feed.connect, daemon=True)
    state.live_thread.start()
    return True


def _watch_live(symbol: str) -> bool:
    """Subscribe a charted symbol to the RUNNING live feed on demand, so its candle moves
    even when it isn't in the live segment (e.g. SENSEX, or any non-Nifty50 name). Without
    this, charting an unsubscribed symbol shows a frozen chart (no ticks for it)."""
    eng, feed = state.live_engine, state.live_feed
    if not (state.live and eng and feed):
        return False
    ik = state.merged.get(symbol)
    if not ik:
        return False
    if ik in eng.k2s:
        return True                                  # already streaming
    eng.k2s[ik] = symbol                             # route its ticks into the aggregator
    try:
        feed.subscribe([ik])
    except Exception:
        eng.k2s.pop(ik, None)
        return False
    state.live_count = len(eng.k2s)
    threading.Thread(target=_seed_live, args=(eng, [symbol], state.live_tf), daemon=True).start()
    return True


def _market_open() -> bool:
    n = now_ist()
    if n.weekday() >= 5:
        return False
    mins = n.hour * 60 + n.minute
    return 9 * 60 + 15 <= mins <= 15 * 60 + 30


async def _autorun_loop(interval: int, segment: str, scanners, tf: str = "15min") -> None:
    """Re-run the chosen scan every `interval` seconds during market hours, until
    stopped or the market closes for the day. Idles (no scans) while market closed."""
    while state.autorun:
        n = now_ist()
        if n.weekday() < 5 and (n.hour * 60 + n.minute) > 15 * 60 + 30:
            break                                       # past today's close -> auto-stop
        if _market_open() and not state.scanning:
            try:
                await _do_scan(segment, scanners, tf)
            except Exception:
                pass
        for _ in range(max(1, interval)):               # sleep in 1s steps so stop is responsive
            if not state.autorun:
                break
            await asyncio.sleep(1)
    state.autorun = False
    state.autorun_task = None
    await broadcast({"type": "state"})


@app.get("/")
def index() -> HTMLResponse:
    # no-store: the SPA's JS changes often; never let the browser serve a stale build
    return HTMLResponse((STATIC / "index.html").read_text(),
                        headers={"Cache-Control": "no-store, max-age=0"})


# ----------------------------- Upstox OAuth login -----------------------------
def _env_path() -> Path:
    return Path(os.environ.get("DOTENV_PATH", ".env"))


_ENV_LOCK = threading.Lock()


def _write_env_token(token: str) -> None:
    """Persist UPSTOX_ACCESS_TOKEN into .env ATOMICALLY (temp file + os.replace, 0600,
    under a lock) so a concurrent/interrupted write can never corrupt or world-expose the
    shared secrets file."""
    p = _env_path()
    with _ENV_LOCK:
        lines = p.read_text().splitlines() if p.exists() else []
        out, found = [], False
        for line in lines:
            if line.strip().startswith("UPSTOX_ACCESS_TOKEN="):
                out.append(f"UPSTOX_ACCESS_TOKEN={token}")
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f"UPSTOX_ACCESS_TOKEN={token}")
        data = ("\n".join(out) + "\n").encode()
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".env.", suffix=".tmp")
        try:
            os.write(fd, data)
            os.close(fd)
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)               # atomic swap; readers see old OR new, never partial
            try:
                os.chmod(p, 0o600)
            except Exception:
                pass
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise


def _set_access_token(token: str) -> None:
    """Apply a freshly-issued token everywhere: live config, the data adapter, the cached
    validity probe, and .env (persisted). token='' logs out."""
    state.cfg.access_token = token
    state.data._token = token
    state.token_live = None              # force a fresh validity probe
    try:
        _write_env_token(token)
    except Exception:
        pass


def _exchange_code(code: str) -> str:
    """Trade the OAuth `code` for a daily access token (server-side; secret never leaves here)."""
    body = urllib.parse.urlencode({
        "code": code, "client_id": state.cfg.api_key, "client_secret": state.cfg.api_secret,
        "redirect_uri": state.cfg.redirect_uri, "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request(_UPSTOX_TOKEN, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json", "User-Agent": _OAUTH_UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    tok = data.get("access_token")
    if not tok:
        raise RuntimeError(str(data)[:200])
    return tok


def _auth_msg_page(msg: str) -> str:
    return (f"<html><body style='background:#0a0e14;color:#e6edf3;font-family:system-ui;"
            f"text-align:center;padding-top:18vh'><h2>Upstox login</h2><p>{html.escape(msg)}</p>"
            f"<p><a href='/' style='color:#58a6ff'>&larr; Back to dashboard</a></p></body></html>")


@app.get("/auth/upstox/login")
def upstox_login():
    """Kick off the Upstox OAuth flow — redirects the browser to Upstox to log in."""
    if not state.cfg.api_key or not state.cfg.api_secret:
        return HTMLResponse(_auth_msg_page("Set UPSTOX_API_KEY and UPSTOX_API_SECRET in .env first."),
                            status_code=400)
    state.oauth_state = secrets.token_urlsafe(16)        # CSRF nonce
    params = urllib.parse.urlencode({
        "response_type": "code", "client_id": state.cfg.api_key,
        "redirect_uri": state.cfg.redirect_uri, "state": state.oauth_state})
    return RedirectResponse(f"{_UPSTOX_AUTH}?{params}")


@app.get("/auth/upstox/callback")
def upstox_callback(code: str = "", st: str = Query("", alias="state")):
    """Upstox redirects here with ?code=...&state=... — exchange it for a token, then home."""
    expected = state.oauth_state
    state.oauth_state = ""                  # consume the nonce IMMEDIATELY -> single-use on every path
    # CSRF: require an in-flight nonce AND a constant-time match (an empty/absent one is rejected,
    # so a forged callback can't silently install an attacker's token = token-fixation defence).
    if not expected or not secrets.compare_digest(st, expected):
        return HTMLResponse(_auth_msg_page("Security check failed. Please start the login again."),
                            status_code=400)
    if not code:
        return HTMLResponse(_auth_msg_page("Login cancelled or no code was returned."), status_code=400)
    try:
        _set_access_token(_exchange_code(code))
    except Exception as e:
        print(f"[oauth] token exchange failed: {str(e)[:300]}")   # detail stays SERVER-side
        return HTMLResponse(_auth_msg_page("Token exchange failed. Please try logging in again."),
                            status_code=400)
    return RedirectResponse("/", status_code=303)        # back to the dashboard, now logged in


@app.post("/api/logout")
def logout() -> dict:
    _set_access_token("")
    _stop_live()
    state.live = False
    return {"ok": True}


@app.get("/api/state")
def get_state() -> dict:
    L = state.limits
    return {
        "mode": state.mode, "armed": state.armed, "kill_switch": state.risk.kill_switch,
        "live": state.live, "live_count": state.live_count, "live_tf": state.live_tf,
        "live_ticks": state.live_engine.ticks_seen if state.live_engine else 0,
        "live_bars": state.live_engine.bars_seen if state.live_engine else 0,
        "autorun": state.autorun, "autorun_interval": state.autorun_interval,
        "market_open": _market_open(),
        "scanning": state.scanning,
        "scan_done": state.scan_done, "scan_total": state.scan_total,
        "segment": state.segment, "segments": SEGMENT_LABELS,
        "last_scan": state.last_scan, "alert_count": len(state.alerts),
        "token_valid": state.probe_token(),
        "oauth_ready": bool(state.cfg.api_key and state.cfg.api_secret),  # can we show "Login with Upstox"?
        "redirect_uri": state.cfg.redirect_uri,                           # what must be registered in Upstox console
        "universe_size": len(state.merged) if state.merged else None,
        "limits": {"max_position_value": L.max_position_value,
                   "max_total_exposure_value": L.max_total_exposure_value,
                   "max_daily_loss": L.max_daily_loss,
                   "max_open_positions": L.max_open_positions},
    }


@app.get("/api/universe")
def universe(segment: str = "Nifty 50") -> dict:
    state.ensure_loaded()
    syms = state.segments.get(segment, [])
    note = "" if syms else ("options arrive with the options scanner build"
                            if segment == "Options" else "")
    return {"segment": segment, "total": len(syms), "symbols": syms, "note": note}


@app.get("/api/search")
def search(q: str = "", limit: int = 60) -> dict:
    """Global symbol search across the WHOLE charted universe (equities + indices incl.
    SENSEX/BANKEX + futures + options), regardless of the selected segment."""
    state.ensure_loaded()
    terms = q.upper().split()
    if not terms:
        return {"symbols": []}
    out = [s for s in state.merged if all(t in s.upper() for t in terms)]
    out.sort(key=lambda s: (len(s), s))     # shorter/closer matches first (SENSEX before its options)
    return {"symbols": out[:limit]}


@app.get("/api/candles")
def candles(symbol: str = "RELIANCE", tf: str = "15min"):
    state.ensure_loaded()
    ik = state.merged.get(symbol)
    if not ik:
        return JSONResponse({"error": "unknown symbol"}, status_code=404)
    try:
        cs = _candles(ik, tf)        # historical + today's live intraday session
    except Exception as e:           # transient rate-limit etc. -> degrade, don't 500
        return {"symbol": symbol, "tf": tf, "candles": [], "bands": [], "error": str(e)[:160]}
    bb = Bollinger(20, 1.5)
    rsi_ind = RSI(14)
    out_c, out_b, out_rsi = [], [], []
    for c in cs:
        t = _chart_time(c.ts)
        out_c.append({"time": t, "open": c.open, "high": c.high, "low": c.low, "close": c.close})
        bands = bb.update(c.close)
        if bands:
            lo, mid, up = bands
            out_b.append({"time": t, "lower": lo, "mid": mid, "upper": up})
        rv = rsi_ind.update(c.close)
        if rv is not None:
            out_rsi.append({"time": t, "value": round(rv, 2)})
    return {"symbol": symbol, "tf": tf, "candles": out_c, "bands": out_b, "rsi": out_rsi,
            "markers": _chart_markers(symbol, tf, cs)}


@app.get("/api/alerts")
def alerts() -> dict:
    # prune at read: a quiet live feed won't re-evaluate freshness on insert, so age them out here
    now = now_ist()
    fresh = [a for a in state.alerts if _is_live(a, now)]
    for a in fresh:                                  # keep the displayed age current
        a["age_min"] = round(_alert_age_min(a.get("ts", ""), now) or 0)
    return {"alerts": fresh}


@app.post("/api/alerts/clear")
async def clear_alerts() -> dict:
    state.alerts = []
    await broadcast({"type": "alerts"})
    return {"status": "cleared"}


@app.get("/api/positions")
def positions() -> dict:
    ps = state.broker.get_positions()
    return {"cash": state.broker.cash,
            "positions": [{"symbol": p.symbol, "qty": p.qty, "avg_price": p.avg_price,
                           "realized_pnl": p.realized_pnl} for p in ps]}


@app.post("/api/scan")
async def scan(payload: dict | None = None) -> dict:
    if state.scanning:
        return {"status": "already_running"}
    seg = (payload or {}).get("segment", state.segment)
    enabled = (payload or {}).get("scanners")
    tf = _scan_tf((payload or {}).get("tf"))
    n, scanned = await _do_scan(seg, enabled, tf)
    return {"status": "ok", "alerts": n, "scanned": scanned, "tf": tf, "errors": state.scan_errors}


@app.post("/api/scan/stop")
async def scan_stop() -> dict:
    state.scan_cancel = True
    return {"status": "stopping", "done": state.scan_done, "total": state.scan_total}


@app.post("/api/live")
async def live(payload: dict) -> dict:
    on = bool(payload.get("on"))
    if payload.get("segment"):
        state.segment = payload["segment"]
    tf = _scan_tf(payload.get("tf"))
    if on:
        state.live = await asyncio.to_thread(_start_live, state.segment, tf)
    else:
        _stop_live()
        state.live = False
    await broadcast({"type": "state"})
    return {"live": state.live, "subscribed": state.live_count, "tf": state.live_tf}


@app.get("/api/live/prices")
def live_prices() -> dict:
    """Live forming-bar OHLC per subscribed symbol, straight from the websocket tick
    aggregator (in-memory — NO Upstox REST call, so it's safe to poll often). Drives the
    moving chart. `time` is chart-time (IST-shifted epoch) of the current 15-min bucket."""
    eng = state.live_engine
    if not eng or not state.live:
        return {"live": False, "prices": {}}
    off = int(IST.utcoffset(None).total_seconds())          # +19800 (IST)
    cur = dict(eng.agg._cur)        # atomic snapshot — feed thread mutates _cur concurrently
    prices = {sym: {"time": int(b["start"]) + off, "open": b["o"], "high": b["h"],
                    "low": b["l"], "close": b["c"]}
              for sym, b in cur.items()}
    return {"live": True, "ticks": eng.ticks_seen, "prices": prices}


@app.post("/api/live/watch")
async def live_watch(payload: dict) -> dict:
    """Ensure the charted symbol is streaming, so ANY chart moves live (not just the
    segment's symbols). Called by the frontend whenever you open a chart."""
    sym = (payload or {}).get("symbol", "")
    ok = await asyncio.to_thread(_watch_live, sym) if sym else False
    return {"watching": ok, "symbol": sym, "subscribed": state.live_count}


@app.post("/api/autorun")
async def autorun(payload: dict) -> dict:
    on = bool(payload.get("on"))
    if on:
        state.autorun_interval = int(payload.get("interval", 900))
        segment = payload.get("segment", state.segment)
        scanners = payload.get("scanners")
        tf = _scan_tf(payload.get("tf"))
        state.autorun = True
        if state.autorun_task is None:
            state.autorun_task = asyncio.create_task(
                _autorun_loop(state.autorun_interval, segment, scanners, tf))
    else:
        state.autorun = False
    await broadcast({"type": "state"})
    return {"autorun": state.autorun, "interval": state.autorun_interval}


@app.post("/api/arm")
async def arm(payload: dict) -> dict:
    state.armed = bool(payload.get("armed"))
    state.limits.arm_live = state.armed
    await broadcast({"type": "state"})
    return {"armed": state.armed}


@app.post("/api/kill")
async def kill() -> dict:
    state.risk.engage_kill_switch("dashboard")
    state.armed = False
    state.limits.arm_live = False
    _stop_live()
    state.live = False
    await broadcast({"type": "state"})
    return {"kill_switch": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state.ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state.ws_clients.discard(ws)
