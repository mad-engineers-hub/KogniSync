"""
backend/tests/test_gtfs_provider.py

Contract and unit tests for GTFSRealtimeProvider (Milestone M3.8).
Verifies:
1. Capability discovery reports BLOCKED when feed is unconfigured.
2. Trip Updates parsing (delay, schedule cancellation).
3. Service Alerts parsing (cause, effect, active periods, translation).
4. Stale feed detection via header timestamp age (> 10m rejected).
5. Network timeout and HTTP failure handling.
6. Malformed JSON entities handled defensively without crash.
"""
import time
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
from app.services.disruption.providers.gtfs_realtime import (
    GTFSRealtimeProvider,
    MAX_GTFS_FEED_AGE_SECONDS,
)


@pytest.fixture
def mock_gtfs_payload():
    now_ts = int(time.time())
    return {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts - 60,  # 1 minute ago (fresh)
        },
        "entity": [
            {
                "id": "alert-101",
                "alert": {
                    "header_text": {"translation": [{"text": "BMRCL Purple Line Maintenance", "language": "en"}]},
                    "description_text": {"translation": [{"text": "Power block between MG Road and Indiranagar", "language": "en"}]},
                    "cause": "MAINTENANCE",
                    "effect": "SIGNIFICANT_DELAYS",
                    "active_period": [{"start": now_ts - 1800, "end": now_ts + 7200}],
                },
            },
            {
                "id": "tu-202",
                "trip_update": {
                    "trip": {
                        "trip_id": "BMTC-500D-01",
                        "route_id": "500D",
                        "schedule_relationship": "SCHEDULED",
                    },
                    "stop_time_update": [
                        {"stop_sequence": 5, "arrival": {"delay": 900}},  # 15 min delay
                        {"stop_sequence": 6, "departure": {"delay": 1200}},  # 20 min delay
                    ],
                },
            },
            {
                "id": "tu-cancel-303",
                "trip_update": {
                    "trip": {
                        "trip_id": "IR-12658-SBC",
                        "route_id": "SBC-MAS",
                        "schedule_relationship": "CANCELED",
                    },
                },
            },
        ],
    }


def test_gtfs_unconfigured_discovery():
    provider = GTFSRealtimeProvider(feed_url=None)
    assert provider.is_configured() is False
    assert provider.is_available() is False
    assert provider.get_connectivity_status() == "unconfigured"

    cap = provider.get_capabilities()
    assert cap.is_available is False
    assert "BLOCKED — authorized GTFS Realtime feed unavailable" in cap.status_notice
    assert cap.provenance_source == "unknown"


@pytest.mark.anyio
async def test_gtfs_fetch_success(mock_gtfs_payload):
    provider = GTFSRealtimeProvider(
        feed_url="https://transit.example.gov/gtfs-rt.json",
        api_key="mock-transit-token",
    )
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        assert provider.is_configured() is True
        assert provider.is_available() is True

        import json
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_gtfs_payload
        mock_resp.content = json.dumps(mock_gtfs_payload).encode("utf-8")
        mock_resp.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp

            events = await provider.fetch_disruptions()

            # Assert contract headers
            mock_get.assert_called_once()
            call_headers = mock_get.call_args[1]["headers"]
            assert call_headers["Authorization"] == "Bearer mock-transit-token"

            # Assert parsed entities
            assert len(events) == 3

            # Alert entity
            alert_ev = next(e for e in events if e.id == "gtfs-alert-alert-101")
            assert alert_ev.event_type == "transport_delay"
            assert alert_ev.severity == "critical"  # SIGNIFICANT_DELAYS -> critical
            assert "BMRCL Purple Line Maintenance" in alert_ev.title
            assert alert_ev.provenance == "provider_live"

            # Trip update delay entity
            tu_ev = next(e for e in events if e.id == "gtfs-delay-tu-202")
            assert tu_ev.event_type == "transport_delay"
            assert tu_ev.estimated_delay_minutes == 20  # Max delay 1200s // 60
            assert tu_ev.delay_seconds == 1200
            assert tu_ev.provenance == "provider_live"

            # Canceled trip entity
            cancel_ev = next(e for e in events if e.id == "gtfs-cancel-tu-cancel-303")
            assert cancel_ev.event_type == "service_cancellation"
            assert cancel_ev.severity == "critical"
            assert "Canceled" in cancel_ev.title


