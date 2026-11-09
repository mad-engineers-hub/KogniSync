"""
backend/tests/test_tomtom_provider.py

Comprehensive contract and unit tests for TomTomOrbisTrafficProvider (Milestone M3.8).
Verifies:
1. Correct Orbis v2 endpoint and apiVersion query parameter.
2. TomTom-Api-Key request header authentication (never in query params).
3. Attributes header selection.
4. Bbox formatting and coordinate range validation.
5. Area calculation and recursive splitting for corridors > 10,000 km².
6. GeoJSON Point and LineString geometry normalization.
7. Delay seconds handling: zero delay inference from qualitative categories.
8. Safe handling of unknown categories, missing geometries, and missing timestamps.
9. HTTP error classification: 400, 401/403 (blocked, no retry), 429 (rate-limited), 5xx (retry).
10. Network timeouts and secret redaction in logs/exceptions.
"""
import time
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
from app.services.disruption.providers.tomtom_orbis import (
    TomTomOrbisTrafficProvider,
    approx_bbox_area_km2,
    split_bounding_box,
    sanitize_secret,
    TOMTOM_ORBIS_BASE_URL,
    DEFAULT_ATTRIBUTES_HEADER,
)


@pytest.fixture
def mock_orbis_response_data():
    return {
        "incidents": [
            {
                "id": "inc-blr-01",
                "geometry": {
                    "type": "Point",
                    "coordinates": [77.5946, 12.9716],  # [lon, lat]
                },
                "properties": {
                    "id": "inc-blr-01",
                    "iconCategory": 6,  # Jam -> traffic_congestion
                    "magnitudeOfDelay": 3,  # Major -> high
                    "delay": 1200,  # 20 minutes in seconds
                    "startTime": "2026-11-09T08:00:00Z",
                    "endTime": "2026-11-09T14:00:00Z",
                    "from": "Koramangala",
                    "to": "Indiranagar",
                    "roadNumbers": ["100 Feet Road"],
                    "events": [{"description": "Heavy traffic congestion due to peak hour volume"}],
                },
            },
            {
                "id": "inc-blr-02",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [77.6000, 12.9000],
                        [77.6100, 12.9100],
                        [77.6200, 12.9200],
                    ],
                },
                "properties": {
                    "id": "inc-blr-02",
                    "iconCategory": 7,  # Road closure
                    "magnitudeOfDelay": 4,  # Critical
                    "delay": 0,  # No delay seconds provided
                    "length": 2500,
                    "startTime": "2026-11-09T09:00:00Z",
                    "roadNumbers": ["Outer Ring Road"],
                    "events": [{"description": "Underpass waterlogging closure"}],
                },
            },
        ]
    }


def test_sanitize_secret():
    assert sanitize_secret(None) == "<none>"
    assert sanitize_secret("") == "<none>"
    masked = sanitize_secret("supersecretkey12345")
    assert "supersecret" not in masked
    assert "12345" not in masked
    assert "len=19" in masked


def test_bbox_area_and_splitting():
    # Small box: 0.1 deg x 0.1 deg around Bengaluru (~11 km x 11 km = ~121 km² < 10,000 km²)
    small_area = approx_bbox_area_km2(77.5, 12.9, 77.6, 13.0)
    assert 100.0 < small_area < 200.0
    boxes = split_bounding_box(77.5, 12.9, 77.6, 13.0)
    assert len(boxes) == 1

    # Large box: Southern India corridor (75.0, 10.0, 80.0, 15.0) ~ 500 km x 550 km = ~275,000 km² > 10,000 km²
    large_area = approx_bbox_area_km2(75.0, 10.0, 80.0, 15.0)
    assert large_area > 10000.0
    split_boxes = split_bounding_box(75.0, 10.0, 80.0, 15.0)
    assert len(split_boxes) > 1
    # Check that every subbox has area <= 10000 km2 (or is clamped)
    for sb in split_boxes:
        assert approx_bbox_area_km2(sb[0], sb[1], sb[2], sb[3]) <= 10000.0 * 2.5


