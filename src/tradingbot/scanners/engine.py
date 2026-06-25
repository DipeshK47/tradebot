"""Scanner engine — routes candle streams to scanners by timeframe and collects
alerts. Backtest/offline form; the live form will feed the same on_candle from the
Upstox websocket as bars finalize.
"""
from __future__ import annotations

from .base import Alert, Scanner
from ..strategies.base import Candle


def run_scanners(scanners: list[Scanner],
                 candles_by_tf: dict[str, dict[str, list[Candle]]]) -> list[Alert]:
    """candles_by_tf = {timeframe: {symbol: [Candle, ...]}}.

    Each scanner only receives candles of its declared timeframe.
    """
    alerts: list[Alert] = []
    for scanner in scanners:
        data = candles_by_tf.get(scanner.timeframe, {})
        for symbol, candles in data.items():
            for c in candles:
                a = scanner.feed(symbol, c)   # feed() dedups + orders per symbol
                if a is not None:
                    alerts.append(a)
    return alerts
