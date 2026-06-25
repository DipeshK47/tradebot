# Trading Bot — Indian Market (NSE/BSE)

A systematic stock tracker + alerting system + automated trading bot for Indian markets, built around the **Dhan** broker API.

**Status:** Planning complete (2026-06-23). Pre-Phase-0.

## What this is
- A **two-brain** system: a deterministic fast engine that scans, trades, and enforces hard risk limits; and an LLM "slow brain" that reads news/sentiment and *advises only* (never trades, never loosens a limit).
- Validated the responsible way: **backtest → paper → live (small size)**.
- Controlled from a **web command-center dashboard** + **Telegram** (secure two-way control).
- Honest about the odds: this is disciplined edge-seeking with strict risk control, **not** a guaranteed-profit machine.

## Read these first
- [`MASTER_PLAN.md`](./MASTER_PLAN.md) — the full consolidated build plan.
- [`docs/research/`](./docs/research/) — the three fact-checked research reports this plan is built on:
  - `01-broker-sebi-strategy-architecture.md`
  - `02-brain-scanning-news-whatsapp.md`
  - `03-copytrade-disclosed-flows.md`

## Key decisions
- **Broker:** Dhan (broker-side Super Orders = stops survive a crash; auto-refreshable token).
- **Host:** Oracle Cloud Always-Free VPS (static IP, always-on, ₹0) — paid micro-VPS fallback.
- **Universe:** liquid set (~200 F&O / Nifty 500), not all listed stocks.
- **Compliance:** personal+family use only; static-IP whitelist; <10 orders/sec; never sell signals; never trade on non-public info.

## Hard safety rules
1. Every live position gets a **broker-side protective stop**.
2. Risk limits are **deterministic and fail-closed** — the LLM cannot override them.
3. "Arm live" defaults **OFF** on every restart; a global kill-switch flattens everything.
