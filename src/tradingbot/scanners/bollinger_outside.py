"""Bollinger 'full candle outside the band' scanner.

Fires when an entire candle clears a band: low > upper (fully above) or
high < lower (fully below). Default timeframe 1 hour, BB(20, 2σ).
"""
from __future__ import annotations

from typing import Optional

from ..indicators import Bollinger
from ..strategies.base import Candle
from .base import Alert, Scanner


class BollingerOutsideScanner(Scanner):
    name = "bollinger_outside"

    def __init__(self, timeframe: str = "1hour", period: int = 20, num_std: float = 2.0):
        self.timeframe = timeframe
        self.period = period
        self.num_std = num_std
        self._bb: dict[str, Bollinger] = {}

    def on_candle(self, symbol: str, c: Candle) -> Optional[Alert]:
        bb = self._bb.setdefault(symbol, Bollinger(self.period, self.num_std))
        bands = bb.peek()        # band from PRIOR candles only — excludes this candle
        bb.update(c.close)       # then fold this close into the window for next time
        if bands is None:
            return None
        lower, mid, upper = bands
        if upper <= lower:       # degenerate (flat / zero-variance) window -> no signal
            return None

        if c.low > upper:        # entire candle above the upper band
            return Alert(symbol, self.name, "up",
                         f"Full {self.timeframe} candle ABOVE upper BB "
                         f"(low {c.low:.2f} > upper {upper:.2f})",
                         c.close, c.ts,
                         {"upper": upper, "mid": mid, "lower": lower})
        if c.high < lower:       # entire candle below the lower band
            return Alert(symbol, self.name, "down",
                         f"Full {self.timeframe} candle BELOW lower BB "
                         f"(high {c.high:.2f} < lower {lower:.2f})",
                         c.close, c.ts,
                         {"upper": upper, "mid": mid, "lower": lower})
        return None
