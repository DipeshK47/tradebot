<!-- Auto-extracted from research workflow output, 2026-06-23 -->

I have comprehensive research findings and adversarial verification results. No additional tooling is needed — this is a synthesis task. Let me produce the report directly.

# Build-Ready Recommendation: Indian-Market Stock Tracker + Alerting + Automated Trading Bot

*Prepared 2026-06-23. Where adversarial verification refuted or could not confirm a claim, it is flagged inline and re-listed in Section 7. Do not treat flagged numbers as load-bearing.*

---

## 1. Broker API Comparison — Dhan vs Upstox

| Dimension | **Dhan (DhanHQ v2)** | **Upstox (v2 + v3)** |
|---|---|---|
| **Auth** | JWT in `access-token` header. 24h token expiry (regenerate daily; SEBI-aligned, v2.4 Oct 2025). 3 methods: Web, API+TOTP, OAuth (API key valid ~12 months). Web tokens renewable via `RenewToken`. | OAuth2 auth-code grant, **no refresh token**. Token expires at a fixed **3:30 AM IST next day** regardless of generation time. Daily interactive login (2FA/TOTP) required. `extended_token` for read-only continuity. |
| **Live data (WS)** | `wss://api-feed.dhan.co` — **binary** packets (Ticker/Quote/OI/Full). 5 connections/user, 5000 instruments/connection, 100/subscription msg. Separate 20/200-level depth feed. | `wss://.../feed/market-data-feed` (v3) — **Protobuf** (need the `.proto`; subscribe must be binary). Modes: ltpc/option_greeks/full/full_d30. Standard: 2 connections, caps LTPC 5000 / Greeks 3000 / Full 2000 (combined 2000). Plus tier: 5 connections. |
| **Historical** | Daily from scrip **inception**; intraday 1/5/15/25/60-min, **last 5 years**, **max 90 days/request** (must loop+cache). No bulk multi-symbol endpoint. | v3: daily/weekly/monthly **from Jan 2000**; minutes (1–300) & hours **from Jan 2022**. Per-request caps: 1mo (≤15min), 1qtr (>15min/hours), 1 decade (days). More granular intervals. |
| **Order types** | MARKET/LIMIT/SL/SL-M; CNC/INTRADAY/MARGIN/MTF/CO/BO. **Super Order** (entry+target+SL+trailing). **Forever/GTT** (SINGLE/OCO). Slicing. | MARKET/LIMIT/SL/SL-M; products **I/D/MTF only**. **BO/CO NOT supported via API.** Multi-order (max 10). **GTT v3** (SINGLE/MULTIPLE, multi-leg = trailing SL replacement). |
| **Bracket/SL mgmt** | **Native broker-side bracket/cover + trailing via Super Orders** — survives your process restarting. Strong advantage. | No BO/CO. Must emulate SL+target via multi-leg/trailing GTT. |
| **Rate limits** | Order **10/sec, 250/min, 7,000/day**; Data **5/sec, 100k/day**; Quote 1/sec; Option Chain 1/3sec. *(Verification: CONFIRMED against current v2 docs. Older support-page figures of 25/sec are legacy/pre-v2.3.)* | Order 10/sec, 500/min, 2000/30min (50/sec if SEBI-registered algo); other APIs 50/sec, 500/min, 2000/30min. |
| **Sandbox** | `sandbox.dhan.co/v2/`; sign up at developer.dhanhq.co (no Dhan account). Orders fill at static price 100, capital resets daily to ₹10L. **No streaming/real-time quotes.** | `sandbox.upstox.com`; emulates live with identical validation, no market-hours limit. Order lifecycle only. Token valid 30 days, one app/user. |
| **Python SDK** | `dhanhq` (PyPI, MIT, v2.x). Covers orders, Super/Forever, depth, live feed WS, order-update WS, eDIS, TOTP/OAuth. | `upstox-python-sdk` (`upstox_client`). v2 base + v3 classes (`OrderApiV3`, `HistoryV3Api`). `MarketDataStreamerV3`, `PortfolioDataStreamer`. |
| **Cost** | **Trading API free.** Data API ₹499+tax/month, **free if ≥25 trades in last 30 days**. | **API free.** Brokerage: promo flat **₹10/order via API until 31 Mar 2026** (standard up to ₹20). |
| **Selling holdings** | DDPI optional (₹100 one-time); without it, CDSL eDIS flow required. | POA/DDPI equivalent flagged in token response (`poa`). |

