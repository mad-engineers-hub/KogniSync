"""
backend/app/services/disruption/freshness.py

Deterministic Data Freshness & Reliability Engine (Milestone M3.8).
Distinguishes between provider observation time, fetch time, and verification time.
Enforces provider- and data-type-specific freshness thresholds, clock skew tolerance,
stale-event disclosure generation, and expired-event exclusion.
"""
from datetime import datetime, timezone, timedelta
from typing import Literal
from pydantic import BaseModel, Field
from app.core.config import settings
from app.services.disruption.schemas import DisruptionEvent

FreshnessStatus = Literal["fresh", "aging", "stale", "expired", "unknown"]
DisruptionDataType = Literal["road_incident", "service_alert", "trip_update", "vehicle_position"]


class FreshnessPolicy(BaseModel):
    fresh_threshold_seconds: int
    aging_threshold_seconds: int
    max_clock_skew_seconds: int = 120  # Tolerates 2 minutes of forward clock drift


DEFAULT_FRESHNESS_POLICIES: dict[DisruptionDataType, FreshnessPolicy] = {
    "road_incident": FreshnessPolicy(
        fresh_threshold_seconds=settings.FRESHNESS_ROAD_INCIDENT_SECONDS,       # 1800s (30m)
        aging_threshold_seconds=settings.FRESHNESS_ROAD_INCIDENT_SECONDS * 2,   # 3600s (60m)
    ),
    "service_alert": FreshnessPolicy(
        fresh_threshold_seconds=settings.FRESHNESS_SERVICE_ALERT_SECONDS,       # 3600s (60m)
        aging_threshold_seconds=settings.FRESHNESS_SERVICE_ALERT_SECONDS * 2,   # 7200s (120m)
    ),
    "trip_update": FreshnessPolicy(
        fresh_threshold_seconds=settings.FRESHNESS_TRIP_UPDATE_SECONDS,         # 300s (5m)
        aging_threshold_seconds=settings.FRESHNESS_TRIP_UPDATE_SECONDS * 2,     # 600s (10m)
    ),
    "vehicle_position": FreshnessPolicy(
        fresh_threshold_seconds=settings.FRESHNESS_VEHICLE_POSITION_SECONDS,    # 60s (1m)
        aging_threshold_seconds=settings.FRESHNESS_VEHICLE_POSITION_SECONDS * 3,# 180s (3m)
    ),
}


class FreshnessReport(BaseModel):
    status: FreshnessStatus
    age_seconds: int
    is_usable: bool
    is_expired: bool
    requires_disclosure: bool
    disclosure_notice: str | None = None
    observed_at: str | None = None
    fetched_at: str | None = None
    last_verified_at: str | None = None


def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return None


class DataFreshnessEngine:
    """
    Deterministic freshness evaluation engine.
    Ensures that cached or historical observations are never masqueraded as fresh.
    """

    def __init__(self, policies: dict[DisruptionDataType, FreshnessPolicy] | None = None):
        self.policies = policies or DEFAULT_FRESHNESS_POLICIES

    def evaluate_event_freshness(
        self,
        event: DisruptionEvent,
        data_type: DisruptionDataType = "road_incident",
        as_of: datetime | None = None,
        fetched_at: datetime | None = None,
    ) -> FreshnessReport:
        now = as_of or datetime.now(timezone.utc)
        policy = self.policies.get(data_type, self.policies["road_incident"])

        # 1. Check expiration bounds first (valid_until < now)
        if event.valid_until:
            valid_until_dt = parse_iso_datetime(event.valid_until)
            if valid_until_dt and valid_until_dt < now:
                return FreshnessReport(
                    status="expired",
                    age_seconds=max(0, int((now - valid_until_dt).total_seconds())),
                    is_usable=False,
                    is_expired=True,
                    requires_disclosure=True,
                    disclosure_notice="Event has expired according to provider schedule.",
                    observed_at=event.observed_at,
                    fetched_at=fetched_at.isoformat() if fetched_at else None,
                    last_verified_at=event.last_verified_at,
                )

        # 2. Check if event is explicitly resolved
        if event.status == "resolved":
            return FreshnessReport(
                status="expired",
                age_seconds=0,
                is_usable=False,
                is_expired=True,
                requires_disclosure=True,
                disclosure_notice="Event is resolved.",
                observed_at=event.observed_at,
                fetched_at=fetched_at.isoformat() if fetched_at else None,
                last_verified_at=event.last_verified_at,
            )

        # 3. Parse observation timestamp
        observed_dt = parse_iso_datetime(event.observed_at)
        if not observed_dt:
            # Missing observation timestamp -> unknown freshness
            return FreshnessReport(
                status="unknown",
                age_seconds=-1,
                is_usable=True,
                is_expired=False,
                requires_disclosure=True,
                disclosure_notice="Observation timestamp unavailable from source.",
                observed_at=None,
                fetched_at=fetched_at.isoformat() if fetched_at else None,
                last_verified_at=event.last_verified_at,
            )

        # 4. Handle clock skew (observation in future)
        time_diff = (now - observed_dt).total_seconds()
        if time_diff < -policy.max_clock_skew_seconds:
            # Excessive future timestamp -> anomaly
            return FreshnessReport(
                status="unknown",
                age_seconds=int(time_diff),
                is_usable=False,
                is_expired=False,
                requires_disclosure=True,
                disclosure_notice="Observation timestamp is in the future beyond allowable clock skew.",
                observed_at=event.observed_at,
                fetched_at=fetched_at.isoformat() if fetched_at else None,
                last_verified_at=event.last_verified_at,
            )
        elif time_diff < 0:
            # Within clock skew tolerance -> clamp to 0
            age_seconds = 0
        else:
            age_seconds = int(time_diff)

        # 5. Classify based on thresholds
        if age_seconds <= policy.fresh_threshold_seconds:
            status: FreshnessStatus = "fresh"
            is_usable = True
            requires_disclosure = False
            notice = None
        elif age_seconds <= policy.aging_threshold_seconds:
            status = "aging"
            is_usable = True
            requires_disclosure = True
            notice = f"Observation is {age_seconds // 60}m old (aging). Verify road conditions before departure."
        else:
            status = "stale"
            is_usable = False
            requires_disclosure = True
            notice = f"STALE OBSERVATION — {age_seconds // 60}m old. Excluded from active road hazards."

        return FreshnessReport(
            status=status,
            age_seconds=age_seconds,
            is_usable=is_usable,
            is_expired=False,
            requires_disclosure=requires_disclosure,
            disclosure_notice=notice,
            observed_at=event.observed_at,
            fetched_at=fetched_at.isoformat() if fetched_at else None,
            last_verified_at=event.last_verified_at,
        )


freshness_engine = DataFreshnessEngine()
