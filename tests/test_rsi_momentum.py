"""Tests for the RSI momentum (50 -> 60) scanner.
Runnable: python3 tests/test_rsi_momentum.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.scanners.rsi_momentum import RsiMomentumScanner  # noqa: E402
from tradingbot.strategies.base import Candle  # noqa: E402

T0 = datetime(2026, 6, 1, 9, 15)


def _run(closes):
    sc = RsiMomentumScanner(timeframe="15min", period=14, level1=50.0, level2=60.0)
    out = []
    for i, cl in enumerate(closes):
        c = Candle(T0 + timedelta(minutes=15 * i), cl, cl, cl, cl, 1000)
        a = sc.on_candle("X", c)
        if a:
            out.append(a)
    return out


def test_journey_crosses_50_then_60():
    # decline (RSI low, below 50), then a sustained rally up through 50 and 60
    closes = [100 - i for i in range(15)] + [85 + 2 * i for i in range(30)]
    alerts = _run(closes)
    stages = [a.meta["stage"] for a in alerts]
    assert "cross50" in stages, stages
    assert "cross60" in stages, stages
    # the 60 cross came up through 50 first -> clean
    c60 = next(a for a in alerts if a.meta["stage"] == "cross60")
    assert c60.meta["action"] == "BUY" and c60.meta["from_50"] is True


def test_no_signal_while_declining():
    # strictly declining -> RSI stays low, never crosses up through 50
    alerts = _run([100 - 0.5 * i for i in range(40)])
    assert alerts == []


def test_cross_is_event_not_repeated():
    # one clean run up; the 60 cross should fire exactly once (not every bar above 60)
    closes = [100 - i for i in range(15)] + [85 + 2 * i for i in range(30)]
    alerts = _run(closes)
    assert sum(1 for a in alerts if a.meta["stage"] == "cross60") == 1


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} RSI-momentum tests passed.")


if __name__ == "__main__":
    _run_all()
