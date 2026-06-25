"""Opening Range Breakout (ORB).

Build the high/low of the first `opening_range_minutes` after the session open,
then take the FIRST breakout of that range (one trade per symbol per day). Stop at
the opposite range extreme; target at `rr` times the risk.

Honest note: ORB's edge is asymmetric reward, not high accuracy — expect long
losing streaks. It must be backtested with realistic Indian costs before use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Optional

from ..brokers.models import Side
from .base import Candle, Signal, Strategy


@dataclass
class _DayState:
    day: date
    range_high: float = float("-inf")
    range_low: float = float("inf")
    locked: bool = False
    traded: bool = False


class OpeningRangeBreakout(Strategy):
    name = "orb"

    def __init__(self, opening_range_minutes: int = 15,
                 session_open: time = time(9, 15), rr: float = 2.0):
        self.or_minutes = opening_range_minutes
        self.session_open = session_open
        self.rr = rr
        self._state: dict[str, _DayState] = {}

    def _minutes_since_open(self, t: time) -> int:
        return ((t.hour * 60 + t.minute)
                - (self.session_open.hour * 60 + self.session_open.minute))

    def on_candle(self, symbol: str, candle: Candle) -> Optional[Signal]:
        d = candle.ts.date()
        st = self._state.get(symbol)
        if st is None or st.day != d:        # new day -> reset per-symbol state
            st = _DayState(day=d)
            self._state[symbol] = st

        mins = self._minutes_since_open(candle.ts.time())
        if mins < 0:
            return None                       # before session open

        # Phase 1: accumulate the opening range.
        if mins < self.or_minutes:
            st.range_high = max(st.range_high, candle.high)
            st.range_low = min(st.range_low, candle.low)
            return None

        st.locked = True
        if st.traded or st.range_high == float("-inf"):
            return None

        # Phase 2: first breakout of the locked range.
        if candle.close > st.range_high:
            st.traded = True
            entry, stop = candle.close, st.range_low
            risk = entry - stop
            if risk <= 0:
                return None
            return Signal(symbol, Side.BUY, "orb_breakout_up", entry, stop,
                          target=entry + self.rr * risk)

        if candle.close < st.range_low:
            st.traded = True
            entry, stop = candle.close, st.range_high
            risk = stop - entry
            if risk <= 0:
                return None
            return Signal(symbol, Side.SELL, "orb_breakout_down", entry, stop,
                          target=entry - self.rr * risk)

        return None
