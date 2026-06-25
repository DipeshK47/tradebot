"""RSI threshold scanner.

Fires when RSI(period) CROSSES the threshold (an event, not a persistent state),
which avoids re-alerting every bar while RSI stays above the level. Default:
RSI(14) crossing above 60 on 15-minute candles.
"""
from __future__ import annotations

from typing import Optional

from ..indicators import RSI
from ..strategies.base import Candle
from .base import Alert, Scanner


class RsiScanner(Scanner):
    name = "rsi_threshold"

    def __init__(self, timeframe: str = "15min", period: int = 14,
                 threshold: float = 60.0, direction: str = "above"):
        assert direction in ("above", "below")
        self.timeframe = timeframe
        self.period = period
        self.threshold = threshold
        self.direction = direction
        self._rsi: dict[str, RSI] = {}
        self._prev_val: dict[str, float] = {}

    def on_candle(self, symbol: str, c: Candle) -> Optional[Alert]:
        rsi = self._rsi.setdefault(symbol, RSI(self.period))
        val = rsi.update(c.close)
        if val is None:
            return None
        prev = self._prev_val.get(symbol)
        self._prev_val[symbol] = val
        if prev is None:
            return None

        if self.direction == "above" and prev <= self.threshold < val:
            return Alert(symbol, self.name, "up",
                         f"RSI({self.period}) crossed ABOVE {self.threshold:.0f} "
                         f"-> {val:.1f}", c.close, c.ts, {"rsi": val})
        if self.direction == "below" and prev >= self.threshold > val:
            return Alert(symbol, self.name, "down",
                         f"RSI({self.period}) crossed BELOW {self.threshold:.0f} "
                         f"-> {val:.1f}", c.close, c.ts, {"rsi": val})
        return None