### Recommendation: integrate **Dhan first**

1. **Native Super Orders (bracket/cover + trailing SL) run broker-side** — your stop/target survives a crash or redeploy. With Upstox you'd hand-roll this on top of multi-leg GTT, which is more code and more risk in the most safety-critical path.
2. **No daily interactive OAuth required for the order-capable token.** Dhan's TOTP/API token flow can be fully automated each morning. Upstox's hard 3:30 AM token death with no refresh token forces a daily human-in-the-loop login — the single worst operational constraint for an always-on bot.
3. **Trading API is free and the Data API is free once you cross 25 trades/30 days** — cheap to operate.
4. **5-year intraday history** out of the box is enough to start backtesting now.

Keep Upstox as the documented fallback (its longer daily history back to 2000 and ₹10/order promo are nice-to-haves), but build the broker abstraction so a second implementation drops in later. Note Dhan's 90-days-per-request historical limit and 5 req/s data cap mean **bulk backfill must be chunked, looped, and cached locally** — budget for this.

---

## 2. SEBI Retail Algo-Trading Compliance — what you must actually do

**Governing rule:** SEBI circular dated **4 Feb 2025**, "Safer participation of retail investors in Algorithmic trading," with NSE operational standards (NSE/INVG/67858, May 2025; FAQ Nov 2025).

**Effective dates:** Original 1 Aug 2025 → deferred to 1 Oct 2025 → glide path to **1 April 2026 (final, universal)**. As of today (2026-06-23) that deadline **has passed**, so the full framework is in force for all brokers. *(Verification: CONFIRMED — but note the confirmation rests on date arithmetic against a firmly-documented deadline plus dense secondary reporting; a SEBI primary source dated **after** 1 April 2026 confirming no further extension was not independently located. Treat as high-confidence, not absolute.)*

### What a tech-savvy individual building a personal bot via a broker API MUST do
- **Self-developed personal-use algos are explicitly permitted.** You do not need to be a registered entity.
- **Use the broker's approved API only.** You cannot connect directly to the exchange. Every API order is treated by NSE as an "algo order" requiring exchange-ID tagging — *regardless of speed*.
- **Static IP whitelisting** with the broker. Required for order-affecting calls (read-only endpoints are exempt). IP changeable at most once per calendar week.
- **OAuth-only auth + 2FA.** Other auth mechanisms are discontinued.
- **Daily session reset** — re-authenticate the broker token before pre-open each trading day.
- **Algo-ID tagging** — orders carry the exchange-issued ID. Sub-threshold direct-API retail orders use a generic tag (NSE: first 12 digits `444444444444`). The broker SDK/onboarding handles issuance; your code passes the tag.

