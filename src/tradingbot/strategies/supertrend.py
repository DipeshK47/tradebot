"""Supertrend strategy (ATR-banded trend follower).

Emits BUY when the trend flips up, SELL when it flips down. Stop is the Supertrend
line itself (a built-in trailing stop). ATR here uses a simple moving average of
True Range (Wilder smoothing is a later refinement). Regime-dependent — whipsaws
in sideways markets; must be backtested with costs.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from ..brokers.models import Side
from .base import Candle, Signal, Strategy


class Supertrend(Strategy):
    name = "supertrend"

    def __init__(self, period: int = 10, multiplier: float = 3.0, rr: float = 2.0):
        self.period = period
        self.mult = multiplier
        self.rr = rr
        self._tr: dict[str, deque] = {}
        self._prev_close: dict[str, float] = {}
        self._prev_fu: dict[str, float] = {}
        self._prev_fl: dict[str, float] = {}
        self._st_is_upper: dict[str, Optional[bool]] = {}

    def on_candle(self, symbol: str, c: Candle) -> Optional[Signal]:
        tr_window = self._tr.setdefault(symbol, deque(maxlen=self.period))
        prev_close = self._prev_close.get(symbol)

        if prev_close is None:
            tr = c.high - c.low
        else:
            tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        tr_window.append(tr)
        self._prev_close[symbol] = c.close

        if len(tr_window) < self.period:
            return None

        atr = sum(tr_window) / len(tr_window)
        hl2 = (c.high + c.low) / 2.0
        basic_upper = hl2 + self.mult * atr
        basic_lower = hl2 - self.mult * atr

        prev_fu = self._prev_fu.get(symbol)
        prev_fl = self._prev_fl.get(symbol)

        if prev_fu is None:  # first computed bar -> seed state, no signal
            self._prev_fu[symbol] = basic_upper
            self._prev_fl[symbol] = basic_lower
            self._st_is_upper[symbol] = c.close < hl2
            return None

        fu = basic_upper if (basic_upper < prev_fu or prev_close > prev_fu) else prev_fu
        fl = basic_lower if (basic_lower > prev_fl or prev_close < prev_fl) else prev_fl

        was_upper = self._st_is_upper[symbol]
        if was_upper:                       # previously in downtrend (line = upper)
            st_is_upper = not (c.close > fu)
        else:                               # previously in uptrend (line = lower)
            st_is_upper = (c.close < fl)

        self._prev_fu[symbol] = fu
        self._prev_fl[symbol] = fl
        self._st_is_upper[symbol] = st_is_upper

        if was_upper and not st_is_upper:   # flip down -> up
            entry, stop = c.close, fl
            risk = entry - stop
            target = entry + self.rr * risk if risk > 0 else None
            return Signal(symbol, Side.BUY, "supertrend_flip_up", entry, stop, target)
        if not was_upper and st_is_upper:   # flip up -> down
            entry, stop = c.close, fu
            risk = stop - entry
            target = entry - self.rr * risk if risk > 0 else None
            return Signal(symbol, Side.SELL, "supertrend_flip_down", entry, stop, target)
        return None
