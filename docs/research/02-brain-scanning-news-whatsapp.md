<!-- Auto-extracted from research workflow output, 2026-06-23 -->

I'll write this architecture addendum directly from the research and verification findings provided. No tools needed — the material is all here.

# Architecture Addendum: Full-Universe Scanning, News/Sentiment, WhatsApp Control, and an LLM Reasoning Brain

**For:** Project owner (retail trader/builder)
**Date:** 2026-06-23
**Scope:** Extends the existing Dhan-based Indian-market trading bot build plan with four capabilities. Candid throughout: where the research is solid I state it plainly; where adversarial verification refuted or could not confirm a claim, I flag it in Section 7 and do not present it as fact.

---

## 1. Two-Brain Architecture

The core design principle, backed strongly by the 2026 literature, is a **two-tier split**: a deterministic fast engine that owns execution and risk, and a slow LLM "strategist" that only advises.

### Components and data flow

```
                    ┌──────────────────────────────────────────────┐
                    │            SLOW BRAIN (LLM tier)             │
                    │  cadence: per-minute / per-material-event    │
                    │  - news + filings interpretation             │
                    │  - sentiment scoring (FinBERT + LLM)         │
                    │  - market-regime label (risk-on/off, vol)    │
                    │  - rank/prune a DETERMINISTIC candidate set  │
                    │  - WhatsApp/Telegram narration (read-only)   │
                    │  emits: strict JSON {signal, confidence,     │
                    │         horizon, regime, rationale, sources} │
                    └───────────────┬──────────────────────────────┘
                                    │ writes advisory signals (timestamped)
                                    ▼
                    ┌──────────────────────────────────────────────┐
                    │         SHARED SIGNAL STORE (cache)          │
                    │  LLM writes here; fast loop READS latest.    │
                    │  Each signal has t_signal for staleness decay│
                    └───────────────┬──────────────────────────────┘
                                    │ read latest cached signal (never blocks)
                                    ▼
   Dhan WS feed ──► ┌──────────────────────────────────────────────┐
   (ticks)          │        FAST ENGINE (deterministic tier)      │
                    │  - per-symbol candle + incremental indicators│
                    │  - strategy rules (price/indicator triggers) │
                    │  - HARD RISK ENGINE (position size, loss,    │
                    │    exposure caps) — FAIL-CLOSED, absolute veto│
                    │  - order gateway (the ONLY thing that trades)│
                    └───────────────┬──────────────────────────────┘
                                    ▼
                              Dhan Order API
```

### Where the LLM is ALLOWED to influence

- **Bias / weighting** a deterministically-generated candidate set (e.g., "of the 12 breakouts the fast engine flagged, these 4 align with positive filings and risk-on regime").
- **Regime label** that selects which *pre-defined, pre-approved* parameter set the fast engine uses (e.g., wider stops in high-vol).
- **Sizing tilt within hard caps** — it may suggest "smaller size," never "larger than the cap."
- **Narration** — human-readable explanations pushed to WhatsApp/Telegram. This is read-only and cannot move money.

### Where the LLM is FORBIDDEN

- It **never** touches the order gateway. No order is placed, modified, or cancelled by an LLM-emitted instruction directly.
- It **cannot** write authoritative state (positions, balances, fills). It reads a deterministic, environment-updated state store only.
- It **cannot** raise or remove any hard risk limit. Limits are immutable rules enforced at the gateway.
- It is **not** in the tick-level hot path. The reasons are decisive and each independently sufficient (verified, see §5): LLM latency (~1s time-to-first-token, up to ~15s at long context) is millions of times slower than the microsecond execution budget; per-call cost makes per-tick invocation absurd; hosted LLMs are non-deterministic even at temperature 0; hallucination and prompt injection add attack surface.

**Staleness handling:** because the cached LLM signal is always slightly old, the fast engine treats it as a *slowly-varying prior*, decays its weight over time (e.g., `weight = e^(−λ·(t_now − t_signal))`), and never lets a stale signal override live risk state.

