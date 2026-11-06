# KogniSync Live Provider Verification & Journey Quality

**Document Reference:** `docs/architecture/LIVE_PROVIDER_VERIFICATION.md`  
**Milestone:** KogniSync M2.4  
**Date:** November 6, 2026  
**Status:** Verification Completed (Automated Mock Suite: PASS | Live External API: BLOCKED — credentials unavailable)  
**Author:** KogniSync Core Engineering  

---

## 1. Executive Summary & Verification Status

Milestone **M2.4** establishes rigorous verification standards for KogniSync's transport provider adapter architecture, validates the Google Routes API v2 adapter, tightens provider failure observability, and verifies how provider-enriched metrics feed into multimodal composition, proportional carbon calculation, and Pareto multi-objective optimization.

### 1.1 Status Matrix

| Verification Dimension | Status | Evidence & Reference |
| :--- | :---: | :--- |
| **Adapter Contract & Capabilities** | **PASS** | `backend/tests/test_live_provider_verification.py::test_1` |
| **Controlled Smoke Test (Mocked Integration)** | **PASS** | `backend/tests/test_live_provider_verification.py::test_2` |
| **Distinct Failure Classification** | **PASS** | `backend/tests/test_live_provider_verification.py::test_3` (7 parametrized error scenarios) |
| **Dynamic Duration & Ranking Updates** | **PASS** | `backend/tests/test_live_provider_verification.py::test_4` |
| **Proportional Route Metric Updates (Carbon)** | **PASS** | `backend/tests/test_live_provider_verification.py::test_5` |
| **Hard Constraint Enforcement (Budget & Deadline)** | **PASS** | `backend/tests/test_live_provider_verification.py::test_6,7` |
| **Pareto Frontier Determinism** | **PASS** | `backend/tests/test_live_provider_verification.py::test_8` |
| **Granular Provenance Integrity** | **PASS** | `backend/tests/test_live_provider_verification.py::test_9` |
| **Explainability & Credibility Disclosures** | **PASS** | `backend/tests/test_live_provider_verification.py::test_10` |
| **Anti-Credential Leakage** | **PASS** | `backend/tests/test_live_provider_verification.py::test_11` |
| **Live External Network Verification** | **BLOCKED** | Credentials unavailable in environment (`GOOGLE_MAPS_API_KEY` unset) |

> [!IMPORTANT]
> In accordance with KogniSync's truth-in-advertising guidelines, live external network calls are marked **BLOCKED — credentials unavailable**. Live responses are never fabricated. Automated CI and unit testing rely exclusively on mocked HTTP transports (`httpx.MockTransport`) to guarantee deterministic results without incurring paid API quota costs or leaking secrets.

---

## 2. Credential Audit & Environment Configuration

### 2.1 Credential Audit
During Phase 2 inspection:
- `settings.GOOGLE_MAPS_API_KEY`: `None` / empty.
- `settings.GOOGLE_ROUTES_ENABLED`: `False`.
- No Google Maps or Google Routes API keys exist in environment variables.
- Status is safely surfaced via `GET /api/v1/journeys/providers`:
  ```json
  {
    "defaultProvider": "google_routes",
    "liveVerificationStatus": "BLOCKED — credentials unavailable",
    "providers": [
      {
        "providerId": "google_routes",
        "name": "Google Routes API v2",
        "supportedModes": ["bus", "cab", "metro", "rapido", "walk"],
        "isAvailable": false,
        "isLiveAuthenticated": false,
        "timeoutSeconds": 3.0,
        "liveVerificationStatus": "BLOCKED — credentials unavailable"
      }
    ]
  }
  ```

### 2.2 Enabling Live External Access (Production / Staging)
To verify or run with the genuine Google Routes API v2 in production:
1. Obtain an API key from Google Cloud Console with the **Routes API** enabled.
2. In your `.env` or deployment secret store, configure:
   ```bash
   GOOGLE_ROUTES_ENABLED=True
   GOOGLE_MAPS_API_KEY="AIzaSy..."
   ```
3. Restart the backend service. `GET /api/v1/journeys/providers` will report `isAvailable: true` and `liveVerificationStatus: "PASS"`.

---

## 3. Controlled Smoke-Test Scope & Outcome

