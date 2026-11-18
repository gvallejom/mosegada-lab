"""Domain types shared across the entire bot."""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class OrderStatus(str, Enum):
    FILLED = "filled"
    FAILED = "failed"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class ExchangeId(str, Enum):
    HYPERLIQUID = "hyperliquid"
    ASTER = "aster"
    MOCK = "mock"


class SkipReason(str, Enum):
    FUNDING_INSUFFICIENT = "funding_insufficient"
    EDGE_INSUFFICIENT = "edge_insufficient"
    RISK_HIGH = "risk_high"
    FREQUENCY_LIMIT = "frequency_limit"
    NO_OPPORTUNITY = "no_opportunity"
    KILL_SWITCH_ACTIVE = "kill_switch_active"


@dataclass
class FundingSnapshot:
    exchange: ExchangeId
    symbol: str
    rate: float
    annualised_bps: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MarketData:
    exchange: ExchangeId
    symbol: str
    bid: float
    ask: float
    mid: float
    volume_24h_usd: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def spread_bps(self) -> float:
        if self.mid == 0:
            return float("inf")
        return ((self.ask - self.bid) / self.mid) * 10_000


@dataclass
class Leg:
    exchange: ExchangeId
    symbol: str
    side: Side
    size: float
    entry_price: float
    current_price: float = 0.0
    unrealised_pnl: float = 0.0


@dataclass
class DeltaNeutralPosition:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    long_leg: Optional[Leg] = None
    short_leg: Optional[Leg] = None
    status: PositionStatus = PositionStatus.OPEN
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    accumulated_funding: float = 0.0
    fees_paid: float = 0.0

    @property
    def net_delta(self) -> float:
        lv = (self.long_leg.size * self.long_leg.current_price) if self.long_leg else 0.0
        sv = (self.short_leg.size * self.short_leg.current_price) if self.short_leg else 0.0
        t = lv + sv
        return (lv - sv) / t if t > 0 else 0.0

    @property
    def notional_usd(self) -> float:
        lv = (self.long_leg.size * self.long_leg.entry_price) if self.long_leg else 0.0
        sv = (self.short_leg.size * self.short_leg.entry_price) if self.short_leg else 0.0
        return (lv + sv) / 2

    @property
    def price_pnl(self) -> float:
        lp = self.long_leg.unrealised_pnl if self.long_leg else 0.0
        sp = self.short_leg.unrealised_pnl if self.short_leg else 0.0
        return lp + sp

    @property
    def total_pnl(self) -> float:
        return self.price_pnl + self.accumulated_funding - self.fees_paid


@dataclass
class OpportunitySignal:
    symbol: str
    long_exchange: ExchangeId
    short_exchange: ExchangeId
    expected_funding_bps: float
    expected_edge_bps: float
    suggested_size_usd: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PortfolioSnapshot:
    total_equity_usd: float = 0.0
    total_exposure_usd: float = 0.0
    net_delta: float = 0.0
    open_positions: int = 0
    unrealised_pnl: float = 0.0
    accumulated_funding: float = 0.0
    total_volume_usd: float = 0.0
    total_fees_usd: float = 0.0
    drawdown_pct: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SkipEvent:
    reason: SkipReason
    details: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
