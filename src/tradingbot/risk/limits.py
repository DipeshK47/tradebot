"""Deterministic, fail-closed risk engine and position sizing.

This is the safety core. The LLM 'brain' can NEVER modify these limits, and the
engine denies anything it cannot positively verify. Every order must pass through
check_order() before it can reach a broker.

Fail-closed philosophy: a limit left at 0 / unset means 'not configured', which
DENIES the trade. Limits must be explicitly set to positive values to trade.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..brokers.models import Order


@dataclass
class RiskLimits:
    # Per-trade sizing
    max_risk_per_trade_pct: float = 1.0       # % of equity risked per trade
    # Hard caps (rupees), all must be > 0 to permit trading (fail-closed)
    max_position_value: float = 0.0
    max_total_exposure_value: float = 0.0
    max_daily_loss: float = 0.0               # positive number; breach halts trading
    max_open_positions: int = 0
    max_orders_per_day: int = 0
    # Instruments allowed to trade (empty => nothing allowed, fail-closed)
    instrument_whitelist: frozenset[str] = field(default_factory=frozenset)
    # Live-trading interlock: must be explicitly armed each session; defaults OFF.
    arm_live: bool = False


@dataclass
class PortfolioState:
    equity: float
    open_exposure_value: float = 0.0
    open_positions: int = 0
    orders_today: int = 0
    realized_pnl_today: float = 0.0
    has_position_in_symbol: bool = False


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = "ok"


def position_size(equity: float, risk_per_trade_pct: float,
                  entry_price: float, stop_price: float, lot_size: int = 1) -> int:
    """Fixed-fractional sizing: qty so that an entry->stop move loses ~equity*risk%.

    Fail-closed: returns 0 on any degenerate input (no stop distance, non-positive
    equity/price), because 'no valid stop' must mean 'no trade'.
    """
    if equity <= 0 or entry_price <= 0 or lot_size <= 0:
        return 0
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return 0
    rupees_at_risk = equity * (risk_per_trade_pct / 100.0)
    qty = int((rupees_at_risk / risk_per_unit) // lot_size) * lot_size
    return max(qty, 0)


class RiskEngine:
    """Fail-closed pre-trade gate. Every order passes through check_order()."""

    def __init__(self, limits: RiskLimits, mode: str = "paper"):
        self.limits = limits
        self.mode = mode
        self.kill_switch = False
        self._kill_reason = ""

    def engage_kill_switch(self, reason: str = "manual") -> None:
        self.kill_switch = True
        self._kill_reason = reason

    def check_order(self, order: Order, reference_price: float,
                    portfolio: PortfolioState) -> RiskDecision:
        try:
            L = self.limits

            if self.kill_switch:
                return RiskDecision(False, f"kill_switch_engaged:{self._kill_reason}")

            # Live trading must be explicitly armed (defaults OFF every restart).
            if self.mode == "live" and not L.arm_live:
                return RiskDecision(False, "live_not_armed")

            # Whitelist (empty whitelist => nothing tradable).
            if order.symbol not in L.instrument_whitelist:
                return RiskDecision(False, f"symbol_not_whitelisted:{order.symbol}")

            if order.qty <= 0:
                return RiskDecision(False, "non_positive_qty")
            if reference_price <= 0:
                return RiskDecision(False, "no_reference_price")

            order_value = order.qty * reference_price

            if L.max_position_value <= 0 or order_value > L.max_position_value:
                return RiskDecision(False, "exceeds_max_position_value")

            if (L.max_total_exposure_value <= 0 or
                    portfolio.open_exposure_value + order_value > L.max_total_exposure_value):
                return RiskDecision(False, "exceeds_max_total_exposure")

            # New-position count cap (only when opening a brand-new symbol).
            opens_new = not portfolio.has_position_in_symbol
            if opens_new and (L.max_open_positions <= 0 or
                              portfolio.open_positions >= L.max_open_positions):
                return RiskDecision(False, "exceeds_max_open_positions")

            if L.max_orders_per_day <= 0 or portfolio.orders_today >= L.max_orders_per_day:
                return RiskDecision(False, "exceeds_max_orders_per_day")

            # Daily-loss circuit breaker.
            if L.max_daily_loss <= 0 or portfolio.realized_pnl_today <= -abs(L.max_daily_loss):
                return RiskDecision(False, "daily_loss_limit_hit")

            return RiskDecision(True, "ok")
        except Exception as e:  # fail-closed on ANY unexpected error
            return RiskDecision(False, f"risk_engine_error:{type(e).__name__}")
