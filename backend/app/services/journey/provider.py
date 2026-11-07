"""
backend/app/services/journey/provider.py

Reusable transport provider interface, error classification, and normalized data contracts.
Part of KogniSync M2.3: Real Transport Provider Integration Foundation.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from app.services.journey.schemas import (
    AttributeProvenanceSchema,
    TransportMode,
)


class ProviderErrorCode(str, Enum):
    """Normalized classification for transport provider failures."""
    TIMEOUT = "timeout"
    AUTH_FAILURE = "auth_failure"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INVALID_REQUEST = "invalid_request"
    EMPTY_RESULT = "empty_result"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_MODE = "unsupported_mode"


class TransportProviderError(Exception):
    """
    Standard exception raised by transport providers.
    Ensures safe error classification without exposing API keys or secrets.
    """
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        provider_id: str,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(f"[{provider_id}] {code.value}: {message}")
        self.code = code
        self.message = message
        self.provider_id = provider_id
        self.details = details or {}
        self.cause = cause


class TransportSegmentSearchRequest(BaseModel):
    """Normalized request passed to an external transport provider adapter."""
    model_config = ConfigDict(populate_by_name=True)

    origin_title: str = Field(validation_alias=AliasChoices("origin_title", "originTitle"), serialization_alias="originTitle")
    origin_city: str = Field(validation_alias=AliasChoices("origin_city", "originCity"), serialization_alias="originCity")
    origin_lat: float = Field(validation_alias=AliasChoices("origin_lat", "originLat"), serialization_alias="originLat")
    origin_lng: float = Field(validation_alias=AliasChoices("origin_lng", "originLng"), serialization_alias="originLng")
    destination_title: str = Field(validation_alias=AliasChoices("destination_title", "destinationTitle"), serialization_alias="destinationTitle")
    destination_city: str = Field(validation_alias=AliasChoices("destination_city", "destinationCity"), serialization_alias="destinationCity")
    destination_lat: float = Field(validation_alias=AliasChoices("destination_lat", "destinationLat"), serialization_alias="destinationLat")
    destination_lng: float = Field(validation_alias=AliasChoices("destination_lng", "destinationLng"), serialization_alias="destinationLng")
    mode: TransportMode
    departure_time: str | None = Field(default=None, validation_alias=AliasChoices("departure_time", "departureTime"), serialization_alias="departureTime")
    arrival_deadline: str | None = Field(default=None, validation_alias=AliasChoices("arrival_deadline", "arrivalDeadline"), serialization_alias="arrivalDeadline")


class NormalizedTransportSegmentResponse(BaseModel):
    """
    Normalized response returned by a transport provider adapter.
    Encapsulates live provider attributes and per-attribute provenance.
    Never leaks raw vendor payloads into public API contracts.
    """
    model_config = ConfigDict(populate_by_name=True)

    provider_id: str = Field(validation_alias=AliasChoices("provider_id", "providerId"), serialization_alias="providerId")
    provider_name: str = Field(validation_alias=AliasChoices("provider_name", "providerName"), serialization_alias="providerName")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        validation_alias=AliasChoices("retrieved_at", "retrievedAt"),
        serialization_alias="retrievedAt",
    )
    mode: TransportMode
    duration_minutes: int | None = Field(default=None, validation_alias=AliasChoices("duration_minutes", "durationMinutes"), serialization_alias="durationMinutes")
    distance_km: float | None = Field(default=None, validation_alias=AliasChoices("distance_km", "distanceKm"), serialization_alias="distanceKm")
    departure_time: str | None = Field(default=None, validation_alias=AliasChoices("departure_time", "departureTime"), serialization_alias="departureTime")
    arrival_time: str | None = Field(default=None, validation_alias=AliasChoices("arrival_time", "arrivalTime"), serialization_alias="arrivalTime")
    fare: float | None = None
    currency: str = "INR"
    carrier_name: str | None = Field(default=None, validation_alias=AliasChoices("carrier_name", "carrierName"), serialization_alias="carrierName")
    vehicle_name: str | None = Field(default=None, validation_alias=AliasChoices("vehicle_name", "vehicleName"), serialization_alias="vehicleName")
    vehicle_number: str | None = Field(default=None, validation_alias=AliasChoices("vehicle_number", "vehicleNumber"), serialization_alias="vehicleNumber")
    warnings: list[str] = Field(default_factory=list)
    attribute_provenance: dict[str, AttributeProvenanceSchema] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("attribute_provenance", "attributeProvenance"),
        serialization_alias="attributeProvenance",
    )


class ProviderCapabilities(BaseModel):
    """Capability and status reporting for a transport provider."""
    model_config = ConfigDict(populate_by_name=True)

    provider_id: str = Field(validation_alias=AliasChoices("provider_id", "providerId"), serialization_alias="providerId")
    name: str
    supported_modes: list[str] = Field(validation_alias=AliasChoices("supported_modes", "supportedModes"), serialization_alias="supportedModes")
    is_available: bool = Field(validation_alias=AliasChoices("is_available", "isAvailable"), serialization_alias="isAvailable")
    is_live_authenticated: bool = Field(validation_alias=AliasChoices("is_live_authenticated", "isLiveAuthenticated"), serialization_alias="isLiveAuthenticated")
    timeout_seconds: float = Field(validation_alias=AliasChoices("timeout_seconds", "timeoutSeconds"), serialization_alias="timeoutSeconds")


class TransportProvider(ABC):
    """
    Abstract contract for external transport providers.
    All external data sources must implement this interface and normalize their responses.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique machine-readable identifier (e.g., 'google_routes')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g., 'Google Routes API v2')."""
        pass

    @property
    @abstractmethod
    def supported_modes(self) -> set[TransportMode]:
        """Set of transport modes supported by this provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Indicates if the provider is active, configured, and ready for queries."""
        pass

    @abstractmethod
    def is_live_authenticated(self) -> bool:
        """Indicates if genuine external credentials are configured."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Returns provider capabilities and configuration status."""
        pass

    @abstractmethod
    async def search_segment(
        self, request: TransportSegmentSearchRequest
    ) -> NormalizedTransportSegmentResponse:
        """
        Queries the external provider for transport metrics on a single leg.
        Raises TransportProviderError on provider errors or unhandled conditions.
        """
        pass
