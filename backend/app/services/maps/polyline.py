"""Google Encoded Polyline Format encoder and decoder.

Conforms strictly to the Google Maps / Routes encoded polyline specification:
https://developers.google.com/maps/documentation/utilities/polylinealgorithm
"""
from typing import Sequence
from app.services.maps.schemas import RouteCoordinate


def encode_polyline(points: Sequence[tuple[float, float] | RouteCoordinate]) -> str:
    """Encodes a list of lat/lng coordinates into a Google encoded polyline string."""
    encoded_parts = []
    prev_lat = 0
    prev_lng = 0

    for pt in points:
        if isinstance(pt, RouteCoordinate):
            lat, lng = pt.latitude, pt.longitude
        else:
            lat, lng = pt[0], pt[1]

        lat_e5 = round(lat * 1e5)
        lng_e5 = round(lng * 1e5)

        d_lat = lat_e5 - prev_lat
        d_lng = lng_e5 - prev_lng

        prev_lat = lat_e5
        prev_lng = lng_e5

        for delta in (d_lat, d_lng):
            val = ~(delta << 1) if delta < 0 else (delta << 1)
            while val >= 0x20:
                encoded_parts.append(chr((0x20 | (val & 0x1F)) + 63))
                val >>= 5
            encoded_parts.append(chr(val + 63))

    return "".join(encoded_parts)


def decode_polyline(encoded: str) -> list[RouteCoordinate]:
    """Decodes a Google encoded polyline string into a list of RouteCoordinate objects."""
    if not encoded:
        return []

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

        points.append(RouteCoordinate(latitude=lat / 1e5, longitude=lng / 1e5))

    return points
