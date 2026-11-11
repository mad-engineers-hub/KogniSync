"""
backend/app/api/routes/disruptions.py

Real-Time Journey Disruption Intelligence and Recovery endpoints (Milestone M3.7).
Provides provider discovery, active disruption querying, deterministic impact assessment,
and Pareto-ranked recovery recommendations.
"""
from collections import defaultdict, deque
import threading
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.config import settings
from app.core.logging import logger
from app.core.security import TransitPollPrincipal, verify_transit_poll_access
from app.services.disruption.schemas import (
    DisruptionAssessRequest,
    DisruptionEvent,
    DisruptionProviderCapability,
    DisruptionRecoverRequest,
    DisruptionRecoveryResponse,
    GTFSFeedListResponse,
    GTFSFeedStatus,
    JourneyDisruptionAssessment,
)
from app.services.disruption.service import disruption_service
from app.services.disruption.providers.gtfs_registry import gtfs_feed_registry

router = APIRouter(prefix="/api/v1/disruptions", tags=["Disruption Intelligence"])


@router.get(
    "/health",
    summary="Health and operational status of the disruption intelligence service",
)
async def get_disruption_health():
    capabilities = disruption_service.get_provider_capabilities()
    feed_statuses = gtfs_feed_registry.get_feed_statuses()
    has_live = any(c.is_available and c.provenance_source == "provider_live" for c in capabilities)
    has_live_transit = any(s.connectivity_status == "available" for s in feed_statuses)
    return {
        "status": "healthy",
        "service": "Real-Time Disruption Intelligence & Recovery Service",
        "providers_registered": len(capabilities),
        "live_provider_connected": has_live,
        "live_transit_connected": has_live_transit,
        "gtfs_feeds_registered": len(feed_statuses),
        "gtfs_feeds_operational": sum(1 for s in feed_statuses if s.connectivity_status == "available"),
        "simulation_active": any(c.name == "simulation_engine" for c in capabilities),
        "liveVerificationStatus": "PASS" if has_live else "BLOCKED — credentials unavailable",
    }


@router.get(
    "/providers",
    response_model=list[DisruptionProviderCapability],
    summary="Discover registered disruption providers and capabilities",
)
async def get_disruption_providers() -> list[DisruptionProviderCapability]:
    """Returns capabilities, supported transport modes, and availability status of all disruption adapters."""
    return disruption_service.get_provider_capabilities()


def _build_gtfs_feed_list_response() -> GTFSFeedListResponse:
    statuses = gtfs_feed_registry.get_feed_statuses()
    operational_count = sum(1 for s in statuses if s.connectivity_status == "available")
    configured_count = sum(1 for s in statuses if s.enabled and s.connectivity_status != "unconfigured")
    pending_count = sum(1 for s in statuses if s.authorization_status == "pending_credentials")

    if operational_count > 0:
        notice = f"Verified {operational_count} operational transit feed(s)."
    elif pending_count > 0:
        notice = (
            f"No live GTFS Realtime feeds are currently verified and operational "
            f"({pending_count} registered feed(s) awaiting agency credentials)."
        )
    else:
        notice = "No live GTFS Realtime feeds are currently verified and operational."

    return GTFSFeedListResponse(
        feeds=statuses,
        total_configured=configured_count,
        total_operational=operational_count,
        notice=notice,
    )


@router.get(
    "/providers/feeds",
    response_model=GTFSFeedListResponse,
    summary="Inspect sanitized operational status of all registered GTFS Realtime feeds",
)
async def get_registered_gtfs_feeds() -> GTFSFeedListResponse:
    """
    Returns sanitized operational status and diagnostics for registered public-transit GTFS/IUDX feeds.
    Strictly masks server-side tokens and sensitive endpoint query parameters.
    """
    return _build_gtfs_feed_list_response()


