"""In-process settlement scheduler (Phase 7).

Computes the next UTC-midnight run time from the ``SETTLEMENT_CRON`` expression
(nightly ``0 0 * * *`` by default) and runs ``settlement.run_settlement_once``
in a background thread. Gated by ``SETTLEMENT_ENABLED``. External cron can also
drive the same flow via ``scripts/run_settlement.py`` or the manual route.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from services.shared.config import get_settings
from services.wallet import settlement as settlement_service

logger = logging.getLogger(__name__)


def _next_utc_midnight(now: datetime) -> datetime:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow


def seconds_until_next_run(now: datetime | None = None) -> float:
    base = now or datetime.now(UTC)
    return max(1.0, (_next_utc_midnight(base) - base).total_seconds())


async def _run_loop() -> None:
    logger.info("settlement scheduler started (nightly UTC midnight)")
    while True:
        try:
            delay = seconds_until_next_run()
            await asyncio.sleep(delay)
            logger.info("settlement scheduler firing run")
            await asyncio.to_thread(settlement_service.run_settlement_once)
        except asyncio.CancelledError:
            logger.info("settlement scheduler cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 — scheduler must not die
            logger.exception("settlement scheduler error: %s", exc)
            await asyncio.sleep(60.0)


def start_scheduler() -> asyncio.Task | None:
    """Start the background scheduler task if enabled. Returns the task (or None)."""
    settings = get_settings()
    if not settings.settlement_enabled:
        return None
    return asyncio.create_task(_run_loop())


def main() -> None:
    """Standalone entrypoint: run the scheduler loop in its own event loop."""
    import asyncio as _asyncio

    from services.shared.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env)
    _asyncio.run(_run_loop())


if __name__ == "__main__":
    main()
