"""Bollinger breakout-confirmation scanner (the hand-drawn 15-min strategy).

Two-candle rule, BB(length=20, multiplier=1.5), default 15-min:
  1. SIGNAL candle: the FIRST candle that is COMPLETELY outside a band — its whole
     range clears the band (low > upper, or high < lower) — after being inside; a
     *fresh* breakout. A close beyond the band but with the candle still straddling
     it does NOT qualify. While the candle keeps clearing the same band (a band-walk),
     no new signal is raised; it re-arms only once a candle is back inside the band
     (or a new day starts). The band is computed INCLUDING this candle's close, to
     match the chart.
  2. CONFIRMATION = the very NEXT candle, compared by close to the signal candle:
       next close > signal close  -> BUY
       next close < signal close  -> SELL
       next close == signal close -> no signal
  Same logic at both bands — the band only qualifies the signal candle; the next
  candle's close direction picks the side.

Signal state resets each trading day (the BB rolling window stays continuous).
Emits alerts (direction "up" = BUY, "down" = SELL). Entry/exit/stop come later.
"""
from __future__ import annotations

from typing import Optional

from ..indicators import Bollinger
from ..strategies.base import Candle
from .base import Alert, Scanner


class BollingerBreakoutScanner(Scanner):
    name = "bollinger_breakout"

    def __init__(self, timeframe: str = "15min", period: int = 20, num_std: float = 1.5):
        self.timeframe = timeframe
        self.period = period
        self.num_std = num_std
        self._bb: dict[str, Bollinger] = {}
        self._pending: dict[str, dict] = {}     # symbol -> {"close", "band"}
        self._prev_zone: dict[str, str] = {}     # symbol -> "upper"|"lower"|"inside"
        self._day: dict[str, object] = {}

    def on_candle(self, symbol: str, c: Candle) -> Optional[Alert]:
        # Reset SIGNAL state each new day (BB window itself stays continuous).
        d = c.ts.date()
        if self._day.get(symbol) != d:
            self._day[symbol] = d
            self._pending.pop(symbol, None)
            self._prev_zone[symbol] = "inside"

        bb = self._bb.setdefault(symbol, Bollinger(self.period, self.num_std))
        bands = bb.update(c.close)               # bands INCLUDE this close (chart convention)

        alert: Optional[Alert] = None

        # 1) Confirm a signal left pending by the PREVIOUS candle.
        pend = self._pending.pop(symbol, None)
        if pend is not None:
            sig_close, band = pend["close"], pend["band"]
            if c.close > sig_close:
                alert = Alert(symbol, self.name, "up",
                              f"BB breakout BUY — close {c.close:.2f} > signal close "
                              f"{sig_close:.2f} (fresh break beyond {band} band)",
                              c.close, c.ts,
                              {"band": band, "signal_close": sig_close,
                               "confirm_close": c.close, "action": "BUY"})
            elif c.close < sig_close:
                alert = Alert(symbol, self.name, "down",
                              f"BB breakout SELL — close {c.close:.2f} < signal close "
                              f"{sig_close:.2f} (fresh break beyond {band} band)",
                              c.close, c.ts,
                              {"band": band, "signal_close": sig_close,
                               "confirm_close": c.close, "action": "SELL"})
            # equal close -> no signal

        # 2) Fresh-breakout detection: the ENTIRE candle must clear the band (not just
        #    the close), entered from a DIFFERENT zone.
        zone = "inside"
        if bands is not None:
            lower, mid, upper = bands
            if c.low > upper:            # whole candle above the upper band
                zone = "upper"
            elif c.high < lower:         # whole candle below the lower band
                zone = "lower"
        prev = self._prev_zone.get(symbol, "inside")
        if zone in ("upper", "lower") and zone != prev:
            self._pending[symbol] = {"close": c.close, "band": zone}   # arm; confirm next bar
        self._prev_zone[symbol] = zone

        return alert
