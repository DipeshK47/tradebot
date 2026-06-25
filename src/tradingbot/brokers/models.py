"""Core domain models shared across brokers, strategies, and the risk engine.

Pure-stdlib so the safety-critical core runs and is testable without any
third-party dependencies or live broker credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"        # stop-loss limit
    SL_M = "SL_M"    # stop-loss market


class Product(str, Enum):
    INTRADAY = "INTRADAY"   # MIS
    DELIVERY = "DELIVERY"   # CNC
    MARGIN = "MARGIN"
    MTF = "MTF"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    """An order request/record. Protective legs (stop_loss/target/trailing_jump)
    map to Dhan Super Orders when live, so the stop is enforced broker-side and
    survives a process crash."""
    symbol: str
    side: Side
    qty: int
    order_type: OrderType = OrderType.MARKET
    product: Product = Product.INTRADAY
    price: Optional[float] = None            # limit price
    trigger_price: Optional[float] = None    # for SL / SL_M
    stop_loss: Optional[float] = None        # protective stop (broker-side when live)
    target: Optional[float] = None
    trailing_jump: Optional[float] = None
    tag: Optional[str] = None                # algo tag (SEBI audit requirement)
    id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: Optional[float] = None
    created_at: Optional[datetime] = None

    @property
    def notional(self) -> float:
        px = self.price or self.avg_fill_price or self.trigger_price or 0.0
        return abs(self.qty) * px


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    ts: datetime
    fees: float = 0.0


@dataclass
class Position:
    symbol: str
    qty: int = 0                 # signed: + long, - short
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self.qty == 0

    def market_value(self, last_price: float) -> float:
        return abs(self.qty) * last_price

    def unrealized_pnl(self, last_price: float) -> float:
        return self.qty * (last_price - self.avg_price)
