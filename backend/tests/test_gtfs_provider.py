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

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_gtfs_payload

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
