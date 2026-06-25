"""Scanner interface + Alert model.

A Scanner watches a candle stream for one symbol and emits an Alert when its
condition fires. Scanners are notification-only — they do NOT size or place trades
(that is the strategy + risk engine path). Same incremental on_candle pattern as
strategies, so backtest behavior == live behavior.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..strategies.base import Candle


@dataclass
class Alert:
    symbol: str
    kind: str                # scanner name, e.g. "bollinger_outside"
    direction: str           # "up" | "down"
    message: str             # human-readable, for Telegram / dashboard
    price: float
    ts: datetime
    meta: dict = field(default_factory=dict)


class Scanner(ABC):
    name: str = "base"
    timeframe: str = "1min"  # "1min" | "5min" | "15min" | "1hour" | "day"

    @abstractmethod
    def on_candle(self, symbol: str, candle: Candle) -> Optional[Alert]:
        """Consume one finalized candle; optionally emit an Alert."""

    def feed(self, symbol: str, candle: Candle) -> Optional[Alert]:
        """Guarded entry point: drops duplicate / out-of-order candles per symbol so
        live websocket re-delivery can't corrupt indicator state, then delegates to
        on_candle. Live + engine code should call feed(), not on_candle directly."""
        seen = getattr(self, "_seen_ts", None)
        if seen is None:
            seen = {}
            self._seen_ts = seen
        last = seen.get(symbol)
        if last is not None and candle.ts <= last:
            return None
        seen[symbol] = candle.ts
        return self.on_candle(symbol, candle)