The controlled smoke test (`test_2_controlled_smoke_test_normalized_response`) verifies the complete normalization pipeline:
- **Corridor Tested:** Bangalore Kempegowda International Airport (`13.198, 77.706`) to MG Road Station (`12.975, 77.609`).
- **Transport Mode:** `cab` (mapped to Google travelMode `DRIVE`, routingPreference `TRAFFIC_AWARE`).
- **Google Endpoint:** `POST https://routes.googleapis.com/directions/v2:computeRoutes`.
- **FieldMask:** `routes.duration,routes.distanceMeters,routes.description,routes.warnings`.
- **Normalized Output:**
  - `duration_minutes`: 28 (from `"1680s"`).
  - `distance_km`: 21.5 (from `21500m`).
  - `retrieved_at`: Valid ISO 8601 UTC timestamp generated post-parsing.
  - `duration` provenance: `source_type="provider_live"`, `is_estimate=False`, `provider_name="Google Routes API v2"`.
  - `distance` provenance: `source_type="provider_live"`, `is_estimate=False`, `provider_name="Google Routes API v2"`.
  - `fare` & `availability`: Correctly absent from provider response; preserved as modeled corridor estimates and simulated demo inventory.

---

## 4. Failure Classification & Fallback Policies

KogniSync strictly distinguishes transient network outages from configuration errors and invalid client requests:

| Provider Error Code | HTTP / Condition | `provider_status` Diagnostic Label | Fallback Policy |
| :--- | :--- | :--- | :--- |
| `AUTH_FAILURE` | 401 / 403 / missing key | `auth_failed_fallback_deterministic` | Search proceeds via corridor model; error logged as auth failure without leaking key. |
| `RATE_LIMITED` | 429 Too Many Requests | `rate_limited_fallback_deterministic` | Search proceeds via corridor model; backoff warning logged. |
| `UNAVAILABLE` | 500 / 502 / 503 / network drop | `unavailable_fallback_deterministic` | Search proceeds via corridor model; provider marked down. |
| `TIMEOUT` | Request exceeds timeout | `timeout_fallback_deterministic` | Search proceeds via corridor model; timeout logged. |
| `INVALID_REQUEST` | 400 Bad Request payload | `invalid_request_fallback_deterministic` | Search proceeds via corridor model; payload schema rejected by upstream. |
| `UNSUPPORTED_MODE` | Mode not in provider set | `unsupported_mode_fallback_deterministic` | Search proceeds via corridor model; leg mode routed to domestic catalog. |
| `EMPTY_RESULT` | 200 OK with `routes: []` | `empty_fallback_deterministic` | Search proceeds via corridor model; no physical path found. |
| `MALFORMED_RESPONSE` | Invalid JSON / missing fields | `malformed_fallback_deterministic` | Search proceeds via corridor model; upstream schema drift logged. |

---

## 5. Provenance Rules & Multimodal Integration

1. **Partial Provider Promotion Guard**:
   - A live duration/distance response from Google Routes only validates `duration` and `distance`.
   - `fare` remains `deterministic_estimate` (`is_estimate=True`).
   - `availability` remains `simulated` (`is_real_inventory=False`).
   - The leg `source_type` remains `deterministic_estimate` with `has_live_provider=True`.
   - The journey `overall_source_type` is `mixed` with `has_live_attributes=True` and `is_fully_confirmed=False`.
2. **Proportional Carbon Updates**:
   - When a provider reports exact corridor distance (`dist`), segment carbon is calculated as:
     $$\text{carbon}_{\text{live}} = \text{round}\left(\text{carbon}_{\text{baseline}} \times \frac{\text{dist}_{\text{live}}}{\text{dist}_{\text{baseline}}}, 1\right)$$
3. **Pareto Optimization & Constraints**:
   - Evaluated using live duration and updated carbon in `JourneyCandidateInput`.
   - Hard budget and arrival deadline filters apply to the updated total price and arrival times without relaxation.
   - Rankings are 100% deterministic across repeated calls.
4. **Explainability & Credibility Notices**:
   - When live duration is present, `aiExplanation.isDurationEstimated` is set to `False`.
   - `dataCredibilityNotice` explicitly clarifies that transit durations reflect live provider traffic feeds, while fares remain corridor estimates and seat availability is simulated demo inventory.

---

## 6. Limitations & Next Steps

1. **Carrier Ticketing**:
   - Google Routes is a routing and directions service; it does not issue PNRs or real tickets.
   - Downstream booking holds operate in local demonstration sandbox mode.
2. **Next Provider Integrations**:
   - Commercial flight GDS / NDC adapter for live flight fares and confirmed seat classes.
   - Long-distance rail API for real-time train delay tracking and verified berth quotas.

