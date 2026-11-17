# KogniSync PR #29 (M4.0.4) — Pre-Merge Code Review & Adversarial Remediation Verification

**Pull Request:** [#29: fix(map): M4.0.4 client fallback origin geometry synchronization](https://github.com/mad-engineers-hub/KogniSync/pull/29)  
**Base Branch:** `main`  
**Head Branch:** `feature/m4-0-4-fallback-origin-sync`  
**Initial Head SHA:** `8f96e2997e4afdf11082c6ade6f0c69460855b07`  
**Remediation Milestone:** M4.0.4.1  
**Status:** **ALL 3 FINDINGS RESOLVED & VERIFIED — APPROVED FOR MERGE**

---

## 1. Executive Summary

During pre-merge review of PR #29, an adversarial inspection identified three critical areas for remediation:
1. **Finding 1 (Medium-High):** Blanket 45 km radial clamp indiscriminately discarded valid custom GPS coordinates for expansive districts/regions (e.g. Palolem in Goa ~60 km from Panaji, Sira in Tumkur ~52 km from center, Jewar in NCR ~72 km from Delhi).
2. **Finding 2 (High):** Synthetic `{ lat: 0, lng: 0 }` fallback coordinates in `JourneyMap.tsx` created Null Island markers and routed polylines across the Atlantic Ocean, causing fitBounds to zoom out globally.
3. **Finding 3 (Medium):** Swallowed HTTP 401/403 catch block in `disruptionIntelligence.test.ts` manufactured passing test responses rather than enforcing hermetic auth contract validation.

In M4.0.4.1, all three findings have been comprehensively remediated and verified with dedicated regression test suites (`gpsCollisionDetector.test.ts`, `nullIslandAvoidance.test.ts`, hermetic disruption tests, and isolated visual captures).

---

## 2. Remediation Verification

### Finding 1: Cross-City Collision Detection & Intentional GPS Preservation
- **Remediation Implemented:**
  - In `frontend/src/api/orchestrationEngine.ts` and `backend/app/services/journey/hubs.py`:
    - Replaced the arbitrary `dist > 45` radial clamp with `detectCrossCityCollision()`.
    - Defined `CANONICAL_CITY_ALIASES` mapping regional variations and registered city hubs.
    - Implemented a 25 km cross-city collision radius: coordinates are only rejected if they fall within $\le 25\text{ km}$ of a *conflicting* registered city hub (e.g. Bangalore coordinates attached to a Tumkur query).
    - Legitimate intentional custom coordinates outside 45 km (e.g. Palolem Beach in Goa ~60 km from Panaji, Sira in Tumkur ~52 km, Jewar in Delhi NCR ~72 km, and map picker pins) are strictly preserved on `userNode.coordinates`.
- **Automated Test Proof:**
  - Created `frontend/src/tests/gpsCollisionDetector.test.ts` (Case 1A–1F, Test 2A–2E, Test 3).
  - All collision detection and coordinate preservation tests pass cleanly.
- **Verdict:** **RESOLVED**

---

### Finding 2: Null Island Elimination & Explicit Spatial Fallback
- **Remediation Implemented:**
  - Created `frontend/src/utils/mapCoordinates.ts` with `isValidCoordinate()`.
    - Strictly rejects `(0, 0)` Null Island coordinates, `NaN`, `Infinity`, `undefined`, and out-of-range latitudes ($|lat| > 90$) and longitudes ($|lng| > 180$).
    - Safely preserves valid individual zero values on the Equator (`lat: 0, lng: 77.5`) and Prime Meridian (`lat: 51.5, lng: 0`).
  - In `frontend/src/api/routes.ts`:
    - `buildClientFallbackRoute` uses `isValidCoordinate` and outputs empty arrays (`[]`) when coordinates are missing, never interpolating towards Null Island.
    - Sets invalid endpoint coordinates to `{ latitude: NaN, longitude: NaN }` instead of `{ latitude: 0, longitude: 0 }`.
  - In `frontend/src/components/map/JourneyMap.tsx`:
    - Filtered all polylines and waypoints through `isValidCoordinate`.
    - Enforced that polylines are only rendered if $\ge 2$ valid points exist.
    - Filtered `allLatLangs` before calling `map.fitBounds` so invalid coordinates never corrupt camera bounds.
    - Added `hasValidSpatialGeometry` state and explicit `<div data-testid="spatial-geometry-unavailable">` overlay when geographic coordinates are unavailable, with a one-click button to switch to Waypoint schematic view.
    - Fixed badge labeling: pure client fallback is labeled `Client Fallback Simulation` rather than `Valhalla OSM Live`.
- **Automated Test Proof:**
  - Created `frontend/src/tests/nullIslandAvoidance.test.ts` (Sections 1, 2A–2C, 3).
  - All coordinate boundary and interpolation tests pass cleanly.
- **Verdict:** **RESOLVED**

---

### Finding 3: Hermetic Disruption Tests & Explicit Auth Enforcement
- **Remediation Implemented:**
  - In `frontend/src/tests/disruptionIntelligence.test.ts`:
    - Completely removed the catch block that swallowed HTTP 401/403 and called `getGTFSFeeds()`.
    - Structured hermetic test cases using `globalThis.fetch` mocking with `try...finally`:
      - **Case A (Network Failure):** Rejects with `TypeError('fetch failed')` $\to$ asserts `pollGTFSFeeds(false)` gracefully returns offline fallback feeds list.
      - **Case B (HTTP 401):** Returns status 401 $\to$ asserts `pollGTFSFeeds(false)` rejects with `ApiError` status 401 (never swallowed).
      - **Case C (HTTP 403):** Returns status 403 $\to$ asserts `pollGTFSFeeds(false)` rejects with `ApiError` status 403.
      - **Case D (HTTP 200):** Returns valid payload $\to$ asserts `pollGTFSFeeds(false, { internalKey: 'valid-test-key' })` correctly returns parsed `GTFSFeedListResponse`.
- **Automated Test Proof:**
  - `disruptionIntelligence.test.ts` passes with 100% hermetic isolation regardless of host port status.
- **Verdict:** **RESOLVED**

---

## 3. Visual Verification & Screenshot Artifacts

All 4 required scenarios were captured using Playwright (`scripts/capture_m4_0_4.cjs`):

| Screenshot | Scenario | Provenance Badge | Description |
| :--- | :--- | :--- | :--- |
| `m4_0_4_client_fallback_tumkur_goa.png` | Tumkur $\to$ Goa | `Client Fallback Simulation` | Pure client fallback with `/api/v1/journeys/search` and `/api/v1/maps/enrich` aborted. Green origin marker clicked at Tumkur (`13.3251°N, 77.0856°E`). Route begins in Tumkur. |
| `m4_0_4_backend_tumkur_goa.png` | Tumkur $\to$ Goa | `Valhalla OSM Live` | Live backend and Valhalla active. Origin marker clicked at Tumkur. Live OSM route geometry displayed. |
| `m4_0_4_client_fallback_bangalore_goa.png` | Bengaluru $\to$ Goa | `Client Fallback Simulation` | Baseline Bengaluru $\to$ Goa client fallback. Green origin marker clicked at Bengaluru (`12.9616°N, 77.5846°E`). |
| `m4_0_4_invalid_geometry_no_null_island.png` | Spatial Unavailable | `Spatial Geometry Unavailable` | Missing spatial coordinates. Explicit overlay rendered with "Switch to Waypoints View" button. Zero Null Island artifacts. |

---

## 4. Full Regression Verification Summary

| Suite / Verification Area | Test Count | Result | Details |
| :--- | :--- | :--- | :--- |
| `frontend/src/tests/gpsCollisionDetector.test.ts` | 12 assertions | **PASSED** | Stale Bengaluru coords cleared on Tumkur query; Palolem, Sira, Jewar, map pins preserved. |
| `frontend/src/tests/nullIslandAvoidance.test.ts` | 18 assertions | **PASSED** | (0,0) rejected, Equator/Prime Meridian preserved, NaN rejected, bounds cleanly filtered. |
| `frontend/src/tests/disruptionIntelligence.test.ts` | Cases A, B, C, D | **PASSED** | Hermetic network error fallback, 401/403 propagation, and 200 payload parsing. |
| `frontend/src/tests/fallbackOriginSync.test.ts` | Tests A through I | **PASSED** | Dynamic synchronization under client fallback simulation verified. |
| Complete Frontend Test Suite (`npm test`) | 15 test suites | **PASSED** | All 15 suites passed (0 skipped, 0 failed). |
| Frontend Typecheck & Build (`npm run build`) | `tsc -b; vite build` | **PASSED** | Zero TypeScript errors, production bundle compiled cleanly. |
| Frontend Linter (`npm run lint`) | `oxlint` | **PASSED** | Zero lint errors across 127 files. |
| Backend Dynamic Map Tests (`pytest`) | 7 tests | **PASSED** | `tests/test_dynamic_journey_map_sync.py` passed in 17.3s. |
| Backend Hardening Suite (`pytest`) | 12 tests | **PASSED** | `tests/test_m4_0_2_hardening.py` passed (11 passed, 1 live Redis skipped). |
| Canonical DB Checksum (`APS-05.db`) | SHA-256 | **VERIFIED** | `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` bit-for-bit match. |

---

## 5. Final Recommendation

**PR #29 IS APPROVED FOR MERGE.**  
All three adversarial review findings have been resolved, verified against strict invariants, backed by automated unit tests, and corroborated by visual evidence.