def test_gtfs_stale_feed_rejection():
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.json")
    stale_ts = int(time.time()) - (MAX_GTFS_FEED_AGE_SECONDS + 300)  # 15 minutes old
    stale_payload = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": stale_ts,
        },
        "entity": [
            {
                "id": "alert-stale",
                "alert": {"header_text": {"translation": [{"text": "Stale Alert"}]}},
            }
        ],
    }

    events = provider.parse_gtfs_payload(stale_payload)
    # Stale feed must be rejected according to specification
    assert events == []


@pytest.mark.anyio
async def test_gtfs_timeout_and_error_handling():
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.json")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ReadTimeout("Read timed out")
            events = await provider.fetch_disruptions()
            assert events == []
            assert provider._consecutive_failure_count == 1
            cap = provider.get_capabilities()
            assert cap.consecutive_failure_count == 1


def test_gtfs_ssrf_protections():
    from app.services.disruption.providers.gtfs_realtime import is_ssrf_safe_url

    # Insecure HTTP
    safe, msg = is_ssrf_safe_url("http://transit.example.gov/feed.json", allow_http=False)
    assert safe is False
    assert "Insecure HTTP scheme" in msg

    # Localhost
    safe, msg = is_ssrf_safe_url("https://localhost:8000/feed.json")
    assert safe is False
    assert "SSRF Protection" in msg

    # Loopback IP
    safe, msg = is_ssrf_safe_url("https://127.0.0.1/feed.json")
    assert safe is False
    assert "SSRF Protection" in msg

    # Private IP 10.x
    safe, msg = is_ssrf_safe_url("https://10.0.0.5/feed.json")
    assert safe is False
    assert "SSRF Protection" in msg

    # Cloud metadata service (169.254.169.254)
    safe, msg = is_ssrf_safe_url("https://169.254.169.254/latest/meta-data/")
    assert safe is False
    assert "SSRF Protection" in msg

    # Google cloud metadata
    safe, msg = is_ssrf_safe_url("https://metadata.google.internal/computeMetadata/v1/")
    assert safe is False
    assert "SSRF Protection" in msg

    # Valid public endpoint
    safe, msg = is_ssrf_safe_url("https://api.transport.nsw.gov.au/live/feed.json")
    assert safe is True


def test_gtfs_vehicle_positions_parsing():
    now_ts = int(time.time())
    payload = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts - 30,
        },
        "entity": [
            {
                "id": "veh-congestion-99",
                "vehicle": {
                    "trip": {"trip_id": "BMTC-V-335E", "route_id": "335E"},
                    "position": {"latitude": 12.9716, "longitude": 77.5946},
                    "congestion_level": "SEVERE_CONGESTION",
                    "timestamp": now_ts - 20,
                },
            },
            {
                "id": "veh-normal-100",
                "vehicle": {
                    "trip": {"trip_id": "BMTC-V-335E-2", "route_id": "335E"},
                    "position": {"latitude": 12.9750, "longitude": 77.6000},
                    "congestion_level": "RUNNING_SMOOTHLY",
                    "timestamp": now_ts - 20,
                },
            },
        ],
    }

    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.json")
    events = provider.parse_gtfs_payload(payload)

    # Normal running vehicle should NOT create a disruption event
    # Only severe/congested vehicle creates a disruption event
    assert len(events) == 1
    ev = events[0]
    assert ev.id == "gtfs-veh-veh-congestion-99"
    assert ev.event_type == "traffic_congestion"
    assert ev.severity == "critical"
    assert ev.point is not None
    assert ev.point.lat == 12.9716
    assert ev.point.lng == 77.5946
    assert ev.estimated_delay_minutes == 15


