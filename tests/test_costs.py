"""Tests for the Indian cost model. Runnable: python3 tests/test_costs.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.backtest.costs import CostModel  # noqa: E402


def test_intraday_costs_positive_and_small():
    cm = CostModel()
    c = cm.round_trip(100, 102, 100)         # ~₹20k turnover each side
    assert c > 0
    assert c < 0.01 * (100 * 100 + 102 * 100)  # well under 1% of turnover


def test_delivery_stt_higher_than_intraday():
    intraday = CostModel().round_trip(100, 102, 100)
    delivery = CostModel.delivery().round_trip(100, 102, 100)
    assert delivery > intraday   # delivery STT (0.1% both sides) dominates


def test_costs_scale_with_size():
    cm = CostModel()
    assert cm.round_trip(100, 102, 200) > cm.round_trip(100, 102, 100)


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} cost tests passed.")


if __name__ == "__main__":
    _run_all()