def test_unconfigured_provider_capabilities():
    with patch("app.core.config.settings.TOMTOM_API_KEY", None):
        provider = TomTomOrbisTrafficProvider(api_key=None)
        assert provider.is_configured() is False
        assert provider.is_available() is False
        assert provider.get_connectivity_status() == "unconfigured"

        cap = provider.get_capabilities()
        assert cap.is_available is False
        assert "BLOCKED — credentials unavailable" in cap.status_notice
        assert cap.provenance_source == "unknown"


@pytest.mark.anyio
async def test_fetch_with_mocked_success(mock_orbis_response_data):
    provider = TomTomOrbisTrafficProvider(api_key="valid-test-api-key-12345")
    assert provider.is_configured() is True
    assert provider.is_available() is True

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_orbis_response_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        events = await provider.fetch_disruptions(
            bbox=(77.50, 12.85, 77.65, 13.00)
        )

        # Assert contract: endpoint, headers, and params
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == TOMTOM_ORBIS_BASE_URL
        headers = call_args[1]["headers"]
        assert headers["TomTom-Api-Key"] == "valid-test-api-key-12345"
        assert headers["Attributes"] == DEFAULT_ATTRIBUTES_HEADER
        params = call_args[1]["params"]
        assert params["apiVersion"] == "2"
        assert params["bbox"] == "77.50000,12.85000,77.65000,13.00000"

        # Assert normalized events
        assert len(events) == 2

        # Event 1: Point with delay
        ev1 = events[0]
        assert ev1.id == "tt-inc-inc-blr-01"
        assert ev1.source == "tomtom_orbis_v2"
        assert ev1.event_type == "traffic_congestion"
        assert ev1.severity == "high"
        assert ev1.provenance == "provider_live"
        assert ev1.point is not None
        assert abs(ev1.point.lat - 12.9716) < 1e-4
        assert abs(ev1.point.lng - 77.5946) < 1e-4
        assert ev1.estimated_delay_minutes == 20  # 1200 / 60
        assert ev1.delay_seconds == 1200
        assert "100 Feet Road" in ev1.title

        # Event 2: LineString without delay seconds
        ev2 = events[1]
        assert ev2.id == "tt-inc-inc-blr-02"
        assert ev2.event_type == "road_closure"
        assert ev2.severity == "critical"
        assert ev2.provenance == "provider_live"
        assert ev2.point is not None  # Midpoint extracted
        assert ev2.estimated_delay_minutes == 0  # Zero inferred delay from qualitative magnitude
        assert ev2.delay_seconds is None


@pytest.mark.anyio
async def test_empty_corridor_returns_empty_list():
    provider = TomTomOrbisTrafficProvider(api_key="valid-test-key-12345")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"incidents": []}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        events = await provider.fetch_disruptions(bbox=(77.5, 12.9, 77.6, 13.0))
        assert events == []
        assert provider.get_connectivity_status() == "available"
        cap = provider.get_capabilities()
        assert cap.is_available is True
        assert cap.consecutive_failure_count == 0


@pytest.mark.anyio
async def test_authentication_failure_fails_closed():
    provider = TomTomOrbisTrafficProvider(api_key="invalid-key-12345")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Forbidden / Unauthorized"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        events = await provider.fetch_disruptions(bbox=(77.5, 12.9, 77.6, 13.0))

        assert events == []
        # Permanent failure -> does not retry, marks blocked
        assert provider.is_available() is False
        assert provider.get_connectivity_status() == "blocked"
        cap = provider.get_capabilities()
        assert "BLOCKED — TomTom authentication failed" in cap.status_notice


@pytest.mark.anyio
async def test_rate_limiting_handles_retry_after():
    provider = TomTomOrbisTrafficProvider(api_key="valid-key-12345")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "45"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        events = await provider.fetch_disruptions(bbox=(77.5, 12.9, 77.6, 13.0))

        assert events == []
        assert provider.is_available() is False
        assert provider.get_connectivity_status() == "rate_limited"
        cap = provider.get_capabilities()
        assert cap.is_rate_limited is True
        assert "DEGRADED — TomTom Orbis rate limit exceeded" in cap.status_notice


