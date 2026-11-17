# KogniSync M4.0.3 Verification Report — Dynamic Origin/Destination Synchronization Across Journey Map

**Document ID:** `DOC-KS-M4-0-3-SYNC-REPORT`  
**Date:** November 15, 2026  
**Branch:** `feature/m4-0-3-dynamic-journey-map-sync`  
**Base:** `origin/main` (`0cb30bb`)  
**Worktree:** `E:\KogniSync\KogniSync-m4-stabilization`  
**Author:** AI Stabilization & Systems Engineering  

---

## 1. Executive Summary

During journey planning for non-hub regional origins (such as **Origin: Tumkur, Destination: Chennai, Date: 2026-11-16**), the application displayed the search header correctly (`Tumkur → Chennai`), but the interactive multimodal journey map displayed route geometry and markers originating in central Bengaluru (`12.96°N, 77.57°E`) instead of Tumkur (`13.3401°N, 77.1006°E`).

This defect has been resolved end-to-end. The system now incorporates a generalized, multi-tiered forward geocoding and regional gazetteer architecture across backend and frontend, dynamically binding route geometry, waypoints, polylines, and viewport bounds to the active search endpoints.

Zero hardcoded city-specific overrides were used. Canonical databases (`BookingInventory/data/APS-05.db`) and original repository worktrees remain completely untouched.

---

## 2. Root-Cause Analysis

A comprehensive audit identified 6 interacting defects causing the map desynchronization:

| # | Component | Defect Mechanism | Impact |
|---|-----------|------------------|--------|
| **1** | `backend/app/services/journey/hubs.py` (L485) | `resolve_hub_context` fell through to `def_lat = 13.0 if is_origin else 15.0; def_lng = 77.6 if is_origin else 74.5` for any city not in the 14-city `CITY_HUB_REGISTRY`. Subtracting local offsets produced `(12.96, 77.57)` (Chamrajpet/Cottonpet in Bengaluru). | Backend journey segments were anchored to Bengaluru coordinates for all unlisted cities. |
| **2** | `frontend/src/api/orchestrationEngine.ts` (L274) | Client-side fallback `resolveHubContext` mirrored the identical hardcoded Bengaluru fallback `13.0, 77.6`. | Offline and fallback journeys synthesized identical Bengaluru origin coordinates. |
| **3** | Forward Geocoding Gap | `LocationService` possessed reverse-geocoding (lat/lng $\rightarrow$ address) but had no forward geocoding (place name $\rightarrow$ lat/lng) or forward API endpoint. | Arbitrary city names could not be dynamically resolved to spatial coordinates. |
| **4** | `frontend/src/pages/ResultsPage.tsx` | Did not parse `originLat`/`originLng`/`destLat`/`destLng` from URL query parameters, and React Query key did not normalize place names or include coordinates. | Cache collisions and inability to restore GPS/exact coordinates from deep links. |
| **5** | `frontend/src/components/results/JourneyResults.tsx` | Did not reset `selectedJourneyId` state when the `journeys` prop changed upon a new search. | An alternative route ID selected in a previous query could persist or force stale active journey selection. |
| **6** | `frontend/src/components/map/JourneyMap.tsx` | Route enrichment query key lacked coordinate isolation; fallback target journey had hardcoded `{ lat: 12.97, lng: 77.59 }`; and no divergence detection existed to discard stale geometries. | Cached polylines from prior searches were reused, and divergent geometries were rendered. |

---

## 3. Architecture & Implementation Summary

### 3.1 Multi-Tiered Forward Geocoding Engine
Implemented in `backend/app/services/location/service.py`:
1. **Tier 1 — Custom / GPS Coordinates:** Exact client-supplied coordinates are given highest precedence.
2. **Tier 2 — In-Memory Forward Cache (`_forward_cache`):** Sub-millisecond lookup for frequently queried locations.
3. **Tier 3 — Regional Gazetteer (`REGIONAL_GAZETTEER`):** Deterministic, offline-safe coordinate resolution for regional urban transit centers (Tumkur, Hubli, Belgaum, Mangalore, Udupi, Coimbatore, Madurai, etc.).
4. **Tier 4 — Live OpenStreetMap Nominatim Search (`_forward_geocode_nominatim`):** Online fallback resolving any arbitrary global locality, city, or transit stop with strict 2.5s timeouts and User-Agent compliance.

### 3.2 Canonical API Endpoint
Added in `backend/app/api/routes/location.py`:
- `GET /api/v1/location/geocode?q={location_name}`
- Returns `GeocodeResponse` with camelCase aliases (`coordinates.lat`, `coordinates.lng`, `displayName`, `provider`).

### 3.3 Dynamic Hub & Corridor Distance Resolution
- Updated `backend/app/services/journey/hubs.py`:
  - `resolve_hub_context` dynamically forward-geocodes unrecognized place names and creates dynamic `HubProfile` and `user_node` at the exact geocoded coordinates.
  - Spatial resolution to metropolitan hubs is strictly bounded to a $35\text{ km}$ radius, preventing independent regional cities (e.g. Tumkur, $70\text{ km}$ away) from being absorbed into Bengaluru.
  - `estimate_corridor_distance_km` computes Great-Circle distance using Haversine $\times 1.25$ circuity factor based on real resolved coordinates.
- Updated `frontend/src/api/orchestrationEngine.ts`:
  - Added matching `REGIONAL_GAZETTEER` and coordinate-aware `resolveHubContext` and `estimateCorridorDistanceKm`.

