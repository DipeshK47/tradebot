"""Event-driven backtest engine.

Drives a Strategy over candle series, opens one position per symbol on a signal,
exits on stop/target/end-of-day, and applies the Indian cost model. Uses the same
Strategy interface + position sizing as live, so backtest behavior == live behavior.

Caveat: this models stop/target at candle granularity (conservative: stop checked
before target within a bar). Validate execution-sensitive strategies on finer data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from ..brokers.models import Side
from ..risk.limits import position_size
from ..strategies.base import Candle, Strategy
from .costs import CostModel


@dataclass
class Trade:
    symbol: str
    side: Side
    entry_ts: datetime
    entry: float
    exit_ts: datetime
    exit: float
    qty: int
    gross_pnl: float
    costs: float
    reason: str

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.costs


@dataclass
class BacktestResult:
    starting_equity: float = 0.0
    trades: list[Trade] = field(default_factory=list)


def _check_exit(side: Side, stop: float, target: Optional[float], c: Candle):
    if side is Side.BUY:
        if c.low <= stop:
            return stop, "stop"
        if target is not None and c.high >= target:
            return target, "target"
    else:
        if c.high >= stop:
            return stop, "stop"
        if target is not None and c.low <= target:
            return target, "target"
    return None


class Backtester:
    def __init__(self, strategy_factory: Callable[[], Strategy],
                 costs: Optional[CostModel] = None,
                 equity: float = 100_000.0, risk_per_trade_pct: float = 1.0):
        self.factory = strategy_factory
        self.costs = costs or CostModel()
        self.equity = equity
        self.risk_pct = risk_per_trade_pct

    def run(self, candles_by_symbol: dict[str, list[Candle]]) -> BacktestResult:
        result = BacktestResult(starting_equity=self.equity)
        for symbol, candles in candles_by_symbol.items():
            self._run_symbol(symbol, candles, result)
        return result

    def _run_symbol(self, symbol: str, candles: list[Candle], result: BacktestResult):
        strat = self.factory()
        n = len(candles)
        last_of_day = [
            i == n - 1 or candles[i + 1].ts.date() != candles[i].ts.date()
            for i in range(n)
        ]

        open_t: Optional[dict] = None
        for i, c in enumerate(candles):
            sig = strat.on_candle(symbol, c)   # always advance strategy state

            if open_t is not None:
                ex = _check_exit(open_t["side"], open_t["stop"], open_t["target"], c)
                if ex is None and last_of_day[i]:
                    ex = (c.close, "eod")        # square off intraday at day's end
                if ex is not None:
                    self._close(symbol, open_t, c.ts, ex[0], ex[1], result)
                    open_t = None

            if open_t is None and sig is not None:
                qty = position_size(self.equity, self.risk_pct, sig.entry, sig.stop)
                if qty > 0:
                    open_t = dict(side=sig.side, entry=sig.entry, stop=sig.stop,
                                  target=sig.target, qty=qty, entry_ts=c.ts)

        if open_t is not None:                   # close anything still open at the end
            last = candles[-1]
            self._close(symbol, open_t, last.ts, last.close, "eod", result)

    def _close(self, symbol, t, exit_ts, exit_price, reason, result):
        sign = t["side"].sign
        gross = (exit_price - t["entry"]) * t["qty"] * sign
        if sign > 0:
            cost = self.costs.round_trip(t["entry"], exit_price, t["qty"])
        else:  # short: sold at entry, bought back at exit
            cost = self.costs.round_trip(exit_price, t["entry"], t["qty"])
        result.trades.append(Trade(symbol, t["side"], t["entry_ts"], t["entry"],
                                   exit_ts, exit_price, t["qty"], gross, cost, reason))