This mirrors the published "slow-brain/fast-reflex" decomposition (reactive ms–µs with no LLM, reflective seconds, strategic minutes) and the "Hierarchy of Truth" — internal risk limits beat external noisy signals when they conflict.

---

## 2. Full-Universe Scanning (Dhan)

### Exact Dhan WebSocket limits (DhanHQ v2 Live Market Feed)

| Limit | Value |
|---|---|
| Instruments per connection | **5,000** |
| Concurrent connections per user | **5** |
| Total trackable | **25,000** (5 × 5,000) |
| Instruments per subscribe JSON message | **100** (send many messages per socket) |
| Over-limit | 6th socket → **error 805**, oldest socket dropped |
| Keepalive | server pings every **10s**; closed after **>40s** no response |
| Wire format | requests JSON; responses **binary, little-endian, 8-byte header** |
| Packet modes | **Ticker (2)** LTP only; **Quote (4)** OHLC/vol/bid-ask; **Full (8)** Quote + 5-level depth + OI |

REST rate limits (matter only for startup buffer-warming, not the tick stream): Data 10/s, Quote 1/s, Order 25/s, Non-trading 20/s.

> **Doc inconsistency to verify yourself:** one older Dhan freshdesk article claims "5 connections with *unlimited* instruments each." The main v2 docs say 5 × 5,000 = 25,000. **Treat 25,000 as authoritative** and confirm against current docs before relying on "unlimited."

### Sharding scheme

1. Download the scrip master (`api-scrip-master-detailed.csv`); map symbols → `security_id` + `exchange_segment`. **Subscriptions are by numeric Security ID, not ticker.**
2. Partition N symbols into chunks of ≤5,000 → one WebSocket per chunk (≤5 sockets).
3. Within a socket, send subscribe messages in batches of ≤100.
4. One task/process per socket; maintain ping/pong; auto-reconnect + re-subscribe + gap-fill on drop.

Because the realistic liquid universe (≤~1,800 names) fits in **one** connection, most real scanners need only **1–2 sockets**, leaving headroom under the 5-socket cap.

### The realistic liquid universe to actually scan

NSE lists ~2,200+ companies, but scanning all of them is pointless — illiquid names give wide spreads, severe slippage (a wide spread can be ~25× the hidden cost of a liquid name), and stale/circuit-locked bars that break RSI/EMA logic. Scan the **liquid tradable subset**, in order of tightness:

- **~200–250 F&O stocks** — tightest spreads, best for intraday/algo execution.
- **Nifty 500** — ~92% of free-float market cap, ~84% of NSE traded value. Best breadth/quality tradeoff.
- **~1,000–1,800 turnover/volume-filtered names** — practical outer bound before you hit dead shells.

**Recommendation:** start at F&O (~200–250) or Nifty 500, expand toward ~1,800 only if compute holds.

### Per-symbol indicator computation

**Stream, don't recompute.** Recomputing a full indicator over the whole price vector per tick is O(n) and won't scale.

- **talipp** — purpose-built incremental indicators with `add()`/`update()`/`remove()`, **O(1) per new value** (~200ms vs ~6,800ms for 50k inputs batch). This is the per-symbol primitive. Note: talipp is pure Python, so it still runs on the GIL-bound path — keep per-symbol indicator count modest.
- **Polars** — one vectorized pass at **bar-close** for cross-sectional ranking/screening (top movers, relative volume). Multi-threaded, ~4–9× pandas, releases the GIL. No built-in indicators (use `group_by_dynamic`/rolling).
- **pandas-ta / TA-Lib** — batch only, for warming buffers and backtests, not per-tick.
- **Per-symbol state** — `collections.deque(maxlen=N)` ring buffer of candles + persistent talipp objects. Ticks aggregate into the current candle; finalize on bar boundary with a ~1–2 min late-tick buffer.
- **Buffer warming at startup** — `/v2/charts/intraday` (1/5/15/25/60 min, ≤90 days/req) to backfill, respecting 10 req/s.

