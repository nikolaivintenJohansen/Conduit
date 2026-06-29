"""External cron entrypoint for batch settlement (Phase 7).

Run one settlement sweep and exit. Intended for a host cron / k8s CronJob:

    python -m scripts.run_settlement
    python -m scripts.run_settlement --partner cursor

Requires STRIPE_SECRET_KEY + STRIPE_CONNECT onboarding to be complete for any
partner that should actually receive a transfer.
"""

from __future__ import annotations

import argparse
import sys

from services.shared.config import get_settings
from services.shared.logging import configure_logging
from services.wallet import settlement as settlement_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one batch settlement sweep")
    parser.add_argument(
        "--partner",
        default=None,
        help="Partner slug to limit the run to a single partner",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env)
    report = settlement_service.run_settlement_once(partner_slug=args.partner)
    cleared = len(report.cleared)
    failed = len(report.failed)
    skipped = len(report.results) - cleared - failed
    print(
        f"settlement run: cleared={cleared} failed={failed} skipped={skipped} "
        f"duration={(report.finished_at - report.started_at).total_seconds():.2f}s",
        flush=True,
    )
    for result in report.results:
        print(
            f"  partner={result.partner_slug} status={result.status} "
            f"events={result.event_count} payout={result.payout_microdollars}"
            + (f" error={result.error}" if result.error else ""),
            flush=True,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
