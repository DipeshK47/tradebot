"""Previous-day high/low breakout scanner.

Tracks each day's high/low from the intraday stream; on the next day, fires when
price breaks the PREVIOUS day's high (up) or low (down). One alert per side per day.
Single intraday stream — no separate daily feed needed.
"""
from __future__ import annotations

from typing import Optional

from ..strategies.base import Candle
from .base import Alert, Scanner


class PrevDayBreakScanner(Scanner):
    name = "prev_day_break"

    def __init__(self, timeframe: str = "15min"):
        self.timeframe = timeframe
        self._cur_day: dict[str, object] = {}
        self._cur_high: dict[str, float] = {}
        self._cur_low: dict[str, float] = {}
        self._prev_high: dict[str, float] = {}
        self._prev_low: dict[str, float] = {}
        self._fired_high: dict[str, bool] = {}
        self._fired_low: dict[str, bool] = {}

    def on_candle(self, symbol: str, c: Candle) -> Optional[Alert]:
        day = c.ts.date()
        cur = self._cur_day.get(symbol)
        if cur is None or day > cur:
            # new (strictly later) day: yesterday's running H/L becomes the reference
            if cur is not None:
                self._prev_high[symbol] = self._cur_high[symbol]
                self._prev_low[symbol] = self._cur_low[symbol]
            self._cur_day[symbol] = day
            self._cur_high[symbol] = c.high
            self._cur_low[symbol] = c.low
            self._fired_high[symbol] = False
            self._fired_low[symbol] = False
        elif day == cur:
            self._cur_high[symbol] = max(self._cur_high[symbol], c.high)
            self._cur_low[symbol] = min(self._cur_low[symbol], c.low)
        else:
            return None  # stray earlier-dated candle: ignore, don't corrupt reference

        ph = self._prev_high.get(symbol)
        pl = self._prev_low.get(symbol)

        if ph is not None and not self._fired_high[symbol] and c.high > ph:
            self._fired_high[symbol] = True
            return Alert(symbol, self.name, "up",
                         f"Broke previous-day HIGH {ph:.2f}", c.close, c.ts,
                         {"prev_high": ph})
        if pl is not None and not self._fired_low[symbol] and c.low < pl:
            self._fired_low[symbol] = True
            return Alert(symbol, self.name, "down",
                         f"Broke previous-day LOW {pl:.2f}", c.close, c.ts,
                         {"prev_low": pl})
        return None