def test_gtfs_binary_protobuf_feed_decoding():
    from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed

    now_ts = int(time.time())
    feed_data = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts - 45,
        },
        "entity": [
            {
                "id": "pb-alert-01",
                "alert": {
                    "header_text": {"translation": [{"text": "Metro Line 1 Signal Failure", "language": "en"}]},
                    "description_text": {"translation": [{"text": "Major delay between Central and South", "language": "en"}]},
                    "cause": "TECHNICAL_PROBLEM",
                    "effect": "SIGNIFICANT_DELAYS",
                    "active_period": [{"start": now_ts - 600, "end": now_ts + 3600}],
                },
            },
            {
                "id": "pb-tu-02",
                "trip_update": {
                    "trip": {
                        "trip_id": "METRO-T42",
                        "route_id": "LINE-BLUE",
                        "schedule_relationship": "SCHEDULED",
                    },
                    "stop_time_update": [
                        {"stop_sequence": 3, "stop_id": "STN-A", "arrival": {"delay": 720}},
                    ],
                    "delay": 720,
                },
            },
            {
                "id": "pb-veh-03",
                "vehicle": {
                    "trip": {"trip_id": "BUS-99", "route_id": "ROUTE-99"},
                    "position": {"latitude": 12.9352, "longitude": 77.6245, "bearing": 90.0},
                    "congestion_level": "SEVERE_CONGESTION",
                    "timestamp": now_ts - 25,
                },
            },
        ],
    }

    raw_protobuf = encode_gtfs_feed(feed_data)
    assert isinstance(raw_protobuf, bytes)
    assert len(raw_protobuf) > 0

    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    events = provider.decode_and_parse_feed(raw_protobuf, content_type="application/x-protobuf")

    assert len(events) == 3

    # 1. Alert entity
    alert_ev = next(e for e in events if e.id == "gtfs-alert-pb-alert-01")
    assert alert_ev.event_type == "transport_delay"
    assert alert_ev.severity == "critical"
    assert "Metro Line 1 Signal Failure" in alert_ev.title
    assert alert_ev.provenance == "provider_live"

    # 2. Trip Update entity
    tu_ev = next(e for e in events if e.id == "gtfs-delay-pb-tu-02")
    assert tu_ev.event_type == "transport_delay"
    assert tu_ev.estimated_delay_minutes == 12  # 720 // 60
    assert tu_ev.delay_seconds == 720

    # 3. Vehicle Position entity
    veh_ev = next(e for e in events if e.id == "gtfs-veh-pb-veh-03")
    assert veh_ev.event_type == "traffic_congestion"
    assert veh_ev.severity == "critical"
    assert veh_ev.point is not None
    assert round(veh_ev.point.lat, 4) == 12.9352
    assert round(veh_ev.point.lng, 4) == 77.6245


def test_gtfs_binary_protobuf_integer_enums():
    from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed

    now_ts = int(time.time())
    feed_data = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts - 10,
        },
        "entity": [
            {
                "id": "pb-cancel-99",
                "trip_update": {
                    "trip": {
                        "trip_id": "TRIP-CANCELED-88",
                        "route_id": "EXPRESS-1",
                        "schedule_relationship": 3,  # CANCELED enum = 3
                    },
                },
            },
            {
                "id": "pb-alert-enum",
                "alert": {
                    "header_text": {"translation": [{"text": "Strike Alert"}]},
                    "cause": 4,  # STRIKE = 4
                    "effect": 1,  # NO_SERVICE = 1
                },
            },
        ],
    }

    raw_protobuf = encode_gtfs_feed(feed_data)
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    events = provider.decode_and_parse_feed(raw_protobuf, content_type="application/octet-stream")

    assert len(events) == 2
    cancel_ev = next(e for e in events if e.id == "gtfs-cancel-pb-cancel-99")
    assert cancel_ev.event_type == "service_cancellation"
    assert cancel_ev.severity == "critical"

    alert_ev = next(e for e in events if e.id == "gtfs-alert-pb-alert-enum")
    assert alert_ev.event_type == "service_cancellation"
    assert alert_ev.severity == "critical"
    assert "Strike Alert" in alert_ev.title


