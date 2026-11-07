"""
backend/app/services/location/schemas.py

Pydantic v2 schemas for location services, GPS reverse-geocoding,
and coordinates contracts.
"""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, field_validator
from app.services.journey.schemas import CoordinatesSchema


class ReverseGeocodeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lat: float = Field(..., description="Latitude coordinate between -90 and 90")
    lng: float = Field(..., description="Longitude coordinate between -180 and 180")

    @field_validator("lat")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if v < -90.0 or v > 90.0:
            raise ValueError("Latitude must be between -90 and 90 degrees.")
        return v

    @field_validator("lng")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if v < -180.0 or v > 180.0:
            raise ValueError("Longitude must be between -180 and 180 degrees.")
        return v


class ReverseGeocodeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    formatted_address: str = Field(
        ...,
        validation_alias=AliasChoices("formatted_address", "formattedAddress"),
        serialization_alias="formattedAddress",
        description="User-readable primary address string",
    )
    locality: str | None = Field(
        default=None,
        description="Sub-city neighborhood or locality name (e.g., Indiranagar, Guindy)",
    )
    city: str = Field(
        ...,
        description="Primary municipality or city name (e.g., Bangalore, Chennai)",
    )
    state: str | None = Field(
        default=None,
        description="State or province (e.g., Karnataka, Tamil Nadu)",
    )
    country: str = Field(
        default="India",
        description="Country name",
    )
    coordinates: CoordinatesSchema = Field(
        ...,
        description="Precise WGS-84 coordinates preserved from client device",
    )
    provider: str = Field(
        ...,
        description="Reverse geocoding provider (e.g., 'osm_nominatim', 'kognisync_regional_hub', 'google_geocoding')",
    )
    attribution: str | None = Field(
        default=None,
        description="Legal attribution notice required by geocoding provider (e.g., '© OpenStreetMap contributors')",
    )
    is_estimate: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_estimate", "isEstimate"),
        serialization_alias="isEstimate",
        description="True if location resolved via proximity estimation rather than precise street address",
    )

