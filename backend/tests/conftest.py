"""
Shared pytest configuration for KogniSync backend tests.

Generates an ephemeral random per-session JWT_SECRET_KEY only if the test
environment has not explicitly configured a valid (>= 32 char) key.
This replaces the removed hardcoded development fallback secret without
compromising fail-closed production or unconfigured-environment checks.
"""
import os
import secrets
import pytest


def _ensure_ephemeral_test_jwt_secret() -> str | None:
    from app.core.config import settings
    from app.core.security import is_forbidden_jwt_secret

    current = settings.JWT_SECRET_KEY or os.environ.get("JWT_SECRET_KEY")
    if (
        settings.ENVIRONMENT != "production"
        and (
            not current
            or len(current.strip()) < 32
            or is_forbidden_jwt_secret(current)
        )
    ):
        ephemeral = f"ephemeral_pytest_{secrets.token_urlsafe(36)}"
        os.environ["JWT_SECRET_KEY"] = ephemeral
        settings.JWT_SECRET_KEY = ephemeral
        return ephemeral
    return None


@pytest.fixture(scope="session", autouse=True)
def ephemeral_test_jwt_secret():
    """Provide a fresh per-test-session random JWT signing key when none is configured."""
    generated = _ensure_ephemeral_test_jwt_secret()
    yield generated


@pytest.fixture
def anyio_backend():
    """Ensure anyio tests run exclusively against asyncio."""
    return "asyncio"
