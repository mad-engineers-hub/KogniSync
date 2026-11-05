"""
backend/app/api/routes/auth.py

Development and demonstration authentication routes.
Allows frontend and integration suites to obtain valid signed tokens in development,
while failing closed (404 Not Found) in production environments.

Security Invariants:
1. Gated: Returns 404 in production; never accessible on production deployments.
2. Anti-impersonation: Only issues tokens for designated demo identities (usr_demo_*).
   Arbitrary real or existing user IDs cannot be acquired through this endpoint.
3. Short-lived: Demo tokens have an explicit short TTL of 15 minutes (900s).
"""
from datetime import timedelta
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status
from app.core.config import settings
from app.core.security import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

DEMO_TOKEN_EXPIRE_SECONDS = 900  # 15 minutes explicitly configured TTL
ALLOWED_DEMO_PREFIX = "usr_demo_"


class DemoTokenRequest(BaseModel):
    user_id: Optional[str] = "usr_demo_traveler"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in_seconds: int = DEMO_TOKEN_EXPIRE_SECONDS


@router.post("/demo-token", response_model=TokenResponse)
async def get_demo_token(req: DemoTokenRequest = DemoTokenRequest()) -> TokenResponse:
    """
    Issues a valid JWT bearer token for local demonstration and development.
    Strictly disabled and hidden (404) in production environments.
    Restricted strictly to designated demo identities (usr_demo_*).
    """
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )

    target_user = req.user_id or "usr_demo_traveler"

    # Anti-impersonation check: refuse to issue tokens for arbitrary real or existing users
    if target_user != "usr_demo_traveler" and not target_user.startswith(ALLOWED_DEMO_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: demo token issuance is restricted to designated demo identities (usr_demo_*).",
        )

    token = create_access_token(
        subject=target_user,
        expires_delta=timedelta(seconds=DEMO_TOKEN_EXPIRE_SECONDS),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=target_user,
        expires_in_seconds=DEMO_TOKEN_EXPIRE_SECONDS,
    )
