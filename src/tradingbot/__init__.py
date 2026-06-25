"""tradingbot — Indian-market stock tracker, alerting & automated trading bot.

Architecture (see ../../MASTER_PLAN.md):
  - FAST engine (deterministic): scans, trades, and enforces hard risk limits.
  - SLOW brain (LLM): advises only — never trades, never loosens a limit.

The safety-critical core (risk, models, strategy logic) is pure-stdlib so it runs
and is unit-tested without any third-party deps or live broker credentials.
"""

__version__ = "0.0.1"
