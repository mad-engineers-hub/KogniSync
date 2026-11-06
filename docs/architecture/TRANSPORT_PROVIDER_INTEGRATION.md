# KogniSync Transport Provider Adapter Architecture & External Integration Foundation

**Document Reference:** `docs/architecture/TRANSPORT_PROVIDER_INTEGRATION.md`  
**Milestone:** KogniSync M2.3  
**Status:** Active & Implemented  
**Author:** KogniSync Core Engineering  

---

## 1. Executive Summary & Objective

In Milestones M2.0–M2.2, KogniSync established the backend as the authoritative home for multimodal journey composition, Pareto multi-objective optimization, and data provenance. However, transport metrics across legs relied strictly on corridor models and synthetic schedules.

Milestone **M2.3** establishes a production-oriented, pluggable **Transport Provider Adapter Architecture** and integrates **Google Routes API v2** as the first external transport data provider. This enables KogniSync to ingest genuine, traffic-aware travel durations and exact road distances while rigorously preserving KogniSync's multimodal composition, Pareto frontier optimization, and data credibility invariants.

```
                      +---------------------------------------+
                      |       JourneyOrchestrationService     |
                      +-------------------+-------------------+
                                          |
                        Queries Registered Adapters (per-leg)
                                          |
                      +-------------------v-------------------+
                      |        TransportProvider (ABC)        |
                      +-------------------+-------------------+
                                          |
               +--------------------------+--------------------------+
               |                                                     |
+--------------v---------------+                      +--------------v---------------+
| GoogleRoutesTransportAdapter |                      | Future Adapters (GDS/Transit)|
| (Routes v2 computeRoutes)    |                      | (e.g. IRCTC, ONDC, Amadeus)  |
+--------------+---------------+                      +--------------+---------------+
               |                                                     |
      Normalized Response                                   Normalized Response
 (Duration, Distance, Provenance)                      (Timetable, Fare, Inventory)
               |                                                     |
               +--------------------------+--------------------------+
                                          |
                     Leg Integration & Fallback Boundary
               (Partial responses isolate live attributes;
                unverified attributes remain estimates/demo)
                                          |
                      +-------------------v-------------------+
                      |      Multi-Objective Pareto Optimizer  |
                      +-------------------+-------------------+
                                          |
                                Public API Contract
                       (JourneySearchResponse with Provenance)
```

---

## 2. Reusable Provider Interface

The provider contract is defined in `backend/app/services/journey/provider.py`. It establishes a clean abstraction boundary ensuring that external vendor schemas never leak into public API responses.

### 2.1 Abstract Base Class (`TransportProvider`)

```python
class TransportProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique machine-readable identifier (e.g., 'google_routes')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g., 'Google Routes API v2')."""
        pass

    @property
    @abstractmethod
    def supported_modes(self) -> set[TransportMode]:
        """Set of transport modes supported by this provider (e.g., {'cab', 'rapido', 'bus', 'metro', 'walk'})."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Indicates if the adapter is active, configured, and enabled."""
        pass

    @abstractmethod
    def is_live_authenticated(self) -> bool:
        """Indicates if genuine external credentials are configured."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Returns provider status, timeout configuration, and supported modes."""
        pass

    @abstractmethod
    async def search_segment(
        self, request: TransportSegmentSearchRequest
    ) -> NormalizedTransportSegmentResponse:
        """
        Queries the external provider for transport metrics on a single leg.
        Raises TransportProviderError on provider errors or unhandled conditions.
        """
        pass
```

### 2.2 Error Classification (`ProviderErrorCode`)

To provide deterministic failure handling and clear observability without credential leakage, errors are strictly classified into an enumerated type:

