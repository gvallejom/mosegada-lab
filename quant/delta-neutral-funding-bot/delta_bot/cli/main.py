"""Operational CLI for the bot.

Usage:
    python -m delta_bot.cli.main status
    python -m delta_bot.cli.main positions
    python -m delta_bot.cli.main balances
    python -m delta_bot.cli.main skips [--limit 20]
    python -m delta_bot.cli.main close <position_id>
    python -m delta_bot.cli.main close-all --confirm
    python -m delta_bot.cli.main wallet

These commands DO NOT touch a running engine — they read DB state and/or
make their own connections to exchanges.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys

from delta_bot.config.settings import load_settings
from delta_bot.persistence.database import Database
from delta_bot.exchanges.factory import build_exchanges
from delta_bot.core.types import ExchangeId, Side


async def cmd_status(args):
    s = load_settings()
    db = Database(db_path=s.db_path)
    await db.initialize()
    open_pos = await db.load_positions(status="open")
    closed = await db.load_closed_positions(limit=10_000)
    skips = await db.get_skip_events(limit=5)
    await db.close()

    funding_total = sum(float(p.get("accumulated_funding") or 0) for p in closed)
    fees_total = sum(float(p.get("fees_paid") or 0) for p in closed)
    print(json.dumps({
        "paper_trading": s.paper_trading,
        "open_positions": len(open_pos),
        "closed_positions": len(closed),
        "lifetime_funding_usd": round(funding_total, 4),
        "lifetime_fees_usd": round(fees_total, 4),
        "lifetime_net_usd": round(funding_total - fees_total, 4),
        "recent_skips": skips,
    }, indent=2))


async def cmd_positions(args):
    s = load_settings()
    db = Database(db_path=s.db_path)
    await db.initialize()
    rows = await db.load_positions(status="open")
    await db.close()
    if not rows:
        print("No open positions.")
        return
    for p in rows:
        ll = p.get("long_leg") or {}
        sl = p.get("short_leg") or {}
        print(f"{p.get('id'):>14}  long={ll.get('exchange')}/{ll.get('symbol')}@{ll.get('entry_price')}  "
              f"short={sl.get('exchange')}/{sl.get('symbol')}@{sl.get('entry_price')}  "
              f"funding={p.get('accumulated_funding')}  fees={p.get('fees_paid')}")


async def cmd_balances(args):
    s = load_settings()
    exchanges = build_exchanges(s)
    for eid, ex in exchanges.items():
        try:
            await ex.connect()
            bal = await ex.get_balance()
            print(f"{eid.value:14s}  equity={bal.get('total_equity', 0):.2f}  "
                  f"available={bal.get('available', 0):.2f}")
        except Exception as e:
            print(f"{eid.value:14s}  ERROR: {e}")
        finally:
            try:
                await ex.disconnect()
            except Exception:
                pass


async def cmd_skips(args):
    s = load_settings()
    db = Database(db_path=s.db_path)
    await db.initialize()
    rows = await db.get_skip_events(limit=args.limit)
    await db.close()
    for r in rows:
        print(f"{r['timestamp']}  {r['reason']:25s}  {r['details']}")


async def cmd_close(args):
    """Close a single position by id, by hitting both legs reduce-only."""
    s = load_settings()
    db = Database(db_path=s.db_path)
    await db.initialize()
    rows = await db.load_positions(status="open")
    target = next((p for p in rows if p.get("id") == args.position_id), None)
    if not target:
        print(f"Position {args.position_id} not found or already closed.")
        await db.close()
        sys.exit(1)

    exchanges = build_exchanges(s)
    for ex in exchanges.values():
        await ex.connect()

    try:
        ll = target.get("long_leg") or {}
        sl = target.get("short_leg") or {}
        if ll:
            ex = exchanges[ExchangeId(ll["exchange"])]
            await ex.place_order(ll["symbol"], Side.SHORT, float(ll["size"]), reduce_only=True)
            print(f"Closed long leg on {ll['exchange']}")
        if sl:
            ex = exchanges[ExchangeId(sl["exchange"])]
            await ex.place_order(sl["symbol"], Side.LONG, float(sl["size"]), reduce_only=True)
            print(f"Closed short leg on {sl['exchange']}")
    finally:
        for ex in exchanges.values():
            try:
                await ex.disconnect()
            except Exception:
                pass
        await db.close()


async def cmd_close_all(args):
    if not args.confirm:
        print("Refusing to close all without --confirm")
        sys.exit(1)
    s = load_settings()
    db = Database(db_path=s.db_path)
    await db.initialize()
    rows = await db.load_positions(status="open")
    await db.close()
    for p in rows:
        ns = argparse.Namespace(position_id=p["id"])
        await cmd_close(ns)


async def cmd_preflight(args):
    """No-trades validation. Verify everything is wired before risking funds.

    Checks (in order):
        1. Settings load + sanity.
        2. Database initializes.
        3. Each exchange connects.
        4. Each exchange returns a balance.
        5. Each exchange returns funding for a sample symbol.
        6. Wallet addresses derive correctly from the configured private keys.
        7. (Hyperliquid only) the trading wallet address matches the signer
           OR is registered as an API wallet.

    Exits non-zero on any failure.
    """
    import sys
    failures: list[str] = []
    warnings: list[str] = []

    # 1. settings
    try:
        s = load_settings()
        print(f"[OK] settings loaded (paper_trading={s.paper_trading})")
    except Exception as e:
        print(f"[FAIL] settings: {e}")
        sys.exit(1)

    # 2. database
    try:
        db = Database(db_path=s.db_path)
        await db.initialize()
        await db.close()
        print(f"[OK] database init at {s.db_path}")
    except Exception as e:
        failures.append(f"database: {e}")
        print(f"[FAIL] database: {e}")

    # 3-5. exchanges
    try:
        exchanges = build_exchanges(s)
    except Exception as e:
        print(f"[FAIL] factory: {e}")
        sys.exit(1)

    for eid, ex in exchanges.items():
        try:
            await ex.connect()
            print(f"[OK] {eid.value} connect")
        except Exception as e:
            failures.append(f"{eid.value} connect: {e}")
            print(f"[FAIL] {eid.value} connect: {e}")
            continue

        try:
            bal = await ex.get_balance()
            print(f"[OK] {eid.value} balance: equity={bal.get('total_equity', 0):.4f} "
                  f"available={bal.get('available', 0):.4f}")
            if not s.paper_trading and bal.get("total_equity", 0) <= 0:
                warnings.append(f"{eid.value} balance is zero — deposit before trading")
        except Exception as e:
            failures.append(f"{eid.value} balance: {e}")
            print(f"[FAIL] {eid.value} balance: {e}")

        try:
            fr = await ex.fetch_funding_rate("BTC")
            print(f"[OK] {eid.value} funding(BTC): rate={fr.rate:.6f} "
                  f"ann_bps={fr.annualised_bps:.1f}")
        except Exception as e:
            failures.append(f"{eid.value} funding: {e}")
            print(f"[FAIL] {eid.value} funding: {e}")

        try:
            md = await ex.fetch_market_data("BTC")
            spread_bps = ((md.ask - md.bid) / md.mid * 10_000) if md.mid else 0
            print(f"[OK] {eid.value} market(BTC): mid={md.mid:.2f} spread={spread_bps:.2f} bps")
        except Exception as e:
            failures.append(f"{eid.value} market: {e}")
            print(f"[FAIL] {eid.value} market: {e}")

        try:
            opens = await ex.get_open_positions()
            if opens:
                warnings.append(
                    f"{eid.value} reports {len(opens)} OPEN position(s) "
                    f"already on the exchange — verify before starting the bot"
                )
                for p in opens:
                    print(f"  EXISTING: {p['symbol']} {p['side']} size={p['size']} "
                          f"entry={p.get('entry_price')}")
            else:
                print(f"[OK] {eid.value} open positions: 0")
        except Exception as e:
            warnings.append(f"{eid.value} get_open_positions: {e}")

        try:
            await ex.disconnect()
        except Exception:
            pass

    # 6-7. wallets
    if s.evm_private_key:
        try:
            from delta_bot.wallets.evm import EvmWallet
            w = EvmWallet(s.evm_private_key, s.evm_rpc_url, s.evm_chain_id)
            addr = w.address()
            print(f"[OK] EVM wallet derives to {addr}")
            if s.hyperliquid_wallet_address:
                if addr.lower() != s.hyperliquid_wallet_address.lower():
                    warnings.append(
                        f"EVM signer ({addr}) != HYPERLIQUID_WALLET_ADDRESS "
                        f"({s.hyperliquid_wallet_address}). This is OK ONLY if "
                        f"the signer is registered as an API wallet on Hyperliquid."
                    )
                else:
                    print("[OK] EVM signer == Hyperliquid trading address")
        except Exception as e:
            failures.append(f"EVM wallet derive: {e}")
            print(f"[FAIL] EVM wallet derive: {e}")
    else:
        warnings.append("EVM_PRIVATE_KEY not set — required for live Hyperliquid")

    if s.solana_private_key:
        try:
            from delta_bot.wallets.solana import SolanaWallet
            w = SolanaWallet(s.solana_private_key, s.solana_rpc_url)
            print(f"[OK] Solana wallet derives to {w.address()}")
        except Exception as e:
            warnings.append(f"Solana wallet derive: {e}")

    # Telegram sanity (does not actually send a message in preflight to avoid
    # spamming the chat; just checks token presence).
    if s.telegram_bot_token and s.telegram_chat_id:
        print("[OK] Telegram credentials present")
    else:
        warnings.append("Telegram not configured — alerts will only appear in logs")

    # ── summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        print("PREFLIGHT FAILED. Do not start the bot.")
        sys.exit(2)
    if warnings:
        print("PREFLIGHT PASSED with warnings. Review them before going live.")
    else:
        print("PREFLIGHT PASSED.")


async def cmd_wallet(args):
    s = load_settings()
    if s.evm_private_key:
        from delta_bot.wallets.evm import EvmWallet
        try:
            w = EvmWallet(s.evm_private_key, s.evm_rpc_url, s.evm_chain_id)
            print(f"EVM address:  {w.address()}")
            try:
                bal = w.native_balance()
                print(f"EVM native balance: {bal:.6f}")
            except Exception as e:
                print(f"EVM balance fetch failed: {e}")
        except Exception as e:
            print(f"EVM wallet error: {e}")
    else:
        print("EVM_PRIVATE_KEY not set.")

    if s.solana_private_key:
        from delta_bot.wallets.solana import SolanaWallet
        try:
            w = SolanaWallet(s.solana_private_key, s.solana_rpc_url)
            print(f"SOL address:  {w.address()}")
            try:
                bal = w.sol_balance()
                print(f"SOL balance: {bal:.6f}")
            except Exception as e:
                print(f"SOL balance fetch failed: {e}")
        except Exception as e:
            print(f"Solana wallet error: {e}")
    else:
        print("SOLANA_PRIVATE_KEY not set.")


def main():
    p = argparse.ArgumentParser(prog="delta-bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("positions")
    sub.add_parser("balances")
    sub.add_parser("preflight")
    sk = sub.add_parser("skips"); sk.add_argument("--limit", type=int, default=20)
    cl = sub.add_parser("close"); cl.add_argument("position_id")
    ca = sub.add_parser("close-all"); ca.add_argument("--confirm", action="store_true")
    sub.add_parser("wallet")
    args = p.parse_args()

    coros = {
        "status": cmd_status, "positions": cmd_positions,
        "balances": cmd_balances, "skips": cmd_skips,
        "close": cmd_close, "close-all": cmd_close_all,
        "wallet": cmd_wallet, "preflight": cmd_preflight,
    }
    asyncio.run(coros[args.cmd](args))


if __name__ == "__main__":
    main()
