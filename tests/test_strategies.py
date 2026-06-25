"""Tests for Supertrend and Bollinger strategies. Runnable:
    python3 tests/test_strategies.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.brokers.models import Side  # noqa: E402
from tradingbot.strategies.base import Candle  # noqa: E402
from tradingbot.strategies.bollinger import BollingerBreakout  # noqa: E402
from tradingbot.strategies.supertrend import Supertrend  # noqa: E402

T0 = datetime(2026, 6, 1, 9, 15)


def _c(i, o, h, low, cl):
    return Candle(T0 + timedelta(minutes=i), o, h, low, cl, 1000)


def test_supertrend_flips_up_then_down():
    st = Supertrend(period=10, multiplier=3.0)
    sides = []
    price = 200.0
    i = 0
    # phase 1: 15 bars DOWN — seed state in a downtrend (no flip-up possible yet)
    for _ in range(15):
        price -= 2
        s = st.on_candle("X", _c(i, price + 1, price + 1.5, price - 1, price)); i += 1
        if s:
            sides.append(s.side)
    # phase 2: 25 bars UP — should flip down->up (BUY)
    for _ in range(25):
        price += 2
        s = st.on_candle("X", _c(i, price - 1, price + 1, price - 1.5, price)); i += 1
        if s:
            sides.append(s.side)
    # phase 3: 15 bars DOWN — should flip up->down (SELL)
    for _ in range(15):
        price -= 2
        s = st.on_candle("X", _c(i, price + 1, price + 1.5, price - 1, price)); i += 1
        if s:
            sides.append(s.side)
    assert Side.BUY in sides, sides
    assert Side.SELL in sides, sides


def test_bollinger_breakout_up():
    bb = BollingerBreakout(period=20, num_std=2.0)
    sig = None
    # 20 bars oscillating ~100 to build a band, then a jump well above it
    for i in range(20):
        px = 99.0 if i % 2 == 0 else 101.0
        assert bb.on_candle("X", _c(i, px, px + 0.5, px - 0.5, px)) is None
    out = bb.on_candle("X", _c(20, 101, 111, 101, 110))
    assert out is not None and out.side is Side.BUY
    assert out.stop < out.entry            # stop at the middle band, below entry
    assert out.target and out.target > out.entry


def test_bollinger_breakout_down():
    bb = BollingerBreakout(period=20, num_std=2.0)
    for i in range(20):
        px = 99.0 if i % 2 == 0 else 101.0
        bb.on_candle("X", _c(i, px, px + 0.5, px - 0.5, px))
    out = bb.on_candle("X", _c(20, 99, 99, 89, 90))
    assert out is not None and out.side is Side.SELL
    assert out.stop > out.entry


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} strategy tests passed.")


if __name__ == "__main__":
    _run_all()