### What is NOT required (below the threshold)
- **No exchange registration of your algo** if you stay **at or below the Threshold Order-Per-Second (TOPS = 10 OPS per exchange/segment)**. A personal bracket/SL bot trading a handful of symbols is far below this.
- **Not required to join the monthly mandatory mock sessions** (P/L is yours, RMS is the broker's).

### What flips the obligation
- **>10 OPS** → you **must register the algorithm through your broker**, get a unique exchange algo-ID, and re-register on any logic change. **Design to stay under 10 OPS.**
- **Family-only restriction:** a registered self-developed algo may serve only self/spouse/dependent children/dependent parents. **You may not sell/offer it to third parties** without becoming an empanelled algo provider.

### Design implications (baked into the architecture)
1. **Fixed-IP host is mandatory**, whitelisted with Dhan. *(Caveat — see §7: the IP need NOT be in India/Mumbai; Mumbai is a latency nicety, not a regulatory requirement.)*
2. **Automate daily token re-auth before pre-open**, fail loudly via Telegram if it fails.
3. **Token-bucket rate limiter that hard-caps order submission well under 10 OPS** — both a rate-limit and a regulatory boundary.
4. **Pass the broker algo tag on every order; log it in an immutable audit table** (5-year audit-trail expectation).

---

## 3. Recommended Architecture & Tech Stack

**Primary recommendation: a single Python (3.12+, asyncio) monolith** with three internal modules — Tracker, Alerter, Trader — sharing one broker websocket feed and one database. Do **not** build microservices/Kafka/Kubernetes: all three consume the same tick stream, and brokers cap websocket connections (~5/user). One in-process asyncio pub/sub bus is enough.

**The one hard split to keep:** run the **live Trader as its own systemd unit / process**, separate from the dashboard, so a dashboard crash or redeploy can never affect open positions, and the dashboard never holds order-placing credentials.

```
Single fixed-IP VPS
 Broker WS ─► market_data (1 conn, decodes binary) ─► asyncio bus
                                  ├─► ALERTER  → Telegram/email
                                  ├─► TRADER   → Dhan REST (Super/GTT orders)   [own systemd unit]
                                  └─► FastAPI (REST+WS) → Dashboard
 Postgres + TimescaleDB (candles + immutable trades/orders audit)
```

| Concern | Primary pick | Alternative |
|---|---|---|
| Runtime | Python 3.12+, asyncio | — |
| Broker | **Dhan** (`dhanhq`) | Upstox (`upstox-python-sdk`) |
| Indicators | **TA-Lib** (C + bindings) | `mintalib` (Cython, fast); avoid relying on `pandas-ta` (slow/under-maintained) |
| Scheduler | asyncio + APScheduler (token refresh, EOD jobs) | — |
| DB | **Postgres 16 + TimescaleDB** (hypertables for candles) | SQLite for v0/paper-only |
| Dashboard | FastAPI (REST+WS) + Next.js/React + lightweight-charts | Streamlit/Dash for read-only tracker only (Streamlit reruns whole script per interaction; Dash single-threaded by default) |
| Alerts | **Telegram bot** primary; SMTP email secondary; web-push optional — all behind one `notify()` interface | — |
| Backtesting | **vectorbt** (sweeps) | backtesting.py (single-strategy realism cross-check) |
| Supervision | **systemd**, `Restart=on-failure`, `WatchdogSec` heartbeats | Docker Compose |
| Secrets | `.env` chmod 600 + `python-dotenv`, or systemd `LoadCredential` / SOPS+age | cloud KMS (overkill solo) |

**Strict paper-vs-live separation:** an `IBroker` interface with `LiveBroker` and `PaperBroker` (the paper one simulates fills against the live tick feed, writes to a `paper_*` schema). Separate credentials, separate DB schema, a globally-displayed `MODE` banner, and live-only interlocks: daily-loss kill-switch, max position size, max orders/day, and an **"arm live" toggle that defaults OFF on every restart**.

### Hosting & rough monthly cost (always-on around IST 09:15–15:30)
- **Single Mumbai-region VPS, 2–4 GB RAM: ~₹500–1,500/month** *(Verification: pricing CONFIRMED; but two stated justifications were flagged — see §7. "Mumbai is required for the static IP" is FALSE: any static IP from any region satisfies SEBI. "Mumbai gives low NSE/BSE latency" is real but marginal for a sub-10-OPS bot.)* Pick the VPS for a reliable **fixed public IP**; Mumbai is optional, not mandatory.
- Broker API: **₹0** (per-trade brokerage only). Telegram/email/Grafana-Cloud-free/Sentry-free: **₹0**. Domain+TLS: ~₹100–200.
- Managed cloud (AWS/GCP `ap-south-1`): ~₹1,500–3,000/month, turnkey snapshots + elastic IP. **Avoid serverless** for the trading loop — you need a persistent stateful websocket and changing serverless egress IPs break static-IP whitelisting.
- **Total: ~₹600–1,800/month (~$8–22)**, dominated by the VPS. Just leave it running; scheduled start/stop adds fragility for marginal savings.

**Operational must-haves:** websocket auto-reconnect with backoff + re-subscribe + **position reconciliation from the broker on startup** (never trust in-memory state after restart); dead-man's-switch on stale ticks; structured JSON logging; immutable `trades`/`orders` audit table as source of truth; Telegram ops channel for start/stop/reconnect/token-refresh/kill-switch events.

---

## 4. Strategy Library

**Implement first** (each has *some* published edge but all are regime-dependent — none guarantees profit):

| Strategy | Entry | Exit / Stop | Params | Honest read |
|---|---|---|---|---|
| **Opening Range Breakout (ORB)** | First 15–60 min range after 9:15 IST; long on close > range high (short < low), confirm with above-avg volume + VWAP/21-EMA alignment | Stop at opposite range extreme; target ≥1.5–2× risk; one trade/day | Range window 15/30/60min | Cost-aware 8yr Nifty backtest: 48.7% win, PF 1.23, +91.6% total. Edge is asymmetry, not accuracy — expect 8–10-trade losing streaks. |
| **VWAP pullback** | Uptrend: buy pullback to VWAP (stop just below); downtrend: sell rally to VWAP. Require confirming candle | Target ≥1.5× risk | Session VWAP | **Liquid Nifty 50 / Next 50 / Midcap 100 only** — wide spreads kill it on small-caps. |
| **Supertrend trend filter** | Price above line = long, below = short; combine with 5/20-EMA filter | ATR trailing stop | Period 10, mult 2–3 (10/3 or 14/3 on 10–15 min) | ~50–55% win on 5-min Nifty; positive only because winners run 2–3× losers. Whipsaws sideways. Ignore vendor "1,000,000%" claims. |
| **Bollinger (regime-aware)** | Mean-reversion in ranges: tag outer band + rejection → target mid-band. Breakout after squeeze: close beyond band | ATR stop beyond trigger bar; ~15-bar time stop for mean-reversion | 20-SMA, ±2σ; ATR(14); squeeze = bandwidth bottom ~20th pct | Mean-reversion shows high headline win rates but rare catastrophic losses when fading a real breakout. Never fade without a stop. |
| **RSI-2 mean-reversion (Connors)** | Above 200-SMA, buy RSI(2) < 5–10 | Exit close > 5-day MA or RSI(2) > 70 | RSI period 2 | Edge has decayed since 2008; ~34–35% max drawdown in modern tests. A tactical building block, not a standalone system. |
| **52-week-high / relative-strength momentum** | Buy names near 52-wk high (George–Hwang) | Trend/volatility-scaled exit | Lookbacks 21/63/126/252-day | Academically robust **but suffers momentum crashes** (worst monthly ≈ −69%), concentrated after bear bottoms; works mainly in UP markets. |

Use **MACD (12/26/9)** and **MA crossovers** only as *filters/confirmation*, not standalone signals — both are lagging with wildly inconsistent reported accuracy.

### Risk management (blunt)
- **Position sizing:** fixed-fractional **0.5–2% equity risk per trade**; size = (equity × risk%) ÷ (entry − stop). If you use Kelly, use **¼–½ Kelly** — full Kelly can produce 50–80% drawdowns even with a real edge and blows up on overfit/small-sample inputs.
- **Stops:** ATR-based, **1.5–2.5× ATR**, adapts to volatility; Chandelier trailing exit = Highest-High(22) − 3×ATR. *(Verification: the indicator definitions are confirmed; the specific performance numbers "ATR trailing beats fixed by 26–48% PF" and "−32% drawdown" were **REFUTED** as recycled, unsourced marketing — see §7. Use ATR stops because they adapt to volatility, not because of those numbers.)*
- **Reward:risk** ≥1.5–2:1. Trend systems accept <50% win rates because R:R is large.
- **Circuit breakers:** daily loss cap, halt after N consecutive losses, reduce size / halt at a portfolio-drawdown threshold. These are your own kill-switches (distinct from exchange price halts).

### Realistic expectations (read this twice)
- **SEBI's own data:** ~93% of individual F&O traders lost money FY22–FY24 (aggregate >₹1.8 lakh crore); in equity-cash intraday, ~71% lost in FY23 (76% for under-30s, 80% for >500 trades/yr). Loss-makers spent +57% of their losses on trading costs.
- **~80% of strategies that look good in backtest fail live** (overfitting). *(Verification: UNCERTAIN — the qualitative thrust is well-supported by academic work, e.g. 82% of 452 anomaly signals failed under stricter multiple-testing; the exact "80%" is an approximation, not a primary-sourced constant.)*
- **"8–15% annual net for survivors"** is a single-source, US-retail framing. *(Verification: UNCERTAIN — plausible, within a broad documented spectrum, but not independently confirmable as a precise band.)*
- **Bottom line:** these are conditional, regime-dependent tools, not money machines. Backtest with realistic Indian costs + slippage, validate out-of-sample, size with fractional-Kelly or fixed-%, use ATR stops and drawdown circuit breakers. Expect single-digit-to-low-double-digit net returns *at best*, against a base rate where most retail traders lose.

---

## 5. Data & Backtesting Recommendation

**Historical (chosen): Dhan v2 historical API** (5-yr intraday, daily to inception) as primary, backfilled into TimescaleDB once — chunk by the **90-day/request** limit, respect **5 req/s**, cache locally. Supplement free EOD via **Getbhavcopy / nser** (NSE bhavcopy). Reach for paid authorized vendors (**Global Datafeeds, TrueData**) only if you later need tick-level archives. `yfinance` (`.NS`/`.BO`) is fine for quick prototyping only — it's an unofficial scraper with frequent HTTP 429 bans; **not for bulk/production backfill**.

**Real-time (chosen):** the **Dhan broker WebSocket** (binary; 5 conns / 5000 instruments each) — free exchange-grade ticks. No third-party feed needed for a single-broker stack.

**Instruments:** load Dhan's CSV scrip master (Security ID is Dhan's key). If you ever add a second broker, normalize on **(exchange, tradingsymbol)** and/or **ISIN** — never key off reusable exchange tokens.

