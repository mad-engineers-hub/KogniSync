"""
backend/app/api/routes/auth.py

Development and demonstration authentication routes.
Allows frontend and integration suites to obtain valid signed tokens in development,
while failing closed (404/403) in production environments.
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status
from app.core.config import settings
from app.core.security import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


class DemoTokenRequest(BaseModel):
    user_id: Optional[str] = "usr_demo_traveler"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in_seconds: int = 3600


@router.post("/demo-token", response_model=TokenResponse)
async def get_demo_token(req: DemoTokenRequest = DemoTokenRequest()) -> TokenResponse:
    """
    Issues a valid JWT bearer token for local demonstration and development.
    Strictly disabled and hidden in production environments.
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )

    target_user = req.user_id or "usr_demo_traveler"
    token = create_access_token(subject=target_user)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=target_user,
        expires_in_seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
