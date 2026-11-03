from fastapi import APIRouter, HTTPException, status
from app.services.maps.schemas import (
    EnrichedJourneyRoute,
    MapsHealthResponse,
    RouteEnrichRequest,
)
from app.services.maps.service import maps_service

router = APIRouter(prefix="/api/v1/routes", tags=["Routes & Maps"])


@router.get("/health", response_model=MapsHealthResponse)
async def get_routes_health() -> MapsHealthResponse:
    """Returns the operational status and active backend provider for the maps/routes engine."""
    return maps_service.get_health()


@router.post("/enrich", response_model=EnrichedJourneyRoute)
async def enrich_journey_route(request: RouteEnrichRequest) -> EnrichedJourneyRoute:
    """Enriches a multi-modal journey's segments with spatial route geometry and polyline data."""
    if not request.segments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journey must contain at least one segment to enrich",
        )
    return await maps_service.enrich_journey_route(request)

