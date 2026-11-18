"""Entry point — wires everything together and runs the main loop."""
from __future__ import annotations
import asyncio
import logging
import signal
import sys

import structlog

from delta_bot.config.settings import load_settings
from delta_bot.persistence.database import Database
from delta_bot.alerts.telegram_alert import TelegramAlerter
from delta_bot.core.engine import TradingEngine

logger = structlog.get_logger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Install SIGINT/SIGTERM handlers that flip an asyncio Event.

    Falls back to no-op on platforms that don't support add_signal_handler
    (notably Windows for SIGTERM).
    """
    loop = asyncio.get_event_loop()
    sigs = [signal.SIGINT, signal.SIGTERM] if hasattr(signal, "SIGTERM") else [signal.SIGINT]
    for sig in sigs:
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows: signal handlers via add_signal_handler are limited.
            # KeyboardInterrupt path in main() still covers Ctrl+C.
            pass


async def main() -> int:
    settings = load_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    logger.info("bot.starting", paper=settings.paper_trading,
                interval=settings.main_loop_interval_seconds)

    db = Database(db_path=settings.db_path)
    await db.initialize()

    alerter = TelegramAlerter(
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    try:
        engine = TradingEngine(settings=settings, db=db, alerter=alerter)
    except Exception as e:
        logger.error("bot.engine_init_failed", error=str(e))
        await db.close()
        return 1

    await engine.start()
    await alerter.send(
        "[START] Bot started — " + ("PAPER" if settings.paper_trading else "LIVE")
    )

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    consecutive_errors = 0
    exit_code = 0
    try:
        while not stop_event.is_set():
            try:
                await engine.tick()
                consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                consecutive_errors += 1
                logger.error("bot.tick_error",
                             error=str(e),
                             consecutive=consecutive_errors)
                # Exponential backoff capped at 5 minutes after repeated failures
                if consecutive_errors >= 5:
                    backoff = min(2 ** consecutive_errors, 300)
                    logger.warning("bot.backoff", seconds=backoff)
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    continue

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.main_loop_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    except KeyboardInterrupt:
        logger.info("bot.keyboard_interrupt")
    except Exception as e:
        logger.error("bot.fatal", error=str(e))
        exit_code = 1
    finally:
        logger.info("bot.stopping")
        try:
            await engine.stop()
        except Exception as e:
            logger.warning("bot.stop_engine_failed", error=str(e))
        try:
            await db.close()
        except Exception as e:
            logger.warning("bot.stop_db_failed", error=str(e))
        try:
            await alerter.send("[STOP] Bot stopped")
        except Exception:
            pass

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
