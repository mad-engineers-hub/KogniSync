"""
backend/app/core/security.py

JWT bearer-token verification and identity extraction module.
Guarantees:
1. Cryptographic token signature verification using configured algorithm (HS256).
2. Token expiry (exp) and subject (sub) enforcement.
3. Issuer (iss) and Audience (aud) validation when configured.
4. Fails closed in production if JWT_SECRET_KEY is missing.
5. Consistent 401 Unauthorized responses with WWW-Authenticate header.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import logging
import jwt
from fastapi import Header, HTTPException, status
from app.core.config import settings

logger = logging.getLogger("kognisync.security")


def get_jwt_secret() -> str:
    """
    Authoritatively resolves the JWT secret.
    Fails closed in production if JWT_SECRET_KEY is missing or shorter than 32 characters.
    In development and test environments, falls back to a development-only secret if unset.
    """
    if settings.JWT_SECRET_KEY:
        if settings.ENVIRONMENT == "production" and len(settings.JWT_SECRET_KEY.strip()) < 32:
            logger.error("Authentication configuration error: JWT_SECRET_KEY must be at least 32 characters in production.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service misconfigured: secret key too short for production (min 32 bytes required)",
            )
        return settings.JWT_SECRET_KEY

    if settings.ENVIRONMENT == "production":
        logger.error("Authentication configuration error: JWT_SECRET_KEY is missing in production environment.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service misconfigured: secret key missing in production",
        )

    # Insecure fallback strictly for local development and test suite
    return "kognisync_insecure_development_jwt_secret_key_384729"


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
    secret_key_override: Optional[str] = None,
    algorithm_override: Optional[str] = None,
) -> str:
    """
    Issues a signed JWT access token for an authenticated user ID.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if settings.JWT_ISSUER:
        payload["iss"] = settings.JWT_ISSUER
    if settings.JWT_AUDIENCE:
        payload["aud"] = settings.JWT_AUDIENCE
    if extra_claims:
        payload.update(extra_claims)

    secret = secret_key_override or get_jwt_secret()
    alg = algorithm_override or settings.JWT_ALGORITHM
    return jwt.encode(payload, secret, algorithm=alg)


def decode_access_token(
    token: str,
    secret_key_override: Optional[str] = None,
    verify_exp: bool = True,
) -> Dict[str, Any]:
    """
    Cryptographically verifies and decodes a JWT token.
    Enforces signature validity, expiration, subject claim, and optional issuer/audience.
    """
    secret = secret_key_override or get_jwt_secret()
    options: Dict[str, Any] = {
        "verify_signature": True,
        "verify_exp": verify_exp,
        "require": ["exp", "sub"],
    }
    decode_kwargs: Dict[str, Any] = {
        "algorithms": [settings.JWT_ALGORITHM],
        "options": options,
    }
    if settings.JWT_ISSUER:
        decode_kwargs["issuer"] = settings.JWT_ISSUER
    if settings.JWT_AUDIENCE:
        decode_kwargs["audience"] = settings.JWT_AUDIENCE

    try:
        return jwt.decode(token, secret, **decode_kwargs)
    except jwt.ExpiredSignatureError as e:
        logger.warning(f"Bearer token expired: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token has expired"'},
        ) from e
    except jwt.InvalidSignatureError as e:
        logger.warning(f"Bearer token signature invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token signature is invalid"'},
        ) from e
    except (jwt.InvalidIssuerError, jwt.InvalidAudienceError) as e:
        logger.warning(f"Bearer token claims invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims (issuer or audience mismatch)",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from e
    except jwt.PyJWTError as e:
        logger.warning(f"Bearer token decode failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from e


async def get_current_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    FastAPI dependency that enforces JWT Bearer authentication on protected endpoints.
    Extracts and returns the verified user ID (sub claim).
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme; Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token.strip())
    user_id = payload.get("sub")
    if not user_id or not str(user_id).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: subject (sub) claim missing or empty",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(user_id)

