"""
PaperTradingExchange — realistic simulation that implements BaseExchange.

KEY FIX: Each exchange instance has persistent funding rates per symbol
that only change every ~10 minutes (simulating 8h funding periods).
This ensures stable spread between exchanges.
"""
from __future__ import annotations
import math, time, uuid, random
from typing import Optional
import structlog

from delta_bot.core.types import (
    ExchangeId, FundingSnapshot, MarketData, OrderStatus, Side,
)
from delta_bot.exchanges.base import BaseExchange, OrderResult

logger = structlog.get_logger(__name__)

PRICES = {
    "BTC": 87000.0, "ETH": 2050.0, "SOL": 140.0, "ARB": 0.35,
    "DOGE": 0.17, "WIF": 0.55, "HYPE": 22.0, "PEPE": 0.000008,
}
VOLATILITY = {
    "BTC": 0.55, "ETH": 0.65, "SOL": 0.85, "ARB": 1.1,
    "DOGE": 0.95, "WIF": 1.3, "HYPE": 0.9, "PEPE": 1.5,
}


class PaperTradingExchange(BaseExchange):
    def __init__(self, exchange_id: ExchangeId, initial_balance: float = 10_000.0):
        self.exchange_id = exchange_id
        self._balance = initial_balance
        self._connected = False
        self._orders: list = []
        self._open_positions: dict[str, dict] = {}  # symbol -> position dict
        self._start = time.time()

        # Seed unique per exchange for deterministic but different rates
        seed = hash(exchange_id.value) % 10000
        self._rng = random.Random(seed)
        self._phase = {s: self._rng.uniform(0, 2 * math.pi) for s in PRICES}
        self._offset = {s: self._rng.gauss(0, 0.002) for s in PRICES}

        # Persistent funding: recalculated every ~10 min
        self._cached_funding: dict[str, tuple[float, float]] = {}

    async def connect(self) -> None:
        self._connected = True
        logger.info("paper.connected", exchange=self.exchange_id.value, balance=self._balance)

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    def _get_funding(self, symbol: str) -> float:
        now = time.time()
        cached = self._cached_funding.get(symbol)
        if cached and now < cached[1]:
            return cached[0]
        elapsed = now - self._start
        phase = self._phase.get(symbol, 0)
        cycle = math.sin(elapsed / 1800 + phase)
        base = 0.00015 + self._offset.get(symbol, 0) * 0.1
        rate = base + 0.00025 * cycle + self._rng.gauss(0, 0.00002)
        self._cached_funding[symbol] = (rate, now + 600)
        return rate

    async def fetch_funding_rate(self, symbol: str) -> FundingSnapshot:
        rate = self._get_funding(symbol)
        ann = rate * 3 * 365 * 10_000
        return FundingSnapshot(exchange=self.exchange_id, symbol=symbol,
                               rate=rate, annualised_bps=ann)

    async def fetch_market_data(self, symbol: str) -> MarketData:
        base = PRICES.get(symbol.upper(), 100.0)
        vol = VOLATILITY.get(symbol.upper(), 0.7)
        elapsed = time.time() - self._start
        trend = base * vol * 0.003 * math.sin(elapsed / 3600 + self._offset.get(symbol, 0))
        noise = self._rng.gauss(0, base * vol * 0.0003)
        offset = base * self._offset.get(symbol, 0)
        mid = max(base + trend + noise + offset, base * 0.01)
        spread = mid * 1.5 / 10_000
        return MarketData(
            exchange=self.exchange_id, symbol=symbol,
            bid=mid - spread, ask=mid + spread, mid=mid,
            volume_24h_usd=base * 1000 * self._rng.uniform(0.5, 2),
        )

    async def fetch_tradeable_symbols(self) -> list[str]:
        return list(PRICES.keys())

    async def place_order(
        self,
        symbol: str,
        side: Side,
        size: float,
        reduce_only: bool = False,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        if not self._connected:
            raise RuntimeError(f"Exchange {self.exchange_id.value} not connected")
        if size <= 0:
            raise ValueError(f"Order size must be positive, got {size}")

        md = await self.fetch_market_data(symbol)
        slip = self._rng.uniform(0, 1.5) / 10_000
        price = md.ask * (1 + slip) if side == Side.LONG else md.bid * (1 - slip)
        if limit_price is not None:
            # Reject if limit not met (simulated)
            if side == Side.LONG and price > limit_price:
                raise RuntimeError("Limit not met (long)")
            if side == Side.SHORT and price < limit_price:
                raise RuntimeError("Limit not met (short)")

        fee = size * price * 3.0 / 10_000
        self._balance -= fee

        # Track simulated open position so get_open_positions works
        existing = self._open_positions.get(symbol)
        signed = size if side == Side.LONG else -size
        if existing:
            new_size = existing["size"] + signed
            if abs(new_size) < 1e-9:
                self._open_positions.pop(symbol, None)
            else:
                existing["size"] = new_size
        else:
            self._open_positions[symbol] = {
                "symbol": symbol,
                "side": "long" if signed > 0 else "short",
                "size": signed,
                "entry_price": price,
                "leverage": 1.0,
                "unrealized_pnl": 0.0,
            }

        logger.info("paper.order_filled", exchange=self.exchange_id.value,
                    symbol=symbol, side=side.value, size=round(size, 6),
                    price=round(price, 2), fee=round(fee, 4),
                    reduce_only=reduce_only)
        return OrderResult(
            status=OrderStatus.FILLED,
            filled_price=price,
            filled_size=size,
            fee=fee,
            exchange_order_id=f"p-{uuid.uuid4().hex[:8]}",
        )

    async def get_balance(self) -> dict[str, float]:
        return {"total_equity": self._balance, "available": self._balance}

    async def get_open_positions(self) -> list[dict]:
        return [dict(p) for p in self._open_positions.values()]
