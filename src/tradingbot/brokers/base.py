"""Broker abstraction.

LiveBroker (Dhan) and PaperBroker implement this single interface, so identical
strategy/execution code runs in paper and live with only a config flip.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Order, OrderType, Position, Side


class IBroker(ABC):
    """Minimal order/position surface the engine depends on.

    Implementations MUST guarantee that protective stops are honored even if this
    process dies (live: broker-side Super Order; paper: simulated stop).
    """

    mode: str = "abstract"  # "paper" | "live"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Submit an order; return it updated with id/status/fill."""

    @abstractmethod
    def modify_order(self, order_id: str, **changes) -> Order: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_orders(self) -> list[Order]: ...

    @abstractmethod
    def ltp(self, symbol: str) -> float:
        """Last traded price for a symbol."""

    def flatten_all(self) -> None:
        """Kill-switch helper: square off every open position at market."""
        for pos in self.get_positions():
            if pos.is_flat:
                continue
            side = Side.SELL if pos.qty > 0 else Side.BUY
            self.place_order(Order(symbol=pos.symbol, side=side,
                                   qty=abs(pos.qty), order_type=OrderType.MARKET,
                                   tag="kill_switch"))
