"""Live-feed engine: aggregate websocket LTP ticks into candles and run the scanners
on each bar close, emitting alerts in real time.

  ticks (UpstoxFeed, ltpc mode)  ->  CandleAggregator  ->  scanners  ->  on_alert

Ticks only flow during market hours (09:15-15:30 IST). The aggregator + engine are
pure logic (no network), so they're unit-tested on synthetic ticks; the live socket
path is verified during market hours with a fresh token.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from .scanners.bollinger_breakout import BollingerBreakoutScanner
from .scanners.prev_day_break import PrevDayBreakScanner
from .scanners.rsi_momentum import RsiMomentumScanner
from .strategies.base import Candle

IST = timezone(timedelta(hours=5, minutes=30))


class CandleAggregator:
    """Turn a stream of (symbol, price, epoch) ticks into fixed-timeframe candles,
    invoking on_bar(symbol, Candle) when each bar rolls over."""

    def __init__(self, timeframe_minutes: int = 15, on_bar: Optional[Callable] = None):
        self.tf = timeframe_minutes * 60
        self.on_bar = on_bar
        self._cur: dict = {}                 # symbol -> {start, o, h, l, c}

    def add_tick(self, symbol: str, price: float, ts_epoch: float) -> None:
        bucket = int(ts_epoch // self.tf) * self.tf
        b = self._cur.get(symbol)
        if b is None:
            self._cur[symbol] = {"start": bucket, "o": price, "h": price, "l": price, "c": price}
        elif bucket > b["start"]:
            self._emit(symbol, b)            # previous bar finished -> emit it
            self._cur[symbol] = {"start": bucket, "o": price, "h": price, "l": price, "c": price}
        elif bucket == b["start"]:
            if price > b["h"]:
                b["h"] = price
            if price < b["l"]:
                b["l"] = price
            b["c"] = price
        # bucket < start (out-of-order/stale tick) -> ignore

    def prime(self, symbol: str, candle) -> None:
        """Seed the forming bar from the latest known candle so the symbol has a price
        BEFORE its first live tick (otherwise its chart is frozen / absent from the feed).
        Uses the candle's own bucket, so the next real tick rolls over normally. No-op if a
        live bar already exists for the symbol (never clobber real ticks)."""
        if symbol in self._cur:
            return
        bucket = int(candle.ts.timestamp() // self.tf) * self.tf
        self._cur[symbol] = {"start": bucket, "o": candle.open, "h": candle.high,
                             "l": candle.low, "c": candle.close}

    def _emit(self, symbol: str, b: dict) -> None:
        if self.on_bar:
            self.on_bar(symbol, Candle(datetime.fromtimestamp(b["start"], IST),
                                       b["o"], b["h"], b["l"], b["c"], 0.0))


def extract_ltp(entry: dict):
    """Pull (ltp, ltt_ms) out of a v3 feed entry, in either ltpc or fullFeed shape."""
    ltpc = entry.get("ltpc")
    if ltpc is None:
        ff = entry.get("fullFeed") or {}
        ltpc = (ff.get("marketFF") or ff.get("indexFF") or {}).get("ltpc")
    if not ltpc:
        return None, None
    ltp, ltt = ltpc.get("ltp"), ltpc.get("ltt")
    try:
        ltp = float(ltp) if ltp is not None else None
    except (TypeError, ValueError):
        ltp = None
    try:
        ltt = int(ltt) if ltt is not None else None
    except (TypeError, ValueError):
        ltt = None
    return ltp, ltt


_TF_MIN = {"1min": 1, "5min": 5, "15min": 15, "30min": 30, "1hour": 60, "day": 1440}


class LiveScanEngine:
    """Wires a feed's tick messages through the aggregator into the scanners."""

    def __init__(self, key_to_symbol: dict, on_alert: Callable, tf: str = "15min"):
        self.k2s = key_to_symbol
        self.on_alert = on_alert
        self.tf = tf                                   # alert/bucket timeframe (label)
        self.agg = CandleAggregator(_TF_MIN.get(tf, 15), self._on_bar)
        self.bb = BollingerBreakoutScanner(timeframe=tf)
        self.rsi = RsiMomentumScanner(timeframe=tf)
        self.pdb = PrevDayBreakScanner(timeframe=tf)
        self.ticks_seen = 0
        self.bars_seen = 0
        self.alerts_seen = 0

    def seed(self, symbol: str, candles: list) -> None:
        """Warm up the scanners with historical candles (suppresses their alerts)."""
        for c in candles:
            for s in (self.bb, self.rsi, self.pdb):
                s.feed(symbol, c)

    def on_message(self, msg: dict) -> None:
        feeds = (msg or {}).get("feeds") or {}
        for ik, entry in feeds.items():
            sym = self.k2s.get(ik)
            if not sym:
                continue
            ltp, ltt = extract_ltp(entry or {})
            if ltp is None:
                continue
            self.ticks_seen += 1
            ts = (ltt / 1000.0) if ltt else datetime.now(IST).timestamp()
            self.agg.add_tick(sym, ltp, ts)

    def _on_bar(self, symbol: str, candle: Candle) -> None:
        self.bars_seen += 1
        for s in (self.bb, self.rsi, self.pdb):
            a = s.feed(symbol, candle)
            if a is not None:
                self.alerts_seen += 1
                self.on_alert(a, self.tf)
