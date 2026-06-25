"""Demo: backtest ORB on deterministic synthetic intraday data.

Proves the full pipeline (strategy -> sizing -> engine -> costs -> stats) end to
end with no dependencies and no broker credentials. Replace `build_day` with real
Dhan historical candles once the Data API is connected.

    python3 scripts/demo_backtest.py
"""
import os
import sys
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradingbot.backtest.costs import CostModel  # noqa: E402
from tradingbot.backtest.engine import Backtester  # noqa: E402
from tradingbot.backtest.stats import compute_stats, format_report  # noqa: E402
from tradingbot.strategies.base import Candle  # noqa: E402
from tradingbot.strategies.orb import OpeningRangeBreakout  # noqa: E402


def build_day(day: datetime, outcome: str) -> list[Candle]:
    """One synthetic day. Opening range [100,110]; a long breakout at 9:30 to 111."""
    base = datetime(day.year, day.month, day.day, 9, 15)
    cs = [
        Candle(base, 105, 110, 100, 108, 1000),
        Candle(base + timedelta(minutes=5), 108, 109, 101, 104, 900),
        Candle(base + timedelta(minutes=10), 104, 107, 102, 106, 800),
        Candle(base + timedelta(minutes=15), 107, 111.5, 106, 111, 1500),  # breakout
    ]
    t = base + timedelta(minutes=20)
    if outcome == "win":
        cs.append(Candle(t, 111, 134, 110, 133, 2000))     # tags target 133
    elif outcome == "loss":
        cs.append(Candle(t, 111, 112, 99, 100, 1800))      # tags stop 100
    else:  # chop -> exits at end of day
        cs.append(Candle(t, 111, 116, 108, 113, 1200))
        cs.append(Candle(base + timedelta(minutes=370), 113, 114, 112, 112.5, 700))
    return cs


def main():
    outcomes = ["win", "loss", "win", "chop", "win", "loss", "win", "chop"]
    candles: list[Candle] = []
    for k, o in enumerate(outcomes):
        candles += build_day(datetime(2026, 6, 1 + k), o)

    bt = Backtester(
        strategy_factory=lambda: OpeningRangeBreakout(
            opening_range_minutes=15, session_open=time(9, 15), rr=2.0),
        costs=CostModel(),          # intraday Indian costs
        equity=100_000,
        risk_per_trade_pct=1.0,
    )
    res = bt.run({"DEMO": candles})

    print(format_report(compute_stats(res)))
    print("\nTrades:")
    for t in res.trades:
        print(f"  {t.entry_ts.date()}  {t.side.value:4} {t.qty}@{t.entry:.0f} "
              f"-> {t.exit:.1f} [{t.reason:6}]  gross ₹{t.gross_pnl:>8,.0f}  "
              f"net ₹{t.net_pnl:>8,.0f}")


if __name__ == "__main__":
    main()
