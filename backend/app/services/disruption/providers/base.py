"""
backend/app/services/disruption/providers/base.py

Abstract base class for disruption intelligence providers (Milestone M3.7).
Enforces capability discovery, timeout handling, and provenance tracking.
"""
from abc import ABC, abstractmethod
from typing import Sequence
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionProviderCapability,
)
from app.services.journey.schemas import TransportMode


class DisruptionProvider(ABC):
    """Abstract base class for live or simulated disruption feeds."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider machine name."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider label."""
        ...

    @abstractmethod
    def get_capabilities(self) -> DisruptionProviderCapability:
        """Returns structured metadata about supported modes, provenance, and live availability."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if provider credentials and network transport are validated."""
        ...

    @abstractmethod
    async def fetch_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        scenario: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[DisruptionEvent]:
        """Fetches active disruptions matching query parameters with bounded timeouts."""
        ...

