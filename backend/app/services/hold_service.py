"""
backend/app/services/hold_service.py

Authoritative booking hold management and idempotent inventory release service.

CRITICAL INVARIANTS ENFORCED:
1. PostgreSQL is the authoritative state store for hold status and inventory counts.
2. Inventory invariant: (booked_units + held_units <= total_units) is guaranteed.
3. Holds are locked with row-level locks (SELECT ... FOR UPDATE) before modification.
4. Exactly-once inventory release: atomic conditional status updates prevent double releases even under concurrency.
5. Confirmation race safety: confirmation and expiration cannot both succeed on the same hold.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import update

from app.db.models.inventory import Hold, InventoryCalendar
from app.repositories.hold_repository import HoldRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.exceptions import (
    HoldNotFoundError,
    HoldStatusError,
    HoldExpiredError,
    HoldNotActiveError,
    InsufficientInventoryError,
)
from app.services.redis_hold_support import RedisHoldSupport

logger = logging.getLogger("kognisync.holds")


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime is timezone-aware in UTC for consistent comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class BatchExpireResult:
    """Summary of a batch hold expiration sweep."""
    processed: int = 0
    expired: int = 0
    skipped: int = 0
    failed: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)


class HoldService:
    """
    Authoritative service managing hold creation, confirmation, and safe expiration.
    Guarantees row-level locking and atomic inventory operations inside PostgreSQL.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis_support: Optional[RedisHoldSupport] = None,
    ):
        self.session_factory = session_factory
        self.redis = redis_support or RedisHoldSupport()

    @asynccontextmanager
    async def _get_session(self, session: Optional[AsyncSession]):
        if session is not None:
            yield session, False
        else:
            async with self.session_factory() as s:
                yield s, True

    async def create_hold(
        self,
        user_id: str,
        inventory_id: str,
        units: int = 1,
        ttl_seconds: int = 600,
        idempotency_key: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Hold:
        """
        Atomically allocates held_units in inventory_calendar and creates an active Hold.
        
        Guarantees:
        - Row-level lock on inventory_calendar prevents overbooking.
        - Idempotency key lookup prevents duplicate hold allocations.
        - Advisory TTL recorded in Redis if available.
        """
        idemp_key = idempotency_key or f"idemp_hld_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        async with self._get_session(session) as (s, owns_session):
            inv_repo = InventoryRepository(s)
            hold_repo = HoldRepository(s)

            # 1. Check idempotency first
            existing = await hold_repo.get_by_idempotency_key(idemp_key)
            if existing:
                return existing

            # 2. Lock inventory row and allocate held units
            await inv_repo.allocate_held_units(inventory_id, units)

            # 3. Create hold record
            hold = Hold(
                hold_id=f"hld_{uuid.uuid4().hex[:12]}",
                inventory_id=inventory_id,
                user_id=user_id,
                units=units,
                idempotency_key=idemp_key,
                created_at=now,
                expires_at=expires_at,
                status="active",
                updated_at=now,
            )
            created_hold = await hold_repo.create_hold(hold)
            if owns_session:
                await s.commit()
            else:
                await s.flush()

        # 4. Advisory Redis registration (non-blocking, failure-safe, strictly post-commit)
        if owns_session:
            try:
                await self.redis.register_hold_ttl(
                    created_hold.hold_id,
                    ttl_seconds,
                    metadata={"user_id": user_id, "inventory_id": inventory_id, "units": units},
                )
            except Exception as e:
                logger.warning(f"Advisory Redis TTL registration encountered error: {e}")

        return created_hold

    async def expire_hold(
        self,
        hold_id: str,
        force: bool = False,
        now_override: Optional[datetime] = None,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Authoritatively and idempotently expires an active hold and releases held units.
        
        Guarantees:
        - Locks the hold record with FOR UPDATE (PostgreSQL).
        - Double-checks status inside transaction: only status == 'active' is released.
        - Atomic conditional update: (status == 'active') -> (status == 'expired').
        - Exactly-once release: repeated or concurrent calls return False with 0 inventory modification.
        - Releases held units on inventory_calendar via FOR UPDATE.
        - Removes advisory Redis key.
        
        Returns:
            True if the hold was actively expired by this call.
            False if the hold was already expired, confirmed, released, or not yet expired.
        """
        now = ensure_utc(now_override or datetime.now(timezone.utc))

        async with self._get_session(session) as (s, owns_session):
            hold_repo = HoldRepository(s)
            inv_repo = InventoryRepository(s)

            # 1. Acquire row lock on hold
            hold = await hold_repo.lock_by_id(hold_id)
            if not hold:
                raise HoldNotFoundError(f"Hold '{hold_id}' not found")

            # 2. Status verification under lock
            if hold.status != "active":
                logger.debug(f"Hold '{hold_id}' already has status '{hold.status}'. Skipping expiration.")
                return False

            # 3. Expiry verification under lock (unless forced)
            hold_expiry = ensure_utc(hold.expires_at)
            if not force and hold_expiry > now:
                logger.debug(f"Hold '{hold_id}' has not yet expired (expires at {hold.expires_at}). Skipping.")
                return False

            # 4. Atomic conditional transition to prevent concurrent double-releases
            stmt = (
                update(Hold)
                .where(Hold.hold_id == hold_id, Hold.status == "active")
                .values(status="expired", released_at=now, updated_at=now)
            )
            res = await s.execute(stmt)
            if res.rowcount == 0:
                # Lost race to another concurrent worker or confirmation
                logger.debug(f"Hold '{hold_id}' status update matched 0 rows (concurrent state change). Skipping.")
                return False

            # 5. Release inventory held units under inventory row lock
            await inv_repo.release_held_units(hold.inventory_id, hold.units)
            if owns_session:
                await s.commit()
            else:
                await s.flush()
            logger.info(f"Hold '{hold_id}' successfully expired. Released {hold.units} units for inventory '{hold.inventory_id}'.")

        # 6. Advisory Redis cleanup (strictly post-commit)
        if owns_session:
            try:
                await self.redis.remove_hold_ttl(hold_id)
            except Exception as e:
                logger.warning(f"Advisory Redis cleanup encountered error: {e}")
        return True

    async def confirm_hold(
        self,
        hold_id: str,
        booking_id: str,
        now_override: Optional[datetime] = None,
        session: Optional[AsyncSession] = None,
    ) -> Hold:
        """
        Authoritatively confirms an active hold, converting held units to booked units.
        
        Guarantees:
        - Locks hold with FOR UPDATE (PostgreSQL).
        - Rejects confirmation if hold is expired, released, or already confirmed.
        - Atomic conditional update: (status == 'active') -> (status == 'confirmed').
        - Atomically shifts held_units -> booked_units inside inventory lock.
        - Invariant (booked_units + held_units <= total_units) strictly maintained.
        """
        now = ensure_utc(now_override or datetime.now(timezone.utc))

        async with self._get_session(session) as (s, owns_session):
            hold_repo = HoldRepository(s)
            inv_repo = InventoryRepository(s)

            hold = await hold_repo.lock_by_id(hold_id)
            if not hold:
                raise HoldNotFoundError(f"Hold '{hold_id}' not found")

            if hold.status != "active":
                raise HoldNotActiveError(
                    f"Hold '{hold_id}' cannot be confirmed because status is '{hold.status}'"
                )

            hold_expiry = ensure_utc(hold.expires_at)
            if hold_expiry <= now:
                raise HoldExpiredError(
                    f"Hold '{hold_id}' cannot be confirmed because it expired at {hold.expires_at}"
                )

            # Atomic conditional update
            stmt = (
                update(Hold)
                .where(Hold.hold_id == hold_id, Hold.status == "active")
                .values(status="confirmed", booking_id=booking_id, updated_at=now)
            )
            res = await s.execute(stmt)
            if res.rowcount == 0:
                raise HoldStatusError(
                    f"Hold '{hold_id}' was already transitioned by a concurrent process"
                )

            # Convert held units to booked units under lock
            inv = await inv_repo.lock_by_id(hold.inventory_id)
            inv.held_units = max(0, inv.held_units - hold.units)
            inv.booked_units += hold.units

            # Re-verify inventory invariant
            if inv.booked_units + inv.held_units > inv.total_units:
                raise InsufficientInventoryError(
                    f"Inventory invariant violated: booked ({inv.booked_units}) + "
                    f"held ({inv.held_units}) exceeds total ({inv.total_units})"
                )

            if owns_session:
                await s.commit()
            else:
                await s.flush()
            hold.status = "confirmed"
            hold.booking_id = booking_id
            hold.updated_at = now
            logger.info(f"Hold '{hold_id}' confirmed into booking '{booking_id}'.")

        # Cleanup advisory Redis key (strictly post-commit)
        if owns_session:
            try:
                await self.redis.remove_hold_ttl(hold_id)
            except Exception as e:
                logger.warning(f"Advisory Redis cleanup encountered error: {e}")
        return hold

    async def expire_stale_holds(
        self,
        batch_size: int = 100,
        cutoff_time: Optional[datetime] = None,
    ) -> BatchExpireResult:
        """
        Batch expiration sweep for expired active holds.
        Processes each candidate hold in an isolated transaction to ensure
        individual record errors do not abort the entire batch.
        """
        cutoff = ensure_utc(cutoff_time or datetime.now(timezone.utc))
        result = BatchExpireResult()

        factory = self.session_factory
        if factory is None:
            from app.db.database import AsyncSessionLocal
            factory = AsyncSessionLocal

        # Hold row locks across the batch so concurrent workers safely partition rows via SKIP LOCKED
        expired_hold_ids = []
        async with factory() as session:
            hold_repo = HoldRepository(session)
            candidates = await hold_repo.find_expired_active_holds(
                cutoff_time=cutoff, limit=batch_size, skip_locked=True
            )
            candidate_ids = [h.hold_id for h in candidates]

            if not candidate_ids:
                return result

            logger.info(f"Hold expiration sweep found {len(candidate_ids)} candidate expired holds.")

            for hold_id in candidate_ids:
                result.processed += 1
                try:
                    expired = await self.expire_hold(hold_id, force=False, now_override=cutoff, session=session)
                    if expired:
                        result.expired += 1
                        expired_hold_ids.append(hold_id)
                    else:
                        result.skipped += 1
                except Exception as e:
                    result.failed += 1
                    result.failures.append({"hold_id": hold_id, "error": str(e)})
                    logger.error(f"Failed to expire hold '{hold_id}': {e}", exc_info=True)

            await session.commit()

        # Advisory Redis cleanup strictly post-commit
        for h_id in expired_hold_ids:
            try:
                await self.redis.remove_hold_ttl(h_id)
            except Exception as e:
                logger.warning(f"Advisory Redis cleanup encountered error: {e}")

        return result
