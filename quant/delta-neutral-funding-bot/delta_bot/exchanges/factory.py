"""Factory that builds the right BaseExchange impls based on Settings."""
from __future__ import annotations
import structlog

from delta_bot.config.settings import Settings
from delta_bot.core.types import ExchangeId
from delta_bot.exchanges.base import BaseExchange
from delta_bot.simulation.paper_trading import PaperTradingExchange

logger = structlog.get_logger(__name__)


def build_exchanges(settings: Settings) -> dict[ExchangeId, BaseExchange]:
    """Return {exchange_id: client} according to settings.

    PAPER_TRADING=true  -> two paper exchanges (HL + Aster simulated)
    PAPER_TRADING=false -> live HyperliquidExchange + AsterExchange (require keys)
    """
    out: dict[ExchangeId, BaseExchange] = {}

    if settings.paper_trading:
        out[ExchangeId.HYPERLIQUID] = PaperTradingExchange(ExchangeId.HYPERLIQUID)
        out[ExchangeId.ASTER] = PaperTradingExchange(ExchangeId.ASTER)
        logger.info("factory.paper_mode")
        return out

    # LIVE mode: import lazily so paper users don't need the SDKs installed.
    from delta_bot.exchanges.hyperliquid_client import HyperliquidExchange
    from delta_bot.exchanges.aster_client import AsterExchange

    if not (settings.hyperliquid_api_key or settings.evm_private_key):
        raise RuntimeError(
            "Live mode: set EVM_PRIVATE_KEY (used to sign Hyperliquid orders) "
            "and HYPERLIQUID_WALLET_ADDRESS in .env"
        )
    if not settings.hyperliquid_wallet_address:
        raise RuntimeError("Live mode: HYPERLIQUID_WALLET_ADDRESS missing")
    if not (settings.aster_api_key and settings.aster_api_secret):
        raise RuntimeError("Live mode: ASTER_API_KEY / ASTER_API_SECRET missing")

    # Hyperliquid signs with a wallet private key (NOT an API key); we accept
    # either HYPERLIQUID_API_SECRET (raw key) or fall back to EVM_PRIVATE_KEY.
    hl_signer = settings.hyperliquid_api_secret or settings.evm_private_key

    out[ExchangeId.HYPERLIQUID] = HyperliquidExchange(
        private_key=hl_signer,
        wallet_address=settings.hyperliquid_wallet_address,
        testnet=settings.hyperliquid_testnet,
    )
    out[ExchangeId.ASTER] = AsterExchange(
        api_key=settings.aster_api_key,
        api_secret=settings.aster_api_secret,
        wallet_address=settings.aster_wallet_address,
        testnet=settings.aster_testnet,
    )
    logger.info("factory.live_mode",
                hl_testnet=settings.hyperliquid_testnet,
                aster_testnet=settings.aster_testnet)
    return out
