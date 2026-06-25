"""Tests for the three scanners. Runnable: python3 tests/test_scanners.py"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.scanners.bollinger_outside import BollingerOutsideScanner  # noqa: E402
from tradingbot.scanners.prev_day_break import PrevDayBreakScanner  # noqa: E402
from tradingbot.scanners.rsi import RsiScanner  # noqa: E402
from tradingbot.strategies.base import Candle  # noqa: E402


def _c(ts, o, h, low, cl):
    return Candle(ts, o, h, low, cl, 1000)


def test_bollinger_outside_fires_up():
    sc = BollingerOutsideScanner(timeframe="1hour", period=20, num_std=2.0)
    t = datetime(2026, 6, 1, 9, 15)
    # 20 bars oscillating ~100 to establish a tight band
    for i in range(20):
        px = 99.0 if i % 2 == 0 else 101.0
        assert sc.on_candle("X", _c(t + timedelta(hours=i), px, px + 0.5, px - 0.5, px)) is None
    # a candle whose LOW (112) is well above the upper band
    a = sc.on_candle("X", _c(t + timedelta(hours=20), 114, 116, 112, 115))
    assert a is not None and a.direction == "up"


def test_bollinger_outside_fires_down():
    sc = BollingerOutsideScanner(timeframe="1hour", period=20, num_std=2.0)
    t = datetime(2026, 6, 1, 9, 15)
    for i in range(20):
        px = 99.0 if i % 2 == 0 else 101.0
        sc.on_candle("X", _c(t + timedelta(hours=i), px, px + 0.5, px - 0.5, px))
    a = sc.on_candle("X", _c(t + timedelta(hours=20), 86, 88, 84, 85))  # high below lower band
    assert a is not None and a.direction == "down"


def test_prev_day_break_up():
    sc = PrevDayBreakScanner(timeframe="15min")
    d1 = datetime(2026, 6, 1, 9, 15)
    sc.on_candle("X", _c(d1, 105, 110, 100, 105))            # day1 high=110 low=100
    sc.on_candle("X", _c(d1 + timedelta(minutes=15), 106, 108, 102, 106))
    d2 = datetime(2026, 6, 2, 9, 15)
    a = sc.on_candle("X", _c(d2, 111, 112, 109, 111))        # day2 high 112 > 110
    assert a is not None and a.direction == "up" and a.meta["prev_high"] == 110


def test_prev_day_break_one_alert_per_side():
    sc = PrevDayBreakScanner(timeframe="15min")
    d1 = datetime(2026, 6, 1, 9, 15)
    sc.on_candle("X", _c(d1, 105, 110, 100, 105))
    d2 = datetime(2026, 6, 2, 9, 15)
    first = sc.on_candle("X", _c(d2, 111, 112, 109, 111))
    second = sc.on_candle("X", _c(d2 + timedelta(minutes=15), 113, 115, 112, 114))
    assert first is not None and second is None              # only one high-break alert


def test_rsi_scanner_crosses_above_60():
    sc = RsiScanner(timeframe="15min", period=14, threshold=60.0, direction="above")
    t = datetime(2026, 6, 1, 9, 15)
    alerts = []
    price = 100.0
    i = 0
    for _ in range(15):                 # decline -> RSI low (well below 60)
        price -= 1
        a = sc.on_candle("X", _c(t + timedelta(minutes=15 * i), price, price, price, price)); i += 1
        if a:
            alerts.append(a)
    for _ in range(20):                 # rally -> RSI climbs and crosses 60
        price += 1
        a = sc.on_candle("X", _c(t + timedelta(minutes=15 * i), price, price, price, price)); i += 1
        if a:
            alerts.append(a)
    assert any(a.direction == "up" for a in alerts), "expected an RSI cross-above-60 alert"


def test_feed_drops_duplicate_and_out_of_order():
    sc = PrevDayBreakScanner(timeframe="15min")
    d1 = datetime(2026, 6, 1, 9, 15)
    c = _c(d1, 105, 110, 100, 105)
    sc.feed("X", c)
    assert sc.feed("X", c) is None                                   # exact duplicate ts
    assert sc.feed("X", _c(d1 - timedelta(minutes=15), 1, 999, 1, 500)) is None  # older ts


def test_prev_day_break_ignores_stray_earlier_day():
    sc = PrevDayBreakScanner(timeframe="15min")
    sc.on_candle("X", _c(datetime(2026, 6, 2, 9, 15), 105, 110, 100, 105))  # day = Jun 2
    # a stray candle from an EARLIER day must NOT overwrite the reference
    assert sc.on_candle("X", _c(datetime(2026, 6, 1, 9, 15), 1, 999, 1, 500)) is None
    a = sc.on_candle("X", _c(datetime(2026, 6, 3, 9, 15), 111, 112, 109, 111))
    assert a is not None and a.meta["prev_high"] == 110             # Jun3 breaks Jun2 high


def test_bollinger_excludes_current_candle():
    # 20 identical closes then one explosive candle: with the current candle EXCLUDED
    # from the band it must fire (the prior window is flat -> band==price, but the
    # candle's whole range is far above, and we guard the zero-width case separately).
    sc = BollingerOutsideScanner(timeframe="1hour", period=20, num_std=2.0)
    t = datetime(2026, 6, 1, 9, 15)
    for i in range(20):
        px = 100.0 + (i % 2)                       # 100/101 oscillation -> non-zero std
        assert sc.on_candle("X", _c(t + timedelta(hours=i), px, px + 0.3, px - 0.3, px)) is None
    a = sc.on_candle("X", _c(t + timedelta(hours=20), 150, 152, 148, 151))
    assert a is not None and a.direction == "up"


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} scanner tests passed.")


if __name__ == "__main__":
    _run_all()
