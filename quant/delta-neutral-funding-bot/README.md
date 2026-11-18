# Delta-Neutral Funding Bot

> ⚠️ Runs in **paper trading** mode by default (simulated exchanges, no keys, no real money). Educational / portfolio project — not financial advice.

Cross-exchange delta-neutral funding-rate arbitrage bot. Goes long on the
exchange where funding is cheapest and short on the exchange where funding
is highest, collecting the spread while keeping net price exposure ~0.

Currently supports **Hyperliquid** and **Aster** perpetual futures.

---

## Quick start

```bash
# 1. install
python -m venv .venv
. .venv/Scripts/activate          # Windows
# . .venv/bin/activate            # macOS/Linux
pip install -r requirements.txt

# 2. configure
cp .env.example .env
# edit .env — at minimum, leave PAPER_TRADING=true for the first run

# 3. run paper (no keys needed)
python -m delta_bot.main
```

You should see ticks every 20s, position OPEN/CLOSE events, and a heartbeat
every 10 ticks with equity / funding / fees.

For faster paper runs, add to `.env`:

```
MAIN_LOOP_INTERVAL_SECONDS=5
MIN_MINUTES_BETWEEN_ENTRIES=1
TARGET_OPERATIONS_PER_HOUR=30
```

`python resumen.py` prints a summary of every position stored in the local
SQLite database (volume, fees, funding, net PnL).

---

## Going live

Live trading is disabled until **all** of the following are true:

1. `.env` set with `PAPER_TRADING=false`.
2. Hyperliquid: `EVM_PRIVATE_KEY` (used to sign) + `HYPERLIQUID_WALLET_ADDRESS`.
   For first-time setup, register the API wallet on the Hyperliquid UI so it
   can place orders for your master account.
3. Aster: `ASTER_API_KEY` + `ASTER_API_SECRET` from the Aster dashboard.
4. **Run on testnet first** for at least 24h with `HYPERLIQUID_TESTNET=true`
   and `ASTER_TESTNET=true`. Verify the bot opens, accrues funding, and closes
   positions cleanly. Verify reconciliation works after a forced restart.
5. Calibrate the strategy parameters (`min_funding_rate_bps`,
   `min_expected_edge_bps`, `position_size_usd`, `leverage`) for the actual
   fee tiers you see live. The defaults are conservative paper values.
6. Switch testnet flags to `false` and start with a small `position_size_usd`.

If any of those fail, **stop and investigate** before adding real funds.

---

## Operational CLI

While the bot is running (or stopped), you can query state without touching
the engine:

```bash
python -m delta_bot.cli.main status         # equity, lifetime PnL, recent skips
python -m delta_bot.cli.main positions      # open positions in DB
python -m delta_bot.cli.main balances       # exchange-side balances (live calls)
python -m delta_bot.cli.main wallet         # EVM/SOL addresses + native balance
python -m delta_bot.cli.main skips --limit 50

# manually close a position by id (reduce-only on both legs)
python -m delta_bot.cli.main close <position_id>

# nuke option (closes every open position)
python -m delta_bot.cli.main close-all --confirm
```

---

## Safety features built in

* **Atomic open**: if the second leg fails, the first is rolled back. No
  naked exposure can survive a partial fill.
* **Tolerant close**: if one leg fails to close, the position stays OPEN and
  the bot retries next tick — never marks closed with a leg dangling.
* **Latched kill switch** at `kill_switch_drawdown_pct` (default 15%): once
  tripped, no new entries; existing positions still managed.
* **State recovery**: closed positions reload from SQLite on restart so PnL
  metrics survive crashes.
* **Reconciliation**: on live-mode startup, the bot queries each exchange
  for open positions and alerts if anything unexpected is found.
* **Per-day caps** + per-hour caps + min-minutes-between-entries.
* **Graceful shutdown** on SIGINT/SIGTERM — finishes the current tick, closes
  DB and exchange connections.
* **Read-only wallet helpers** — the bot never holds withdraw permission. To
  move collateral cross-chain, the operator does it from a wallet UI.

---

## Architecture

```
delta_bot/
├── main.py                 # entrypoint + main loop + signal handling
├── cli/main.py             # operational commands
├── config/settings.py      # pydantic-settings, validators
├── core/
│   ├── engine.py           # tick loop, signals, risk, rollback
│   └── types.py            # domain types (Position, Leg, etc.)
├── exchanges/
│   ├── base.py             # BaseExchange ABC + OrderResult
│   ├── factory.py          # paper vs live
│   ├── hyperliquid_client.py
│   └── aster_client.py
├── simulation/
│   └── paper_trading.py    # implements BaseExchange for testing
├── persistence/database.py # async SQLite
├── alerts/telegram_alert.py
└── wallets/
    ├── evm.py              # eth-account + web3 (read-only)
    └── solana.py           # solders (read-only)
```

The engine is exchange-agnostic: it talks to anything that implements
`BaseExchange`. Adding a new exchange is roughly: subclass `BaseExchange`,
implement the 8 methods, register in `factory.py`.

---

## Known limitations / next steps

These are NOT in scope for this build but are obvious next iterations:

* **Backtesting** against historical funding data before going live.
* **Maker orders / partial-fill retry**. Today everything is taker.
* **Auto delta rebalance** when `rebalance_delta_threshold` is exceeded.
  (Setting exists but is not yet enforced — positions are abandoned to drift
  and emergency-closed on 5% PnL loss.)
* **Cross-margin transfers** between Hyperliquid and Aster. Today the
  operator manages collateral manually.
* **HTTP health endpoint / dashboard**. Today everything is logs + Telegram.
* **Rate-limit-aware HTTP client** for Aster. Currently we trust the default
  weight budget; under heavy use you may need backoff per the API's 429s.

---

## Caveats / `# VERIFY` markers

Search the codebase for `# VERIFY` — these are spots where the implementation
is based on the public docs but has not been tested against the live API in
this build. Most live in `aster_client.py` (endpoint paths, fee tier).
**Run on testnet first** to confirm each one.

---

## License

MIT