def test_gtfs_binary_protobuf_stale_feed():
    from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed

    stale_ts = int(time.time()) - (MAX_GTFS_FEED_AGE_SECONDS + 120)
    feed_data = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": stale_ts,
        },
        "entity": [
            {
                "id": "stale-ent",
                "alert": {"header_text": {"translation": [{"text": "Stale Protobuf Alert"}]}},
            }
        ],
    }
    raw_protobuf = encode_gtfs_feed(feed_data)
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    events = provider.decode_and_parse_feed(raw_protobuf, content_type="application/x-protobuf")
    assert events == []


def test_gtfs_malformed_protobuf_handling():
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    # Truncated protobuf wire bytes
    corrupt_bytes = b"\x0a\x08\x0a\x032.0\x18\x80"
    events = provider.decode_and_parse_feed(corrupt_bytes, content_type="application/x-protobuf")
    assert events == []

    # Random binary garbage
    garbage_bytes = b"\xff\xfe\xfd\xfc\xfb"
    events = provider.decode_and_parse_feed(garbage_bytes, content_type="application/x-protobuf")
    assert events == []

    # Empty bytes
    assert provider.decode_and_parse_feed(b"") == []


@pytest.mark.anyio
async def test_gtfs_fetch_binary_protobuf_http():
    from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed

    now_ts = int(time.time())
    feed_data = {
        "header": {"gtfs_realtime_version": "2.0", "timestamp": now_ts - 30},
        "entity": [
            {
                "id": "http-pb-01",
                "alert": {
                    "header_text": {"translation": [{"text": "Live Protobuf Incident"}]},
                    "cause": "MAINTENANCE",
                    "effect": "SIGNIFICANT_DELAYS",
                },
            }
        ],
    }
    raw_protobuf = encode_gtfs_feed(feed_data)

    provider = GTFSRealtimeProvider(
        feed_url="https://transit.example.gov/gtfs-rt.pb",
        api_key="pb-token-xyz",
    )
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = raw_protobuf
        mock_resp.headers = {"content-type": "application/x-protobuf"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await provider.fetch_disruptions()

            assert len(events) == 1
            assert events[0].id == "gtfs-alert-http-pb-01"
            assert events[0].provenance == "provider_live"


def test_gtfs_configured_awaiting_verification_state():
    """Milestone M3.8.3: Configured GTFS feed must report unknown connectivity before initial fetch."""
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        assert provider.is_configured() is True
        assert provider.is_available() is True
        assert provider.get_connectivity_status() == "unknown"

        cap = provider.get_capabilities()
        assert cap.is_available is True
        assert cap.is_configured is True
        assert cap.connectivity_status == "unknown"
        assert cap.status_notice == "Configured — awaiting initial live connection verification."
        assert cap.provenance_source == "unknown"
        assert cap.last_successful_request is None
        assert cap.consecutive_failure_count == 0


def test_gtfs_official_schema_binary_fixtures():
    """
    Milestone M3.8.3: Independently constructed raw byte fixtures following the official
    Google Transit gtfs-realtime.proto field numbers (TripDescriptor, StopTimeUpdate, VehiclePosition).
    Verifies that the decoder conforms to the official specification without using the internal encoder.
    """
    import struct
    from app.services.disruption.providers.gtfs_protobuf import (
        _decode_trip_descriptor,
        _decode_stop_time_update,
        _decode_vehicle_descriptor,
        _decode_vehicle_position,
        _decode_trip_update,
    )

    # 1. Official TripDescriptor fixture
    # Tag 1 (trip_id): 0x0a + len 8 + b"TRIP-100"
    # Tag 2 (start_time): 0x12 + len 8 + b"08:00:00"
    # Tag 3 (start_date): 0x1a + len 8 + b"20261110"
    # Tag 4 (schedule_relationship): 0x20 + 0x03 (CANCELED = 3)
    # Tag 5 (route_id): 0x2a + len 7 + b"ROUTE-A"
    # Tag 6 (direction_id): 0x30 + 0x01 (1)
    raw_trip = (
        b"\x0a\x08TRIP-100"
        b"\x12\x0808:00:00"
        b"\x1a\x0820261110"
        b"\x20\x03"
        b"\x2a\x07ROUTE-A"
        b"\x30\x01"
    )
    trip_dec = _decode_trip_descriptor(raw_trip)
    assert trip_dec["trip_id"] == "TRIP-100"
    assert trip_dec["start_time"] == "08:00:00"
    assert trip_dec["start_date"] == "20261110"
    assert trip_dec["schedule_relationship"] == "CANCELED"
    assert trip_dec["route_id"] == "ROUTE-A"
    assert trip_dec["direction_id"] == 1

    # 2. Official StopTimeUpdate fixture
    # Tag 1 (stop_sequence): 0x08 + 0x04
    # Tag 2 (arrival): 0x12 + len 3 + (tag 1 delay 300: 0x08 + 0xac + 0x02)
    # Tag 3 (departure): 0x1a + len 3 + (tag 1 delay 360: 0x08 + 0xe8 + 0x02)
    # Tag 4 (stop_id): 0x22 + len 7 + b"STOP-55"
    # Tag 5 (schedule_relationship): 0x28 + 0x00 (SCHEDULED = 0)
    raw_stu = (
        b"\x08\x04"
        b"\x12\x03\x08\xac\x02"
        b"\x1a\x03\x08\xe8\x02"
        b"\x22\x07STOP-55"
        b"\x28\x00"
    )
    stu_dec = _decode_stop_time_update(raw_stu)
    assert stu_dec["stop_sequence"] == 4
    assert stu_dec["arrival"]["delay"] == 300
    assert stu_dec["departure"]["delay"] == 360
    assert stu_dec["stop_id"] == "STOP-55"
    assert stu_dec["schedule_relationship"] == 0

    # 3. Official VehicleDescriptor fixture
    # Tag 1 (id): 0x0a + len 6 + b"BUS-99"
    # Tag 2 (label): 0x12 + len 8 + b"Fleet-99"
    # Tag 3 (license_plate): 0x1a + len 12 + b"KA-01-A-1111"
    raw_vd = (
        b"\x0a\x06BUS-99"
        b"\x12\x08Fleet-99"
        b"\x1a\x0cKA-01-A-1111"
    )
    vd_dec = _decode_vehicle_descriptor(raw_vd)
    assert vd_dec["id"] == "BUS-99"
    assert vd_dec["label"] == "Fleet-99"
    assert vd_dec["license_plate"] == "KA-01-A-1111"

    # 4. Official VehiclePosition fixture
    # Tag 1 (trip): 0x0a + len + raw_trip
    # Tag 2 (position): 0x12 + len 10 + (tag 1 lat float: 0x0d + 4 bytes, tag 2 lon float: 0x15 + 4 bytes)
    lat_bytes = struct.pack("<f", 12.9716)
    lon_bytes = struct.pack("<f", 77.5946)
    raw_pos = b"\x0d" + lat_bytes + b"\x15" + lon_bytes
    # Tag 3 (current_stop_sequence): 0x18 + 0x05
    # Tag 4 (current_status): 0x20 + 0x01 (STOPPED_AT = 1)
    # Tag 5 (timestamp): 0x28 + 0x80\xe2\xcf\xaa\x06 (1700000000)
    # Tag 6 (congestion_level): 0x30 + 0x04 (SEVERE_CONGESTION = 4)
    # Tag 7 (stop_id): 0x3a + len 7 + b"STOP-MG"
    # Tag 8 (vehicle): 0x42 + len + raw_vd
    # Tag 9 (occupancy_status): 0x48 + 0x01
    raw_veh = (
        b"\x0a" + bytes([len(raw_trip)]) + raw_trip
        + b"\x12" + bytes([len(raw_pos)]) + raw_pos
        + b"\x18\x05"
        + b"\x20\x01"
        + b"\x28\x80\xe2\xcf\xaa\x06"
        + b"\x30\x04"
        + b"\x3a\x07STOP-MG"
        + b"\x42" + bytes([len(raw_vd)]) + raw_vd
        + b"\x48\x01"
    )
    veh_dec = _decode_vehicle_position(raw_veh)
    assert veh_dec["trip"]["trip_id"] == "TRIP-100"
    assert round(veh_dec["position"]["latitude"], 4) == 12.9716
    assert round(veh_dec["position"]["longitude"], 4) == 77.5946
    assert veh_dec["current_stop_sequence"] == 5
    assert veh_dec["current_status"] == 1
    assert veh_dec["timestamp"] == 1700000000
    assert veh_dec["congestion_level"] == "SEVERE_CONGESTION"
    assert veh_dec["stop_id"] == "STOP-MG"
    assert veh_dec["vehicle"]["id"] == "BUS-99"
    assert veh_dec["occupancy_status"] == 1

    # 5. Official TripUpdate fixture
    # Tag 1 (trip): 0x0a + len + raw_trip
    # Tag 2 (stop_time_update): 0x12 + len + raw_stu
    # Tag 3 (vehicle): 0x1a + len + raw_vd
    # Tag 4 (timestamp): 0x20 + 0x80\xe2\xcf\xaa\x06
    # Tag 5 (delay): 0x28 + 0xd8\x04 (600s)
    raw_tu = (
        b"\x0a" + bytes([len(raw_trip)]) + raw_trip
        + b"\x12" + bytes([len(raw_stu)]) + raw_stu
        + b"\x1a" + bytes([len(raw_vd)]) + raw_vd
        + b"\x20\x80\xe2\xcf\xaa\x06"
        + b"\x28\xd8\x04"
    )
    tu_dec = _decode_trip_update(raw_tu)
    assert tu_dec["trip"]["trip_id"] == "TRIP-100"
    assert len(tu_dec["stop_time_update"]) == 1
    assert tu_dec["stop_time_update"][0]["stop_sequence"] == 4
    assert tu_dec["vehicle"]["id"] == "BUS-99"
    assert tu_dec["timestamp"] == 1700000000
    assert tu_dec["delay"] == 600


def test_gtfs_tag_mapping_regression_validation():
    """
    Milestone M3.8.3 Regression: Proves that the official tag mapping correctly distinguishes
    start_time (tag 2) from route_id (tag 5), and arrival (tag 2) from stop_id (tag 4).
    The previous pre-remediation mapping inverted these tags, which would cause official
    feeds to have route_id='08:00:00' and start_date='ROUTE-A'.
    """
    from app.services.disruption.providers.gtfs_protobuf import (
        _decode_trip_descriptor,
        _decode_stop_time_update,
    )

    # Official protobuf bytes: tag 2 is start_time, tag 5 is route_id
    raw_trip = b"\x0a\x07TRIP-01\x12\x0807:30:00\x1a\x0820261110\x20\x00\x2a\x08METRO-01\x30\x00"
    trip = _decode_trip_descriptor(raw_trip)

    # Correct conformance
    assert trip["start_time"] == "07:30:00"
    assert trip["route_id"] == "METRO-01"
    assert trip["start_date"] == "20261110"

    # StopTimeUpdate: tag 2 is arrival, tag 4 is stop_id
    raw_stu = b"\x08\x01\x12\x03\x08\xc8\x01\x22\x06STN-01"
    stu = _decode_stop_time_update(raw_stu)
    assert stu["stop_sequence"] == 1
    assert stu["arrival"]["delay"] == 200
    assert stu["stop_id"] == "STN-01"


@pytest.mark.anyio
async def test_gtfs_corrupt_feed_does_not_record_false_success():
    """Milestone M3.8.3: HTTP 200 with truncated protobuf varint must NOT record false success."""
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        # Truncated varint: 0x80 has MSB set indicating more bytes, but stream ends
        corrupt_bytes = b"\x0a\x08\x0a\x032.0\x18\x80"
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = corrupt_bytes
        mock_resp.headers = {"content-type": "application/x-protobuf"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await provider.fetch_disruptions()

            assert events == []
            # Must NOT record success
            assert provider._last_successful_request is None
            assert provider._consecutive_failure_count == 1
            assert provider._last_failed_request is not None
            assert "Malformed feed payload" in provider._last_status_reason
            assert provider.get_connectivity_status() == "unknown"


@pytest.mark.anyio
async def test_gtfs_truncated_length_delimited_field():
    """Milestone M3.8.3: Length-delimited field claiming more bytes than payload must record failure."""
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        # Tag 1 length 64 bytes, but only 5 provided
        corrupt_bytes = b"\x0a\x40\x0a\x032.0"
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = corrupt_bytes
        mock_resp.headers = {"content-type": "application/x-protobuf"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await provider.fetch_disruptions()

            assert events == []
            assert provider._last_successful_request is None
            assert provider._consecutive_failure_count == 1


@pytest.mark.anyio
async def test_gtfs_unsupported_wire_type():
    """Milestone M3.8.3: Payload containing unsupported wire type must record failure."""
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        # Wire type 7 is reserved/unsupported
        corrupt_bytes = b"\x0f\x01\x02"
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = corrupt_bytes
        mock_resp.headers = {"content-type": "application/x-protobuf"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await provider.fetch_disruptions()

            assert events == []
            assert provider._last_successful_request is None
            assert provider._consecutive_failure_count == 1


@pytest.mark.anyio
async def test_gtfs_corrupt_json_payload():
    """Milestone M3.8.3: HTTP 200 with invalid JSON must record failure and not false success."""
    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.json")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        corrupt_json = b'{"header": {"version": "2.0"}, "entity": ['  # Truncated JSON
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = corrupt_json
        mock_resp.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await provider.fetch_disruptions()

            assert events == []
            assert provider._last_successful_request is None
            assert provider._consecutive_failure_count == 1


@pytest.mark.anyio
async def test_gtfs_valid_empty_feed_records_success():
    """Milestone M3.8.3: Valid empty feed (0 entities, fresh header) must record genuine success."""
    from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed

    now_ts = int(time.time())
    valid_empty = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts - 10,
        },
        "entity": [],
    }
    raw_pb = encode_gtfs_feed(valid_empty)

    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = raw_pb
        mock_resp.headers = {"content-type": "application/x-protobuf"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            events = await provider.fetch_disruptions()

            assert events == []
            assert provider._last_successful_request is not None
            assert provider._consecutive_failure_count == 0
            assert provider.get_connectivity_status() == "available"
            cap = provider.get_capabilities()
            assert cap.connectivity_status == "available"
            assert cap.provenance_source == "provider_live"


@pytest.mark.anyio
async def test_gtfs_subsequent_valid_feed_recovers_health():
    """Milestone M3.8.3: A valid feed recovers provider health after prior failures."""
    from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed

    now_ts = int(time.time())
    valid_feed = {
        "header": {"gtfs_realtime_version": "2.0", "timestamp": now_ts - 5},
        "entity": [],
    }
    raw_pb = encode_gtfs_feed(valid_feed)

    provider = GTFSRealtimeProvider(feed_url="https://transit.example.gov/gtfs-rt.pb")
    provider._consecutive_failure_count = 2  # Prior failures
    provider._last_failed_request = "2026-11-09T00:00:00Z"

    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.content = raw_pb
        mock_resp.headers = {"content-type": "application/x-protobuf"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await provider.fetch_disruptions()

            assert provider._consecutive_failure_count == 0
            assert provider.get_connectivity_status() == "available"

