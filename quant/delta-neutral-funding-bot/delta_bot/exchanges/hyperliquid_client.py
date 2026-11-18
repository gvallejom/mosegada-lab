"""Hyperliquid live exchange client.

Uses the official `hyperliquid-python-sdk` (sync). All blocking calls are
wrapped in `asyncio.to_thread` so the event loop never stalls.

# VERIFY before going live:
#   * The wallet you sign with must own the account_address you trade on.
#   * Run on testnet first (HYPERLIQUID_TESTNET=true) until reconciliation
#     and a few open/close cycles complete cleanly.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from delta_bot.core.types import (
    ExchangeId, FundingSnapshot, MarketData, OrderStatus, Side,
)
from delta_bot.exchanges.base import BaseExchange, OrderResult

logger = structlog.get_logger(__name__)

# Default slippage tolerance for market orders (10 bps)
DEFAULT_SLIPPAGE = 0.001


class HyperliquidExchange(BaseExchange):
    exchange_id: ExchangeId = ExchangeId.HYPERLIQUID

    def __init__(
        self,
        private_key: str,
        wallet_address: str,
        testnet: bool = True,
        default_slippage: float = DEFAULT_SLIPPAGE,
    ) -> None:
        if not private_key:
            raise ValueError("HYPERLIQUID: private_key required")
        if not wallet_address:
            raise ValueError("HYPERLIQUID: wallet_address required")
        self._private_key = private_key
        self._wallet_address = wallet_address
        self._testnet = testnet
        self._default_slippage = default_slippage
        self._connected = False
        self._info = None
        self._exchange = None
        self._meta_cache: dict = {}

    async def connect(self) -> None:
        # Lazy-import so the rest of the bot still imports without the SDK
        try:
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants
            from eth_account import Account
        except ImportError as e:
            raise RuntimeError(
                "Hyperliquid client requires `hyperliquid-python-sdk` and "
                "`eth-account`. Run: pip install hyperliquid-python-sdk eth-account"
            ) from e

        base_url = (
            constants.TESTNET_API_URL if self._testnet else constants.MAINNET_API_URL
        )
        wallet = Account.from_key(self._private_key)

        # SDK is sync — push construction to a thread.
        def _build():
            info = Info(base_url, skip_ws=True)
            exch = Exchange(wallet, base_url, account_address=self._wallet_address)
            meta = info.meta()
            return info, exch, meta

        self._info, self._exchange, self._meta_cache = await asyncio.to_thread(_build)
        self._connected = True
        logger.info("hyperliquid.connected",
                    testnet=self._testnet,
                    address=self._wallet_address[:8] + "...")

    async def disconnect(self) -> None:
        self._connected = False
        self._info = None
        self._exchange = None

    async def is_connected(self) -> bool:
        return self._connected

    # ── helpers ────────────────────────────────────────────────────────────
    def _coin_for(self, symbol: str) -> str:
        # Hyperliquid uses bare names like "BTC", "ETH", "HYPE"
        return symbol.upper()

    def _sz_decimals(self, symbol: str) -> int:
        for asset in (self._meta_cache or {}).get("universe", []):
            if asset.get("name", "").upper() == symbol.upper():
                return int(asset.get("szDecimals", 4))
        return 4

    # ── market data ────────────────────────────────────────────────────────
    async def fetch_funding_rate(self, symbol: str) -> FundingSnapshot:
        if not self._info:
            raise RuntimeError("Not connected")
        coin = self._coin_for(symbol)

        def _fetch():
            ctxs = self._info.meta_and_asset_ctxs()
            # Returns [meta, [asset_ctx, ...]]
            universe = ctxs[0].get("universe", [])
            asset_ctxs = ctxs[1]
            for i, asset in enumerate(universe):
                if asset.get("name", "").upper() == coin:
                    ctx = asset_ctxs[i] if i < len(asset_ctxs) else {}
                    return float(ctx.get("funding", 0.0))
            raise KeyError(f"Symbol {coin} not found on Hyperliquid")

        # Hyperliquid funding is hourly. To match our internal "per 8h period"
        # convention used by paper trading, we multiply by 8 here.
        hourly = await asyncio.to_thread(_fetch)
        rate_per_period = hourly * 8.0
        ann_bps = rate_per_period * 3 * 365 * 10_000
        return FundingSnapshot(
            exchange=self.exchange_id, symbol=symbol,
            rate=rate_per_period, annualised_bps=ann_bps,
        )

    async def fetch_market_data(self, symbol: str) -> MarketData:
        if not self._info:
            raise RuntimeError("Not connected")
        coin = self._coin_for(symbol)

        def _fetch():
            book = self._info.l2_snapshot(coin)
            mids = self._info.all_mids()
            mid = float(mids.get(coin, 0.0))
            levels = book.get("levels", [[], []])
            bid = float(levels[0][0]["px"]) if levels and levels[0] else mid
            ask = float(levels[1][0]["px"]) if levels and levels[1] else mid
            return bid, ask, mid

        bid, ask, mid = await asyncio.to_thread(_fetch)
        return MarketData(
            exchange=self.exchange_id, symbol=symbol,
            bid=bid, ask=ask, mid=mid or (bid + ask) / 2,
            volume_24h_usd=0.0,  # not pulled here to keep latency low
        )

    async def fetch_tradeable_symbols(self) -> list[str]:
        if not self._meta_cache:
            return []
        return [a.get("name") for a in self._meta_cache.get("universe", []) if a.get("name")]

    # ── trading ────────────────────────────────────────────────────────────
    async def place_order(
        self,
        symbol: str,
        side: Side,
        size: float,
        reduce_only: bool = False,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        if not self._exchange:
            raise RuntimeError("Not connected")
        coin = self._coin_for(symbol)
        is_buy = side == Side.LONG
        decimals = self._sz_decimals(coin)
        size = round(size, decimals)
        if size <= 0:
            raise ValueError(f"Size after rounding is non-positive: {size}")

        def _send():
            if limit_price is not None:
                # GTC limit order
                return self._exchange.order(
                    coin, is_buy, size, limit_price,
                    {"limit": {"tif": "Gtc"}}, reduce_only=reduce_only,
                )
            return self._exchange.market_open(
                coin, is_buy, size, None, self._default_slippage,
            ) if not reduce_only else self._exchange.market_close(coin, size)

        resp = await asyncio.to_thread(_send)
        return self._parse_order_response(resp, size)

    def _parse_order_response(self, resp: dict, requested_size: float) -> OrderResult:
        # Hyperliquid response shape:
        # {"status":"ok","response":{"type":"order","data":{"statuses":[{"filled":{"px":"...","sz":"...","oid":N}}]}}}
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            raise RuntimeError(f"Hyperliquid order rejected: {resp}")
        statuses = (resp.get("response", {}).get("data", {}).get("statuses") or [])
        if not statuses:
            raise RuntimeError(f"Hyperliquid order: no statuses in response: {resp}")
        st = statuses[0]
        if "filled" in st:
            f = st["filled"]
            px = float(f.get("avgPx", f.get("px", 0)))
            sz = float(f.get("totalSz", f.get("sz", requested_size)))
            oid = str(f.get("oid", ""))
            # Hyperliquid fee is taker ~3.5 bps by default; report a conservative estimate
            fee = sz * px * 3.5 / 10_000
            return OrderResult(OrderStatus.FILLED, px, sz, fee, oid)
        if "resting" in st:
            # Only happens with limit orders; treat as not filled.
            raise RuntimeError(f"Hyperliquid order resting (not filled): {st}")
        if "error" in st:
            raise RuntimeError(f"Hyperliquid order error: {st['error']}")
        raise RuntimeError(f"Unexpected Hyperliquid status: {st}")

    # ── account ────────────────────────────────────────────────────────────
    async def get_balance(self) -> dict[str, float]:
        if not self._info:
            raise RuntimeError("Not connected")

        def _fetch():
            return self._info.user_state(self._wallet_address)

        state = await asyncio.to_thread(_fetch)
        margin = state.get("marginSummary", {})
        equity = float(margin.get("accountValue", 0.0))
        available = float(margin.get("totalRawUsd", margin.get("accountValue", 0.0)))
        return {"total_equity": equity, "available": available}

    async def get_open_positions(self) -> list[dict]:
        if not self._info:
            raise RuntimeError("Not connected")

        def _fetch():
            return self._info.user_state(self._wallet_address)

        state = await asyncio.to_thread(_fetch)
        out: list[dict] = []
        for asset in state.get("assetPositions", []):
            pos = asset.get("position", {})
            sz = float(pos.get("szi", 0.0))
            if abs(sz) < 1e-12:
                continue
            out.append({
                "symbol": pos.get("coin", ""),
                "side": "long" if sz > 0 else "short",
                "size": sz,
                "entry_price": float(pos.get("entryPx") or 0.0),
                "leverage": float(pos.get("leverage", {}).get("value", 1)),
                "unrealized_pnl": float(pos.get("unrealizedPnl", 0.0)),
            })
        return out
