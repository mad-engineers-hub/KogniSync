"""
backend/app/services/disruption/providers/iudx_adapter.py

Adapter converting IUDX (India Urban Data Exchange) NGSI-LD JSON transit payloads
into normalized GTFS Realtime feed dictionaries (Milestone M4.0).

Supports documented IUDX cOS Resource Server response envelopes and Indian transit
schemas observed across IUDX catalogues (e.g., BMTC Bengaluru `tripInfo` / `positionInfo`
/ `vehicleInfo`, Surat & Chandigarh ITMS `trip_delay` / `last_stop_id` / GeoJSON `location`).
Never fabricates measurements, congestion levels, or coordinates when omitted upstream.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _safe_finite_float(value: Any) -> float | None:
    """Converts value to a finite float or returns None (blocks NaN/Inf/bool)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def parse_timestamp_to_epoch(value: Any) -> int | None:
    """
    Converts ISO-8601 string or numeric epoch seconds/milliseconds into integer Unix seconds.
    Policy: timezone-naive ISO-8601 strings are interpreted as UTC; offset-aware timestamps
    are normalized to UTC Unix epoch seconds. Non-finite floats (NaN/Inf) return None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if not math.isfinite(ts):
            return None
        # Convert millisecond epochs (> 1e12) safely to seconds
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        if ts <= 0:
            return None
        return int(ts)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return parse_timestamp_to_epoch(int(text))
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            return None
    return None


def _extract_iudx_coordinates(item: dict[str, Any], pos_info: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extracts finite (latitude, longitude) from NGSI-LD GeoJSON `location` or `positionInfo`."""
    # 1. Explicit positionInfo lat/lng
    raw_lat = pos_info.get("latitude") if pos_info.get("latitude") is not None else pos_info.get("lat")
    raw_lng = pos_info.get("longitude") if pos_info.get("longitude") is not None else pos_info.get("lon")
    lat = _safe_finite_float(raw_lat)
    lng = _safe_finite_float(raw_lng)
    if lat is not None and lng is not None:
        return lat, lng

    # 2. NGSI-LD GeoJSON location: {"type": "Point", "coordinates": [lng, lat]}
    loc = item.get("location")
    if isinstance(loc, dict):
        # Some NGSI-LD responses wrap value in {"type": "GeoProperty", "value": {"type": "Point", ...}}
        if "value" in loc and isinstance(loc["value"], dict):
            loc = loc["value"]
        coords = loc.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            geo_lat = _safe_finite_float(coords[1])
            geo_lng = _safe_finite_float(coords[0])  # GeoJSON is [lon, lat]
            if geo_lat is not None and geo_lng is not None:
                return geo_lat, geo_lng

    # 3. Direct top-level latitude/longitude
    top_lat = _safe_finite_float(item.get("latitude"))
    top_lng = _safe_finite_float(item.get("longitude"))
    if top_lat is not None and top_lng is not None:
        return top_lat, top_lng

    return None, None


def _unwrap_ngsi_value(field: Any) -> Any:
    """Unwraps NGSI-LD Property dicts (`{"type": "Property", "value": ...}`) cleanly."""
    if isinstance(field, dict) and "value" in field and "type" in field and field.get("type") in (
        "Property",
        "GeoProperty",
        "Relationship",
    ):
        return field["value"]
    return field


def is_iudx_payload(data: Any) -> bool:
    """Detects whether a decoded JSON payload matches IUDX cOS NGSI-LD transit structures."""
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            return True
        if isinstance(data.get("type"), str) and data["type"].startswith("urn:dx:"):
            return True
        if "@context" in data and ("observationDateTime" in data or "positionInfo" in data or "tripInfo" in data):
            return True
        if any(k in data for k in ("observationDateTime", "positionInfo", "tripInfo", "vehicleInfo", "trip_delay")):
            return True
        return False

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        sample = data[0]
        if any(k in sample for k in ("observationDateTime", "positionInfo", "tripInfo", "vehicleInfo", "trip_delay")):
            return True
    return False


