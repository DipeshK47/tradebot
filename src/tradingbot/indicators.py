"""Incremental, stdlib-only indicators for the live scanner.

Each indicator is updated one value at a time (O(1)-ish), so the scanner can run
across hundreds of symbols without recomputing over full history each tick.
Returns None during warmup (insufficient data).
"""
from __future__ import annotations

from collections import deque
from typing import Optional


class RSI:
    """Wilder's RSI. Returns None until `period` price changes are seen."""

    def __init__(self, period: int = 14):
        self.period = period
        self._prev_close: Optional[float] = None
        self._avg_gain: Optional[float] = None
        self._avg_loss: Optional[float] = None
        self._gains: list[float] = []
        self._losses: list[float] = []

    def update(self, close: float) -> Optional[float]:
        if self._prev_close is None:
            self._prev_close = close
            return None
        change = close - self._prev_close
        self._prev_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self._avg_gain is None:                     # seeding (simple average)
            self._gains.append(gain)
            self._losses.append(loss)
            if len(self._gains) < self.period:
                return None
            self._avg_gain = sum(self._gains) / self.period
            self._avg_loss = sum(self._losses) / self.period
        else:                                          # Wilder smoothing
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

        if self._avg_loss == 0:
            return 100.0
        rs = self._avg_gain / self._avg_loss
        return 100.0 - 100.0 / (1.0 + rs)


class Bollinger:
    """Bollinger bands over a rolling window. Returns (lower, mid, upper) or None."""

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.k = num_std
        self._win: deque[float] = deque(maxlen=period)

    def peek(self) -> Optional[tuple[float, float, float]]:
        """Bands over the CURRENT window WITHOUT adding a new value — lets a caller
        test a candle against the band of the PRIOR candles only (excludes itself)."""
        if len(self._win) < self.period:
            return None
        mean = sum(self._win) / self.period
        var = sum((x - mean) ** 2 for x in self._win) / self.period
        std = var ** 0.5
        return (mean - self.k * std, mean, mean + self.k * std)

    def update(self, close: float) -> Optional[tuple[float, float, float]]:
        self._win.append(close)
        return self.peek()
