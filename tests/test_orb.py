"""Unit tests for the ORB strategy. Pure-stdlib; runnable directly:
    python3 tests/test_orb.py
"""
import os
import sys
from datetime import datetime, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.brokers.models import Side  # noqa: E402
from tradingbot.strategies.base import Candle  # noqa: E402
from tradingbot.strategies.orb import OpeningRangeBreakout  # noqa: E402


def _c(hh, mm, o, h, low, c):
    return Candle(datetime(2026, 6, 23, hh, mm), o, h, low, c, 1000)


def test_orb_long_breakout():
    orb = OpeningRangeBreakout(opening_range_minutes=15, session_open=time(9, 15), rr=2.0)
    # opening range 9:15-9:29 builds high=110, low=100
    assert orb.on_candle("X", _c(9, 15, 105, 110, 100, 108)) is None
    assert orb.on_candle("X", _c(9, 20, 108, 109, 103, 106)) is None
    # 9:30 close 111 breaks above 110
    out = orb.on_candle("X", _c(9, 30, 109, 112, 109, 111))
    assert out is not None and out.side is Side.BUY
    assert out.stop == 100
    assert abs(out.target - (111 + 2 * (111 - 100))) < 1e-9


def test_orb_short_breakout():
    orb = OpeningRangeBreakout(opening_range_minutes=15, session_open=time(9, 15), rr=2.0)
    orb.on_candle("Y", _c(9, 15, 105, 110, 100, 108))
    out = orb.on_candle("Y", _c(9, 30, 101, 101, 95, 98))   # close 98 < low 100
    assert out is not None and out.side is Side.SELL
    assert out.stop == 110


def test_orb_one_trade_per_day():
    orb = OpeningRangeBreakout(opening_range_minutes=15, session_open=time(9, 15))
    orb.on_candle("X", _c(9, 15, 105, 110, 100, 108))
    first = orb.on_candle("X", _c(9, 30, 109, 112, 109, 111))
    second = orb.on_candle("X", _c(9, 35, 112, 115, 112, 114))
    assert first is not None and second is None


def test_orb_no_signal_inside_range():
    orb = OpeningRangeBreakout(opening_range_minutes=15, session_open=time(9, 15))
    orb.on_candle("X", _c(9, 15, 105, 110, 100, 108))
    # 9:30 close 105 stays inside [100,110] -> no trade
    assert orb.on_candle("X", _c(9, 30, 106, 109, 104, 105)) is None


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} ORB tests passed.")


if __name__ == "__main__":
    _run_all()
