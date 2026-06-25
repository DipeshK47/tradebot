"""Performance statistics + a text tearsheet for a BacktestResult."""
from __future__ import annotations

from dataclasses import dataclass

from .engine import BacktestResult


@dataclass
class Stats:
    n_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_pnl: float
    total_costs: float
    net_pnl: float
    return_pct: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy: float
    max_drawdown: float


def compute_stats(result: BacktestResult) -> Stats:
    trades = result.trades
    n = len(trades)
    nets = [t.net_pnl for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]

    eq = result.starting_equity
    cum, peak, mdd = eq, eq, 0.0
    for x in nets:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)

    gross_win = sum(wins)
    gross_loss = -sum(losses)
    if gross_loss > 0:
        pf = gross_win / gross_loss
    else:
        pf = float("inf") if gross_win > 0 else 0.0

    net = sum(nets)
    return Stats(
        n_trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=(len(wins) / n) if n else 0.0,
        gross_pnl=sum(t.gross_pnl for t in trades),
        total_costs=sum(t.costs for t in trades),
        net_pnl=net,
        return_pct=(net / eq * 100.0) if eq else 0.0,
        avg_win=(sum(wins) / len(wins)) if wins else 0.0,
        avg_loss=(sum(losses) / len(losses)) if losses else 0.0,
        profit_factor=pf,
        expectancy=(net / n) if n else 0.0,
        max_drawdown=mdd,
    )


def format_report(s: Stats) -> str:
    cost_pct = (s.total_costs / s.gross_pnl * 100.0) if s.gross_pnl > 0 else 0.0
    pf = "inf" if s.profit_factor == float("inf") else f"{s.profit_factor:.2f}"
    return "\n".join([
        "── Backtest summary ──",
        f"trades        : {s.n_trades}",
        f"win rate      : {s.win_rate * 100:5.1f}%  ({s.wins}W / {s.losses}L)",
        f"profit factor : {pf}",
        f"expectancy    : ₹{s.expectancy:,.1f} / trade",
        f"avg win/loss  : ₹{s.avg_win:,.0f} / ₹{s.avg_loss:,.0f}",
        f"gross P&L     : ₹{s.gross_pnl:,.0f}",
        f"costs         : ₹{s.total_costs:,.0f}  ({cost_pct:.0f}% of gross)",
        f"net P&L       : ₹{s.net_pnl:,.0f}  ({s.return_pct:+.2f}%)",
        f"max drawdown  : ₹{s.max_drawdown:,.0f}",
    ])