### 3.4 Strict Cache Isolation & View Synchronization
- Updated `frontend/src/pages/ResultsPage.tsx`:
  - Parses `originLat`, `originLng`, `destLat`, `destLng` from `useSearchParams`.
  - Normalizes query keys with `.trim().toLowerCase()` and includes coordinates to prevent stale cache reuse.
- Updated `frontend/src/components/results/JourneyResults.tsx`:
  - Added `useEffect` hook to reset `selectedJourneyId` to `null` whenever `journeys` changes, ensuring default top-ranked Pareto selection.
  - Explicitly binds `selectedJourneyId={activeJourney.id}` to `JourneyMap`.
- Updated `frontend/src/components/map/JourneyMap.tsx`:
  - Query key for `enrichJourneyRoute` includes journey ID and exact endpoint coordinates of all segments.
  - Added spatial congruency check in `effectiveRoute`: if server-enriched geometry origin diverges by $> 0.5^\circ$ from `targetJourney.origin.coordinates`, it is rejected in favor of client fallback.
  - Added waypoints to Leaflet `allLatLangs` ensuring `fitBounds` accurately envelopes active endpoints.

---

## 4. Verification & Test Execution

### 4.1 Automated Frontend Test Suite (`src/tests/dynamicJourneyMapSync.test.ts`)
Run via `node scripts/runTests.mjs`:

```
=================================================================
RUNNING DYNAMIC JOURNEY MAP SYNCHRONIZATION TEST SUITE (M4.0.3)
=================================================================

--- Test A: Origin Change (Bengaluru → Chennai to Tumkur → Chennai) ---
✓ Origin dynamically shifted: Bangalore (12.9566, 77.5796) -> Tumkur (13.3251, 77.0856)
✓ Route geometry origin verified at Tumkur: 13.3251°N, 77.0856°E

--- Test B: Destination Change (Tumkur → Chennai to Tumkur → Coimbatore) ---
✓ Destination dynamically shifted: Chennai (13.0977, 80.2857) -> Coimbatore (11.0318, 76.9708)

--- Test C: Both Endpoints Change (Hubli → Goa) ---
✓ Both endpoints independent of Bangalore: Origin Hubli (15.3497, 75.109), Destination Goa (15.3143, 74.139)

--- Test D: Query Cache Key Isolation ---
✓ Cache keys strictly isolate distinct geographic origins and destinations

--- Test E: Pareto Route Selection Updates Active Geometry ---
✓ Active journey selection switches between jny-tumkur-to-chennai-cheapest and jny-tumkur-to-chennai-greenest

--- Test F: Graceful Handling of Empty & Single-Segment Geometries ---
✓ Empty journey gracefully produces clean 0-segment geometry without throwing

--- Test G: URL Parameter Parsing & Direct Coordinate Restoration ---
✓ URL parameters directly restore request and exact origin coordinates

--- Test H: Regression Protection & Provenance Classification ---
✓ Provenance contracts and multi-modal constraints strictly preserved across all journeys

=================================================================
ALL TESTS (A through H) PASSED SUCCESSFULLY! ✓
=================================================================
```

### 4.2 Automated Backend Test Suite (`backend/tests/test_dynamic_journey_map_sync.py`)
Run via `py -3.13 -m pytest`:

```
collected 7 items

test_forward_geocode_regional_gazetteer_tumkur PASSED            [ 14%]
test_forward_geocode_api_endpoint PASSED                         [ 28%]
test_resolve_hub_context_tumkur_dynamic PASSED                   [ 42%]
test_resolve_hub_context_custom_coordinates PASSED               [ 57%]
test_dynamic_corridor_distance_calculation PASSED                [ 71%]
test_journey_orchestration_tumkur_origin_propagation PASSED      [ 85%]
test_maps_enrich_reflects_dynamic_origin PASSED                  [100%]

============================= 7 passed in 15.07s =============================
```

### 4.3 Regression Safety Verification
- `test_location_service.py` & `test_maps_geometry.py`: **16 passed in 13.96s**.
- `test_m4_0_2_hardening.py` (including live Redis Lua limiter): **12 passed in 11.64s**.
- Frontend production build (`tsc -b; vite build`): **0 errors, 2091 modules transformed**.

---

## 5. Canonical Database Checksum Integrity

The canonical SQLite database was verified before and after code modifications:

| Database File | Expected SHA-256 Checksum | Verified SHA-256 Checksum | Match Status |
|---------------|---------------------------|---------------------------|--------------|
| `BookingInventory/data/APS-05.db` | `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` | `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` | **PERFECT MATCH (UNMODIFIED)** |

---

## 6. Changed-File Inventory

The following 10 tracked files were modified and 2 new automated test suites created:

```
M  backend/app/api/routes/location.py
M  backend/app/services/journey/hubs.py
M  backend/app/services/journey/service.py
M  backend/app/services/location/schemas.py
M  backend/app/services/location/service.py
M  frontend/scripts/runTests.mjs
M  frontend/src/api/orchestrationEngine.ts
M  frontend/src/components/map/JourneyMap.tsx
M  frontend/src/components/results/JourneyResults.tsx
M  frontend/src/pages/ResultsPage.tsx
A  backend/tests/test_dynamic_journey_map_sync.py
A  frontend/src/tests/dynamicJourneyMapSync.test.ts
```