class PollRateLimiter:
    """Thread-safe sliding-window rate limiter & force-poll abuse guard for operational polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests_by_principal: dict[str, deque[float]] = defaultdict(deque)
        self._global_requests: deque[float] = deque()
        self._last_force_poll_at: float | None = None

    def reset(self) -> None:
        with self._lock:
            self._requests_by_principal.clear()
            self._global_requests.clear()
            self._last_force_poll_at = None

    def check_and_record(self, principal_id: str, force: bool = False) -> None:
        now = time.monotonic()
        window = max(1, int(settings.TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS))
        max_requests = max(1, int(settings.TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS))
        force_min_interval = max(0.0, float(settings.TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS))

        with self._lock:
            if force and self._last_force_poll_at is not None:
                elapsed_since_force = now - self._last_force_poll_at
                if elapsed_since_force < force_min_interval:
                    retry_after = max(1, int(force_min_interval - elapsed_since_force + 0.999))
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many forced transit feed poll requests; cooldown floor active.",
                        headers={"Retry-After": str(retry_after)},
                    )

            cutoff = now - window
            bucket = self._requests_by_principal[principal_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            while self._global_requests and self._global_requests[0] <= cutoff:
                self._global_requests.popleft()

            # Apply per-caller limit plus bounded global ceiling (2x per-caller ceiling)
            if len(bucket) >= max_requests or len(self._global_requests) >= (max_requests * 2):
                oldest = bucket[0] if bucket else self._global_requests[0]
                retry_after = max(1, int(window - (now - oldest) + 0.999))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many transit feed poll requests; rate limit exceeded.",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)
            self._global_requests.append(now)
            if force:
                self._last_force_poll_at = now


poll_rate_limiter = PollRateLimiter()


@router.post(
    "/providers/feeds/poll",
    response_model=GTFSFeedListResponse,
    summary="Trigger controlled polling cycle for enabled authorized transit feeds",
)
async def poll_registered_gtfs_feeds(
    force: bool = Query(False, description="Bypass per-feed polling cooldown interval when true"),
    principal: TransitPollPrincipal = Depends(verify_transit_poll_access),
) -> GTFSFeedListResponse:
    """
    Executes an operationally authorized poll across enabled transit feeds using IP-pinned SSRF transport.
    Requires server-side operational credentials, elevated privilege for `force=true`,
    and enforces strict sliding-window rate limiting to prevent upstream provider abuse.
    """
    if force and not principal.can_force:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: elevated operational privilege required for force polling",
        )
    poll_rate_limiter.check_and_record(principal.principal_id, force=force)
    await gtfs_feed_registry.poll_all_enabled_feeds(force=force)
    return _build_gtfs_feed_list_response()


@router.get(
    "",
    response_model=list[DisruptionEvent],
    summary="Fetch active disruption events",
)
async def get_disruptions(
    corridor: Optional[str] = Query(None, description="Optional corridor filter (e.g. 'NH-75', 'Chennai-Bengaluru')"),
    scenario: Optional[str] = Query(None, description="Optional demonstration scenario (e.g. 'shiradi_ghat', 'silk_board')"),
    include_simulated: bool = Query(True, description="Whether to include simulated demo disruptions"),
    bbox: Optional[str] = Query(None, description="Optional bounding box 'minLon,minLat,maxLon,maxLat'"),
) -> list[DisruptionEvent]:
    """Returns active disruption incidents matching filters, with explicit provenance tagging."""
    parsed_bbox: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) == 4:
                parsed_bbox = (parts[0], parts[1], parts[2], parts[3])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bbox format. Expected 'minLon,minLat,maxLon,maxLat' with valid floats.",
            )

    try:
        events = await disruption_service.get_active_disruptions(
            corridor=corridor,
            scenario=scenario,
            include_simulated=include_simulated,
            bbox=parsed_bbox,
        )
        return events
    except Exception as e:
        logger.error(f"Error fetching disruptions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active disruptions from registered providers.",
        )


@router.post(
    "/assess",
    response_model=JourneyDisruptionAssessment,
    summary="Assess disruption impact on a multimodal journey",
)
async def assess_journey(request: DisruptionAssessRequest) -> JourneyDisruptionAssessment:
    """
    Evaluates active disruptions against journey segments.
    Computes delay, arrival time slip, transfer buffer erosion, and connection risk.
    """
    try:
        assessment = await disruption_service.assess_journey_disruptions(
            journey=request.journey,
            include_simulated=request.include_simulated,
            scenario=request.scenario,
        )
        return assessment
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error assessing journey disruptions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Disruption assessment service encountered an unexpected error.",
        )


@router.post(
    "/recover",
    response_model=DisruptionRecoveryResponse,
    summary="Generate Pareto-ranked recovery alternatives for a disrupted journey",
)
async def recover_journey(request: DisruptionRecoverRequest) -> DisruptionRecoveryResponse:
    """
    Generates feasible recovery options (mode shifts, highway detours, schedule advances),
    evaluates hard constraints, and ranks recommendations via the deterministic Pareto engine.
    """
    try:
        response = await disruption_service.recover_journey(
            journey=request.journey,
            budget_max=request.budget_max,
            preferred_arrival_before=request.preferred_arrival_before,
            include_simulated=request.include_simulated,
            scenario=request.scenario,
        )
        return response
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error generating journey recovery recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Journey recovery service encountered an unexpected error.",
        )