def normalize_iudx_payload(data: Any) -> dict[str, Any]:
    """
    Normalizes an IUDX NGSI-LD JSON response into a GTFS-RT-compatible FeedMessage dict:
    `{"header": {"gtfs_realtime_version": "2.0", "timestamp": ...}, "entity": [...]}`
    """
    if isinstance(data, dict):
        err_type = str(data.get("type", ""))
        if err_type.startswith("urn:dx:") and "Success" not in err_type and "results" not in data:
            title = data.get("title") or err_type
            detail = data.get("detail") or ""
            raise ValueError(f"IUDX API error ({title}): {detail}".strip(": "))

        if isinstance(data.get("results"), list):
            records = data["results"]
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("Invalid IUDX JSON payload: expected object or array")

    entities: list[dict[str, Any]] = []
    max_ts: int | None = None

    for idx, raw_item in enumerate(records):
        if not isinstance(raw_item, dict):
            continue

        try:
            item = {k: _unwrap_ngsi_value(v) for k, v in raw_item.items()}
            pos_info = item.get("positionInfo") if isinstance(item.get("positionInfo"), dict) else {}
            trip_info = item.get("tripInfo") if isinstance(item.get("tripInfo"), dict) else {}
            veh_info = item.get("vehicleInfo") if isinstance(item.get("vehicleInfo"), dict) else {}

            # Extract entity identifier
            raw_id = (
                item.get("entity_id")
                or veh_info.get("vehicle_id")
                or veh_info.get("id")
                or item.get("vehicle_id")
                or item.get("id")
                or trip_info.get("trip_id")
                or item.get("trip_id")
                or f"iudx-item-{idx}"
            )
            base_id = str(raw_id)

            # Extract observation timestamp
            obs_ts = (
                parse_timestamp_to_epoch(item.get("observationDateTime"))
                or parse_timestamp_to_epoch(pos_info.get("timestamp"))
                or parse_timestamp_to_epoch(trip_info.get("timestamp"))
                or parse_timestamp_to_epoch(item.get("timestamp"))
            )
            if obs_ts is not None and (max_ts is None or obs_ts > max_ts):
                max_ts = obs_ts

            # Extract trip & route metadata without inventing values
            trip_id = str(trip_info.get("trip_id") or trip_info.get("tripId") or item.get("trip_id") or "")
            route_id = str(
                trip_info.get("route_id")
                or trip_info.get("routeId")
                or item.get("route_id")
                or item.get("routeId")
                or ""
            )
            route_short_name = str(item.get("route_short_name") or trip_info.get("route_short_name") or "")
            effective_route = route_id or route_short_name
            stop_id = str(
                item.get("stop_id")
                or item.get("last_stop_id")
                or pos_info.get("stop_id")
                or trip_info.get("stop_id")
                or ""
            )
            sched_rel = trip_info.get("schedule_relationship") or item.get("schedule_relationship")

            # 1. VehiclePosition entity (when coordinates or vehicleInfo present)
            lat, lng = _extract_iudx_coordinates(item, pos_info)
            congestion = (
                pos_info.get("congestion_level")
                or pos_info.get("congestionLevel")
                or item.get("congestion_level")
                or item.get("congestionLevel")
            )
            speed = _safe_finite_float(pos_info.get("speed") if pos_info.get("speed") is not None else item.get("speed"))
            bearing = _safe_finite_float(
                pos_info.get("bearing") if pos_info.get("bearing") is not None else item.get("bearing")
            )

            veh_label = (
                veh_info.get("label")
                or veh_info.get("vehicle_label")
                or item.get("vehicle_label")
                or veh_info.get("license_plate")
                or item.get("license_plate")
            )
            veh_plate = veh_info.get("license_plate") or item.get("license_plate")

            if lat is not None and lng is not None:
                position_dict: dict[str, Any] = {"latitude": lat, "longitude": lng}
                if speed is not None:
                    position_dict["speed"] = speed
                if bearing is not None:
                    position_dict["bearing"] = bearing

                vehicle_entity: dict[str, Any] = {
                    "trip": {
                        **({"trip_id": trip_id} if trip_id else {}),
                        **({"route_id": effective_route} if effective_route else {}),
                        **({"schedule_relationship": str(sched_rel)} if sched_rel else {}),
                    },
                    "vehicle": {
                        "id": str(veh_info.get("vehicle_id") or item.get("vehicle_id") or base_id),
                        **({"label": str(veh_label)} if veh_label else {}),
                        **({"license_plate": str(veh_plate)} if veh_plate else {}),
                    },
                    "position": position_dict,
                    **({"stop_id": stop_id} if stop_id else {}),
                    **({"congestion_level": str(congestion)} if congestion else {}),
                    **({"timestamp": obs_ts} if obs_ts is not None else {}),
                }
                entities.append({"id": base_id, "vehicle": vehicle_entity})

            # 2. TripUpdate entity (when trip_delay/delay or cancellation relationship is reported)
            raw_delay = (
                trip_info.get("delay")
                if trip_info.get("delay") is not None
                else (
                    item.get("trip_delay")
                    if item.get("trip_delay") is not None
                    else item.get("delay")
                )
            )
            delay_val: int | None = None
            finite_delay = _safe_finite_float(raw_delay)
            if finite_delay is not None:
                delay_val = int(finite_delay)

            if delay_val is not None or (sched_rel and str(sched_rel).upper() in ("CANCELED", "SKIPPED", "NO_SERVICE")):
                tu_dict: dict[str, Any] = {
                    "trip": {
                        **({"trip_id": trip_id} if trip_id else {}),
                        **({"route_id": effective_route} if effective_route else {}),
                        "schedule_relationship": str(sched_rel or "SCHEDULED").upper(),
                    },
                    **({"delay": delay_val} if delay_val is not None else {}),
                    **({"timestamp": obs_ts} if obs_ts is not None else {}),
                }
                if stop_id:
                    tu_dict["stop_time_update"] = [
                        {
                            "stop_id": stop_id,
                            **({"arrival": {"delay": delay_val}} if delay_val is not None else {}),
                        }
                    ]
                entities.append({"id": f"{base_id}-tu", "trip_update": tu_dict})

            # 3. Alert entity if explicit alert payload is embedded
            if "alert" in item and isinstance(item["alert"], dict):
                entities.append({"id": f"{base_id}-alert", "alert": item["alert"]})
        except Exception:
            # Isolate malformed individual records without crashing valid sibling entries
            continue

    header: dict[str, Any] = {"gtfs_realtime_version": "2.0", "source_format": "iudx_ngsi_ld"}
    if max_ts is not None:
        header["timestamp"] = max_ts

    return {"header": header, "entity": entities}

