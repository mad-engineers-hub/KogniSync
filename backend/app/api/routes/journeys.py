"""
backend/app/api/routes/journeys.py

Canonical multimodal journey orchestration and search endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from app.core.logging import logger
from app.services.journey.schemas import JourneySearchRequest, JourneySearchResponse
from app.services.journey.service import journey_orchestrator
from app.services.disruption.schemas import (
    DisruptionAssessRequest,
    DisruptionRecoverRequest,
    DisruptionRecoveryResponse,
    JourneyDisruptionAssessment,
)
from app.services.disruption.service import disruption_service

router = APIRouter(prefix="/api/v1/journeys", tags=["Journey Orchestration"])


@router.get("/health")
async def get_journey_orchestrator_health():
    """Returns the operational status and supported modes of the journey orchestration engine."""
    return {
        "status": "healthy",
        "service": "Backend Multimodal Journey Orchestration Engine",
        "supported_modes": ["flight", "train", "bus", "cab", "rapido", "metro", "walk", "auto"],
        "archetypes_available": 5,
        "providers_registered": len(journey_orchestrator.transport_providers),
    }


@router.get("/providers")
async def get_transport_providers():
    """Returns registered transport provider adapters, capabilities, and availability status."""
    providers_info = []
    has_live = False
    for p in journey_orchestrator.transport_providers:
        cap = p.get_capabilities().model_dump(by_alias=True)
        is_live = p.is_available()
        cap["liveVerificationStatus"] = "PASS" if is_live else "BLOCKED — credentials unavailable"
        if is_live:
            has_live = True
        providers_info.append(cap)

    return {
        "providers": providers_info,
        "defaultProvider": "google_routes",
        "liveVerificationStatus": "PASS" if has_live else "BLOCKED — credentials unavailable",
    }


@router.post(
    "/search",
    response_model=JourneySearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search, compose, and Pareto-optimize multimodal journeys across transport modes",
)
async def search_journeys(request: JourneySearchRequest) -> JourneySearchResponse:
    """
    Coordinates travel request inputs, hub context resolution, corridor transit speed & fares,
    multimodal composition (first-mile, main transport, last-mile), hard constraint filtering,
    and deterministic Pareto multi-objective ranking.
    """
    try:
        response = await journey_orchestrator.search_journeys(request)
        return response
    except ValueError as e:
        logger.warning(f"Validation error in journey orchestration search: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error in journey orchestration search: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Journey orchestration service encountered an unexpected error. Please verify search parameters.",
        )


@router.post(
    "/{journey_id}/assess-disruptions",
    response_model=JourneyDisruptionAssessment,
    summary="Assess disruptions for a specific journey ID (Milestone M3.7)",
)
async def assess_journey_by_id(
    journey_id: str,
    request: DisruptionAssessRequest,
) -> JourneyDisruptionAssessment:
    """Evaluates active disruptions affecting the provided journey payload."""
    try:
        return await disruption_service.assess_journey_disruptions(
            journey=request.journey,
            include_simulated=request.include_simulated,
            scenario=request.scenario,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error assessing journey {journey_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assess disruptions for the requested journey.",
        )


@router.post(
    "/{journey_id}/recover",
    response_model=DisruptionRecoveryResponse,
    summary="Generate recovery recommendations for a specific journey ID (Milestone M3.7)",
)
async def recover_journey_by_id(
    journey_id: str,
    request: DisruptionRecoverRequest,
) -> DisruptionRecoveryResponse:
    """Generates Pareto-ranked recovery alternatives for the disrupted journey."""
    try:
        return await disruption_service.recover_journey(
            journey=request.journey,
            budget_max=request.budget_max,
            preferred_arrival_before=request.preferred_arrival_before,
            include_simulated=request.include_simulated,
            scenario=request.scenario,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error recovering journey {journey_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recovery alternatives for the requested journey.",
        )

