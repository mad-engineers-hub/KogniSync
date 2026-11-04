#!/usr/bin/env python3
"""
scripts/run_hold_worker.py — Operational CLI Runner for Hold Expiration Worker.

Runs periodic database sweeps to expire stale active holds and release inventory
in PostgreSQL. Safe to run concurrently across multiple instances.

Usage:
    python scripts/run_hold_worker.py --once
    python scripts/run_hold_worker.py --interval 10 --batch-size 100
"""
import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add backend directory to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import AsyncSessionLocal
from app.services.hold_service import HoldService
from app.services.hold_expiration_worker import HoldExpirationWorker
from app.services.redis_hold_support import RedisHoldSupport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("kognisync.run_worker")


async def main_async(args: argparse.Namespace) -> None:
    redis_support = RedisHoldSupport()
    hold_service = HoldService(
        session_factory=AsyncSessionLocal,
        redis_support=redis_support,
    )
    worker = HoldExpirationWorker(
        hold_service=hold_service,
        interval_seconds=args.interval,
        batch_size=args.batch_size,
    )

    if args.once:
        logger.info("Running single hold expiration sweep...")
        res = await worker.run_sweep_once()
        logger.info(
            f"Sweep finished: processed={res.processed}, expired={res.expired}, "
            f"skipped={res.skipped}, failed={res.failed}"
        )
        await redis_support.close()
        return

    # Continuous loop
    worker.start()
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Received termination signal. Shutting down worker...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, RuntimeError):
            # Signal handling on Windows
            pass

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await worker.stop()
        await redis_support.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="KogniSync Hold Expiration Worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single sweep and exit immediately",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Sweep interval in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum holds to evaluate per batch sweep (default: 100)",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

