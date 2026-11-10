"""
backend/app/services/disruption/providers/gtfs_protobuf.py

Pure-Python Protocol Buffers decoder and encoder for GTFS Realtime feeds (Milestone M3.8.2).
Provides zero-dependency binary protobuf decoding for GTFS-RT FeedMessage payloads:
- FeedHeader (version, timestamp, incrementality)
- FeedEntity (id, is_deleted)
- TripUpdate (trip descriptor, stop time updates, delay)
- Alert (header/description translated strings, cause, effect, active periods)
- VehiclePosition (position lat/lng, congestion level, timestamp)

Adheres strictly to the GTFS Realtime protobuf specification:
https://gtfs.org/documentation/realtime/reference/
"""
from __future__ import annotations

import struct
from typing import Any


# Wire Types in Protocol Buffers
WIRE_VARINT = 0
WIRE_64BIT = 1
WIRE_LENGTH_DELIMITED = 2
WIRE_START_GROUP = 3  # Deprecated
WIRE_END_GROUP = 4    # Deprecated
WIRE_32BIT = 5

# GTFS-RT Cause Enum Mapping
CAUSE_MAP: dict[int, str] = {
    1: "UNKNOWN_CAUSE",
    2: "OTHER_CAUSE",
    3: "TECHNICAL_PROBLEM",
    4: "STRIKE",
    5: "DEMONSTRATION",
    6: "ACCIDENT",
    7: "HOLIDAY",
    8: "WEATHER",
    9: "MAINTENANCE",
    10: "CONSTRUCTION",
    11: "POLICE_ACTIVITY",
    12: "MEDICAL_EMERGENCY",
}

# GTFS-RT Effect Enum Mapping
EFFECT_MAP: dict[int, str] = {
    1: "NO_SERVICE",
    2: "REDUCED_SERVICE",
    3: "SIGNIFICANT_DELAYS",
    4: "DETOUR",
    5: "ADDITIONAL_SERVICE",
    6: "MODIFIED_SERVICE",
    7: "OTHER_EFFECT",
    8: "UNKNOWN_EFFECT",
    9: "STOP_MOVED",
}

# GTFS-RT ScheduleRelationship Enum Mapping
SCHEDULE_RELATIONSHIP_MAP: dict[int, str] = {
    0: "SCHEDULED",
    1: "ADDED",
    2: "UNSCHEDULED",
    3: "CANCELED",
    5: "REPLACEMENT",
    6: "DUPLICATED",
    7: "DELETED",
}

# GTFS-RT CongestionLevel Enum Mapping
CONGESTION_LEVEL_MAP: dict[int, str] = {
    0: "UNKNOWN_CONGESTION_LEVEL",
    1: "RUNNING_SMOOTHLY",
    2: "STOP_AND_GO",
    3: "CONGESTION",
    4: "SEVERE_CONGESTION",
}

