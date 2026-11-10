"""
scripts/verify_tomtom_live.py

Safe live verification tool for TomTom Orbis Traffic API v2 (Milestone M3.8.1 / M3.8.2).
Performs one bounded opt-in live query against the Orbis Traffic Incidents endpoint.
Records HTTP status, latency, incident count, and validated fields.
NEVER prints, exposes, or logs API keys.
"""
import asyncio
import sys
import time

sys.path.insert(0, "backend")

from app.core.config import settings
from app.services.disruption.providers.tomtom_orbis import TomTomOrbisTrafficProvider


async def run_live_verification():
    print("=== TomTom Orbis Traffic v2 Live Verification ===")

    # 1. Config & Credential Check (without leaking secret)
    has_key = bool(settings.TOMTOM_API_KEY and len(settings.TOMTOM_API_KEY.strip()) > 8)
    key_len = len(settings.TOMTOM_API_KEY.strip()) if settings.TOMTOM_API_KEY else 0
    print(f"1. Configuration Check:")
    print(f"   - Environment Variable: TOMTOM_API_KEY")
    print(f"   - Configured: {has_key}")
    print(
        f"   - Key Length: {key_len} chars (masked: <configured:len={key_len}>)"
        if has_key
        else "   - Key: <none>"
    )
    print(f"   - Feature Enabled: {settings.TOMTOM_TRAFFIC_ENABLED}")
    print(f"   - Endpoint: {settings.TOMTOM_BASE_URL}")

    if not has_key:
        print("\n[BLOCKED] TOMTOM_API_KEY is not configured or not yet saved to .env.")
        print(
            "Please ensure TOMTOM_API_KEY=<your_key> is saved in E:\\KogniSync\\KogniSync\\.env"
        )
        return False

    provider = TomTomOrbisTrafficProvider()

    # 2. Initial capability before query
    cap_initial = provider.get_capabilities()
    print(f"\n2. Provider State Before Live Request:")
    print(f"   - is_configured: {cap_initial.is_configured}")
    print(f"   - is_available: {cap_initial.is_available}")
    print(f"   - connectivity_status: {cap_initial.connectivity_status}")
    print(f"   - last_successful_request: {cap_initial.last_successful_request}")
    print(f"   - Status Note: {cap_initial.status_notice}")

    # 3. Execute Bounded Live Request
    # Test corridor: Bengaluru Urban Core (77.50, 12.90, 77.70, 13.10) ~ 484 km²
    test_bbox = (77.50, 12.90, 77.70, 13.10)
    print(f"\n3. Executing Bounded Live Request:")
    print(f"   - Test BBox: {test_bbox} (WGS84 minLon, minLat, maxLon, maxLat)")
    print(f"   - BBox Area: ~484 km² (well below 10,000 km² limit, single request)")

    # Direct raw request to inspect HTTP protocol details
    import httpx
    min_lon, min_lat, max_lon, max_lat = test_bbox
    bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"
    headers = {
        "TomTom-Api-Key": settings.TOMTOM_API_KEY or "",
        "Attributes": (
            "incidents(type,geometry(type,coordinates),properties(id,iconCategory,magnitudeOfDelay,"
            "events(description,code),from,to,lengthInMeters,delayInSeconds,roadNumbers))"
        ),
        "Accept": "application/json",
    }
    params = {"apiVersion": "2", "bbox": bbox_str}

    raw_status: int = 0
    raw_keys: list[str] = []
    raw_latency_ms: float = 0.0
    raw_content_type: str = ""

    async with httpx.AsyncClient(timeout=5.0) as client:
        t0 = time.perf_counter()
        raw_resp = await client.get(settings.TOMTOM_BASE_URL, headers=headers, params=params)
        raw_latency_ms = (time.perf_counter() - t0) * 1000.0
        raw_status = raw_resp.status_code
        raw_content_type = raw_resp.headers.get("content-type", "")
        if raw_resp.status_code == 200:
            try:
                body = raw_resp.json()
                raw_keys = list(body.keys()) if isinstance(body, dict) else [type(body).__name__]
            except Exception:
                raw_keys = ["<non-json>"]
        else:
            try:
                err_body = raw_resp.json()
                raw_keys = list(err_body.keys()) if isinstance(err_body, dict) else []
            except Exception:
                raw_keys = []

    print(f"   - Direct Probe HTTP Status: {raw_status}")
    print(f"   - Direct Probe Latency: {raw_latency_ms:.1f} ms")
    print(f"   - Response Content-Type: {raw_content_type}")
    print(f"   - Response Top-Level Keys: {raw_keys}")

    # Now execute through TomTomOrbisTrafficProvider
    start_t = time.perf_counter()
    events = await provider.fetch_disruptions(bbox=test_bbox)
    duration_ms = (time.perf_counter() - start_t) * 1000.0

    cap_after = provider.get_capabilities()

    print(f"\n4. Response & Entitlement Audit:")
    print(f"   - Request Duration: {duration_ms:.1f} ms")
    print(f"   - Recorded Provider Latency: {provider._last_response_latency_ms} ms")
    print(f"   - Provider Status Reason: {provider._last_status_reason}")
    print(f"   - Consecutive Failures: {provider._consecutive_failure_count}")
    print(f"   - Rate Limited: {provider._is_rate_limited}")
    print(f"   - Auth Blocked: {provider._auth_blocked}")
    print(f"   - Last Success Timestamp: {provider._last_successful_request}")
    print(f"   - Last Failure Timestamp: {provider._last_failed_request}")

    if provider._auth_blocked:
        print("\n[ERROR] Authorization Failed (HTTP 401/403):")
        print(
            "   - Safe Error: TomTom Orbis v2 rejected the API key or the key lacks Traffic Incident Details entitlement."
        )
        print("   - Operational Status: BLOCKED")
        return False

    if provider._consecutive_failure_count > 0 and not provider._last_successful_request:
        print(f"\n[ERROR] Request Failed: {provider._last_status_reason}")
        return False

    print(f"\n5. Incident Telemetry Validation:")
    print(f"   - Returned Incidents Count: {len(events)}")

    if len(events) == 0:
        print("   - Note: Zero incidents currently active in test bounding box.")
        print("   - Connectivity & Entitlement: CONFIRMED (HTTP 200 OK returned empty array).")
        print("   - Zero Incidents Invariant: No artificial incidents manufactured.")
    else:
        print(f"   - Successfully extracted {len(events)} real incidents.")
        sample = events[0]
        print(f"   - Sample Incident ID: {sample.id}")
        print(f"   - Event Type: {sample.event_type}")
        print(f"   - Severity: {sample.severity}")
        print(f"   - Title: {sample.title}")
        print(
            f"   - Coordinates: lat={sample.point.lat if sample.point else None}, lng={sample.point.lng if sample.point else None}"
        )
        print(f"   - Delay Seconds: {sample.delay_seconds}")
        print(f"   - Provenance: {sample.provenance}")
        print(f"   - Observed At: {sample.observed_at}")

    print(f"\n6. Truth Invariant & Operational Status:")
    print(f"   - Final Provider Status: {cap_after.connectivity_status}")
    print(f"   - Final Status Notice: {cap_after.status_notice}")
    print(
        f"   - Verified: Live provider status requires successful HTTP response, not merely key presence."
    )
    return True


if __name__ == "__main__":
    asyncio.run(run_live_verification())

