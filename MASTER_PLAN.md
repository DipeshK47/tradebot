# Master Plan — Indian-Market Stock Tracker, Alerting & Automated Trading Bot

*Owner build. Consolidated 2026-06-23 from three fact-checked research workflows (see `docs/research/`). Where a fact was flagged UNCERTAIN/REFUTED in research, it is marked ⚠️ and must be re-verified at build time.*

---

## 0. Honest scope (read first)

We are building a genuinely capable, disciplined systematic trading system for NSE/BSE — **not** a guaranteed money printer, and not a literal "copy the world's best traders in real time" machine (that data does not exist publicly; see §9). The edge comes from **good strategies × strict risk management × disciplined execution**, validated by **backtest → paper → live (small)**. SEBI's own data: ~93% of F&O traders and ~71% of intraday equity traders lose money. The seatbelts get built before the engine.

**End goal:** fully automated entry → manage → exit, reached *last*, only after paper trading proves an edge after costs.

---

## 1. Architecture — the two-brain design

```
            ┌──────────────────────── SLOW BRAIN (LLM) ────────────────────────┐
            │  cadence: per-minute / per-event   (NEVER in the tick hot path)   │
            │  • news + filings interpretation, sentiment (FinBERT + LLM)       │
            │  • market-regime label (risk-on/off, volatility)                  │
            │  • rank/prune the candidate set the FAST engine produced          │
            │  • write plain-English trade narration for dashboard + Telegram   │
            │  emits → strict JSON {signal, confidence, horizon, regime, why}   │
            └───────────────────────────────┬──────────────────────────────────┘
                                            │ writes timestamped advisory signals
                                            ▼
                            ┌──────────── SIGNAL STORE (cache) ────────────┐
                            │  fast loop READS latest; staleness-decayed    │
                            └───────────────────────────────┬──────────────┘
                                                            │ non-blocking read
   Dhan WebSocket (ticks) ─────────────────────────────────▼──────────────────┐
                            │             FAST ENGINE (deterministic)           │
                            │  • per-symbol candles + incremental indicators    │
                            │  • strategy rules (price/indicator triggers)      │
                            │  • HARD RISK ENGINE — fail-closed, absolute veto   │
                            │    (max size / max daily loss / max exposure)     │
                            │  • ORDER GATEWAY — the ONLY thing that can trade   │
                            └───────────────────────────────┬──────────────────┘
                                                            ▼
                                                      Dhan Order API
                                                  (Super Order = broker-side
                                                   bracket + trailing stop)
```

**Iron rules:**
- The LLM **advises**; it can up/down-weight candidates and pick a *pre-approved* parameter set, but it **never** places/modifies/cancels an order and **can never loosen a risk limit**.
- The **deterministic risk engine is fail-closed**: if a condition isn't explicitly satisfied, it does **not** trade.
- **Every live position carries a broker-side protective stop** (Dhan SL/Super Order on the exchange) so a host crash, network drop, or WS disconnect can never leave a position unguarded.

---

## 2. Tech stack

| Concern | Pick | Notes |
|---|---|---|
| Language/runtime | **Python 3.12+, asyncio** | single app, three internal modules (Tracker / Alerter / Trader) |
| Process split | **live Trader = its own process** | dashboard crash can't touch open positions; dashboard never holds order creds |
| Broker | **Dhan** (`dhanhq` SDK) | Upstox kept as documented fallback behind an `IBroker` interface |
| Live data | Dhan WebSocket (binary) | 5 conns × 5,000 instruments = 25,000 cap |
| Indicators (live) | **talipp** (incremental, O(1)/tick) + **Polars** (bar-close cross-section) | TA-Lib/pandas-ta for batch/backtests only |
| DB | **Postgres 16 + TimescaleDB** | hypertables for candles; immutable `trades`/`orders` audit table |
| Backtesting | **vectorbt** (sweeps) + **backtesting.py** (execution-realism cross-check) | model Indian costs per-segment |
| Dashboard | **FastAPI (REST+WS) + React + lightweight-charts** | the "command center" (§8) |
| Alerts/control | **Telegram bot** (primary) + web dashboard; email/WhatsApp later | |
| Scheduler | asyncio + APScheduler | daily token refresh, EOD jobs |
| Supervision | **systemd** `Restart=on-failure` + `WatchdogSec` heartbeat | |
| Secrets | `.env` (chmod 600) / systemd `LoadCredential` | never hardcode tokens |

