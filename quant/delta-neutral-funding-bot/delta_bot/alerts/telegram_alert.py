"""Telegram alerter — sends messages or logs them if no token configured."""
from __future__ import annotations
import structlog

logger = structlog.get_logger(__name__)


class TelegramAlerter:
    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token
        self.chat_id = chat_id
        self._enabled = bool(token and chat_id)
        if not self._enabled:
            logger.info("telegram.disabled", msg="No token — alerts logged only")

    async def send(self, message: str):
        if self._enabled:
            try:
                import aiohttp
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json={"chat_id": self.chat_id, "text": message})
            except Exception as e:
                logger.warning("telegram.send_failed", error=str(e))
        else:
            logger.info("telegram.log_only", message=message)