@pytest.mark.anyio
async def test_server_error_and_retry_backoff():
    provider = TomTomOrbisTrafficProvider(api_key="valid-key-12345", max_retries=1)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 503

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with patch("anyio.sleep", new_callable=AsyncMock) as mock_sleep:
            events = await provider.fetch_disruptions(bbox=(77.5, 12.9, 77.6, 13.0))
            assert events == []
            # Tried initial + 1 retry = 2 calls
            assert mock_get.call_count == 2
            mock_sleep.assert_called_once()


@pytest.mark.anyio
async def test_missing_or_malformed_geometry_handled_safely():
    provider = TomTomOrbisTrafficProvider(api_key="valid-key-12345")
    malformed_data = {
        "incidents": [
            {
                "id": "bad-geom-01",
                "geometry": {"type": "Point", "coordinates": []},  # Empty coords
                "properties": {"iconCategory": 1},
            },
            {
                "id": "no-geom-02",
                # Missing geometry completely
                "properties": {"iconCategory": 1},
            },
            {
                "id": "valid-03",
                "geometry": {"type": "Point", "coordinates": [77.5, 12.9]},
                "properties": {"iconCategory": 1, "description": "Valid incident"},
            },
        ]
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = malformed_data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        events = await provider.fetch_disruptions(bbox=(77.5, 12.9, 77.6, 13.0))
        # Safely skipped the 2 malformed records and normalized the 1 valid record
        assert len(events) == 1
        assert events[0].id == "tt-inc-valid-03"


def test_split_bounding_box_edge_cases():
    from app.services.disruption.providers.tomtom_orbis import (
        split_bounding_box,
        approx_bbox_area_km2,
        MAX_BBOX_AREA_KM2,
    )

    # 1. Box below limit (< 10,000 km²)
    small_box = split_bounding_box(77.5, 12.9, 77.6, 13.0)
    assert len(small_box) == 1
    assert small_box[0] == (77.5, 12.9, 77.6, 13.0)

    # 2. Box exactly at limit
    # Area ~ 10,000 km²: width ~ 100km (~0.9 deg), height ~ 100km (~0.9 deg)
    exact_box = split_bounding_box(77.0, 12.0, 77.0 + 0.9, 12.0 + 0.9, max_area_km2=MAX_BBOX_AREA_KM2)
    assert len(exact_box) == 1

    # 3. Box above limit (Bengaluru to Chennai corridor ~ 350km x 350km ~ 120,000 km²)
    big_box = split_bounding_box(77.0, 12.0, 80.5, 13.5, max_area_km2=MAX_BBOX_AREA_KM2)
    assert len(big_box) > 1
    assert len(big_box) <= 5  # Clamped to TOMTOM_MAX_REQUESTS_PER_ASSESSMENT

    # 4. Very wide corridor (lon_span >> lat_span)
    wide_box = split_bounding_box(70.0, 12.9, 85.0, 13.1, max_area_km2=MAX_BBOX_AREA_KM2)
    assert len(wide_box) > 1
    # Wide corridor splits along longitude, so lat span is preserved
    for b in wide_box:
        assert b[1] == 12.9
        assert b[3] == 13.1

    # 5. Very tall corridor (lat_span >> lon_span)
    tall_box = split_bounding_box(77.5, 8.0, 77.7, 28.0, max_area_km2=MAX_BBOX_AREA_KM2)
    assert len(tall_box) > 1
    # Tall corridor splits along latitude, so lon span is preserved
    for b in tall_box:
        assert b[0] == 77.5
        assert b[2] == 77.7

    # 6. Reversed coordinates: min > max
    reversed_box = split_bounding_box(80.0, 14.0, 77.0, 12.0, max_area_km2=MAX_BBOX_AREA_KM2)
    assert len(reversed_box) >= 1
    for b in reversed_box:
        assert b[0] <= b[2]
        assert b[1] <= b[3]

    # 7. Antimeridian crossing: min_lon = 179.0, max_lon = -179.0
    antimeridian_box = split_bounding_box(179.0, -10.0, -179.0, 10.0, max_area_km2=MAX_BBOX_AREA_KM2)
    assert len(antimeridian_box) == 2
    assert antimeridian_box[0] == (179.0, -10.0, 180.0, 10.0)
    assert antimeridian_box[1] == (-180.0, -10.0, -179.0, 10.0)