---

## 3. Broker = Dhan (decided)

Why Dhan first: **native Super Orders** (entry + target + stop + trailing, enforced **broker-side**) survive a process restart — exactly the safety net a remote/always-on bot needs; and the **order token can be auto-refreshed** (Upstox's token dies at 3:30 AM with no refresh token, forcing a daily manual login — a dealbreaker). Trading API is free; data API ₹500/mo (free once ≥25 trades/30 days).

Key limits baked into design: historical = **90 days/request, 5-yr intraday** (chunk + cache backfill); order rate **10/s, 250/min, 7,000/day**; subscriptions keyed by numeric **Security ID** (load the scrip-master CSV).

---

## 4. Compliance (SEBI retail algo framework — live since 1 Apr 2026 ⚠️ re-verify)

A **personal, self-built bot is explicitly allowed** — no registration as long as we stay under the threshold. What we MUST do:
- Trade **only your own + immediate-family accounts** (self/spouse/dependent children/parents). Never anyone else's.
- Use **Dhan's official API only**, from a **static whitelisted IP** (§7), with **OAuth + 2FA** and **daily token re-auth before pre-open**.
- **Tag every order** with the algo ID (the SDK/onboarding handles issuance) and keep an **immutable 5-yr audit log** — required for *all* API orders, even below the threshold.
- **Rate-limit hard, well under 10 orders per *second*** (this is per-second, not per-day — daily count is irrelevant; we can place thousands/day freely). Staying <10 OPS avoids mandatory exchange algo-registration. ⚠️ 10 OPS is an NSE/ISF value — treat as a config constant and re-check.
- **Never sell signals or auto-trade others' accounts** (= unregistered advice / unauthorized PMS — SEBI is actively prosecuting this). **Never ingest or act on UPSI / leaked info** — public, post-publication data only.

---

## 5. The universe & scanning

Don't scan all ~2,200 listed names (illiquid = junk signals). Scan the **liquid tradable set**:
- **Start: ~200–250 F&O stocks** (tightest spreads) or **Nifty 500** (~84% of traded value).
- Expand toward ~1,800 turnover-filtered names only if compute holds.

The liquid universe fits in **one** WebSocket connection, so Dhan is *not* the bottleneck — **laptop/VPS CPU (Python GIL) is**. Solution: **incremental indicators** (talipp, O(1)/tick) + **bar-close** vectorized passes (Polars), ring-buffer per symbol, buffer-warm from the historical API at startup. ⚠️ The exact symbol ceiling on a given machine is unverified — **benchmark before committing**.

---

## 6. Strategy library (initial) + risk management

Implement a small, well-understood set; backtest to pick what survives Indian costs:
- **Opening Range Breakout (ORB)** — first 15–60 min range, breakout + volume + VWAP confirm; stop at opposite extreme; ≥1.5–2R target.
- **VWAP pullback** (liquid names only), **Supertrend** trend filter (10/3), **Bollinger** (regime-aware: mean-revert in range, breakout after squeeze), **RSI-2** mean-reversion, **52-wk-high momentum** (long sleeve). MACD/MA-cross = confirmation filters only.

**Hard risk rules (immutable, enforced at the gateway):**
- Position size = **0.5–2% equity risk per trade**; size = (equity × risk%) ÷ (entry − stop).
- **ATR-based stops** (1.5–2.5× ATR) ⚠️ use ATR because it adapts, not for any quoted performance number (those were refuted marketing).
- R:R ≥ 1.5–2:1; **daily-loss kill-switch**, halt after N consecutive losses, portfolio-drawdown circuit breaker.
- Kelly only at **¼–½ Kelly** if used at all.

---

## 7. Hosting = Oracle Cloud **Always Free** VPS (your question, answered)

This solves static-IP + always-on **for ₹0**:
- **Oracle Cloud "Always Free"** gives a VM with a **reserved (static) public IPv4** — provision it in **Mumbai (ap-mumbai-1)** or Hyderabad. The bot + dashboard run here 24/7; your laptop is just a browser client. The static public IP is what we whitelist with Dhan. ✅
- Free-tier shapes: **ARM Ampere A1 up to 4 cores / 24 GB RAM** (plenty) or small AMD micro VMs.
- **Two real caveats** (so you're not surprised):
  1. **ARM capacity** is often "out of host capacity" in popular regions — may take a few retries / a script to grab one.
  2. **Idle reclaim** — Oracle can reclaim *idle* Always-Free compute. A bot that's quiet outside market hours can look idle; mitigate with a lightweight keepalive, or upgrade to a "pay-as-you-go" account (which exempts Always-Free resources from reclaim) while still paying ₹0 for them.
- **Fallback (you said ignore cost):** a dedicated **₹400–600/month VPS** (DigitalOcean/Linode/Hetzner Mumbai/Indian provider) removes both caveats and is rock-solid for something managing real trades. **Recommendation: try Oracle free first; if it's flaky, move to a paid micro-VPS — the code is identical either way.**

---

## 8. Dashboard — the "command center" (your workstation)

A first-class **web dashboard served from the VPS**, opened from your laptop/phone, showing **everything** and controlling everything:
- **Live**: candlestick charts (lightweight-charts) + indicators, the scanner's hits, market-regime label.
- **Positions/P&L**: open trades, broker-side stops, realized/unrealized P&L, exposure vs limits.
- **Bot brain**: each decision with the LLM's plain-English rationale + the news/flow context behind it.
- **News & smart-money**: live free-news feed, sentiment, the disclosed-flow watchlist (§9).
- **Controls**: **arm/disarm live (defaults OFF on every restart)**, global **kill-switch / flatten-all**, manual exit per position, per-strategy enable, risk-limit display.
- **Logs/audit**: structured event stream.
- **Telegram** mirrors the critical bits to your phone with secure two-way control (§10).

Phased: a lean read-only version first (Phase 1), the full rich command-center as we go.

---

## 9. "Copying top traders" — the realistic design

**Real-time mirroring is impossible** — the NSE/BSE order book is anonymous; the public feed is price + volume only, never a name. All "who traded what" is **post-trade and lagged**. So we use **disclosed flows as a conviction overlay on a longer-horizon sleeve — never a blind mirror, never an intraday trigger.**

| Source | Reveals | Lag |
|---|---|---|
| **Bulk / block deals** | named client, qty, price | same day, after close |
| **Insider / promoter (PIT/SAST)** | named insider buys/sells | T+2–T+4 |
| **FII/DII + participant OI** | category aggregate (context only) | EOD / ~19:00 |
| **Superstar holdings (≥1%)** | named big-investor stakes | up to ~a quarter stale |

**Use:** build a daily **smart-money watchlist** (superstar *accumulation across quarters*, credible bulk/block *buys*, *promoter buying*) that **upgrades conviction/size** on names **our own technical engine independently flags**, and can **veto shorts** on names being accumulated. It **never originates a trade**. Pitfalls designed around: horizon mismatch (they hold years), unobservable exits (hidden below 1%), late-signal slippage (no-chase cooldown), survivorship bias (⚠️ never trust winner-list-only backtests). Data via cookie-gated NSE/BSE endpoints + aggregators (Trendlyne/Screener/Tijori) — **brittle scrapers, budget for breakage.**

---

## 10. News, alerts & secure control

- **News (free-first, confirmed):** Zerodha Pulse + ET/Moneycontrol/Mint RSS + GDELT (macro tone) + NSE/BSE filing scrapers → de-dup → ticker-link → FinBERT/LLM sentiment (anonymize tickers before scoring). **Honest calibration:** you are structurally *late* on news; treat it as a **weak, decaying, cost-sensitive feature**, not an edge. No paid feeds until an edge is proven. X/Telegram tips = manipulation, never truth.
- **Telegram two-way control security** (so only you can move money): allow-list your numeric user-id → verify webhook secret → **confirm tap with single-use signed token** → **PIN/TOTP step-up for exit/flatten** → idempotency (no double-fire). The platform authenticates the channel; *we* authenticate owner + intent.

---

## 11. Data & backtesting

- **Historical:** Dhan API (5-yr intraday) backfilled into TimescaleDB, chunked by 90-day limit + cached; free EOD bhavcopy supplement. `yfinance` = prototyping only.
- **Backtester:** **vectorbt** for parameter sweeps + **backtesting.py** for execution realism. Model **Indian costs per segment** (STT, exchange txn, SEBI, 18% GST, stamp duty, brokerage, slippage — delivery ≈ 2× intraday ⚠️ compute from component rates, not a single blended number). Validate **out-of-sample (70/30) + walk-forward**; ~most good-looking backtests fail live from overfitting.
- **Paper trading:** our own `PaperBroker` simulating fills against the **live feed** (broker sandboxes are integration tools, not realistic fill sims).

---

## 12. Phased roadmap

- **Phase 0 — Foundations:** Oracle VPS + reserved IP whitelisted with Dhan; Postgres+TimescaleDB; `dhanhq`; automated daily token-refresh (~08:30 IST) with Telegram fail-alert. *Done when:* a `/profile` call succeeds from the static IP every morning.
- **Phase 1 — Tracker + Alerts + Dashboard:** one shared WS feed → candles → indicators; rules engine ("price crosses upper Bollinger band") → Telegram; web command-center (read-only first). *Done when:* live dashboard for the liquid universe + a clean phone alert with no spam.
- **Phase 2 — Backtesting:** backfill history; `on_candle(ctx)->signals` interface so identical code runs in backtest/paper/live; vectorbt sweeps with real costs; OOS + walk-forward. *Done when:* ORB + Supertrend validated OOS with realistic costs.
- **Phase 3 — Paper-trading bot:** `IBroker` + `PaperBroker`; MODE banner; startup position reconciliation; dead-man's-switch; full guardrails. *Done when:* the exact strategy paper-trades 2+ weeks, P&L tracks backtest, auto-recovers from crashes.
- **Phase 4 — Live, small size:** `LiveBroker` via Super Orders; hard rate-limiter; all interlocks; "arm live" defaults OFF; algo tag + immutable audit. Start at **minimum size, one strategy, 1–2 symbols**, 4 weeks, then scale.
- **Continuous (parallel from Phase 1+):** news/sentiment slow-brain; disclosed-flow conviction overlay.

---

## 13. Open decisions (need your input)

1. **Trading capital** (₹ amount you'll actually trade with) — required to set position-size and risk-limit numbers. (Infra cost is separate and ~free.)
2. **Dhan account + API access** — do you already have a Dhan account with API enabled (need client id + API key)? If not, that's step 1 of Phase 0.
3. **Universe to start** — F&O (~200) [recommended] vs Nifty 500.
4. **First strategy to build+backtest** — ORB [recommended first] vs Supertrend vs Bollinger.
5. **Host** — Oracle free-tier [try first] vs paid micro-VPS [rock-solid].

## 14. ⚠️ Re-verify at build time
SEBI framework go-live status (post-Apr-2026 circular); the 10-OPS threshold value; Dhan WS instrument cap (docs inconsistent: 25,000 vs "unlimited"); block-deal params (₹25cr, new windows, live ~Dec 2025); single-machine symbol ceiling (benchmark); news-edge existence (treat as unproven).
