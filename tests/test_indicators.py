"""Tests for incremental indicators. Runnable: python3 tests/test_indicators.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.indicators import RSI, Bollinger  # noqa: E402


def test_rsi_all_gains_is_100():
    rsi = RSI(period=14)
    val = None
    for p in range(1, 20):          # strictly increasing -> only gains
        val = rsi.update(float(p))
    assert val == 100.0


def test_rsi_all_losses_is_0():
    rsi = RSI(period=14)
    val = None
    for p in range(20, 1, -1):      # strictly decreasing -> only losses
        val = rsi.update(float(p))
    assert val == 0.0


def test_rsi_warmup_returns_none():
    rsi = RSI(period=14)
    # 1 update sets prev_close, then 14 changes seed the averages ->
    # the first numeric RSI value appears on update #15.
    assert rsi.update(100.0) is None                       # #1: sets prev_close
    warm = [rsi.update(100.0 + i) for i in range(1, 14)]   # #2..#14: 13 distinct changes
    assert all(v is None for v in warm)
    assert rsi.update(120.0) is not None                   # #15: first RSI value


def test_bollinger_constant_series_zero_width():
    bb = Bollinger(period=20, num_std=2.0)
    out = None
    for _ in range(20):
        out = bb.update(100.0)
    lower, mid, upper = out
    assert mid == 100.0 and lower == 100.0 and upper == 100.0


def test_bollinger_warmup_none_then_value():
    bb = Bollinger(period=5, num_std=2.0)
    for _ in range(4):
        assert bb.update(100.0) is None
    assert bb.update(100.0) is not None


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} indicator tests passed.")


if __name__ == "__main__":
    _run_all()
