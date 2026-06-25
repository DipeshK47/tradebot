"""Bollinger Band breakout strategy.

BUY on a close crossing above the upper band, SELL on a close crossing below the
lower band; stop at the middle band (SMA). A regime-aware mean-reversion variant
is a later addition — see MASTER_PLAN §6. Always trade with the stop; fading a
real breakout without one is how Bollinger mean-reversion blows up.
"""
from __future__ import annotations

from collections import deque
from math import sqrt
from typing import Optional

from ..brokers.models import Side
from .base import Candle, Signal, Strategy


class BollingerBreakout(Strategy):
    name = "bollinger_breakout"

    def __init__(self, period: int = 20, num_std: float = 2.0, rr: float = 2.0):
        self.period = period
        self.k = num_std
        self.rr = rr
        self._win: dict[str, deque] = {}
        self._prev: dict[str, tuple[float, float, float]] = {}  # (close, upper, lower)

    def on_candle(self, symbol: str, c: Candle) -> Optional[Signal]:
        win = self._win.setdefault(symbol, deque(maxlen=self.period))
        win.append(c.close)
        if len(win) < self.period:
            return None

        mean = sum(win) / len(win)
        var = sum((x - mean) ** 2 for x in win) / len(win)
        std = sqrt(var)
        upper = mean + self.k * std
        lower = mean - self.k * std

        prev = self._prev.get(symbol)
        self._prev[symbol] = (c.close, upper, lower)
        if prev is None:
            return None
        prev_close, prev_upper, prev_lower = prev

        if c.close > upper and prev_close <= prev_upper:
            entry, stop = c.close, mean
            risk = entry - stop
            target = entry + self.rr * risk if risk > 0 else None
            return Signal(symbol, Side.BUY, "bb_breakout_up", entry, stop, target)
        if c.close < lower and prev_close >= prev_lower:
            entry, stop = c.close, mean
            risk = stop - entry
            target = entry - self.rr * risk if risk > 0 else None
            return Signal(symbol, Side.SELL, "bb_breakout_down", entry, stop, target)
        return None