### What a single laptop CAN and CANNOT handle

- **CAN:** ~500–1,800 liquid symbols in **Ticker/Quote** mode, incremental indicators, **bar-close** evaluation, parsing via precompiled `struct.Struct`/numpy, 1 process per shard across 2–4 cores. RAM is not the constraint (~tens to low-hundreds of MB).
- **CANNOT (it falls over):** subscribing the full listed universe in **Full/depth** mode and recomputing many indicators **per tick in pure Python on one core**. The wall is the **Python GIL** serializing per-message CPU work — the asyncio loop backs up, signals go stale, and you risk the 40s server disconnect.

> **Honesty flag (verification: UNCERTAIN):** the specific "500–1,800 symbols" ceiling is an engineering rule-of-thumb with **no primary-source backing** and conflicting secondary estimates (some cite as few as ~50–500, others 10,000+ with Numba/multithreading). The *mechanisms* (GIL, mode cost, O(1) vs recompute) are confirmed; the *exact number* is not. **Benchmark on your own hardware before committing.** Also note Dhan's 25,000 cap far exceeds the liquid universe — your binding constraint is laptop CPU, not the API.

---

## 3. News + Sentiment Pipeline

### Sources (free-first)

**Primary, highest-signal, freshest — exchange filings:**
- **NSE/BSE corporate announcements** via unofficial wrappers (`BseIndiaApi`, `bshada/nse-bse-api`). **Verification-flagged caveat:** there is **no clean official public REST API** — the exchange JSON endpoints need browser-like cookies and aggressively block scrapers, so these wrappers are **fragile, no SLA, will break** when NSE/BSE change anti-bot measures. Budget for breakage.
- Optional paid prototyping shortcut: **StockInsights.ai** tagged feed (ticker-prefixed `NSE:`/`BSE:`, AI summary, 26 category tags, pos/neg/neutral). REST-only, no latency SLA, no public pricing.

**Breadth (free):**
- **Pulse by Zerodha** (free aggregator firehose), plus RSS from Economic Times, Moneycontrol, LiveMint, Business Standard. Good for small/mid-cap mentions, but second-hand vs the original filing.

**Macro tone (free):** **GDELT 2.0** — free, 15-min cadence. Use for macro/thematic sentiment only; it's too slow and not ticker-linked for per-stock event reaction.

**Skip / avoid:**
- **NewsAPI.org free tier** — 24-hour delay, useless for real-time. Real-time starts at $449/mo Business.
- **X/Twitter** — real-time filtered stream needs the ~$5,000/mo Pro tier (closed to new signups); pay-per-use otherwise. Treat X/Telegram tips as an **adversarial manipulation source**, not signal (SEC/SEBI document active pump-and-dump crackdowns).

### Ingestion → ticker-linking → LLM sentiment

