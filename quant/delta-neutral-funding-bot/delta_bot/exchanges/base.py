"""Abstract base for all exchange clients.

All concrete exchanges (Hyperliquid, Aster, paper) implement this interface
so the engine never needs to know which exchange it's talking to.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from delta_bot.core.types import (
    ExchangeId,
    FundingSnapshot,
    MarketData,
    OrderStatus,
    Side,
)


class OrderResult:
    """Generic order result returned by every exchange impl."""
    __slots__ = ("status", "filled_price", "filled_size", "fee", "exchange_order_id")

    def __init__(
        self,
        status: OrderStatus,
        filled_price: float,
        filled_size: float,
        fee: float,
        exchange_order_id: str = "",
    ) -> None:
        self.status = status
        self.filled_price = filled_price
        self.filled_size = filled_size
        self.fee = fee
        self.exchange_order_id = exchange_order_id


class BaseExchange(ABC):
    """Interface that the trading engine talks to.

    Every method MUST raise on failure — the engine relies on exception
    propagation to trigger rollback logic.
    """

    exchange_id: ExchangeId

    # ── lifecycle ──────────────────────────────────────────────────────────
    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        ...

    # ── market data (read-only) ────────────────────────────────────────────
    @abstractmethod
    async def fetch_funding_rate(self, symbol: str) -> FundingSnapshot:
        ...

    @abstractmethod
    async def fetch_market_data(self, symbol: str) -> MarketData:
        ...

    @abstractmethod
    async def fetch_tradeable_symbols(self) -> list[str]:
        ...

    # ── trading ────────────────────────────────────────────────────────────
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: Side,
        size: float,
        reduce_only: bool = False,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """Place an order. Must raise on any non-success status."""
        ...

    # ── account ────────────────────────────────────────────────────────────
    @abstractmethod
    async def get_balance(self) -> dict[str, float]:
        """Return at minimum {'total_equity': float, 'available': float}."""
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[dict]:
        """List of open positions as dicts:
            {symbol, side, size, entry_price, leverage, unrealized_pnl}
        Used by the reconciliation loop on engine startup.
        """
        ...