# Reverse maps for encoder
CAUSE_REVERSE_MAP = {v: k for k, v in CAUSE_MAP.items()}
EFFECT_REVERSE_MAP = {v: k for k, v in EFFECT_MAP.items()}
SCHEDULE_RELATIONSHIP_REVERSE_MAP = {v: k for k, v in SCHEDULE_RELATIONSHIP_MAP.items()}
CONGESTION_LEVEL_REVERSE_MAP = {v: k for k, v in CONGESTION_LEVEL_MAP.items()}


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decodes an unsigned varint from bytes starting at pos."""
    val = 0
    shift = 0
    length = len(data)
    while pos < length:
        b = data[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, pos
        shift += 7
    raise ValueError("Truncated protobuf varint in feed stream")


def decode_signed_varint32(val: int) -> int:
    """Converts raw 32-bit varint to signed 32-bit integer."""
    val = val & 0xFFFFFFFF
    if val >= 0x80000000:
        return val - 0x100000000
    return val


def decode_fields(data: bytes) -> list[tuple[int, int, Any]]:
    """
    Parses raw protobuf fields into a list of (tag, wire_type, raw_value).
    raw_value is int for wire 0, 8-byte bytes or float for wire 1,
    length-delimited bytes for wire 2, and 4-byte bytes or float for wire 5.
    """
    fields: list[tuple[int, int, Any]] = []
    pos = 0
    length = len(data)

    while pos < length:
        key, pos = decode_varint(data, pos)
        tag = key >> 3
        wire_type = key & 0x07

        if wire_type == WIRE_VARINT:
            val, pos = decode_varint(data, pos)
            fields.append((tag, wire_type, val))
        elif wire_type == WIRE_64BIT:
            if pos + 8 > length:
                raise ValueError("Truncated 64-bit field")
            raw_bytes = data[pos : pos + 8]
            pos += 8
            fields.append((tag, wire_type, raw_bytes))
        elif wire_type == WIRE_LENGTH_DELIMITED:
            field_len, pos = decode_varint(data, pos)
            if pos + field_len > length:
                raise ValueError(f"Truncated length-delimited field of length {field_len}")
            raw_bytes = data[pos : pos + field_len]
            pos += field_len
            fields.append((tag, wire_type, raw_bytes))
        elif wire_type == WIRE_32BIT:
            if pos + 4 > length:
                raise ValueError("Truncated 32-bit field")
            raw_bytes = data[pos : pos + 4]
            pos += 4
            fields.append((tag, wire_type, raw_bytes))
        else:
            raise ValueError(f"Unsupported wire type {wire_type} for tag {tag}")

    return fields


def _decode_string(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _decode_feed_header(raw_bytes: bytes) -> dict[str, Any]:
    header: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            header["gtfs_realtime_version"] = _decode_string(val)
        elif tag == 2:
            header["incrementality"] = val
        elif tag == 3:
            header["timestamp"] = val
    return header


def _decode_translation(raw_bytes: bytes) -> dict[str, str]:
    t: dict[str, str] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            t["text"] = _decode_string(val)
        elif tag == 2:
            t["language"] = _decode_string(val)
    return t


def _decode_translated_string(raw_bytes: bytes) -> dict[str, list[dict[str, str]]]:
    translations: list[dict[str, str]] = []
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            translations.append(_decode_translation(val))
    return {"translation": translations}


def _decode_time_range(raw_bytes: bytes) -> dict[str, int]:
    tr: dict[str, int] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            tr["start"] = val
        elif tag == 2:
            tr["end"] = val
    return tr


def _decode_trip_descriptor(raw_bytes: bytes) -> dict[str, Any]:
    trip: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            trip["trip_id"] = _decode_string(val)
        elif tag == 2:
            trip["start_time"] = _decode_string(val)
        elif tag == 3:
            trip["start_date"] = _decode_string(val)
        elif tag == 4:
            trip["schedule_relationship"] = SCHEDULE_RELATIONSHIP_MAP.get(val, "SCHEDULED")
        elif tag == 5:
            trip["route_id"] = _decode_string(val)
        elif tag == 6:
            trip["direction_id"] = val
    return trip


def _decode_stop_time_event(raw_bytes: bytes) -> dict[str, Any]:
    event: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            event["delay"] = decode_signed_varint32(val)
        elif tag == 2:
            event["time"] = val
        elif tag == 3:
            event["uncertainty"] = decode_signed_varint32(val)
    return event


def _decode_stop_time_update(raw_bytes: bytes) -> dict[str, Any]:
    stu: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            stu["stop_sequence"] = val
        elif tag == 2:
            stu["arrival"] = _decode_stop_time_event(val)
        elif tag == 3:
            stu["departure"] = _decode_stop_time_event(val)
        elif tag == 4:
            stu["stop_id"] = _decode_string(val)
        elif tag == 5:
            stu["schedule_relationship"] = val
    return stu


def _decode_vehicle_descriptor(raw_bytes: bytes) -> dict[str, Any]:
    vd: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            vd["id"] = _decode_string(val)
        elif tag == 2:
            vd["label"] = _decode_string(val)
        elif tag == 3:
            vd["license_plate"] = _decode_string(val)
    return vd


def _decode_trip_update(raw_bytes: bytes) -> dict[str, Any]:
    tu: dict[str, Any] = {"stop_time_update": []}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            tu["trip"] = _decode_trip_descriptor(val)
        elif tag == 2:
            tu["stop_time_update"].append(_decode_stop_time_update(val))
        elif tag == 3:
            tu["vehicle"] = _decode_vehicle_descriptor(val)
        elif tag == 4:
            tu["timestamp"] = val
        elif tag == 5:
            tu["delay"] = decode_signed_varint32(val)
    return tu


def _decode_position(raw_bytes: bytes) -> dict[str, float]:
    pos: dict[str, float] = {}
    for tag, wire_type, val in decode_fields(raw_bytes):
        if tag == 1 and wire_type == WIRE_32BIT:
            pos["latitude"] = round(struct.unpack("<f", val)[0], 6)
        elif tag == 2 and wire_type == WIRE_32BIT:
            pos["longitude"] = round(struct.unpack("<f", val)[0], 6)
        elif tag == 3 and wire_type == WIRE_32BIT:
            pos["bearing"] = round(struct.unpack("<f", val)[0], 2)
        elif tag == 4 and wire_type == WIRE_64BIT:
            pos["odometer"] = struct.unpack("<d", val)[0]
        elif tag == 5 and wire_type == WIRE_32BIT:
            pos["speed"] = round(struct.unpack("<f", val)[0], 2)
    return pos


def _decode_vehicle_position(raw_bytes: bytes) -> dict[str, Any]:
    veh: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            veh["trip"] = _decode_trip_descriptor(val)
        elif tag == 2:
            veh["position"] = _decode_position(val)
        elif tag == 3:
            veh["current_stop_sequence"] = val
        elif tag == 4:
            veh["current_status"] = val
        elif tag == 5:
            veh["timestamp"] = val
        elif tag == 6:
            veh["congestion_level"] = CONGESTION_LEVEL_MAP.get(val, "UNKNOWN_CONGESTION_LEVEL")
        elif tag == 7:
            veh["stop_id"] = _decode_string(val)
        elif tag == 8:
            veh["vehicle"] = _decode_vehicle_descriptor(val)
        elif tag == 9:
            veh["occupancy_status"] = val
    return veh


def _decode_alert(raw_bytes: bytes) -> dict[str, Any]:
    alert: dict[str, Any] = {"active_period": []}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            alert["active_period"].append(_decode_time_range(val))
        elif tag == 3:
            alert["cause"] = CAUSE_MAP.get(val, "UNKNOWN_CAUSE")
        elif tag == 4:
            alert["effect"] = EFFECT_MAP.get(val, "UNKNOWN_EFFECT")
        elif tag == 6:
            alert["header_text"] = _decode_translated_string(val)
        elif tag == 7:
            alert["description_text"] = _decode_translated_string(val)
        elif tag == 10:
            alert["severity_level"] = val
        elif tag == 11:
            alert["timestamp"] = val
    return alert


def _decode_feed_entity(raw_bytes: bytes) -> dict[str, Any]:
    entity: dict[str, Any] = {}
    for tag, _, val in decode_fields(raw_bytes):
        if tag == 1:
            entity["id"] = _decode_string(val)
        elif tag == 2:
            entity["is_deleted"] = bool(val)
        elif tag == 3:
            entity["trip_update"] = _decode_trip_update(val)
        elif tag == 4:
            entity["vehicle"] = _decode_vehicle_position(val)
        elif tag == 5:
            entity["alert"] = _decode_alert(val)
    return entity


def decode_gtfs_feed(data: bytes) -> dict[str, Any]:
    """
    Decodes binary GTFS Realtime Protocol Buffers payload into a standardized
    feed dictionary with 'header' and 'entity' list.
    """
    feed: dict[str, Any] = {"header": {}, "entity": []}
    if not data:
        return feed

    for tag, _, val in decode_fields(data):
        if tag == 1:
            feed["header"] = _decode_feed_header(val)
        elif tag == 2:
            feed["entity"].append(_decode_feed_entity(val))

    return feed


# ==============================================================================
# Protocol Buffers Encoder (for Contract Testing & Live Test Vectors)
# ==============================================================================


def encode_varint(v: int) -> bytes:
    """Encodes integer to unsigned protobuf varint."""
    if v < 0:
        # 64-bit two's complement
        v = (1 << 64) + v
    buf = bytearray()
    while v >= 0x80:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    buf.append(v & 0x7F)
    return bytes(buf)


def _encode_key(tag: int, wire_type: int) -> bytes:
    return encode_varint((tag << 3) | wire_type)


def _encode_varint_field(tag: int, val: int) -> bytes:
    return _encode_key(tag, WIRE_VARINT) + encode_varint(val)


def _encode_string_field(tag: int, val: str) -> bytes:
    b = val.encode("utf-8")
    return _encode_key(tag, WIRE_LENGTH_DELIMITED) + encode_varint(len(b)) + b


def _encode_float_field(tag: int, val: float) -> bytes:
    return _encode_key(tag, WIRE_32BIT) + struct.pack("<f", val)


def _encode_bytes_field(tag: int, payload: bytes) -> bytes:
    return _encode_key(tag, WIRE_LENGTH_DELIMITED) + encode_varint(len(payload)) + payload


def _encode_translation(t: dict[str, str]) -> bytes:
    buf = bytearray()
    if "text" in t:
        buf.extend(_encode_string_field(1, t["text"]))
    if "language" in t:
        buf.extend(_encode_string_field(2, t["language"]))
    return bytes(buf)


def _encode_translated_string(tag: int, ts: dict[str, Any]) -> bytes:
    inner = bytearray()
    for t in ts.get("translation", []):
        inner.extend(_encode_bytes_field(1, _encode_translation(t)))
    return _encode_bytes_field(tag, bytes(inner))


def _encode_time_range(tr: dict[str, int]) -> bytes:
    buf = bytearray()
    if "start" in tr:
        buf.extend(_encode_varint_field(1, tr["start"]))
    if "end" in tr:
        buf.extend(_encode_varint_field(2, tr["end"]))
    return bytes(buf)


def _encode_alert(alert: dict[str, Any]) -> bytes:
    buf = bytearray()
    for ap in alert.get("active_period", []):
        buf.extend(_encode_bytes_field(1, _encode_time_range(ap)))

    cause_val = alert.get("cause")
    if isinstance(cause_val, str):
        cause_val = CAUSE_REVERSE_MAP.get(cause_val, 1)
    if isinstance(cause_val, int):
        buf.extend(_encode_varint_field(3, cause_val))

    effect_val = alert.get("effect")
    if isinstance(effect_val, str):
        effect_val = EFFECT_REVERSE_MAP.get(effect_val, 8)
    if isinstance(effect_val, int):
        buf.extend(_encode_varint_field(4, effect_val))

    if "header_text" in alert and isinstance(alert["header_text"], dict):
        buf.extend(_encode_translated_string(6, alert["header_text"]))
    if "description_text" in alert and isinstance(alert["description_text"], dict):
        buf.extend(_encode_translated_string(7, alert["description_text"]))

    if "timestamp" in alert:
        buf.extend(_encode_varint_field(11, int(alert["timestamp"])))

    return bytes(buf)


def _encode_trip_descriptor(trip: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "trip_id" in trip:
        buf.extend(_encode_string_field(1, str(trip["trip_id"])))
    if "start_time" in trip:
        buf.extend(_encode_string_field(2, str(trip["start_time"])))
    if "start_date" in trip:
        buf.extend(_encode_string_field(3, str(trip["start_date"])))

    sched_rel = trip.get("schedule_relationship")
    if isinstance(sched_rel, str):
        sched_rel = SCHEDULE_RELATIONSHIP_REVERSE_MAP.get(sched_rel, 0)
    if isinstance(sched_rel, int):
        buf.extend(_encode_varint_field(4, sched_rel))

    if "route_id" in trip:
        buf.extend(_encode_string_field(5, str(trip["route_id"])))
    if "direction_id" in trip:
        buf.extend(_encode_varint_field(6, int(trip["direction_id"])))

    return bytes(buf)


def _encode_stop_time_event(tag: int, ste: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "delay" in ste:
        buf.extend(_encode_varint_field(1, int(ste["delay"])))
    if "time" in ste:
        buf.extend(_encode_varint_field(2, int(ste["time"])))
    if "uncertainty" in ste:
        buf.extend(_encode_varint_field(3, int(ste["uncertainty"])))
    return _encode_bytes_field(tag, bytes(buf))


def _encode_stop_time_update(stu: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "stop_sequence" in stu:
        buf.extend(_encode_varint_field(1, int(stu["stop_sequence"])))
    if "arrival" in stu:
        buf.extend(_encode_stop_time_event(2, stu["arrival"]))
    if "departure" in stu:
        buf.extend(_encode_stop_time_event(3, stu["departure"]))
    if "stop_id" in stu:
        buf.extend(_encode_string_field(4, str(stu["stop_id"])))
    if "schedule_relationship" in stu:
        buf.extend(_encode_varint_field(5, int(stu["schedule_relationship"])))
    return bytes(buf)


def _encode_vehicle_descriptor(vd: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "id" in vd:
        buf.extend(_encode_string_field(1, str(vd["id"])))
    if "label" in vd:
        buf.extend(_encode_string_field(2, str(vd["label"])))
    if "license_plate" in vd:
        buf.extend(_encode_string_field(3, str(vd["license_plate"])))
    return bytes(buf)


def _encode_trip_update(tu: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "trip" in tu:
        buf.extend(_encode_bytes_field(1, _encode_trip_descriptor(tu["trip"])))
    for stu in tu.get("stop_time_update", []):
        buf.extend(_encode_bytes_field(2, _encode_stop_time_update(stu)))
    if "vehicle" in tu:
        buf.extend(_encode_bytes_field(3, _encode_vehicle_descriptor(tu["vehicle"])))
    if "timestamp" in tu:
        buf.extend(_encode_varint_field(4, int(tu["timestamp"])))
    if "delay" in tu:
        buf.extend(_encode_varint_field(5, int(tu["delay"])))
    return bytes(buf)


def _encode_position(pos: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "latitude" in pos:
        buf.extend(_encode_float_field(1, float(pos["latitude"])))
    if "longitude" in pos:
        buf.extend(_encode_float_field(2, float(pos["longitude"])))
    if "bearing" in pos:
        buf.extend(_encode_float_field(3, float(pos["bearing"])))
    return bytes(buf)


def _encode_vehicle_position(veh: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "trip" in veh:
        buf.extend(_encode_bytes_field(1, _encode_trip_descriptor(veh["trip"])))
    if "position" in veh:
        buf.extend(_encode_bytes_field(2, _encode_position(veh["position"])))
    if "current_stop_sequence" in veh:
        buf.extend(_encode_varint_field(3, int(veh["current_stop_sequence"])))
    if "current_status" in veh:
        buf.extend(_encode_varint_field(4, int(veh["current_status"])))
    if "timestamp" in veh:
        buf.extend(_encode_varint_field(5, int(veh["timestamp"])))

    cong = veh.get("congestion_level")
    if isinstance(cong, str):
        cong = CONGESTION_LEVEL_REVERSE_MAP.get(cong, 0)
    if isinstance(cong, int):
        buf.extend(_encode_varint_field(6, cong))

    if "stop_id" in veh:
        buf.extend(_encode_string_field(7, str(veh["stop_id"])))
    if "vehicle" in veh:
        buf.extend(_encode_bytes_field(8, _encode_vehicle_descriptor(veh["vehicle"])))
    if "occupancy_status" in veh:
        buf.extend(_encode_varint_field(9, int(veh["occupancy_status"])))

    return bytes(buf)


def _encode_feed_entity(entity: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "id" in entity:
        buf.extend(_encode_string_field(1, str(entity["id"])))
    if "is_deleted" in entity:
        buf.extend(_encode_varint_field(2, 1 if entity["is_deleted"] else 0))
    if "trip_update" in entity:
        buf.extend(_encode_bytes_field(3, _encode_trip_update(entity["trip_update"])))
    if "vehicle" in entity:
        buf.extend(_encode_bytes_field(4, _encode_vehicle_position(entity["vehicle"])))
    if "alert" in entity:
        buf.extend(_encode_bytes_field(5, _encode_alert(entity["alert"])))
    return bytes(buf)


def _encode_feed_header(header: dict[str, Any]) -> bytes:
    buf = bytearray()
    if "gtfs_realtime_version" in header:
        buf.extend(_encode_string_field(1, str(header["gtfs_realtime_version"])))
    if "incrementality" in header:
        buf.extend(_encode_varint_field(2, int(header["incrementality"])))
    if "timestamp" in header:
        buf.extend(_encode_varint_field(3, int(header["timestamp"])))
    return bytes(buf)


def encode_gtfs_feed(feed: dict[str, Any]) -> bytes:
    """Encodes a GTFS Realtime feed dictionary into official Protocol Buffer binary bytes."""
    buf = bytearray()
    if "header" in feed:
        buf.extend(_encode_bytes_field(1, _encode_feed_header(feed["header"])))
    for ent in feed.get("entity", []):
        buf.extend(_encode_bytes_field(2, _encode_feed_entity(ent)))
    return bytes(buf)