**Backtesting framework (chosen): vectorbt** for fast parameter sweeps over NSE universes, with **backtesting.py** as an execution-realism cross-check. (Avoid Backtrader — stalled ~2021; vectorbt free edition is maintenance-only but sufficient.) Note vectorbt's **one-signal-per-bar** limit makes intrabar SL+target ordering approximate — validate any execution-sensitive (bracket/intrabar) strategy in backtesting.py or a tick/1-min sim layer before going live.

**Indian cost modeling:** in vectorbt's `Portfolio.from_signals()` use `fees` + `fixed_fees` + `slippage`. Encode the real component rates rather than a single blended guess:
- Brokerage: flat **₹20/order** (or ₹0 delivery at discount brokers) — *Zerodha official, confirmed*.
- STT: **delivery 0.10% buy+sell; intraday 0.025% sell-side only**; NSE txn ~0.00307%; SEBI ₹10/cr; **GST 18%** on (brokerage+txn+SEBI); stamp duty 0.015% (delivery) / 0.003% (intraday) buy-side.
- Slippage ~0.05% large-caps, higher for mid/small.

> *Verification flag (UNCERTAIN): the popular "≈0.11%/trade + 0.05% slippage ≈ 0.32% round-trip" shorthand is a single-vendor (BacktestIndia) convention and matches **delivery** only; **intraday is roughly half** that. Compute from the component rates per segment instead of hard-coding 0.32%.*

