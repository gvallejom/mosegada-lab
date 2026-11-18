"""Aster Finance perpetual futures client.

The Aster public API at fapi.asterdex.com uses Binance-Futures-style
endpoints: SIGNED requests carry an `X-MBX-APIKEY` header plus a
`signature` query param computed as HMAC-SHA256(secret, query_string).

Docs: https://github.com/asterdex/api-docs

# VERIFY before mainnet:
#   * Endpoint paths under /fapi/v1 and /fapi/v3 against the latest doc.
#   * Symbol format (Aster uses BTCUSDT-style, not bare BTC).
#   * Fee tiers — we report a fixed 4 bps taker as a conservative estimate.
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import time
import urllib.parse
from typing import Any, Optional

import aiohttp
import structlog

from delta_bot.core.types import (
    ExchangeId, FundingSnapshot, MarketData, OrderStatus, Side,
)
from delta_bot.exchanges.base import BaseExchange, OrderResult

logger = structlog.get_logger(__name__)

MAINNET_REST = "https://fapi.asterdex.com"
# Aster's testnet host — confirm with the user before pointing live keys at it.
TESTNET_REST = "https://testnet.asterdex.com"

# Symbol mapping: bot uses bare bases ("BTC"); Aster expects "BTCUSDT".
_QUOTE = "USDT"


def to_aster_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(_QUOTE):
        return s
    return f"{s}{_QUOTE}"


def from_aster_symbol(symbol: str) -> str:
    s = symbol.upper()
    return s[:-len(_QUOTE)] if s.endswith(_QUOTE) else s


class AsterExchange(BaseExchange):
    exchange_id: ExchangeId = ExchangeId.ASTER

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        wallet_address: str = "",
        testnet: bool = True,
        recv_window_ms: int = 5000,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("ASTER: api_key and api_secret required")
        self._api_key = api_key
        self._api_secret = api_secret.encode()
        self._wallet_address = wallet_address
        self._testnet = testnet
        self._base = TESTNET_REST if testnet else MAINNET_REST
        self._recv = recv_window_ms
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        self._exchange_info: dict[str, Any] = {}

    # ── lifecycle ──────────────────────────────────────────────────────────
    async def connect(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"X-MBX-APIKEY": self._api_key},
        )
        # Pull exchangeInfo for symbol metadata + connectivity check.
        info = await self._public_get("/fapi/v1/exchangeInfo")
        self._exchange_info = info
        self._connected = True
        logger.info("aster.connected", testnet=self._testnet,
                    symbols=len(info.get("symbols", [])))

    async def disconnect(self) -> None:
        self._connected = False
        if self._session:
            await self._session.close()
            self._session = None

    async def is_connected(self) -> bool:
        return self._connected

    # ── HTTP helpers ───────────────────────────────────────────────────────
    def _sign(self, params: dict[str, Any]) -> str:
        qs = urllib.parse.urlencode(params, doseq=True)
        sig = hmac.new(self._api_secret, qs.encode(), hashlib.sha256).hexdigest()
        return f"{qs}&signature={sig}"

    async def _public_get(self, path: str, params: Optional[dict] = None) -> Any:
        if not self._session:
            raise RuntimeError("Aster session not initialised")
        url = self._base + path
        async with self._session.get(url, params=params) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(f"Aster GET {path} -> {resp.status}: {data}")
            return data

    async def _signed_request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
    ) -> Any:
        if not self._session:
            raise RuntimeError("Aster session not initialised")
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self._recv
        signed_qs = self._sign(params)
        url = f"{self._base}{path}?{signed_qs}"
        async with self._session.request(method, url) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(f"Aster {method} {path} -> {resp.status}: {data}")
            return data

    # ── market data ────────────────────────────────────────────────────────
    async def fetch_funding_rate(self, symbol: str) -> FundingSnapshot:
        sym = to_aster_symbol(symbol)
        # premiumIndex includes lastFundingRate (per 8h)
        data = await self._public_get("/fapi/v1/premiumIndex", {"symbol": sym})
        rate = float(data.get("lastFundingRate", 0.0))
        ann_bps = rate * 3 * 365 * 10_000  # 3 funding periods/day
        return FundingSnapshot(
            exchange=self.exchange_id, symbol=symbol,
            rate=rate, annualised_bps=ann_bps,
        )

    async def fetch_market_data(self, symbol: str) -> MarketData:
        sym = to_aster_symbol(symbol)
        ticker, ticker24 = await asyncio.gather(
            self._public_get("/fapi/v1/ticker/bookTicker", {"symbol": sym}),
            self._public_get("/fapi/v1/ticker/24hr", {"symbol": sym}),
            return_exceptions=True,
        )
        if isinstance(ticker, Exception):
            raise ticker
        bid = float(ticker.get("bidPrice", 0))
        ask = float(ticker.get("askPrice", 0))
        mid = (bid + ask) / 2 if bid and ask else max(bid, ask)
        vol = 0.0
        if not isinstance(ticker24, Exception):
            try:
                vol = float(ticker24.get("quoteVolume", 0))
            except Exception:
                vol = 0.0
        return MarketData(
            exchange=self.exchange_id, symbol=symbol,
            bid=bid, ask=ask, mid=mid, volume_24h_usd=vol,
        )

    async def fetch_tradeable_symbols(self) -> list[str]:
        return [
            from_aster_symbol(s["symbol"])
            for s in self._exchange_info.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"
        ]

    # ── trading ────────────────────────────────────────────────────────────
    def _step_size(self, sym: str) -> float:
        for s in self._exchange_info.get("symbols", []):
            if s.get("symbol") == sym:
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        return float(f.get("stepSize", "0.001"))
        return 0.001

    @staticmethod
    def _round_to_step(qty: float, step: float) -> float:
        if step <= 0:
            return qty
        return (int(qty / step)) * step

    async def place_order(
        self,
        symbol: str,
        side: Side,
        size: float,
        reduce_only: bool = False,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        sym = to_aster_symbol(symbol)
        step = self._step_size(sym)
        qty = self._round_to_step(size, step)
        if qty <= 0:
            raise ValueError(f"Size after rounding is non-positive: {qty}")

        params: dict[str, Any] = {
            "symbol": sym,
            "side": "BUY" if side == Side.LONG else "SELL",
            "quantity": f"{qty:.10f}".rstrip("0").rstrip("."),
            "newOrderRespType": "RESULT",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        if limit_price is not None:
            params["type"] = "LIMIT"
            params["timeInForce"] = "GTC"
            params["price"] = f"{limit_price}"
        else:
            params["type"] = "MARKET"

        resp = await self._signed_request("POST", "/fapi/v1/order", params)
        return self._parse_order_response(resp, qty)

    def _parse_order_response(self, resp: dict, requested_size: float) -> OrderResult:
        status = resp.get("status", "")
        if status not in ("FILLED", "PARTIALLY_FILLED", "NEW"):
            raise RuntimeError(f"Aster order not filled: {resp}")
        if status == "NEW":
            # Resting limit order — engine treats as failure for atomicity.
            raise RuntimeError(f"Aster limit order resting (not filled): {resp}")
        avg_price = float(resp.get("avgPrice", resp.get("price", 0)) or 0)
        if avg_price <= 0:
            raise RuntimeError(f"Aster order has zero avg price: {resp}")
        executed = float(resp.get("executedQty", requested_size) or requested_size)
        fee = executed * avg_price * 4.0 / 10_000  # ~4 bps taker default
        return OrderResult(
            status=OrderStatus.FILLED,
            filled_price=avg_price,
            filled_size=executed,
            fee=fee,
            exchange_order_id=str(resp.get("orderId", "")),
        )

    # ── account ────────────────────────────────────────────────────────────
    async def get_balance(self) -> dict[str, float]:
        # /fapi/v3/balance is preferred on newer accounts; fall back to v2.
        try:
            data = await self._signed_request("GET", "/fapi/v3/balance")
        except Exception:
            data = await self._signed_request("GET", "/fapi/v2/balance")
        usdt = next((b for b in data if b.get("asset") == _QUOTE), None)
        if not usdt:
            return {"total_equity": 0.0, "available": 0.0}
        return {
            "total_equity": float(usdt.get("balance", 0.0)),
            "available": float(usdt.get("availableBalance",
                                         usdt.get("withdrawAvailable", 0.0))),
        }

    async def get_open_positions(self) -> list[dict]:
        try:
            data = await self._signed_request("GET", "/fapi/v3/positionRisk")
        except Exception:
            data = await self._signed_request("GET", "/fapi/v2/positionRisk")
        out: list[dict] = []
        for p in data:
            amt = float(p.get("positionAmt", 0))
            if abs(amt) < 1e-12:
                continue
            out.append({
                "symbol": from_aster_symbol(p.get("symbol", "")),
                "side": "long" if amt > 0 else "short",
                "size": amt,
                "entry_price": float(p.get("entryPrice", 0) or 0),
                "leverage": float(p.get("leverage", 1) or 1),
                "unrealized_pnl": float(p.get("unRealizedProfit", 0) or 0),
            })
        return out
