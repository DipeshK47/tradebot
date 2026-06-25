"""Tests for the Bollinger breakout-confirmation scanner.
Runnable: python3 tests/test_bb_breakout.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.scanners.bollinger_breakout import BollingerBreakoutScanner  # noqa: E402
from tradingbot.strategies.base import Candle  # noqa: E402

T0 = datetime(2026, 6, 1, 9, 15)


def _run(closes):
    sc = BollingerBreakoutScanner(timeframe="15min", period=20, num_std=1.5)
    out = []
    for i, cl in enumerate(closes):
        c = Candle(T0 + timedelta(minutes=15 * i), cl, cl + 0.5, cl - 0.5, cl, 1000)
        a = sc.on_candle("X", c)
        if a:
            out.append(a)
    return out


# 20 warmup closes oscillating 99/101 (mean ~100, std ~1) -> band ~[98.5, 101.5]
WARM = [99.0 if i % 2 == 0 else 101.0 for i in range(20)]


def test_upper_band_then_higher_close_is_buy():
    # 105 closes above upper band (signal), 107 closes higher -> BUY
    alerts = _run(WARM + [105.0, 107.0])
    assert len(alerts) == 1 and alerts[0].direction == "up"
    assert alerts[0].meta["band"] == "upper" and alerts[0].meta["action"] == "BUY"


def test_upper_band_then_lower_close_is_sell():
    # 105 above upper (signal), 103 closes lower -> SELL
    alerts = _run(WARM + [105.0, 103.0])
    assert len(alerts) == 1 and alerts[0].direction == "down"
    assert alerts[0].meta["band"] == "upper" and alerts[0].meta["action"] == "SELL"


def test_lower_band_then_higher_close_is_buy():
    # 95 closes below lower band (signal), 97 closes higher -> BUY
    alerts = _run(WARM + [95.0, 97.0])
    assert len(alerts) == 1 and alerts[0].direction == "up"
    assert alerts[0].meta["band"] == "lower"


def test_lower_band_then_lower_close_is_sell():
    alerts = _run(WARM + [95.0, 93.0])
    assert len(alerts) == 1 and alerts[0].direction == "down"
    assert alerts[0].meta["band"] == "lower"


def test_equal_close_no_signal():
    alerts = _run(WARM + [105.0, 105.0])
    assert alerts == []


def test_no_breakout_no_signal():
    # gentle oscillation, nothing closes beyond the band
    alerts = _run(WARM + [100.0, 100.5, 99.5, 100.0])
    assert alerts == []


def test_band_walk_fires_once():
    # a strong run all beyond the upper band must fire exactly ONE alert
    # (the confirmation of the first fresh breakout), not one per candle.
    alerts = _run(WARM + [105.0, 107.0, 109.0, 111.0, 113.0])
    assert len(alerts) == 1 and alerts[0].direction == "up"


def test_reentry_rearms():
    # breakout (BUY), back inside the band, then a second fresh breakout (BUY) -> 2 alerts
    alerts = _run(WARM + [105.0, 107.0, 100.0, 105.0, 107.0])
    assert len(alerts) == 2 and all(a.direction == "up" for a in alerts)


def test_close_beyond_band_but_candle_straddles_no_signal():
    # NEW RULE: the whole candle must clear the band. A candle that CLOSES above the
    # upper band but whose low is still inside (straddling the band) must NOT arm a signal.
    sc = BollingerBreakoutScanner(timeframe="15min", period=20, num_std=1.5)
    alerts = []
    for i, cl in enumerate(WARM):                       # warmup (band ~[98.5,101.5])
        c = Candle(T0 + timedelta(minutes=15 * i), cl, cl + 0.5, cl - 0.5, cl, 1000)
        a = sc.on_candle("X", c)
        if a:
            alerts.append(a)
    # straddle: close 102 (> upper ~101.7) but low 100 (< upper) -> NOT fully outside
    straddle = Candle(T0 + timedelta(minutes=15 * 20), 101.0, 103.0, 100.0, 102.0, 1000)
    a = sc.on_candle("X", straddle)
    if a:
        alerts.append(a)
    # a benign inside candle next: if the straddle had (wrongly) armed, this would confirm
    nxt = Candle(T0 + timedelta(minutes=15 * 21), 100.5, 101.0, 100.0, 100.5, 1000)
    a = sc.on_candle("X", nxt)
    if a:
        alerts.append(a)
    assert alerts == [], "a straddling candle (close out, low/high not) must not signal"


def test_full_candle_outside_then_higher_is_buy():
    # control: a candle FULLY above the upper band (low > upper) DOES arm; higher next -> BUY
    sc = BollingerBreakoutScanner(timeframe="15min", period=20, num_std=1.5)
    for i, cl in enumerate(WARM):
        sc.on_candle("X", Candle(T0 + timedelta(minutes=15 * i), cl, cl + 0.5, cl - 0.5, cl, 1000))
    out = []
    sig = Candle(T0 + timedelta(minutes=15 * 20), 105.0, 106.0, 104.5, 105.0, 1000)  # low 104.5 > upper
    out.append(sc.on_candle("X", sig))
    nxt = Candle(T0 + timedelta(minutes=15 * 21), 107.0, 108.0, 106.5, 107.0, 1000)
    out.append(sc.on_candle("X", nxt))
    fired = [a for a in out if a]
    assert len(fired) == 1 and fired[0].direction == "up" and fired[0].meta["action"] == "BUY"


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} BB-breakout tests passed.")


if __name__ == "__main__":
    _run_all()