Consider the **marketcalls/vectorbt-backtesting-skills** repo (NSE cost breakdowns, holidays/hours, QuantStats tearsheets) as a ready-made cost layer. **Paper trading:** broker sandboxes are integration-test environments, not realistic fill simulators (Dhan sandbox fills everything at price 100, no streaming). Use your own `PaperBroker` simulating fills against the live feed, or adopt **OpenAlgo's sandbox mode** (₹1cr virtual, T+1 sim, same unified API).

---

## 6. Phased Build Roadmap

**Phase 0 — Foundations (week 0–1)**
- Provision fixed-IP VPS; whitelist IP with Dhan; Postgres+TimescaleDB; `dhanhq` SDK; `.env` secrets (chmod 600).
- Automated daily token-refresh job (APScheduler, ~08:30 IST) with Telegram fail-alert.
- *Milestone:* token auto-refreshes and a `/profile` call succeeds from the whitelisted IP each morning.

**Phase 1 — Tracker + Alerts (week 1–3)**
- One shared Dhan WS feed → decode binary → 1-min candle aggregation → TimescaleDB.
- FastAPI `/ws/quotes` + `/api/candles`; Streamlit/Dash read-only tracker first, React later.
- TA-Lib indicators; declarative rules engine with cooldown/de-dup; Telegram `notify()`.
- *Milestone:* live candlestick dashboard for ~20 liquid symbols; a "price crosses upper Bollinger band" alert lands on your phone with no spam.

**Phase 2 — Backtesting (week 3–5)**
- Backfill 5-yr history (chunked 90-day loops, cached). Write strategies against a thin `on_candle(ctx)->signals` interface so identical logic runs in backtest/paper/live.
- vectorbt sweeps with per-segment Indian costs; out-of-sample (70/30) + walk-forward validation.
- *Milestone:* ORB + Supertrend backtested with realistic costs, OOS results reported, overfit-resistant params chosen.

