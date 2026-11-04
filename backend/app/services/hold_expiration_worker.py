"""
backend/app/services/hold_expiration_worker.py

Background worker for automatic periodic expiration of stale booking holds.

RELIABILITY & CONCURRENCY GUARANTEES:
1. Periodic Sweeps: Periodically runs bounded batch queries against PostgreSQL.
2. Crash Resilience: If the worker restarts, all missed expired holds are recovered on the next sweep.
3. Multi-Instance Concurrency: Multiple worker instances safely run concurrently because
   candidate queries and expiration operations utilize row-level locking (FOR UPDATE SKIP LOCKED).
4. Zero Redis Dependency: Operates authoritatively via PostgreSQL even if Redis is completely unavailable.
"""
import asyncio
import logging
import signal
from typing import Optional
from app.services.hold_service import HoldService, BatchExpireResult

logger = logging.getLogger("kognisync.hold_worker")


class HoldExpirationWorker:
    """
    Background worker that runs periodic database sweeps to expire stale active holds.
    Safe for multi-instance deployments.
    """

    def __init__(
        self,
        hold_service: HoldService,
        interval_seconds: float = 10.0,
        batch_size: int = 100,
    ):
        self.hold_service = hold_service
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def run_once(self, cutoff_time=None) -> BatchExpireResult:
        """Execute a single batch expiration sweep with optional cutoff."""
        return await self.hold_service.expire_stale_holds(batch_size=self.batch_size, cutoff_time=cutoff_time)

    async def run_sweep_once(self) -> BatchExpireResult:
        """Execute a single batch expiration sweep."""
        return await self.run_once()

    async def _loop(self) -> None:
        """Internal worker loop."""
        logger.info(
            f"HoldExpirationWorker started (interval: {self.interval_seconds}s, batch_size: {self.batch_size})."
        )
        while self._running:
            try:
                result = await self.run_sweep_once()
                if result.processed > 0:
                    logger.info(
                        f"Hold sweep completed: processed={result.processed}, "
                        f"expired={result.expired}, skipped={result.skipped}, failed={result.failed}"
                    )
            except Exception as e:
                logger.error(f"Unexpected error during hold expiration sweep: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

        logger.info("HoldExpirationWorker stopped.")

    def start(self) -> None:
        """Start the background worker task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Gracefully stop the background worker task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