1. **Poll** filings wrappers + Pulse/RSS; pull GDELT for macro.
2. **De-duplicate aggressively** — one event hits the filing + multiple wire rehashes + reposts. Cluster by event/entity/time window; without this you double-count.
3. **Ticker-link** — filings arrive ticker-prefixed (easy); free-text media needs finance NER to map company → ticker (harder for Indian names).
4. **Sentiment/event extraction** — FinBERT/embeddings for cheap headline sentiment + an LLM for nuance and event typing (earnings surprise, M&A, SEBI/RBI action, rating change, management change, buyback, insider disclosure).
5. **Critical de-biasing:** **anonymize company identifiers before sentiment scoring.** Research found a "distraction effect" (the model's background knowledge of a company) was *more* consequential than look-ahead bias; anonymized headlines outperformed originals.

### Cadence

Per-event / per-minute, feeding the shared signal store the fast engine reads. This is the slow brain — not tick-level.

### HONEST note: can retail profit from news speed?

**No — not on the impulse move.** This is well-supported. HFT round-trips in microseconds; institutions co-locate and parse structured feeds and reprice material news in milliseconds-to-seconds, before you can even read the headline. Your realistic pipeline latency (filing → RSS/aggregator poll in seconds-minutes → your NLP → broker round-trip → human confirm) is **seconds to minutes** — you arrive after the first jump.

The only viable retail angle is the **slower post-event drift / medium-horizon repricing**, not instantaneous reaction. And even that edge is **flagged UNCERTAIN by verification** (see §7): Post-Earnings-Announcement Drift in India is documented by at least one strong study but **contested** (one of the cited sources actually concludes the Indian market is *efficient* w.r.t. earnings), the option-active overreaction/reversal pattern is a **US finding not established for India**, and "drift is the more catchable retail edge" is an **unproven normative judgment** that doesn't net out transaction costs. **Do not treat news trading as a reliable edge; treat it as a feature with weak, decaying, costs-sensitive predictive value.**

---

## 4. WhatsApp Two-Way Control

### Recommended provider

For a **single-owner control channel, Telegram is the recommended primary** (verification: **CONFIRMED**). It is zero-cost, no template approval, no 24h window, instant inline confirm/cancel buttons via `callback_query`, and a built-in `setWebhook` secret token. The owner already started the bot, so it can message anytime.

If WhatsApp delivery is a **hard requirement**, use **Meta WhatsApp Cloud API directly** (not Twilio). Twilio adds **$0.005/msg** on top of Meta's fee for no benefit to a single-user bot (verification: CONFIRMED).

| | Telegram (recommended) | Meta Cloud API | Twilio |
|---|---|---|---|
| Cost | $0 | Meta category fee only | Meta fee + $0.005/msg |
| Template approval | None | Required outside 24h window | Same (Meta rule) |
| 24h window | None | Yes | Yes |
| Confirm buttons | Inline keyboard (trivial) | Interactive (templated/in-window) | Same |

### The template / 24-hour-window constraint (WhatsApp only)

When the user messages the bot, a **24-hour window** opens (and **resets** each time they message again) during which free-form messages are free. **Outside the window, any business-initiated message — e.g. a 3am fill alert — MUST be a pre-approved template** (most naturally a **Utility** template; PIN/confirm = **Authentication** template). This is a Meta platform rule, identical through every BSP. Template approval takes ~24–48h. **Telegram has no analog** — another reason it's the cleaner choice.

### Secure command-authentication for 'exit' (so only the owner can move money)

Webhook signature verification proves the message came from *the platform*, **not from the authorized owner**. Layer these (all from the research, defense-in-depth — no single layer is sufficient):

1. **Allow-list the sender id (most important).** Hard-pin the owner's Telegram numeric `user_id` (or WhatsApp `WaId`). Reject every inbound from any other id outright.
2. **Verify webhook authenticity.** Telegram `X-Telegram-Bot-Api-Secret-Token` (a secret you set) / Meta `X-Hub-Signature-256` (HMAC-SHA256 over **raw body** with App Secret, computed before JSON parsing, timing-safe compare) / Twilio `X-Twilio-Signature` (use the SDK validator). Reject failures **before** parsing.
3. **Confirmation handshake.** Never act on a raw "exit." Reply with a confirm carrying a **server-generated single-use, short-TTL, trade-id-bound signed token** (Telegram: inline button whose `callback_data` carries the token; call `answerCallbackQuery`). User must echo/tap it.
4. **PIN / step-up for destructive actions.** Require a per-action PIN or TOTP in the confirmation for anything that moves money (exit/flatten/cancel). The PIN never travels in your outbound text.
5. **Idempotency.** Each command carries a unique action id; record processed ids, drop duplicates. Webhooks retry on non-2xx and can arrive out of order — without this a retried "exit" double-fires. Return 2xx fast, dedupe by message id.
6. **Command-injection hygiene.** Strict allow-list grammar (`exit <id>`, `flatten`, `status`); never `eval`/shell-interpolate; unicode-normalize before matching; reject ambiguous input.
7. **Secret management.** A leaked Telegram bot token = anyone can send as your bot. Store in a secret manager, never hardcode, rotate on suspicion.

> Net: the **platform** authenticates the **channel**; **you** must authenticate the **owner and the intent.** Allow-list + signed-token confirm + PIN + idempotency = a safe exit path.

WhatsApp reliability extra: a **Low quality rating** (if the owner ever marks messages spam) gates tier upgrades and risks restriction. Negligible for one user, but real.

---

## 5. Guardrails & Failure Modes

### Hard limits the LLM cannot override

Encode as **immutable rules / decision-table axioms enforced at the order gateway**, fail-closed (if a condition isn't explicitly satisfied, execution halts):

- **Max position size per symbol** and **max total exposure.**
- **Max daily loss** / per-trade loss → kill-switch trip.
- **Price/size sanity bounds** (reject fat-finger orders).
- **Whitelist of tradable instruments** (the liquid universe).

A *probabilistic* LLM filter can never satisfy a hard limit — "a probabilistic filter might block 99.9%, but a non-zero evasion probability means you cannot guarantee compliance." (US note: SEC Rule 15c3-5 requires deterministic pre-trade controls under direct control. You're in India so 15c3-5 doesn't bind you, but the **engineering principle holds**: limits must be deterministic, not LLM-mediated.)

### Prompt-injection defense for ingested news

Indirect prompt injection (hidden instructions in news/filings the LLM reads) is **OWASP LLM01:2025, the #1 LLM risk** (malicious web-content payloads rose ~32% Nov 2025–Feb 2026). A poisoned headline could try to flip a recommendation. Defenses:

- The LLM holds **no execution authority** (this alone neutralizes the worst case — a poisoned headline can't place an order).
- **Content segregation** — clearly delimit/mark untrusted feed text in the prompt; never let it be interpreted as instructions.
- **Least privilege** — minimal tool access; high-risk operations live in application code, not model-emitted prompts.
- **Structured output validation** — strict JSON schema via constrained decoding (Pydantic + retry). Remember: schema compliance ≠ semantic correctness; downstream deterministic checks still required.
- **Human-in-the-loop for novel/significant trades**, plus **circuit breakers** (trip on anomalies — same tool+args N times, risk-budget burn) and a **global kill switch**. 2026 analyses warn of agent "recursive death spirals" that burn risk budgets in seconds.

### Laptop / disconnect failure handling → broker-side protective stops

The single most important resilience rule for a laptop-hosted bot: **never rely on the laptop to hold a stop.** If the laptop crashes, loses network, or the WS disconnects, your in-memory stop logic dies with it.

- **Place protective stops broker-side** (Dhan stop-loss / SL-M orders sitting on the exchange) for every open position, so a position is protected even if your process is dead.
- **WS resilience:** ping/pong heartbeat, auto-reconnect + re-subscribe, gap-fill from historical API after reconnect (the 40s no-response disconnect is real).
- **On startup/reconnect, reconcile** live broker positions/orders against local state before acting (read-only deterministic state store is the source of truth, not the LLM).
- **Kill switch** that flattens or hands off to broker-side stops on anomaly.
- Treat any LLM signal older than a threshold as expired (staleness decay from §1).

---

## 6. Cost Estimate (rough monthly)

Assumes single-owner bot, liquid-universe scanning, LLM on per-minute/per-event cadence (not per tick).

| Item | Choice | Est. monthly |
|---|---|---|
| **Dhan live data** | ₹500/mo per API key (live+historical) | **~₹500 (~$6)** |
| **News — free path** | Pulse + RSS + GDELT + unofficial filings wrappers | **₹0** (engineering/breakage cost only) |
| **News — optional paid** | StockInsights tagged feed (pricing not public) / NewsAPI Business $449 | **$0 → ~$449** if you buy real-time |
| **LLM calls** | e.g. GPT-4.1-class @ ~$2/1M in + $8/1M out, event-gated (only on material events), prompt caching, short context. A few hundred calls/day at modest token counts. | **~$10–60** typical; can spike with long context / high event volume |
| **Messaging — Telegram** | free | **₹0** |
| **Messaging — WhatsApp (if used)** | India utility ~₹0.12/msg, free in-window/service; tiny volume | **~₹0–50 (<$1)**; Twilio adds $0.005/msg if used |
| **Compute** | your existing laptop | **₹0** |

**Realistic baseline (free-news + Telegram + Dhan + modest LLM):** **~$15–70/month**, dominated by LLM usage. Going to real-time paid news (NewsAPI Business $449 or X Pro $5,000) dwarfs everything — **avoid unless you've proven the news edge exists**, which (see §7) is unconfirmed.

> Pricing caveats from research: India WhatsApp per-message rates come from **aggregators, not Meta's page** — verify on the live rate card. StockInsights and X enterprise pricing are not public. LLM cost depends heavily on context length and event frequency.

---

## 7. Open Decisions / Flagged Risks

### Decisions the owner must make

1. **Universe size:** F&O (~200–250) vs Nifty 500 vs ~1,800 turnover-filtered. Start small, benchmark, expand.
2. **Messaging channel:** Telegram (recommended, $0) vs WhatsApp (only if delivery to WhatsApp is genuinely required — accept template/window friction).
3. **News path:** free-first (Pulse/RSS/GDELT/wrappers) vs paid (StockInsights/NewsAPI). **Recommend free-first until the edge is proven.**
4. **LLM model + cadence:** which model, per-minute vs per-event gating, context budget — these drive cost.
5. **Risk limits (the numbers):** max position size, max daily loss, max exposure — must be set as immutable axioms before go-live.
6. **Broker-side stop policy:** confirm every position gets a server-side SL order.

### Claims adversarial verification REFUTED or left UNCERTAIN — do not treat as fact

- **UNCERTAIN — News/PEAD edge (§3):** "PEAD drift is the more catchable retail edge than instantaneous reaction" is **not cleanly confirmed.** PEAD in India is documented by one strong study but **contested** (a cited source concludes the Indian market is efficient w.r.t. earnings); the **option-active overreaction/reversal pattern is a US finding, not established for Indian NSE**; and the "more catchable retail edge" conclusion is an **unproven normative judgment** that ignores transaction costs and declining anomaly magnitude. **Build the news pipeline as a weak, decaying, cost-sensitive feature — not a proven money-maker.**

- **UNCERTAIN — Single-laptop symbol ceiling (§2):** the "~500–1,800 symbols" figure has **no primary-source backing** and secondary estimates conflict wildly (~50–500 up to 10,000+). The mechanisms (GIL, mode cost, incremental vs recompute) are confirmed; the number is not. Also, "within Dhan's API constraints" is slightly misleading — Dhan's 25,000 cap exceeds the liquid universe, so your real limit is **laptop CPU. Benchmark on your hardware.**

- **CONFIRMED — Telegram vs WhatsApp/Twilio (§4):** Telegram is lowest-friction/zero-cost for single-owner; Meta Cloud API beats Twilio (avoids $0.005/msg). Safe to rely on.

- **CONFIRMED — LLM-as-analyst envelope (§1, §5):** "whether an LLM adds genuine alpha is largely unproven; safe envelope = advisory + deterministic veto + human oversight + out-of-cutoff evaluation" is well-supported. **Corollary:** be deeply skeptical of any backtest of the LLM layer — training-cutoff lookahead means pre-cutoff backtests overstate returns (often artifactual). **Evaluate only on post-training-cutoff dates, with point-in-time data, anonymized tickers, walk-forward splits, realistic transaction costs, and the LLM ablated on/off.** The published literature has a reproducibility crisis (0/19 studies fully reproducible).

### Standing risks to keep in view

- **Unofficial NSE/BSE wrappers will break** without warning — no SLA. Have a fallback.
- **Prompt injection via news** is the scariest trading-specific risk — mitigated only because the LLM has no execution authority. Keep it that way.
- **Latency reality:** you are structurally late on news. Design for drift, not reaction.
- **Manipulation sources:** X/Telegram tips are frequently the pump-and-dump itself. Never feed them as ground truth.