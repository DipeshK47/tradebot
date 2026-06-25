"""RSI momentum scanner — the staged 50 -> 60 journey (15-min).

Tracks bullish momentum building through two levels:
  - RSI crosses ABOVE 50  -> "momentum building" alert, and ARMS the setup.
  - RSI crosses ABOVE 60  -> BUY alert. Flagged "clean run from 50" if RSI came up
                             through 50 first and didn't drop back below 50 since.
  - RSI dropping back below 50 disarms the setup.

Cross = an event (fires once per crossing), so it won't spam while RSI sits above
a level. Up-side / bullish only (mirror for shorts later if wanted).
"""
from __future__ import annotations

from typing import Optional

from ..indicators import RSI
from ..strategies.base import Candle
from .base import Alert, Scanner


class RsiMomentumScanner(Scanner):
    name = "rsi_momentum"

    def __init__(self, timeframe: str = "15min", period: int = 14,
                 level1: float = 50.0, level2: float = 60.0):
        self.timeframe = timeframe
        self.period = period
        self.level1 = level1
        self.level2 = level2
        self._rsi: dict[str, RSI] = {}
        self._prev: dict[str, float] = {}
        self._armed: dict[str, bool] = {}     # crossed level1 up, not yet back below

    def on_candle(self, symbol: str, c: Candle) -> Optional[Alert]:
        r = self._rsi.setdefault(symbol, RSI(self.period))
        val = r.update(c.close)
        if val is None:
            return None
        prev = self._prev.get(symbol)
        self._prev[symbol] = val
        if prev is None:
            return None

        alert: Optional[Alert] = None

        # cross UP through level1 (50): momentum building, arm the setup
        if prev <= self.level1 < val:
            self._armed[symbol] = True
            alert = Alert(symbol, self.name, "up",
                          f"RSI({self.period}) crossed above {self.level1:.0f} "
                          f"-> {val:.1f} (momentum building)",
                          c.close, c.ts,
                          {"rsi": round(val, 1), "level": self.level1,
                           "stage": "cross50", "action": "WATCH"})
        # drop back below level1: disarm
        elif prev >= self.level1 > val:
            self._armed[symbol] = False

        # cross UP through level2 (60): BUY (priority over the level1 alert)
        if prev <= self.level2 < val:
            clean = self._armed.get(symbol, False)
            alert = Alert(symbol, self.name, "up",
                          f"RSI({self.period}) crossed above {self.level2:.0f} "
                          f"-> {val:.1f}" + (" [clean run from 50]" if clean else ""),
                          c.close, c.ts,
                          {"rsi": round(val, 1), "level": self.level2,
                           "stage": "cross60", "action": "BUY", "from_50": clean})
        return alert
