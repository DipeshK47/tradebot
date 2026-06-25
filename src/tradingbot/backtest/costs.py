"""Indian equity trading-cost model.

Models the real components — brokerage, STT, exchange txn, SEBI fee, stamp duty,
GST and slippage — instead of one blended %, because intraday costs are roughly
half of delivery and a single blended number misleads (see docs/research/01...).
Rates are 2026 defaults and MUST be re-verified before live use.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    segment: str = "intraday"            # "intraday" | "delivery"
    brokerage_cap: float = 20.0          # ₹ flat cap per order
    brokerage_pct: float = 0.0003        # 0.03%/order (intraday); 0 for many delivery plans
    exch_txn_pct: float = 0.0000297      # NSE equity
    sebi_pct: float = 0.000001           # ₹10 per crore
    gst_pct: float = 0.18                # on (brokerage + txn + sebi)
    slippage_pct: float = 0.0005         # 0.05% assumed per side
    stt_sell_pct: float = 0.00025        # intraday: 0.025% sell side
    stamp_buy_pct: float = 0.00003       # intraday: 0.003% buy side

    @classmethod
    def delivery(cls) -> "CostModel":
        # delivery: 0% brokerage at discount brokers, STT 0.1% on BOTH sides
        return cls(segment="delivery", brokerage_pct=0.0, brokerage_cap=0.0,
                   stt_sell_pct=0.001, stamp_buy_pct=0.00015)

    def _brokerage(self, turnover: float) -> float:
        if self.brokerage_pct <= 0:
            return 0.0
        return min(self.brokerage_cap, turnover * self.brokerage_pct)

    def round_trip(self, buy_price: float, sell_price: float, qty: int) -> float:
        """Total ₹ cost for a buy+sell round trip of `qty` shares."""
        buy_to = buy_price * qty
        sell_to = sell_price * qty
        brokerage = self._brokerage(buy_to) + self._brokerage(sell_to)
        if self.segment == "delivery":
            stt = (buy_to + sell_to) * self.stt_sell_pct      # both sides
        else:
            stt = sell_to * self.stt_sell_pct                 # intraday: sell side only
        exch = (buy_to + sell_to) * self.exch_txn_pct
        sebi = (buy_to + sell_to) * self.sebi_pct
        stamp = buy_to * self.stamp_buy_pct
        gst = (brokerage + exch + sebi) * self.gst_pct
        slippage = (buy_to + sell_to) * self.slippage_pct
        return brokerage + stt + exch + sebi + stamp + gst + slippage
