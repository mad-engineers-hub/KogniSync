from fastapi import APIRouter, HTTPException, status
from app.services.optimizer.schemas import OptimizationRequest, OptimizationResponse
from app.services.optimizer.service import optimizer_service
from app.services.optimizer.metrics import CARBON_FACTORS_KG_PER_KM

router = APIRouter(prefix="/api/v1/optimizer", tags=["Journey Optimizer"])


@router.get("/health")
async def get_optimizer_health():
    """Returns the operational status and emission factor configuration of the optimizer."""
    return {
        "status": "healthy",
        "engine": "Deterministic Multi-Objective Pareto Optimizer",
        "carbon_factors_configured": len(CARBON_FACTORS_KG_PER_KM),
    }


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_journeys(request: OptimizationRequest) -> OptimizationResponse:
    """Computes Pareto-optimal frontier, deterministic scoring, and explanations across candidate journeys."""
    if not request.candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one candidate journey is required for optimization",
        )
    return optimizer_service.optimize_journeys(request)
