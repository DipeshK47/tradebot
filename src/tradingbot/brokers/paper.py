"""Simulated broker: fills against the latest known price, tracks positions/P&L.

Used for paper trading and backtests. Same interface as the live Dhan broker, so
strategy code is identical across modes. Cost model is intentionally simple here
(a flat bps fee); the Phase-2 backtester models Indian costs per segment.
"""
from __future__ import annotations

import itertools
from datetime import datetime

from .base import IBroker
from .models import Fill, Order, OrderStatus, OrderType, Position


class PaperBroker(IBroker):
    mode = "paper"

    def __init__(self, starting_cash: float = 0.0, fee_bps: float = 0.0):
        self.cash = starting_cash
        self.fee_bps = fee_bps
        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._fills: list[Fill] = []
        self._last: dict[str, float] = {}
        self._ids = itertools.count(1)

    # --- market-data plumbing (driven by the feed in paper mode) ---
    def set_price(self, symbol: str, price: float) -> None:
        self._last[symbol] = price

    def ltp(self, symbol: str) -> float:
        return self._last.get(symbol, 0.0)

    def connect(self) -> None:
        return None

    # --- order handling ---
    def place_order(self, order: Order) -> Order:
        order.id = f"paper-{next(self._ids)}"
        order.created_at = order.created_at or datetime.now()
        if order.order_type == OrderType.LIMIT and order.price:
            ref = order.price
        else:
            ref = self.ltp(order.symbol)
        if ref <= 0:
            order.status = OrderStatus.REJECTED
            self._orders.append(order)
            return order
        fee = abs(order.qty) * ref * (self.fee_bps / 10_000.0)
        self._apply_fill(order, ref, fee)
        order.status = OrderStatus.FILLED
        order.filled_qty = order.qty
        order.avg_fill_price = ref
        self._orders.append(order)
        self._fills.append(Fill(order.id, order.symbol, order.side,
                                order.qty, ref, order.created_at, fee))
        return order

    def _apply_fill(self, order: Order, price: float, fee: float) -> None:
        pos = self._positions.get(order.symbol) or Position(order.symbol)
        signed = order.side.sign * order.qty
        new_qty = pos.qty + signed
        if pos.qty == 0 or (pos.qty > 0) == (signed > 0):
            # opening or adding in the same direction -> weighted-average price
            total = pos.avg_price * abs(pos.qty) + price * abs(signed)
            pos.avg_price = total / abs(new_qty) if new_qty != 0 else 0.0
        else:
            # reducing / closing -> realize P&L on the closed quantity
            closed = min(abs(signed), abs(pos.qty))
            direction = 1 if pos.qty > 0 else -1
            pos.realized_pnl += (price - pos.avg_price) * closed * direction
            if new_qty == 0:
                pos.avg_price = 0.0
            elif (new_qty > 0) != (pos.qty > 0):
                pos.avg_price = price  # flipped through zero
        pos.qty = new_qty
        pos.realized_pnl -= fee
        self.cash -= fee
        self._positions[order.symbol] = pos

    def modify_order(self, order_id: str, **changes) -> Order:
        for o in self._orders:
            if o.id == order_id:
                for k, v in changes.items():
                    setattr(o, k, v)
                return o
        raise KeyError(order_id)

    def cancel_order(self, order_id: str) -> None:
        for o in self._orders:
            if o.id == order_id and o.status in (OrderStatus.PENDING, OrderStatus.OPEN):
                o.status = OrderStatus.CANCELLED

    def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.is_flat]

    def get_orders(self) -> list[Order]:
        return list(self._orders)
