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
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import hashlib
import logging
import secrets
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


@dataclass(frozen=True)
class TransitPollPrincipal:
    """Verified operational caller identity and transit-polling capability set."""

    principal_id: str
    can_poll: bool
    can_force: bool


def _extract_jwt_privileges(payload: Dict[str, Any]) -> tuple[bool, bool]:
    role = str(payload.get("role") or "").strip().lower()
    raw_scopes = payload.get("scopes") if payload.get("scopes") is not None else payload.get("scope", "")
    if isinstance(raw_scopes, str):
        scopes = {s.strip().lower() for s in raw_scopes.replace(",", " ").split() if s.strip()}
    elif isinstance(raw_scopes, (list, tuple, set)):
        scopes = {str(s).strip().lower() for s in raw_scopes if str(s).strip()}
    else:
        scopes = set()

    can_force = role in ("admin", "superadmin") or bool(scopes & {"transit:force_poll", "admin"})
    can_poll = can_force or role in ("operator", "ops") or bool(scopes & {"transit:poll", "ops:poll"})
    return can_poll, can_force


async def verify_transit_poll_access(
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
    x_elevated_key: Optional[str] = Header(None, alias="X-Elevated-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> TransitPollPrincipal:
    """
    Fails closed across ALL environments unless valid operational credentials
    (`X-Internal-Key` or an operational Bearer JWT) are supplied.
    Force polling (`force=true`) additionally requires elevated privilege (`X-Elevated-Key`
    or admin/`transit:force_poll` JWT claims).
    """
    if not x_internal_key and not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: operational credentials required for transit feed polling",
            headers={"WWW-Authenticate": "Bearer"},
        )

    can_force = False
    principal_id: str | None = None

    if x_internal_key is not None:
        if not settings.INTERNAL_API_KEY or not secrets.compare_digest(
            x_internal_key, settings.INTERNAL_API_KEY
        ):
            logger.warning("Transit poll access denied: invalid or unconfigured X-Internal-Key")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: invalid or unconfigured operational credentials",
            )
        key_digest = hashlib.sha256(x_internal_key.encode("utf-8")).hexdigest()[:12]
        principal_id = f"internal:{key_digest}"
        if (
            x_elevated_key is not None
            and settings.TRANSIT_POLL_ELEVATED_KEY
            and secrets.compare_digest(x_elevated_key, settings.TRANSIT_POLL_ELEVATED_KEY)
        ):
            can_force = True

    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme; Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        payload = decode_access_token(token.strip())
        jwt_can_poll, jwt_can_force = _extract_jwt_privileges(payload)
        if principal_id is None and not jwt_can_poll:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: operational transit polling role or scope required",
            )
        can_force = can_force or jwt_can_force
        if principal_id is None:
            principal_id = f"jwt:{payload.get('sub')}"

    if x_elevated_key is not None and not can_force:
        logger.warning("Transit poll elevated privilege denied: invalid or unconfigured X-Elevated-Key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: invalid or unconfigured elevated polling credentials",
        )

    return TransitPollPrincipal(
        principal_id=principal_id or "unknown",
        can_poll=True,
        can_force=can_force,
    )

