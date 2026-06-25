<!-- Auto-extracted from research workflow output, 2026-06-23 -->

This is a writing task. I have all the research and verification findings I need. I'll produce the markdown section directly.

# Can We Copy Top Traders, and How?

## 1. The hard truth: real-time mirroring is impossible

**You cannot copy a named trader's live intraday trades, because no such data exists publicly — and the research confirms this without exception.**

The NSE/BSE order book is an **anonymous, order-driven electronic limit-order book**. The live tick feed exposes **price and volume only** — never a broker code, client code, or client name. Counterparties are not revealed pre-trade or post-trade in the public feed. Client identity is captured by the exchange only via the confidential **Unique Client Code (UCC)** for surveillance/audit, retained for years, and is never publicly exposed in real time ([NSE Trading System](https://www.nseindia.com/static/products-services/equity-market-trading-system), [NSE UCC FAQ](https://www.nseindia.com/static/trade/unique-client-code-faqs), [India Infoline](https://www.indiainfoline.com/knowledge-center/online-share-trading/what-is-anonymous-trading)).

The anonymity is deliberate: it reduces information leakage and front-running and blocks identity-based manipulation. Large institutions also use **hidden/iceberg orders** (must display ≥10% of size), so even the size of a resting institutional order is partially masked.

Consequence: **named attribution only ever surfaces after the fact, and only above regulatory thresholds.** Every "who traded what" disclosure in India is post-trade and lagged — from same-day-after-hours (bulk/block deals) to T+2–T+4 (insider/SAST) to a full quarter (shareholding patterns). So a literal "mirror this person's trades as they happen" bot is not buildable for Indian equities. Anyone selling you that is lying or selling you offshore forex (which is separately illegal — see §4).

**Verdict: the claim is correct, high-confidence, and load-bearing for the whole plan. We design around lagged, aggregated, named-only-above-thresholds data — never a live feed.**

## 2. What IS obtainable — disclosed-flow sources

Everything below is post-trade. "Names?" = whether an individual entity is identified vs. a category aggregate.

| Source | What it reveals | Latency | Names? | How to fetch |
|---|---|---|---|---|
| **Bulk deals** | Date, symbol, company, **client name** (actual investor), buy/sell, **quantity**, **weighted-avg traded price (WATP)**. Triggered when a date+symbol+broker+client total ≥ **0.5%** of listed equity. Broker *not* named. | **Same day, after market hours** (broker reports within ~1hr of close) | **Yes** (end client) | NSE live snapshot `…/api/snapshot-capital-market-largedeal` (mode `bulk_deals`); historical `…/api/historical/bulk-deals?from=DD-MM-YYYY&to=DD-MM-YYYY`. Cookie-gated JSON. BSE [Bulk Deals report](https://www.bseindia.com/markets/equity/EQReports/bulk_deals). ([unofficed](https://unofficed.com/nse-python/nse-large-deal-api/)) |
| **Block deals** | Scrip, **client name**, quantity, traded price. **New framework live since ~Dec 2025**: min order size **₹25 cr** (up from ₹10 cr); windows **08:45–09:00** (ref = prior close) and **14:05–14:20** (ref = 13:45 VWAP), ±3% band, mandatory delivery. | **Same day, after market hours** | **Yes** | Same NSE endpoints, mode `block_deals` / `…/api/historical/block-deals`. BSE [Block Deals](https://www.bseindia.com/markets/equity/EQReports/block_deals). ([SEBI/HO/MRD/POD-III/CIR/P/2025/134](https://www.taxmann.com/post/blog/sebi-revises-block-deal-framework-minimum-order-size-rs-25-crore)) |
| **FII/DII cash flows** | Net buy/sell **value** for FII/FPI and DII in cash market. **Aggregate category only — no names.** | **Provisional ~18:00 IST** same day; **final next morning** (custodial-confirmed) | No (category) | NSE [reports/fii-dii](https://www.nseindia.com/reports/fii-dii) (CSV); definitive FPI on [NSDL](https://www.fpi.nsdl.co.in/Reports/ReportsListing.aspx). Aggregators: [Trendlyne](https://trendlyne.com/macro-data/fii-dii/latest/cash-pastmonth/), Sensibull. |
| **Participant-wise OI (F&O)** | Long/short open interest split into **FII, DII, Pro, Client** across index/stock F&O. Most granular *position* split available — still category-level. | **Once daily, ~19:00 IST** | No (4 categories) | NSE [derivatives reports](https://www.nseindia.com/all-reports-derivatives); [niftytrader](https://www.niftytrader.in/participant-wise-oi). |
| **Insider / promoter (SEBI PIT Reg 7) + SAST** | **Named** insider/promoter/director/large shareholder, quantity, value, txn type, price/range, dates, **pre/post holding %**. Trigger = >₹10 lakh in a quarter (PIT); 5% and ±2% moves (SAST). | **T+2 to T+4 trading days** (insider→company 2 days, company→exchange 2 days); much now auto via System-Driven Disclosure | **Yes** | NSE [PIT filings](https://www.nseindia.com/companies-listing/corporate-filings-pit-annual) / BSE corp announcements (PDFs, cookie-gated JSON). Searchable: [Trendlyne](https://trendlyne.com/equity/group-insider-trading-sast/), [InsiderScreener](https://www.insiderscreener.com/en/india/insider-trading/), Screener.in. |
| **Superstar quarterly holdings (SHP, LODR Reg 31)** | Every public shareholder holding **≥1%** named per company, with QoQ change. Aggregators stitch these into per-investor "portfolios" (Jhunjhunwala/Rekha, Damani, Kacholia, Kedia, M. Agrawal, Dolly Khanna…). | **Quarter-end + up to ~21 days** → up to **~4 months stale**; investor may have already exited | **Yes** (≥1% only) | [Trendlyne Superstar Portfolios](https://trendlyne.com/portfolio/superstar-shareholders/index/), [Screener.in "Follow Investors"](https://www.screener.in/docs/changelog/Follow-Investors-screener/) (free email alerts on bulk/block/>1% changes), [Tijori](https://www.tijorifinance.com/filter/?qt=advanced), [Value Research](https://www.valueresearchonline.com/stocks/who-owns-what/). Underlying: NSE/BSE SHP filings. |
| **Short-selling / SLB** | Scrip-wise short positions; SLB fees/volumes. **Aggregate, no names.** | **Weekly** (short-selling); SLB market-level | No | NSE `…/api/historical/short-selling`; [NSE SLB](https://www.nseindia.com/market-data/securities-lending-and-borrowing). |

**Fetch reality:** Neither NSE nor BSE offers a free, officially documented public REST API. All `…/api/` calls require a **desktop User-Agent plus a session cookie** fetched from a prior `nseindia.com` GET, or they return empty/401. Community wrappers: [bennythadikaran/NseIndiaApi](https://bennythadikaran.github.io/NseIndiaApi/api.html), [vamsi008/nse-deals-tracker](https://github.com/vamsi008/nse-deals-tracker). Plan for brittle scraping, rate-limiting, and occasional breakage.

## 3. How to use it in OUR bot

**Principle: disclosed flows are a *conviction filter / idea generator* layered on top of OUR own technical strategy — never a blind mirror.** The data is too stale, too partial, and too long-horizon to be a primary trade trigger. Used correctly, it biases *which* names our own signals are allowed to act on.

**Recommended architecture (signal layers):**

1. **Primary engine (ours):** our own technical/quant strategy generates entry/exit signals and does all timing, sizing, and risk management. This is the only thing that pulls the trigger.

2. **Conviction overlay (disclosed flows):** maintain a daily-refreshed **"smart-money watchlist"** built from:
   - **Superstar accumulation** — names where a tracked long-horizon investor is *adding* across consecutive quarters (QoQ ≥1% holding rising), not a single appearance. Accumulation trend matters more than a one-off stake.
   - **Bulk/block deals** — same-day named buys by credible long-term investors (filter out brokers' prop churn and counterparties).
   - **Insider/promoter buying** — promoter/insider *purchases* (T+2–T+4) are a stronger signal than sells (sells happen for many reasons: tax, diversification, pledges).
   - **FII/DII + participant OI** — category-level *context only* (regime/risk-on-off), never a per-stock trigger.

   Use the overlay to **upgrade conviction / increase position size / widen holding horizon** on names our technical engine independently flags, and optionally to **down-weight or veto** shorts on names superstars are aggressively accumulating. The overlay never originates a trade by itself.

3. **Idea generation (offline):** the watchlist feeds candidates into our backtester for independent validation before any name is allowed into the live universe.

**Pitfalls we must design around — these are why blind copying fails:**

- **Horizon mismatch.** These investors compound over **5–20 years** (Jhunjhunwala held Titan ~20 years). Copying them with a quarterly lag is fine for buy-and-hold but **useless as a short-term trigger** ([Kotak Neo](https://www.kotakneo.com/investing-guide/articles/cloning-the-superstar-of-india/)). So flow signals only feed our *longer-horizon* sleeve, not intraday.
- **Unobservable exits.** The ≥1% threshold means a position is **invisible until it crosses 1% and vanishes once it drops below 1%** — a partial or full exit is hidden for up to a quarter. **Never hold solely because a superstar "still owns it"; you don't know that.** Our own exit rules must always be in force.
- **Late-signal / price-spike slippage.** Once a stake becomes public the stock often spikes, so we pay a worse price than the originator. Bake a **post-disclosure cooldown / no-chase rule** (don't buy into the gap; wait for our own pullback signal).
- **Survivorship & selection bias.** The "superstar" roster is curated from people who already got rich; failures aren't listed. An India-specific study found survivor-only backtests on the NIFTY Smallcap 250 overstate annual returns by **~4.94 pp (23.3% relative)** and Sharpe by ~0.097 — far worse than the ~1–2% US figure, and superstars cluster exactly in these small/microcaps ([arxiv 2603.19380](https://arxiv.org/pdf/2603.19380)). **Do not trust any backtest built only on today's winner list.**
- **Long-only / partial visibility.** SHP and 13F-style data show longs only, ≥1% only — no shorts, no sizing relative to net worth, no conviction. Treat as a weak prior, not ground truth.
- **Data-quality risk.** Even in the US analogue, research documents strategic misreporting via permitted restatements; SHP/13F are not audited for completeness.

**Evidence it can help (so we don't over-dismiss it):** "best ideas" literature (Cohen, Polk & Silli) shows managers' highest-conviction picks beat the market ~1.6–2.1%/quarter, and 13F alpha-cloning backtests show excess returns — **but only when selecting the right, long-horizon, concentrated managers, and explicitly not for active/heavily-traded funds** ([Quantpedia](https://quantpedia.com/strategies/alpha-cloning-following-13f-fillings), [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3459526), [alphaclone](https://alphaclone.com/finance/13f-investment-really-works-how-retail-investors-ride-hedge-fund-coattails/index.html)). This is exactly why we use it as a *manager-selected conviction filter on a long sleeve*, not a universal copy engine.

## 4. Legality

**SEBI has no dedicated "copy trading" / "mirror trading" regulation — it is neither banned nor safe-harboured.** The activity gets pulled into existing frameworks: Investment Advisers (IA) 2013 (amended 16 Dec 2024), Research Analysts (RA) 2014, Portfolio Managers (PMS) 2020, and the **4 Feb 2025 algo-trading circular** ([SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html)).

**Where OUR bot sits — PERMITTED (this is the safe design):**
- It trades **only your own + immediate-family accounts**: self, spouse, dependent children, dependent parents. **No one else.**
- It runs via a **SEBI-registered broker's official API**; the **broker is the principal**, static-IP whitelisting applies.
- **Order-per-second (OPS) threshold:** below it, no formal algo registration; above it, the algo must be **registered with the exchange through your broker** and get a unique algo ID. **Verified value: 10 OPS**, set by the NSE (circular NSE/INVG/67858, 5 May 2025) and the Broker Industry Standards Forum — *not* by the SEBI circular itself, which left the number to the exchanges. Framework is **fully mandatory from 1 April 2026** (so it is live now, 2026-06-23).
- **Public data only** — bulk/block deals, shareholding patterns, post-publication filings, prices. This is **not UPSI** and is fine to act on after publication.

**PROHIBITED — do not cross these lines:**
- **Auto-mirroring a named trader's trades into other people's accounts for a fee.** This fails on multiple independent grounds: it breaches the algo framework's **family-only** limit; broadcasting buy/sell calls = **unregistered investment advice**; auto-executing in subscribers' accounts = **unauthorised discretionary/portfolio management** (PMS requires a registered body corporate, ≥₹50 lakh/client, no assured returns).
- SEBI is **actively prosecuting** the "trade-signal-for-fee" model: **Asmita Patel Global School of Trading** (interim order Feb 2025, 6 entities barred, ~₹53.67 cr impounded), **Mohit Gupta/"Safe Trading"** (Mar 2025), **Lifeinspire** (Oct 2025). Telegram tip channels were held to be a front for unregistered advisory.
- Even a **registered IA cannot legally sell "trading calls"** — the Dec 2024 amendment narrowed "investment advice" and IAs are not to give intraday calls. The compliant way to monetise baskets is via a **registered RA "model portfolio"** or a **smallcase** structure.
- **Offshore "copy trading" forex apps are separately illegal** for Indian residents (FEMA + unregulated-platform orders, e.g. OctaFX settlement Jul 2025).

**HARD RULE — never trade on insider info / UPSI.** Under SEBI PIT 2015, **Reg 4(1)** prohibits trading while in possession of UPSI and **Reg 3(1)** prohibits communicating it. Penalties (Sec 15G/11B): up to **₹25 crore or 3× profit, whichever higher**, plus disgorgement and market bans. The UPSI definition was **broadened ~10 June 2025** to align with LODR Schedule III. **Design rule: ingest only published/public data after publication. Never scrape, ingest, or act on leaked, pre-announcement, or private-channel information.** Post-publication bulk-deal/SHP/announcement data is explicitly *not* UPSI.

> **Legal caution:** This is a regulatory summary, not legal advice. The line between "permitted personal automation" and "unregistered advice / unauthorised PMS / un-empanelled algo provider" is fact-sensitive and actively enforced. Before anything touches another person's account, money, or takes a fee, get a written opinion from an Indian securities lawyer. OPS thresholds and registration mechanics are set in NSE/BSE circulars — re-verify at build time.

## 5. Flagged risks / refuted-or-uncertain claims

- **Corrected (verification nuance) — "below 10 OPS, API orders are treated as normal API use" is slightly overstated.** Verification against the primary **NSE circular NSE/INVG/67858 (5 May 2025)** and NSE FAQ (3 Nov 2025) confirms 10 OPS as the threshold and that it's set by the exchange/ISF (not SEBI's Feb 2025 circular, which left the number open). **But:** *all* orders via client APIs are still classified as **algo orders even below 10 OPS** and must carry standardised algo-ID tagging for audit. Below 10 OPS you skip per-strategy **registration**, but the orders are **not** legally "normal non-algo orders." Our bot must therefore **tag every order** regardless of rate.
- **OPS threshold is a config we must re-check at build time.** The 10 OPS value is set by exchange/ISF circulars and can be revised; treat it as a parameter, not a constant.
- **Block-deal parameters are recent (live since ~Dec 2025).** ₹25 cr minimum and the two new windows (08:45–09:00 / 14:05–14:20, ±3%) supersede all legacy ₹10 cr / single-window figures floating around online — verify the current SEBI/exchange text before hardcoding any deal-detection logic.
- **Aggregator API access is "medium" confidence.** No clean official public REST API exists for deals/flows/insider data; third parties (Trendlyne, Tijori, Screener, InsiderScreener) are mostly web/paid with limited or undocumented APIs, and NSE endpoints are cookie-gated and break. Budget for scraping fragility and possible paid data feeds.
- **The core "blind copying produces alpha" conclusion is medium-confidence and deliberately skeptical.** Evidence is mixed; the pro-cloning backtests are gross, survivorship-tilted, and assume disciplined manager selection plus multi-year holds. We treat positive evidence as conditional and use flows only as a conviction overlay — consistent with the honest balance of evidence.
- **Data-quality (misreporting) and survivorship-bias claims are flagged medium-confidence but directionally robust** — enough to justify never trusting a winner-list-only backtest.
- **All latencies are post-trade.** Nothing here closes the real-time gap from §1; no part of this design should ever assume it can.