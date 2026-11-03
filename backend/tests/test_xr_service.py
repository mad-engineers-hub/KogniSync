"""
Unit tests for KogniSync Organizer XR Capability.
Validates organizer schema conformance, request-aware journey matching,
wayfinding instructions, and device profiles.
"""

import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_organizer_enums_conformance():
    """Verify XR enums strictly match BookingInventory/data/enums.json."""
    with open("E:/KogniSync/KogniSync/BookingInventory/data/enums.json", "r") as f:
        data = json.load(f)

    enums = data["enums"]
    # Expected canonical enums
    assert set(enums["xr_scene_type"]) == {"panorama_360", "model_3d", "photogrammetry", "video_360"}
    assert set(enums["xr_asset_format"]) == {"jpg_equirect", "gltf", "glb", "usdz", "ktx2", "mp4"}
    assert set(enums["xr_platform"]) == {"webxr", "arcore", "arkit", "desktop_fallback"}
    assert set(enums["device_class"]) == {"phone_ar", "tablet_ar", "headset_vr", "desktop"}
    assert "xr_scene" in enums["entity_type"]


def test_list_and_filter_xr_scenes():
    """Test GET /api/v1/xr/scenes and query filtering."""
    # List all
    res = client.get("/api/v1/xr/scenes")
    assert res.status_code == 200
    scenes = res.json()
    assert len(scenes) >= 5
    scene_ids = [s["scene_id"] for s in scenes]
    assert "xrs_chennai_central_concourse" in scene_ids
    assert "xrs_ksr_bengaluru_interchange" in scene_ids

    # Filter by entity_type == 'hotel'
    res_hotel = client.get("/api/v1/xr/scenes?entity_type=hotel")
    assert res_hotel.status_code == 200
    hotel_scenes = res_hotel.json()
    assert all(s["entity_type"] == "hotel" for s in hotel_scenes)

    # Filter by city == 'Chennai'
    res_chennai = client.get("/api/v1/xr/scenes?city=Chennai")
    assert res_chennai.status_code == 200
    chennai_scenes = res_chennai.json()
    assert all("chennai" in s["city_name"].lower() for s in chennai_scenes)


def test_get_single_xr_scene():
    """Test GET /api/v1/xr/scenes/{scene_id}."""
    res = client.get("/api/v1/xr/scenes/xrs_chennai_central_concourse")
    assert res.status_code == 200
    data = res.json()
    assert data["scene_id"] == "xrs_chennai_central_concourse"
    assert data["scene_type"] == "panorama_360"
    assert len(data["assets"]) > 0
    assert len(data["hotspots"]) == 4
    assert len(data["wayfinding_cases"]) == 2

    # Verify 404 for unknown scene
    res_404 = client.get("/api/v1/xr/scenes/xrs_unknown_scene_id")
    assert res_404.status_code == 404


def test_match_scenario_1_chennai_to_udupi():
    """Test Scenario 1 (Chennai -> Udupi): returns Chennai Central and Mangalore/Udupi link."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "transfer_hubs": ["Chennai Airport", "Mangalore Airport"],
    }
    res = client.post("/api/v1/xr/match", json=payload)
    assert res.status_code == 200
    data = res.json()
    matched_ids = [s["scene_id"] for s in data["scenes"]]

    # Must contain Udupi/Mangalore transit and Chennai hub
    assert "xrs_mangalore_udupi_transit" in matched_ids
    assert "xrs_chennai_central_concourse" in matched_ids


def test_match_scenario_2_udayapalya_to_chennai():
    """Test Scenario 2 (Udayapalya -> Chennai): returns KSR Bengaluru and Chennai Central."""
    payload = {
        "origin": "Udayapalya",
        "destination": "Chennai",
        "transfer_hubs": ["KSR Bangalore", "Chennai Central"],
    }
    res = client.post("/api/v1/xr/match", json=payload)
    assert res.status_code == 200
    data = res.json()
    matched_ids = [s["scene_id"] for s in data["scenes"]]

    assert "xrs_ksr_bengaluru_interchange" in matched_ids
    assert "xrs_chennai_central_concourse" in matched_ids


def test_match_scenario_3_bangalore_to_goa():
    """Test Scenario 3 (Bangalore -> Goa): returns Goa Madgaon concourse."""
    payload = {
        "origin": "Bangalore",
        "destination": "Goa",
        "transfer_hubs": ["Madgaon Junction"],
    }
    res = client.post("/api/v1/xr/match", json=payload)
    assert res.status_code == 200
    data = res.json()
    matched_ids = [s["scene_id"] for s in data["scenes"]]

    assert "xrs_goa_madgaon_hub" in matched_ids


def test_match_canonical_hotel_xr():
    """Test matching canonical hotel from 08_hotels.csv (has_xr_scene=True)."""
    payload = {
        "destination": "Chennai",
        "hotel_id": "htl_8179b205",  # Grand Courtyard
    }
    res = client.post("/api/v1/xr/match", json=payload)
    assert res.status_code == 200
    data = res.json()
    matched_ids = [s["scene_id"] for s in data["scenes"]]

    assert "xrs_htl_8179b205" in matched_ids


def test_ar_wayfinding_case_details():
    """Test GET /api/v1/xr/wayfinding/{scene_id}."""
    res = client.get("/api/v1/xr/wayfinding/xrs_chennai_central_concourse")
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) >= 2

    bus_case = next(c for c in cases if c["wayfinding_id"] == "arw_chennai_train_to_bus")
    assert bus_case["origin_title"] == "Platform 3 Arrival Gate"
    assert bus_case["destination_title"] == "MTC City Feeder Bus Gate 3"
    assert len(bus_case["steps"]) == 4
    assert bus_case["steps"][-1]["turn_direction"] == "arrival"


def test_device_profiles_and_capabilities():
    """Test GET /api/v1/xr/device-profiles."""
    res = client.get("/api/v1/xr/device-profiles")
    assert res.status_code == 200
    profiles = res.json()
    classes = {p["device_class"] for p in profiles}
    platforms = {p["platform"] for p in profiles}

    assert "desktop" in classes
    assert "phone_ar" in classes
    assert "headset_vr" in classes
    assert "desktop_fallback" in platforms
    assert "webxr" in platforms
