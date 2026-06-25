"""Run the scanners over REAL Upstox historical candles.

Historical data is public (no valid token required), so this works today even
though the live token is expired. Demonstrates all three scanners on actual NSE
data at the requested timeframes: 1h Bollinger-outside, 15m RSI cross>60,
15m previous-day high/low break.

    python3 scripts/scan_real.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("DOTENV_PATH", os.path.join(os.path.dirname(__file__), "..", ".env"))

from tradingbot.config import UpstoxConfig  # noqa: E402
from tradingbot.data.upstox import UpstoxData  # noqa: E402
from tradingbot.scanners.bollinger_breakout import BollingerBreakoutScanner  # noqa: E402
from tradingbot.scanners.bollinger_outside import BollingerOutsideScanner  # noqa: E402
from tradingbot.scanners.prev_day_break import PrevDayBreakScanner  # noqa: E402
from tradingbot.scanners.rsi_momentum import RsiMomentumScanner  # noqa: E402

# A few liquid NSE names (instrument_key = "NSE_EQ|<ISIN>").
INSTRUMENTS = {
    "RELIANCE": "NSE_EQ|INE002A01018",
    "TCS": "NSE_EQ|INE467B01029",
    "INFY": "NSE_EQ|INE009A01021",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "ICICIBANK": "NSE_EQ|INE090A01021",
    "SBIN": "NSE_EQ|INE062A01020",
}


def main():
    cfg = UpstoxConfig.from_env()
    ud = UpstoxData(cfg.access_token)        # token optional — historical is public
    bb_alerts, rsi_alerts, pdb_alerts, bbk_alerts = [], [], [], []

    for sym, ik in INSTRUMENTS.items():
        try:
            h1 = ud.candles(ik, "1hour", "2026-03-25", "2026-06-20")
            m15 = ud.candles(ik, "15min", "2026-06-09", "2026-06-20")
        except Exception as e:
            print(f"  {sym:10} fetch error -> {e}")
            continue
        print(f"  {sym:10} {len(h1):>4} 1h candles | {len(m15):>4} 15m candles")

        bb = BollingerOutsideScanner(timeframe="1hour")
        for c in h1:
            a = bb.feed(sym, c)
            if a:
                bb_alerts.append(a)

        rsi = RsiMomentumScanner(timeframe="15min")
        pdb = PrevDayBreakScanner(timeframe="15min")
        bbk = BollingerBreakoutScanner(timeframe="15min", period=20, num_std=1.5)
        for c in m15:
            a = rsi.feed(sym, c)
            if a:
                rsi_alerts.append(a)
            a = pdb.feed(sym, c)
            if a:
                pdb_alerts.append(a)
            a = bbk.feed(sym, c)
            if a:
                bbk_alerts.append(a)

    def show(title, alerts):
        print(f"\n{title}: {len(alerts)} alerts")
        for a in alerts[:6]:
            print(f"    {a.ts}  {a.symbol:9} {a.direction:4} | {a.message}")

    show("Bollinger full-candle-outside (1h)", bb_alerts)
    show("Bollinger breakout-confirmation [YOUR strategy] (15m)", bbk_alerts)
    show("RSI momentum 50 -> 60 [strategy 2] (15m)", rsi_alerts)
    show("Previous-day H/L break (15m)", pdb_alerts)


if __name__ == "__main__":
    main()
