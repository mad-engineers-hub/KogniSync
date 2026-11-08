"""Google and Valhalla Encoded Polyline Format encoder and decoder.

Conforms strictly to:
- Google Maps / Routes encoded polyline specification (precision 5, factor 1e5):
  https://developers.google.com/maps/documentation/utilities/polylinealgorithm
- Valhalla OSM shape specification (precision 6, factor 1e6):
  https://valhalla.github.io/valhalla/decoding/
"""
from typing import Any, Sequence
from app.services.maps.schemas import RouteCoordinate


def encode_polyline(
    points: Sequence[tuple[float, float] | RouteCoordinate],
    precision: int = 5,
) -> str:
    """Encodes a list of lat/lng coordinates into an encoded polyline string.
    
    Args:
        points: Sequence of (lat, lng) tuples or RouteCoordinate objects.
        precision: Decimal precision (5 for Google, 6 for Valhalla).
    """
    factor = 10**precision
    encoded_parts: list[str] = []
    prev_lat = 0
    prev_lng = 0

    for pt in points:
        if isinstance(pt, RouteCoordinate):
            lat, lng = pt.latitude, pt.longitude
        else:
            lat, lng = pt[0], pt[1]

        lat_int = round(lat * factor)
        lng_int = round(lng * factor)

        d_lat = lat_int - prev_lat
        d_lng = lng_int - prev_lng

        prev_lat = lat_int
        prev_lng = lng_int

        for delta in (d_lat, d_lng):
            val = ~(delta << 1) if delta < 0 else (delta << 1)
            while val >= 0x20:
                encoded_parts.append(chr((0x20 | (val & 0x1F)) + 63))
                val >>= 5
            encoded_parts.append(chr(val + 63))

    return "".join(encoded_parts)


def decode_polyline(encoded: str, precision: int = 5) -> list[RouteCoordinate]:
    """Decodes an encoded polyline string into a list of RouteCoordinate objects.
    
    Args:
        encoded: Encoded polyline string.
        precision: Decimal precision (5 for Google, 6 for Valhalla).
    """
    if not encoded:
        return []

    factor = float(10**precision)
    points: list[RouteCoordinate] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        # Decode latitude delta
        b = 0
        shift = 0
        result = 0
        while True:
            if index >= length:
                break
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        d_lat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += d_lat

        # Decode longitude delta
        shift = 0
        result = 0
        while True:
            if index >= length:
                break
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        d_lng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += d_lng

        points.append(
            RouteCoordinate(
                latitude=round(lat / factor, 6),
                longitude=round(lng / factor, 6),
            )
        )

    return points


def polyline_to_geojson_coordinates(
    encoded: str, precision: int = 5
) -> list[list[float]]:
    """Decodes polyline directly into GeoJSON [longitude, latitude] coordinates."""
    coords = decode_polyline(encoded, precision=precision)
    return [[c.longitude, c.latitude] for c in coords]


def coordinates_to_geojson_linestring(
    coords: Sequence[RouteCoordinate],
) -> dict[str, Any]:
    """Converts a sequence of RouteCoordinate objects to a GeoJSON LineString dict."""
    return {
        "type": "LineString",
        "coordinates": [[c.longitude, c.latitude] for c in coords],
    }
