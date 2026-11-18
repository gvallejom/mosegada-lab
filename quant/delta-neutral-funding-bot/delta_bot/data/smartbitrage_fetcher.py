"""SmartArbitrage data fetcher — scrapes or reads funding/APR data."""
from __future__ import annotations
import structlog

logger = structlog.get_logger(__name__)


class SmartArbitrageFetcher:
    """Fetches opportunities from SmartArbitrage source."""

    async def fetch_opportunities(self) -> list[dict]:
        """
        Returns list of dicts with keys:
          symbol, apr, volume_24h_usd, long_exchange, short_exchange,
          funding_long, funding_short
        """
        logger.info("smartarbitrage.fetch", status="not_implemented")
        return []
