"""Strategy interface.

A strategy consumes finalized candles and emits Signals. It must be deterministic
(no hidden external state) so that the SAME code produces the SAME signals in
backtest, paper, and live — that property is what makes paper results trustworthy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..brokers.models import Side


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Signal:
    symbol: str
    side: Side
    reason: str
    entry: float
    stop: float
    target: Optional[float] = None
    strength: float = 1.0   # 0..1; the LLM overlay may scale this, never the stop


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def on_candle(self, symbol: str, candle: Candle) -> Optional[Signal]:
        """Consume one finalized candle; optionally emit a Signal."""