| Error Code | Enum Member | Meaning & Trigger | Fallback Action |
| :--- | :--- | :--- | :--- |
| `timeout` | `ProviderErrorCode.TIMEOUT` | HTTP request exceeded timeout boundary (`timeout_seconds + 0.5s`). | Log warning, record `timeout_fallback_deterministic`, use corridor estimate. |
| `auth_failure` | `ProviderErrorCode.AUTH_FAILURE` | Missing API key, empty secret, or HTTP 401/403. | Log warning, record `auth_failed_fallback_deterministic`, use corridor estimate. |
| `rate_limited` | `ProviderErrorCode.RATE_LIMITED` | HTTP 429 quota or rate limit exceeded. | Log warning, record `rate_limited_fallback_deterministic`, use corridor estimate. |
| `unavailable` | `ProviderErrorCode.UNAVAILABLE` | HTTP 5xx or network connection drop. | Log warning, record `unavailable_fallback_deterministic`, use corridor estimate. |
| `invalid_request` | `ProviderErrorCode.INVALID_REQUEST` | HTTP 400 bad request / rejected payload. | Log error, record `unavailable_fallback_deterministic`, use corridor estimate. |
| `empty_result` | `ProviderErrorCode.EMPTY_RESULT` | HTTP 200 OK but 0 routes found for corridor. | Log info, record `empty_fallback_deterministic`, use corridor estimate. |
| `malformed_response` | `ProviderErrorCode.MALFORMED_RESPONSE` | Invalid JSON or missing duration fields. | Log error, record `malformed_fallback_deterministic`, use corridor estimate. |
| `unsupported_mode` | `ProviderErrorCode.UNSUPPORTED_MODE` | Provider invoked for an unsupported mode. | Log info, record `unsupported_mode_fallback_deterministic`, use corridor estimate. |

---

## 3. Data Normalization & Attribute-Level Provenance

### 3.1 Normalized Segment Response

External responses are translated into `NormalizedTransportSegmentResponse`:
- **`duration_minutes`**: Parsed from vendor payload (e.g., Google `"1680s"` -> 28 minutes).
- **`distance_km`**: Parsed from vendor payload (e.g., Google `21500m` -> 21.5 km).
- **`retrieved_at`**: UTC ISO 8601 timestamp generated at query time.
- **`attribute_provenance`**: Granular map attaching `AttributeProvenanceSchema` to individual fields (`duration`, `distance`).

### 3.2 Granular Provenance Boundary

In conformance with Milestone M2.1 credibility principles:
1. **Partial Provider Responses**:
   Google Routes provides live traffic duration and road distance, but does **not** provide confirmed cab fares or live seat reservations.
   - `duration`: `source_type="provider_live"`, `is_estimate=False`, `provider_name="Google Routes API v2"`.
   - `distance`: `source_type="provider_live"`, `is_estimate=False`, `provider_name="Google Routes API v2"`.
   - `fare`: Remains `source_type="deterministic_estimate"`, `is_estimate=True`, `provider_name="KogniSync Corridor Fare Model"`.
   - `availability`: Remains `source_type="simulated"`, `is_estimate=True`, `is_real_inventory=False`.
2. **No False Leg Promotion**:
   A partial response does **not** promote the whole leg to `provider_live`. The segment `source_type` remains `deterministic_estimate`, with `has_live_provider=True`.
3. **Journey Provenance**:
   The overall journey is marked `overall_source_type="mixed"` (`has_live_attributes=True`, `has_simulated_attributes=True`, `is_fully_confirmed=False`), ensuring users and booking workers are fully informed that fares and capacity remain modeled.

---

## 4. Google Routes API v2 Adapter Integration

### 4.1 Endpoint & Authentication
- **Endpoint**: `POST https://routes.googleapis.com/directions/v2:computeRoutes`
- **Header**: `X-Goog-Api-Key: <GOOGLE_MAPS_API_KEY>`
- **FieldMask**: `routes.duration,routes.distanceMeters,routes.description,routes.warnings`
- **Configuration**:
  - `GOOGLE_ROUTES_ENABLED: bool` in `Settings` (default `False`).
  - `GOOGLE_MAPS_API_KEY: str | None` in `Settings`.

