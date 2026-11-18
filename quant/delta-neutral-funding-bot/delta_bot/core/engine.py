"""
TradingEngine v6 — simplified, reliable, observable.

FIXES vs previous versions:
  1. Funding rates are cached per exchange (no random flip between ticks)
  2. Edge calculation is inline and transparent (no hidden filters)
  3. Fee ratio check only activates after $20 accumulated funding
  4. Full logging of every decision
  5. Funding accrual and price PnL updated every tick
  6. FIX: closed positions removed from self.positions and stored in
     self._closed_positions so volume/metrics accumulate correctly
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
import structlog

from delta_bot.config.settings import Settings
from delta_bot.core.types import (
    DeltaNeutralPosition, ExchangeId, FundingSnapshot, Leg, MarketData,
    OpportunitySignal, PortfolioSnapshot, PositionStatus, Side,
    SkipEvent, SkipReason,
)
from delta_bot.alerts.telegram_alert import TelegramAlerter
from delta_bot.persistence.database import Database
from delta_bot.exchanges.base import BaseExchange
from delta_bot.exchanges.factory import build_exchanges

logger = structlog.get_logger(__name__)

FundingMap = dict[tuple[ExchangeId, str], FundingSnapshot]
MarketMap = dict[tuple[ExchangeId, str], MarketData]

SYMBOLS = ["BTC", "ETH", "SOL", "ARB", "DOGE", "WIF", "HYPE"]


class TradingEngine:
    def __init__(self, settings: Settings, db: Database, alerter: TelegramAlerter):
        self.s = settings
        self.db = db
        self.alerter = alerter
        self.exchanges: dict[ExchangeId, BaseExchange] = {}
        self.positions: dict[str, DeltaNeutralPosition] = {}
        self._tick = 0
        self._entries_timestamps: list[datetime] = []
        self._base_equity = 10_000.0
        self._peak_equity = 10_000.0
        self._ops_this_session = 0

        # FIX: track closed positions for correct metrics accumulation
        self._closed_positions: list[DeltaNeutralPosition] = []
        self._kill_switch_tripped = False

        # Init exchanges via factory (paper or live based on settings)
        self.exchanges = build_exchanges(settings)
        if not self.exchanges:
            raise RuntimeError("No exchanges built — check settings.")

    async def start(self):
        for eid, ex in self.exchanges.items():
            await ex.connect()
            logger.info("engine.exchange_connected", exchange=eid.value)
        # Restore prior state from DB so metrics survive restarts
        await self._restore_state()
        # In live mode, reconcile with the exchange to detect drift.
        if not self.s.paper_trading:
            await self._reconcile_with_exchange()

    async def _reconcile_with_exchange(self):
        """Compare DB-open positions against what each exchange reports.

        We do NOT auto-close drifted positions. We log + alert and let the
        operator decide. Goal: detect orphan legs after a crash.
        """
        try:
            for eid, ex in self.exchanges.items():
                live_positions = await ex.get_open_positions()
                logger.info("engine.reconcile",
                            exchange=eid.value,
                            live_open=len(live_positions),
                            details=[{
                                "symbol": p["symbol"],
                                "side": p["side"],
                                "size": p["size"],
                            } for p in live_positions])
                if live_positions:
                    await self.alerter.send(
                        f"[RECONCILE] {eid.value}: {len(live_positions)} open "
                        f"position(s) detected on exchange. "
                        f"Verify they match your strategy before continuing."
                    )
        except Exception as e:
            logger.warning("engine.reconcile_failed", error=str(e))

    async def _restore_state(self):
        """Reload open/closed positions from disk so metrics persist."""
        try:
            open_rows = await self.db.load_positions(status="open")
            closed_rows = await self.db.load_closed_positions(limit=10_000)
        except Exception as e:
            logger.warning("engine.restore_failed", error=str(e))
            return

        # We only need totals from closed positions; reconstruct minimal stubs.
        for row in closed_rows:
            try:
                stub = DeltaNeutralPosition()
                stub.id = row.get("id", stub.id)
                stub.status = PositionStatus.CLOSED
                stub.accumulated_funding = float(row.get("accumulated_funding") or 0.0)
                stub.fees_paid = float(row.get("fees_paid") or 0.0)
                # Re-create legs (entry-price only) so notional_usd works
                ll = row.get("long_leg") or {}
                sl = row.get("short_leg") or {}
                if ll:
                    stub.long_leg = Leg(
                        exchange=ExchangeId(ll["exchange"]),
                        symbol=ll["symbol"],
                        side=Side(ll["side"]),
                        size=float(ll["size"]),
                        entry_price=float(ll["entry_price"]),
                        current_price=float(ll.get("current_price") or ll["entry_price"]),
                    )
                if sl:
                    stub.short_leg = Leg(
                        exchange=ExchangeId(sl["exchange"]),
                        symbol=sl["symbol"],
                        side=Side(sl["side"]),
                        size=float(sl["size"]),
                        entry_price=float(sl["entry_price"]),
                        current_price=float(sl.get("current_price") or sl["entry_price"]),
                    )
                self._closed_positions.append(stub)
            except Exception as e:
                logger.warning("engine.restore_closed_skip", error=str(e))

        # Open positions: refuse to silently re-arm them. We log loudly
        # so the operator knows the bot was left holding live exposure.
        if open_rows:
            logger.warning("engine.found_open_positions_on_start",
                           count=len(open_rows),
                           note="These positions are present in the DB. "
                                "They will NOT be auto-managed by this run "
                                "to avoid double-hedging.")
            await self.alerter.send(
                f"[WARN] Found {len(open_rows)} open positions in DB on startup. "
                f"Manual intervention required."
            )

        if self._closed_positions:
            logger.info("engine.restored", closed=len(self._closed_positions))

    async def stop(self):
        logger.info("engine.stopping")
        for ex in self.exchanges.values():
            await ex.disconnect()

    # ──────────────────────────────────────────────────────
    async def tick(self):
        self._tick += 1
        now = datetime.now(timezone.utc)

        # 1 — Fetch all data
        funding: FundingMap = {}
        market: MarketMap = {}
        for eid, ex in self.exchanges.items():
            for sym in SYMBOLS:
                try:
                    funding[(eid, sym)] = await ex.fetch_funding_rate(sym)
                    market[(eid, sym)] = await ex.fetch_market_data(sym)
                except Exception:
                    pass

        # 2 — Compute portfolio snapshot
        snap = self._snapshot()

        # 3 — Kill switch (latched: once tripped, no new positions; existing
        #     ones are still managed/closed so we don't orphan exposure)
        if snap.drawdown_pct > self.s.risk.kill_switch_drawdown_pct:
            if not self._kill_switch_tripped:
                self._kill_switch_tripped = True
                logger.critical("engine.kill_switch", drawdown=snap.drawdown_pct)
                try:
                    await self.alerter.send(
                        f"[KILL SWITCH] Drawdown {snap.drawdown_pct:.2f}% > "
                        f"{self.s.risk.kill_switch_drawdown_pct}%. Halting new entries."
                    )
                except Exception:
                    pass

        # 4 — Heartbeat every 10 ticks
        if self._tick % 10 == 0:
            logger.info("engine.heartbeat", tick=self._tick,
                        equity=round(snap.total_equity_usd, 2),
                        positions=snap.open_positions,
                        funding=round(snap.accumulated_funding, 4),
                        fees=round(snap.total_fees_usd, 4),
                        net_pnl=round(snap.accumulated_funding - snap.total_fees_usd, 4),
                        ops_session=self._ops_this_session,
                        drawdown=round(snap.drawdown_pct, 3))

        # 5 — Update open positions (accrue funding + update prices)
        for pos in list(self.positions.values()):
            if pos.status != PositionStatus.OPEN:
                continue
            self._accrue_funding(pos, funding)
            self._update_prices(pos, market)
            await self.db.save_position(pos)

        # 6 — Close positions that lost edge
        for pos in list(self.positions.values()):
            if pos.status != PositionStatus.OPEN:
                continue
            close, reason = self._should_close(pos, funding)
            if close:
                await self._close_position(pos, reason)

        # 7 — Evaluate new opportunities (skip if kill switch is latched)
        if self._kill_switch_tripped:
            return

        can_open, skip_reason = self._can_open_now(now)
        if not can_open:
            return

        # Find best opportunity
        best = self._find_best_opportunity(funding, market)
        if not best:
            await self.db.log_skip(SkipEvent(reason=SkipReason.NO_OPPORTUNITY,
                                              details="No viable opportunity found"))
            return

        # Risk check
        ok, risk_msg = self._risk_check(best, snap)
        if not ok:
            await self.db.log_skip(SkipEvent(reason=SkipReason.RISK_HIGH, details=risk_msg))
            logger.info("engine.risk_blocked", reason=risk_msg)
            return

        # Execute
        await self._open_position(best, market)

    # ══════════════════════════════════════════════════════
    # SIGNAL GENERATION — transparent, no hidden filters
    # ══════════════════════════════════════════════════════

    def _find_best_opportunity(self, funding: FundingMap, market: MarketMap) -> Optional[OpportunitySignal]:
        """Find the best cross-exchange funding arbitrage."""
        best_signal = None
        best_edge = -999.0

        for sym in SYMBOLS:
            rates = {}
            for eid in self.exchanges:
                key = (eid, sym)
                if key in funding:
                    rates[eid] = funding[key]

            if len(rates) < 2:
                continue

            # Try all pairs
            eids = list(rates.keys())
            for i in range(len(eids)):
                for j in range(len(eids)):
                    if i == j:
                        continue
                    short_eid = eids[i]  # collect funding here
                    long_eid = eids[j]   # pay funding here

                    short_rate = rates[short_eid].annualised_bps
                    long_rate = rates[long_eid].annualised_bps

                    # Net funding spread (what we earn)
                    net_spread = short_rate - long_rate

                    if net_spread <= self.s.strategy.min_funding_rate_bps:
                        continue

                    # Project edge over holding period
                    per_period = net_spread / (365 * 3)
                    gross = per_period * self.s.strategy.holding_periods

                    # Fees: 4 legs total (open+close, both sides) at ~3 bps each
                    fees = 3.0 * 4
                    # Slippage
                    slippage = 2.0

                    edge = gross - fees - slippage

                    if edge > best_edge and edge > self.s.strategy.min_expected_edge_bps:
                        best_edge = edge
                        best_signal = OpportunitySignal(
                            symbol=sym,
                            long_exchange=long_eid,
                            short_exchange=short_eid,
                            expected_funding_bps=net_spread,
                            expected_edge_bps=edge,
                            suggested_size_usd=self.s.strategy.position_size_usd,
                        )

        if best_signal:
            logger.info("engine.signal_found", symbol=best_signal.symbol,
                        funding_bps=round(best_signal.expected_funding_bps, 2),
                        edge_bps=round(best_signal.expected_edge_bps, 2),
                        long_on=best_signal.long_exchange.value,
                        short_on=best_signal.short_exchange.value)
        return best_signal

    # ══════════════════════════════════════════════════════
    # OPEN / CLOSE
    # ══════════════════════════════════════════════════════

    async def _open_position(self, signal: OpportunitySignal, market: MarketMap):
        long_ex = self.exchanges[signal.long_exchange]
        short_ex = self.exchanges[signal.short_exchange]

        # Get prices
        long_md = market.get((signal.long_exchange, signal.symbol))
        short_md = market.get((signal.short_exchange, signal.symbol))
        if not long_md or not short_md:
            return
        if long_md.ask <= 0 or short_md.bid <= 0:
            logger.warning("engine.bad_prices", long_ask=long_md.ask, short_bid=short_md.bid)
            return

        notional = signal.suggested_size_usd * self.s.strategy.leverage
        long_size = notional / long_md.ask
        short_size = notional / short_md.bid

        # Place orders atomically: if the second leg fails, we MUST close
        # the first leg, otherwise we are left with naked directional exposure.
        long_order = None
        short_order = None
        try:
            long_order = await long_ex.place_order(signal.symbol, Side.LONG, long_size)
        except Exception as e:
            logger.error("engine.open_long_failed", error=str(e))
            return

        try:
            short_order = await short_ex.place_order(signal.symbol, Side.SHORT, short_size)
        except Exception as e:
            logger.error("engine.open_short_failed_rolling_back",
                         error=str(e), long_filled=True)
            # Roll back the long leg by selling it back
            try:
                await long_ex.place_order(signal.symbol, Side.SHORT, long_order.filled_size)
                logger.info("engine.rollback_ok")
            except Exception as e2:
                logger.critical("engine.rollback_failed",
                                error=str(e2),
                                exchange=signal.long_exchange.value,
                                symbol=signal.symbol,
                                size=long_order.filled_size)
                await self.alerter.send(
                    f"[CRITICAL] Could not roll back long leg of {signal.symbol} on "
                    f"{signal.long_exchange.value}. Manual intervention needed."
                )
            return

        pos = DeltaNeutralPosition(
            long_leg=Leg(exchange=signal.long_exchange, symbol=signal.symbol,
                         side=Side.LONG, size=long_size,
                         entry_price=long_order.filled_price,
                         current_price=long_order.filled_price),
            short_leg=Leg(exchange=signal.short_exchange, symbol=signal.symbol,
                          side=Side.SHORT, size=short_size,
                          entry_price=short_order.filled_price,
                          current_price=short_order.filled_price),
            fees_paid=long_order.fee + short_order.fee,
        )

        self.positions[pos.id] = pos
        self._entries_timestamps.append(datetime.now(timezone.utc))
        self._ops_this_session += 1
        await self.db.save_position(pos)

        logger.info("engine.OPENED", id=pos.id, symbol=signal.symbol,
                     leverage=self.s.strategy.leverage,
                     notional=round(notional, 0),
                     edge_bps=round(signal.expected_edge_bps, 2),
                     funding_bps=round(signal.expected_funding_bps, 2),
                     fees=round(pos.fees_paid, 4))

        await self.alerter.send(
            f"📈 OPEN: {signal.symbol} | "
            f"edge={signal.expected_edge_bps:.1f}bps | "
            f"funding={signal.expected_funding_bps:.1f}bps | "
            f"${notional:,.0f} notional ({self.s.strategy.leverage}x)")

    async def _close_position(self, pos: DeltaNeutralPosition, reason: str):
        sym = pos.long_leg.symbol if pos.long_leg else "?"

        # Close both legs. If one fails we DO NOT mark the position closed —
        # we keep retrying on subsequent ticks rather than orphaning a leg.
        close_fees = 0.0
        long_closed = pos.long_leg is None
        short_closed = pos.short_leg is None

        if pos.long_leg and not long_closed:
            try:
                ex = self.exchanges[pos.long_leg.exchange]
                o = await ex.place_order(pos.long_leg.symbol, Side.SHORT, pos.long_leg.size)
                close_fees += o.fee
                long_closed = True
            except Exception as e:
                logger.error("engine.close_long_failed", error=str(e), id=pos.id)

        if pos.short_leg and not short_closed:
            try:
                ex = self.exchanges[pos.short_leg.exchange]
                o = await ex.place_order(pos.short_leg.symbol, Side.LONG, pos.short_leg.size)
                close_fees += o.fee
                short_closed = True
            except Exception as e:
                logger.error("engine.close_short_failed", error=str(e), id=pos.id)

        pos.fees_paid += close_fees

        if not (long_closed and short_closed):
            # Persist the partial-close fees but keep status OPEN so we retry next tick.
            await self.db.save_position(pos)
            await self.alerter.send(
                f"[WARN] Partial close on {sym}: long_closed={long_closed}, "
                f"short_closed={short_closed}. Will retry next tick."
            )
            return

        pos.status = PositionStatus.CLOSED
        pos.closed_at = datetime.now(timezone.utc)
        await self.db.save_position(pos)

        # FIX: move to closed list and remove from active positions
        self._closed_positions.append(pos)
        self.positions.pop(pos.id, None)

        logger.info("engine.CLOSED", id=pos.id, symbol=sym, reason=reason,
                     funding=round(pos.accumulated_funding, 4),
                     price_pnl=round(pos.price_pnl, 4),
                     fees=round(pos.fees_paid, 4),
                     total_pnl=round(pos.total_pnl, 4))

        await self.alerter.send(
            f"📉 CLOSE: {sym} | "
            f"funding=${pos.accumulated_funding:.4f} | "
            f"price_pnl=${pos.price_pnl:.4f} | "
            f"fees=${pos.fees_paid:.4f} | "
            f"net=${pos.total_pnl:.4f} | "
            f"reason: {reason}")

    # ══════════════════════════════════════════════════════
    # FUNDING ACCRUAL + PRICE UPDATE
    # ══════════════════════════════════════════════════════

    def _accrue_funding(self, pos: DeltaNeutralPosition, funding: FundingMap):
        if not pos.short_leg or not pos.long_leg:
            return
        sk = (pos.short_leg.exchange, pos.short_leg.symbol)
        lk = (pos.long_leg.exchange, pos.long_leg.symbol)
        ss = funding.get(sk)
        ls = funding.get(lk)
        if not ss or not ls:
            return
        tpp = (8 * 3600) / self.s.main_loop_interval_seconds
        net_rate = ss.rate - ls.rate
        income = net_rate * pos.notional_usd / tpp
        pos.accumulated_funding += income

    def _update_prices(self, pos: DeltaNeutralPosition, market: MarketMap):
        if pos.long_leg:
            md = market.get((pos.long_leg.exchange, pos.long_leg.symbol))
            if md:
                pos.long_leg.current_price = md.mid
                pos.long_leg.unrealised_pnl = (md.mid - pos.long_leg.entry_price) * pos.long_leg.size
        if pos.short_leg:
            md = market.get((pos.short_leg.exchange, pos.short_leg.symbol))
            if md:
                pos.short_leg.current_price = md.mid
                pos.short_leg.unrealised_pnl = (pos.short_leg.entry_price - md.mid) * pos.short_leg.size

    # ══════════════════════════════════════════════════════
    # CLOSE LOGIC
    # ══════════════════════════════════════════════════════

    def _should_close(self, pos: DeltaNeutralPosition, funding: FundingMap) -> tuple[bool, str]:
        if not pos.short_leg or not pos.long_leg:
            return False, ""

        # 1. Short leg funding negative (we're paying)
        sk = (pos.short_leg.exchange, pos.short_leg.symbol)
        lk = (pos.long_leg.exchange, pos.long_leg.symbol)
        ss = funding.get(sk)
        ls = funding.get(lk)

        if ss and ls:
            net_rate = ss.rate - ls.rate
            if net_rate < 0:
                return True, f"Funding flipped negative: net_rate={net_rate:.8f}"

            # Spread collapsed
            spread_bps = (ss.annualised_bps - ls.annualised_bps)
            if spread_bps < self.s.strategy.min_funding_rate_bps * 0.3:
                return True, f"Spread collapsed to {spread_bps:.2f} bps"

        # 2. Emergency: PnL too negative
        if pos.total_pnl < -pos.notional_usd * 0.05:
            return True, f"Emergency: PnL {pos.total_pnl:.2f}"

        return False, ""

    # ══════════════════════════════════════════════════════
    # FREQUENCY + RISK
    # ══════════════════════════════════════════════════════

    def _can_open_now(self, now: datetime) -> tuple[bool, str]:
        from datetime import timedelta

        # Min interval between entries
        if self._entries_timestamps:
            last = self._entries_timestamps[-1]
            elapsed_min = (now - last).total_seconds() / 60
            if elapsed_min < self.s.frequency.min_minutes_between_entries:
                return False, "too_soon"

        # Hourly cap
        one_hour_ago = now - timedelta(hours=1)
        recent_h = sum(1 for t in self._entries_timestamps if t >= one_hour_ago)
        if recent_h >= self.s.frequency.target_operations_per_hour:
            return False, "hourly_limit"

        # Daily caps
        one_day_ago = now - timedelta(hours=24)
        recent_d = sum(1 for t in self._entries_timestamps if t >= one_day_ago)
        if self.s.frequency.target_operations_per_day is not None and \
                recent_d >= self.s.frequency.target_operations_per_day:
            return False, "daily_target"
        if recent_d >= self.s.frequency.max_total_operations_per_day:
            return False, "daily_limit"

        # Optional whitelist of allowed UTC hours
        if self.s.frequency.allowed_hours_utc is not None and \
                now.hour not in self.s.frequency.allowed_hours_utc:
            return False, "hour_not_allowed"

        # Prune old entries
        self._entries_timestamps = [t for t in self._entries_timestamps if t >= one_day_ago]

        return True, ""

    def _risk_check(self, signal: OpportunitySignal, snap: PortfolioSnapshot) -> tuple[bool, str]:
        # Exposure
        new_notional = signal.suggested_size_usd * self.s.strategy.leverage
        if snap.total_exposure_usd + new_notional > self.s.risk.max_total_exposure_usd:
            return False, f"Exposure limit: {snap.total_exposure_usd + new_notional}"

        # Drawdown
        if snap.drawdown_pct > self.s.risk.max_portfolio_drawdown_pct:
            return False, f"Drawdown {snap.drawdown_pct:.2f}%"

        # Fee ratio — only after significant funding
        if snap.accumulated_funding > 20.0:
            ratio = snap.total_fees_usd / snap.accumulated_funding
            if ratio > 0.8:
                return False, f"Fee ratio {ratio:.1%}"

        return True, ""

    # ══════════════════════════════════════════════════════
    # PORTFOLIO SNAPSHOT
    # ══════════════════════════════════════════════════════

    def _snapshot(self) -> PortfolioSnapshot:
        open_pos = [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
        # FIX: include closed positions for correct fee/funding totals
        all_pos = list(self.positions.values()) + self._closed_positions

        exposure = sum(p.notional_usd for p in open_pos)
        funding = sum(p.accumulated_funding for p in all_pos)
        fees = sum(p.fees_paid for p in all_pos)
        price_pnl = sum(p.price_pnl for p in open_pos)

        equity = self._base_equity + funding + price_pnl - fees
        if equity > self._peak_equity:
            self._peak_equity = equity
        dd = (self._peak_equity - equity) / self._peak_equity * 100 if self._peak_equity > 0 else 0

        return PortfolioSnapshot(
            total_equity_usd=equity, total_exposure_usd=exposure,
            open_positions=len(open_pos), unrealised_pnl=price_pnl,
            accumulated_funding=funding, total_fees_usd=fees,
            total_volume_usd=sum(p.notional_usd * 2 for p in all_pos),
            drawdown_pct=max(dd, 0),
        )
