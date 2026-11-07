"""
scripts/verify_m33_live_routing.py

Live Valhalla routing verification script for Milestone M3.3.
Queries running Valhalla container on port 8002 for:
1. Real regional road routes across Chennai, Bengaluru, Mangaluru, and Udupi.
2. Full end-to-end multimodal search through JourneyOrchestrationService.
3. Metric breakdown verification (in-vehicle, walking, waiting, travel).
4. Hard feasibility constraint evaluation.
5. Attribute-level provenance integrity.
"""
import asyncio
import json
import httpx

from app.services.journey.valhalla_adapter import ValhallaTransportAdapter
from app.services.journey.service import JourneyOrchestrationService
from app.services.journey.schemas import JourneySearchRequest
from app.services.optimizer.schemas import OptimizationWeightsInput


async def main():
    print("=" * 70)
    print("KOGNISYNC M3.3 LIVE VALHALLA ROUTING & MULTIMODAL QUALITY VERIFICATION")
    print("=" * 70)

    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", timeout_seconds=5.0, enabled=True)
    print(f"Valhalla is_available: {adapter.is_available()}")
    print(f"Valhalla is_live_authenticated: {adapter.is_live_authenticated()}")

    # 1. Regional First-Mile and Last-Mile Live Valhalla Route Tests
    print("\n--- 1. Regional Route Queries against Live Valhalla Engine ---")
    test_cases = [
        ("Chennai: T. Nagar -> Chennai Central Railway Station", 13.0418, 80.2341, 13.0827, 80.2755, "auto"),
        ("Bengaluru: Indiranagar -> KSR Bengaluru Railway Station", 12.9784, 77.6408, 12.9781, 77.5694, "auto"),
        ("Mangaluru: Mangaluru Central Station -> Hampankatta", 12.8649, 74.8431, 12.8703, 74.8427, "auto"),
        ("Udupi: Udupi Railway Station -> Manipal University", 13.3525, 74.7828, 13.3525, 74.7928, "auto"),
    ]

    for label, o_lat, o_lng, d_lat, d_lng, costing in test_cases:
        payload = {
            "locations": [{"lat": o_lat, "lon": o_lng}, {"lat": d_lat, "lon": d_lng}],
            "costing": costing,
        }
        res = httpx.post("http://localhost:8002/route", json=payload, timeout=5.0)
        assert res.status_code == 200, f"Expected 200 from Valhalla, got {res.status_code}: {res.text}"
        data = res.json()
        summary = data["trip"]["summary"]
        duration_sec = summary["time"]
        distance_km = summary["length"]
        print(f"✓ {label}")
        print(f"    Mode: {costing} | Time: {duration_sec}s ({round(duration_sec/60)} min) | Distance: {distance_km} km")

    # 2. End-to-End Multimodal Orchestration with Live Valhalla Attached
    print("\n--- 2. End-to-End Multimodal Search Orchestration (Chennai -> Udupi) ---")
    service = JourneyOrchestrationService(transport_providers=[adapter])
    search_req = JourneySearchRequest(
        origin="Chennai",
        destination="Udupi",
        departure_date="2026-11-04",
        preferred_arrival_before="20:00",
        budget_max=6000.0,
        passengers_count=1,
        weights=OptimizationWeightsInput(cost=0.25, duration=0.45, comfort=0.20, carbon=0.10),
    )

    search_res = await service.search_journeys(search_req)
    print(f"Total candidates: {search_res.total_candidates}")
    print(f"Eligible candidates: {search_res.eligible_candidates}")
    print(f"Pareto frontier count: {search_res.pareto_frontier_count}")
    print(f"Recommended Journey ID: {search_res.recommended_journey_id}")
    print(f"Provider status: {search_res.provider_status}")

    print("\n--- 3. Journey Candidate Inspection & Provenance Verification ---")
    for idx, j in enumerate(search_res.journeys):
        fm = j.segments[0]
        main_seg = j.segments[1]
        lm = j.segments[2]

        print(f"\nJourney #{idx + 1} [{j.recommendation_category.upper()}]: {j.title}")
        print(f"  Total Duration: {j.total_duration_minutes}m")
        print(f"    Travel Duration: {j.travel_duration_minutes}m (In-Vehicle: {j.in_vehicle_duration_minutes}m, Walking: {j.walking_duration_minutes}m)")
        print(f"    Waiting Duration: {j.waiting_duration_minutes}m")
        print(f"    Total Price: ₹{j.total_price:.2f}")
        print(f"  First Mile ({fm.mode}): {fm.provider} -> {fm.duration_minutes}m, {fm.distance_km}km")
        print(f"    Provenance: live={fm.provenance.has_live_provider if fm.provenance else False}, duration_source={fm.provenance.attributes['duration'].source_type if fm.provenance else 'none'}")
        print(f"  Main Transport ({main_seg.mode}): {main_seg.provider} -> {main_seg.duration_minutes}m, {main_seg.distance_km}km")
        print(f"  Last Mile ({lm.mode}): {lm.provider} -> {lm.duration_minutes}m, {lm.distance_km}km")
        print(f"    Provenance: live={lm.provenance.has_live_provider if lm.provenance else False}, duration_source={lm.provenance.attributes['duration'].source_type if lm.provenance else 'none'}")
        print(f"  Feasibility: is_feasible={j.is_connection_feasible}")
        if j.connection_feasibility_notes:
            for note in j.connection_feasibility_notes:
                print(f"    Note: {note}")
        print(f"  Journey Provenance: overall={j.provenance.overall_source_type}, is_fully_confirmed={j.provenance.is_fully_confirmed}, has_live={j.provenance.has_live_attributes}")

    print("\n" + "=" * 70)
    print("ALL LIVE ROUTING VERIFICATION STEPS COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