### 4.2 Mode Mapping
| Internal Transport Mode | Google Routes `travelMode` | Routing Preference | Notes |
| :--- | :--- | :--- | :--- |
| `cab` | `DRIVE` | `TRAFFIC_AWARE` | Live traffic duration |
| `rapido` | `TWO_WHEELER` | `TRAFFIC_AWARE` | Two-wheeler routing in eligible regions |
| `walk` | `WALK` | `TRAFFIC_UNAWARE` | Pedestrian routing |
| `bus` | `TRANSIT` | `TRAFFIC_UNAWARE` | Urban public transit |
| `metro` | `TRANSIT` | `TRAFFIC_UNAWARE` | Rail/subway transit lines |

### 4.3 Rate Limits & Permitted Usage
- Default quota: ~3,000 queries per minute per project.
- In accordance with Google Maps Platform terms, route geometry and duration are used dynamically for client navigation and multimodal optimization.

---

## 5. Failure & Fallback Mechanics

The `JourneyOrchestrationService` wraps provider invocation in `_resolve_segment_data()`:
```python
dur, dist, overrides = await self._resolve_segment_data(
    origin_node=origin,
    dest_node=destination,
    mode=mode,
    provider_name=provider_name,
    default_duration=default_dur,
    default_distance=default_dist,
    provider_status=provider_status,
)
```
- If the provider succeeds: Segment duration is set to `dur`, segment distance to `dist`, and departure/arrival times are shifted backwards from the arrival deadline to maintain positive buffer invariants.
- If the provider fails or is unconfigured: It silently falls back to `default_duration` and `default_distance` from the deterministic corridor model.
- `provider_status` in the response explicitly captures the outcome without exposing tokens or secrets (e.g. `google_routes: "active_live"`, `google_routes: "rate_limited_fallback_deterministic"`).

---

## 6. Verification Status Matrix

| Component | Implemented | Mock Tested | Live Verified | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Provider Adapter Interface** | **Yes** | **Yes** | N/A | `backend/app/services/journey/provider.py` |
| **Google Routes Adapter** | **Yes** | **Yes** | Optional Smoke Test | `backend/app/services/journey/google_routes_adapter.py` |
| **Timeout & 429 Error Handling** | **Yes** | **Yes** | N/A | Tested via `httpx.MockTransport` |
| **Auth & Malformed Payload Handling** | **Yes** | **Yes** | N/A | Tested via `httpx.MockTransport` |
| **Partial Attribute Provenance** | **Yes** | **Yes** | N/A | Live duration + modeled fare verified |
| **Deterministic Resilient Fallback** | **Yes** | **Yes** | N/A | 100% search reliability on upstream drop |
| **Pareto Optimizer Compatibility** | **Yes** | **Yes** | N/A | Hard constraints preserved with live data |
| **API Endpoints (`/providers`, `/health`)** | **Yes** | **Yes** | N/A | Tested via Starlette TestClient |

> [!NOTE]
> Live external API verification against Google Cloud requires a provisioned `GOOGLE_MAPS_API_KEY` and setting `GOOGLE_ROUTES_ENABLED=True`. In CI and development environments without active credentials, the adapter defaults to unconfigured mode and falls back cleanly to the deterministic spatial engine, ensuring CI never depends on paid API quotas.

---

## 7. Next Integration Steps

1. **Air Transport Provider (e.g., Amadeus / Kiwi / Airline API)**:
   - Provide live flight fares and confirmed timetable schedules for Leg 2 (Main Transport).
2. **Rail Transit Provider (e.g., IRCTC / RailYatri / Open Rail Data)**:
   - Ingest live train status and class-specific fares.
3. **Cab Aggregator Live Quotes (e.g., Uber / Ola / Rapido Rider API)**:
   - Retrieve dynamic surge pricing and vehicle arrival ETAs for First/Last Mile legs.
