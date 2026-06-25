"""Unit tests for the fail-closed risk engine. Pure-stdlib; runnable directly:
    python3 tests/test_risk.py
or via pytest.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.brokers.models import Order, OrderType, Side  # noqa: E402
from tradingbot.risk.limits import (  # noqa: E402
    PortfolioState, RiskEngine, RiskLimits, position_size,
)


def _limits(**over):
    base = dict(
        max_risk_per_trade_pct=1.0,
        max_position_value=50_000,
        max_total_exposure_value=100_000,
        max_daily_loss=2_000,
        max_open_positions=5,
        max_orders_per_day=50,
        instrument_whitelist=frozenset({"RELIANCE"}),
        arm_live=False,
    )
    base.update(over)
    return RiskLimits(**base)


def test_position_size_basic():
    # 1L equity, 1% risk = 1000 rupees; stop 5 away -> 200 shares
    assert position_size(100_000, 1.0, 100.0, 95.0) == 200


def test_position_size_failcloses_on_no_stop():
    assert position_size(100_000, 1.0, 100.0, 100.0) == 0
    assert position_size(0, 1.0, 100.0, 95.0) == 0


def test_position_size_respects_lot():
    # raw would be 200; lot of 75 -> 150
    assert position_size(100_000, 1.0, 100.0, 95.0, lot_size=75) == 150


def test_default_limits_fail_closed():
    # Unconfigured limits must deny everything.
    eng = RiskEngine(RiskLimits(), mode="paper")
    o = Order("RELIANCE", Side.BUY, qty=1)
    assert not eng.check_order(o, 1000.0, PortfolioState(equity=100_000)).allowed


def test_allows_valid_order():
    eng = RiskEngine(_limits(), mode="paper")
    o = Order("RELIANCE", Side.BUY, qty=10, order_type=OrderType.MARKET)
    d = eng.check_order(o, 1000.0, PortfolioState(equity=100_000))
    assert d.allowed, d.reason


def test_blocks_non_whitelisted():
    eng = RiskEngine(_limits(), mode="paper")
    o = Order("PENNYSTOCK", Side.BUY, qty=10)
    assert not eng.check_order(o, 50.0, PortfolioState(equity=100_000)).allowed


def test_blocks_oversized_position():
    eng = RiskEngine(_limits(max_position_value=5_000), mode="paper")
    o = Order("RELIANCE", Side.BUY, qty=10)  # 10 * 1000 = 10k > 5k cap
    assert not eng.check_order(o, 1000.0, PortfolioState(equity=100_000)).allowed


def test_blocks_total_exposure():
    eng = RiskEngine(_limits(), mode="paper")
    o = Order("RELIANCE", Side.BUY, qty=10)  # +10k onto 95k open => 105k > 100k
    st = PortfolioState(equity=100_000, open_exposure_value=95_000,
                        has_position_in_symbol=True)
    assert not eng.check_order(o, 1000.0, st).allowed


def test_live_requires_arm():
    o = Order("RELIANCE", Side.BUY, qty=1)
    eng_off = RiskEngine(_limits(arm_live=False), mode="live")
    assert not eng_off.check_order(o, 1000.0, PortfolioState(equity=100_000)).allowed
    eng_on = RiskEngine(_limits(arm_live=True), mode="live")
    assert eng_on.check_order(o, 1000.0, PortfolioState(equity=100_000)).allowed


def test_daily_loss_halts():
    eng = RiskEngine(_limits(), mode="paper")
    o = Order("RELIANCE", Side.BUY, qty=1)
    st = PortfolioState(equity=100_000, realized_pnl_today=-2_500)
    assert not eng.check_order(o, 1000.0, st).allowed


def test_kill_switch():
    eng = RiskEngine(_limits(), mode="paper")
    eng.engage_kill_switch("test")
    o = Order("RELIANCE", Side.BUY, qty=1)
    assert not eng.check_order(o, 1000.0, PortfolioState(equity=100_000)).allowed


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} risk tests passed.")


if __name__ == "__main__":
    _run_all()
