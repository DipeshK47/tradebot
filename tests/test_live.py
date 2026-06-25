"""Tests for the live tick->candle->scanner engine (no network)."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.live import CandleAggregator, LiveScanEngine, extract_ltp  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
BASE = int(datetime(2026, 6, 24, 9, 15, tzinfo=IST).timestamp())


def test_aggregator_builds_bar_on_rollover():
    bars = []
    agg = CandleAggregator(15, lambda s, c: bars.append((s, c)))
    agg.add_tick("X", 100, BASE + 10)
    agg.add_tick("X", 105, BASE + 60)     # high
    agg.add_tick("X", 98, BASE + 120)     # low
    agg.add_tick("X", 102, BASE + 200)    # close
    assert bars == []                      # bar still forming
    agg.add_tick("X", 103, BASE + 15 * 60 + 5)   # next bar -> emit previous
    assert len(bars) == 1
    _, c = bars[0]
    assert (c.open, c.high, c.low, c.close) == (100, 105, 98, 102)


def test_aggregator_ignores_out_of_order():
    bars = []
    agg = CandleAggregator(15, lambda s, c: bars.append(c))
    agg.add_tick("X", 100, BASE + 60)
    agg.add_tick("X", 99, BASE - 100)      # stale -> ignored, no new bar/emit
    assert bars == []


def test_extract_ltp_shapes():
    assert extract_ltp({"ltpc": {"ltp": 123.5, "ltt": 1700000000000}}) == (123.5, 1700000000000)
    assert extract_ltp({"fullFeed": {"marketFF": {"ltpc": {"ltp": 50}}}}) == (50.0, None)
    assert extract_ltp({}) == (None, None)


def test_engine_ticks_flow_to_bars():
    alerts = []
    eng = LiveScanEngine({"NSE_EQ|K": "X"}, lambda a, tf: alerts.append(a))
    for i in range(40):                    # one tick per 15-min bucket -> 39 bars emitted
        msg = {"feeds": {"NSE_EQ|K": {"ltpc": {"ltp": 100 + i, "ltt": (BASE + i * 15 * 60) * 1000}}}}
        eng.on_message(msg)
    assert eng.ticks_seen == 40
    assert eng.bars_seen >= 38             # scanners ran on the bars without error


def test_engine_skips_unknown_instrument():
    eng = LiveScanEngine({"NSE_EQ|K": "X"}, lambda a, tf: None)
    eng.on_message({"feeds": {"NSE_EQ|OTHER": {"ltpc": {"ltp": 100, "ltt": BASE * 1000}}}})
    assert eng.ticks_seen == 0


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} live-engine tests passed.")


if __name__ == "__main__":
    _run_all()
