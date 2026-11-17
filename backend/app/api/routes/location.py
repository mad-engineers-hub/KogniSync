"""
backend/app/api/routes/location.py

Location services API routes for GPS reverse-geocoding, starting-location autofill,
and spatial coordinate resolution.
"""
from fastapi import APIRouter, Query, HTTPException, status
from app.services.location.schemas import ReverseGeocodeResponse, GeocodeResponse
from app.services.location.service import location_service

router = APIRouter(prefix="/api/v1/location", tags=["Location Services"])


@router.get(
    "/reverse-geocode",
    response_model=ReverseGeocodeResponse,
    summary="Reverse geocode GPS coordinates into human-readable location",
)
async def reverse_geocode(
    lat: float = Query(..., ge=-90.0, le=90.0, description="WGS-84 Latitude (-90 to 90)"),
    lng: float = Query(..., ge=-180.0, le=180.0, description="WGS-84 Longitude (-180 to 180)"),
) -> ReverseGeocodeResponse:
    """
    Reverse-geocodes client GPS coordinates into a normalized place name, locality, and city.
    Uses live OpenStreetMap Nominatim or regional hub proximity matching while preserving precise coordinates.
    """
    try:
        return await location_service.reverse_geocode(lat=lat, lng=lng)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reverse geocode coordinates.",
        )


@router.get(
    "/geocode",
    response_model=GeocodeResponse,
    summary="Forward geocode a place or city name into coordinates",
)
async def geocode_location(
    q: str = Query(..., min_length=1, description="Place or city name to geocode"),
) -> GeocodeResponse:
    """Forward-geocodes a city or place name into WGS-84 coordinates."""
    try:
        res = await location_service.geocode(q)
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Location '{q}' could not be resolved to geographic coordinates.",
            )
        return res
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to geocode location: {exc}",
        )


