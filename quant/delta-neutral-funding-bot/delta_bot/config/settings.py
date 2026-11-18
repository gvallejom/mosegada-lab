"""Centralised settings. Every configurable parameter lives here."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class FrequencySettings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    target_operations_per_hour: int = 6
    target_operations_per_day: Optional[int] = None
    min_minutes_between_entries: int = 8
    max_operations_per_market_per_day: int = 50
    max_operations_per_exchange_per_day: int = 100
    max_total_operations_per_day: int = 200
    allowed_hours_utc: Optional[list[int]] = None
    require_positive_expected_funding: bool = True


class RiskSettings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    max_portfolio_drawdown_pct: float = 10.0
    max_single_position_pct: float = 50.0
    kill_switch_drawdown_pct: float = 15.0
    max_delta_abs: float = 0.05
    max_total_exposure_usd: float = 500_000.0
    min_liquidity_usd: float = 10_000.0


class StrategySettings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    min_funding_rate_bps: float = 0.1
    min_expected_edge_bps: float = 0.01
    rebalance_delta_threshold: float = 0.03
    position_size_usd: float = 1_000.0
    leverage: float = 5.0
    max_slippage_pct: float = 0.10
    holding_periods: int = 3


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    paper_trading: bool = True
    log_level: str = "INFO"
    main_loop_interval_seconds: int = 20

    # EVM
    evm_private_key: str = ""
    evm_rpc_url: str = "https://arb1.arbitrum.io/rpc"
    evm_chain_id: int = 42161

    # Solana
    solana_private_key: str = ""
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"

    # Hyperliquid
    hyperliquid_api_key: str = ""
    hyperliquid_api_secret: str = ""
    hyperliquid_wallet_address: str = ""
    hyperliquid_testnet: bool = True

    # Aster
    aster_api_key: str = ""
    aster_api_secret: str = ""
    aster_wallet_address: str = ""
    aster_testnet: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # DB
    db_path: str = "data/bot.db"

    # Sub-settings
    frequency: FrequencySettings = Field(default_factory=FrequencySettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)

    @field_validator("main_loop_interval_seconds")
    @classmethod
    def _check_interval(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("MAIN_LOOP_INTERVAL_SECONDS must be > 0")
        if v > 600:
            raise ValueError("MAIN_LOOP_INTERVAL_SECONDS too large (>600s)")
        return v

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        u = v.upper()
        if u not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return u


def load_settings() -> Settings:
    env_file = Path(".env")
    if not env_file.exists():
        example = Path(".env.example")
        if example.exists():
            import shutil
            shutil.copy(example, env_file)
    return Settings()