**Phase 3 — Paper-trading bot (week 5–7)**
- `IBroker` abstraction; `PaperBroker` fills against live feed into `paper_*` schema. MODE banner everywhere. Position reconciliation on startup; dead-man's-switch.
- *Milestone:* the exact backtested strategy runs live-feed paper for 2+ weeks; paper P&L roughly tracks backtest expectations; no crashes survive without auto-recovery.

**Phase 4 — Live, small size (week 7+)**
- `LiveBroker` via Dhan **Super Orders** (broker-side bracket + trailing SL). Token-bucket limiter hard-capped well under 10 OPS. All interlocks live; "arm live" defaults OFF; algo tag on every order; immutable audit log.
- Start with **minimum viable size** (1 lot / smallest position), one strategy, one or two liquid symbols.
- *Milestone:* 4 weeks live at micro size with zero reconciliation discrepancies and the kill-switch tested; only then scale size.

---

## 7. Open Decisions & Risks

### Decisions the owner must make
1. **Broker:** confirm **Dhan-first** (recommendation) vs Upstox. Driver: Dhan's broker-side bracket/trailing and automatable token vs Upstox's mandatory daily human OAuth login.
2. **Data API ₹499/month:** free once you hit 25 trades/30 days — accept the cost early, or delay real-time data until trade volume qualifies?
3. **Dashboard fidelity:** Streamlit/Dash (ship in a weekend, read-only) now vs FastAPI+React (polished real-time) later.
4. **Hosting region:** any fixed-IP VPS works for compliance; Mumbai only if you want marginal latency. Decide VPS vs managed cloud (snapshots/elastic-IP convenience for ~2× cost).
5. **DDPI activation (₹100):** activate to auto-sell holdings, or handle CDSL eDIS flow.
6. **Strategy scope:** start single-strategy/single-symbol (recommended) vs a basket.

### Verification call-outs — do NOT build on these as fact
- **REFUTED — "ATR trailing beats fixed stops by 26–48% on profit factor; −32% max drawdown."** Recycled, unsourced marketing, not Indian-market, contradicted by the best available practitioner backtest. **Use ATR stops because they adapt to volatility, not for any promised performance number.**
- **REFUTED/FALSE justification — "Mumbai locality supports the required static IP."** SEBI's static-IP mandate is real and required, but is **not tied to Mumbai or even to India** — any region's static IP qualifies (Zerodha's own explainer: "No mandate for the IP to be from India"). Mumbai's latency benefit is real but marginal for a sub-10-OPS bot. (VPS pricing itself: confirmed accurate.)
- **UNCERTAIN — "~80% of backtested strategies fail live."** Directionally well-supported (overfitting is the documented top failure cause; 82% of anomaly signals failed under stricter testing), but the exact 80% is an approximation.
- **UNCERTAIN — "8–15% annual net returns for survivors."** Single-source, US-retail framing; plausible but not independently confirmable. Don't promise this to yourself.
- **UNCERTAIN — "~0.11%/trade + 0.05% slippage ≈ 0.32% round-trip."** Single-vendor convention; matches **delivery** only, **intraday ≈ half**. Model per-segment from official component rates instead.
- **CONFIRMED but date-logic-dependent — SEBI framework "live since 1 April 2026."** Firmly documented deadline + dense convergent reporting, but no SEBI primary source dated *after* 1 April 2026 was independently located confirming no further extension. **Re-verify against any post-April-2026 SEBI/NSE circular before relying on the exact go-live status.**
- **CONFIRMED — Dhan rate limits** (Order 10/sec, 250/min, 7,000/day; Data 5/sec, 100k/day; Quote 1/sec; Option Chain 1/3sec) against current v2 docs. Older 25/sec support-page figures are legacy/pre-v2.3 — ignore them.

### Standing technical risks
- **Dhan 90-day/request historical limit + 5 req/s** → backfill is slow and must be chunked/cached. No bulk multi-symbol endpoint.
- **Daily token expiry** (both brokers) → automate refresh and alert loudly on failure *before* market open; a missed refresh = no trading that day.
- **vectorbt one-signal-per-bar** → intrabar SL+target ordering is approximate; validate execution-sensitive strategies elsewhere before live.
- **Regulatory boundary = engineering boundary:** keep order submission hard-capped under 10 OPS to avoid mandatory exchange algo-registration.