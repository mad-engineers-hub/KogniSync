# Real-Time Journey Disruption Intelligence & Recovery (Milestone M3.7)

## 1. Executive Summary

Milestone M3.7 introduces **Disruption Intelligence & Multimodal Journey Recovery** to KogniSync. Building on the foundation established across M3.1–M3.6 (real Valhalla road routing, multimodal corridor composition, deterministic Pareto optimization, attribute-level provenance, Leaflet interactive mapping, GPS location, and navigation guidance), M3.7 equips KogniSync to monitor active transit corridors, detect incidents, assess their cascading impact on multimodal connections, and generate feasible recovery alternatives.

The system adheres strictly to the **Zero Fabrication & Inventory Immutability Invariant**:
- Real provider integrations report verified status; missing credentials fail closed with honest `BLOCKED — credentials unavailable` disclosures.
- Valhalla route geometry is never misattributed as a live traffic congestion measurement.
- Deterministic simulation feeds are prominently tagged `SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA`.
- Recovery recommendations enforce explicit `manualRebookingRequired: true`; existing bookings and organizer inventory (`BookingInventory/data/APS-05.db`) are never mutated or silently canceled.

---

## 2. Disruption Intelligence Domain Model

### 2.1 DisruptionEvent Taxonomy

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `id` | `str` | Unique incident identifier (e.g. `sim-disrupt-nh75-shiradi-ghat`). |
| `source` | `str` | Provider adapter name (`simulation_engine`, `live_traffic_feed`). |
| `sourceId` | `str \| None` | External upstream incident identifier. |
| `eventType` | `DisruptionEventType` | Normalized classification: `road_closure`, `traffic_congestion`, `accident`, `road_construction`, `weather`, `transport_delay`, `service_cancellation`, `station_disruption`, `airport_disruption`, `connection_risk`, `unknown`. |
| `severity` | `DisruptionSeverity` | `critical`, `high`, `moderate`, `low`, `unknown`. |
| `status` | `DisruptionStatus` | `active`, `resolved`, `scheduled`, `unknown`. |
| `title` | `str` | Human-readable title carrying simulation notice when applicable. |
| `description` | `str` | Detailed incident summary and impact description. |
| `affectedModes` | `list[TransportMode]` | Modes directly disrupted (`cab`, `bus`, `train`, `metro`, `flight`, `auto`, `rapido`, `walk`). |
| `point` | `CoordinatesSchema` | WGS84 coordinate of incident centroid (`lat`, `lng`). |
| `radiusMeters` | `float` | Spatial buffer around incident centroid (default: 1,000 m). |
| `validFrom` / `validUntil` | `str (ISO 8601)` | Temporal validity bounds. |
| `observedAt` / `lastVerifiedAt` | `str (ISO 8601)` | Data freshness timestamps. |
| `provenance` | `ProvenanceSourceType` | Credibility classification (`provider_live`, `deterministic_estimate`, `simulated`, `unknown`). |
| `confidence` | `float` | Upstream confidence score (0.0 to 1.0). |
| `estimatedDelayMinutes` | `int` | Delay introduced by disruption (minutes). |

---

## 3. Provider Abstraction & Credibility Boundary

The provider subsystem follows a modular adapter architecture managed by `DisruptionProviderRegistry`:

```
                 DisruptionProviderRegistry
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
SimulatedDisruptionProvider        LiveTrafficIncidentProvider
 (Deterministic Scenarios)          (TomTom / External Feed)
 [provenance: "simulated"]          [provenance: "provider_live"]
```

### Provider Availability & Credibility Guarantees:
1. **Live Traffic Provider**:
   - Validates server-side API keys (`TRAFFIC_INCIDENT_API_KEY`).
   - If credentials are not configured, discovery returns `isAvailable: false` with notice `BLOCKED — credentials unavailable (commercial API key required). Simulation active.`.
   - Never fabricates live congestion or treats static Valhalla routes as real-time speed measurements.
2. **Deterministic Simulation Provider**:
   - Generates repeatable, deterministic corridor scenarios for development, automated CI verification, and user demonstrations.
   - All generated titles and payloads prominently display:
     ```text
     SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA
     ```
   - Zero database mutation: purely stateless and reproducible.

---

## 4. Route-to-Disruption Spatial Matching

The matching engine (`RouteDisruptionMatcher`) evaluates incidents against journey legs using pure mathematical calculations without heavy GIS dependencies:

1. **Transport Mode Compatibility**: Discard incidents that do not affect the segment's mode (e.g. road congestion does not match a train or flight leg).
2. **Temporal Window Overlap**: Discard incidents marked `resolved` or whose `validUntil` expired prior to segment execution.
3. **Exact Polyline Geometry Matching**:
   - Decodes segment `encoded_polyline` (precision 6 for Valhalla, 5 for Google).
   - Computes minimum perpendicular distance between incident centroid and route line segments using equirectangular projection:
     $$\text{dist} = \text{point\_to\_segment\_distance\_km}(P, A, B)$$
   - If $\text{dist} \le \text{tolerance}$ (typically 1.0–2.0 km), marks match as `exact_geometry`.
4. **Hub Endpoint Proximity Fallback**:
   - For flight or rail segments without road polylines, checks Haversine distance to origin/destination station coordinates within a 6.0 km buffer (`hub_approximate`).
5. **Deduplication**: Eliminates duplicate event alerts per segment.

---

## 5. Pure Impact Assessment & Connection Risk

The impact assessor (`JourneyImpactAssessor`) evaluates cascading consequences:
1. **Segment Delay Slip**:
   $$\text{estimatedArrivalTime} = \text{originalArrivalTime} + \Delta t_{\text{delay}}$$
2. **Transfer Buffer Erosion**:
   $$\text{availableBufferMinutes} = \frac{\text{nextDepartureMs} - \text{estimatedArrivalMs}}{60000}$$
   $$\text{bufferReductionMinutes} = \max(0, \text{requiredBufferMinutes} - \text{availableBufferMinutes})$$
3. **Connection Risk Classification**:
   - `safe`: $\text{availableBufferMinutes} \ge \text{requiredBufferMinutes}$.
   - `at_risk`: $0 \le \text{availableBufferMinutes} < \text{requiredBufferMinutes}$.
   - `critical`: $\text{availableBufferMinutes} < 0$.
   - `missed_estimated`: Scheduled departure has elapsed or buffer shortfall exceeds connection threshold.
4. **Progress Immutability**:
   - Verified completed legs (`progress.completedSegmentIds`) can **never** be retroactively marked as missed or delayed. Completed status remains immutable.

---

## 6. Multimodal Recovery & Pareto Re-Optimization

When an active disruption is detected, `JourneyRecoveryEngine` automatically synthesizes candidate recoveries:

```
                      Disrupted Journey
                             │
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
Strategy A              Strategy B              Strategy C
Alternative Mode        Same-Mode Detour        Earlier Departure
(e.g. Road -> Rail)     (e.g. NH-73 Charmadi)   (Advance Schedule)
     │                       │                       │
     └───────────────────────┼───────────────────────┘
                             ▼
               Hard Constraints Filter (Budget & Deadline)
                             │
                             ▼
               Authoritative Pareto Optimizer
                             │
                             ▼
          Ranked Recovery Alternatives (Delta Metrics)
          [manualRebookingRequired: true]
```

### Safety & Integrity Constraints:
- **Zero Silent Mutation**: Confirmed bookings, holds, and payment records remain untouched.
- **Explicit Label**: Every recovery card states: `Manual rebooking required. Selecting this option will not automatically alter or charge bookings.`.
- **Hard Constraint Enforcement**: If all alternatives exceed user budget or arrival deadline, the engine emits `strategy: "no_feasible_alternative"` and explains why. Constraints are never silently relaxed.

---

## 7. Demonstration Scenarios

### Scenario 1: NH-75 Shiradi Ghat Landslide (Chennai → Bengaluru → Mangaluru → Udupi)
- **Incident**: Mudslide blocks NH-75 carriageways between Sakleshpur and Gundya (+180 min road delay).
- **Impact**: Road cab/bus leg delayed by 3 hours, completely eliminating transfer buffer at Mangaluru Central.
- **Recovery Strategy 1 (Primary)**: Mode shift to electrified rail (`alternative_transport_mode` via Karwar Express / Vande Bharat). Eliminates road closure delay, reduces fare by 30%, and cuts carbon emissions by 65%.
- **Recovery Strategy 2**: Highway detour via NH-73 Charmadi Ghat (`reroute_same_mode`), adding 45 minutes and ₹450 fuel/toll.

### Scenario 2: Bengaluru Silk Board Gridlock
- **Incident**: Waterlogging and flyover gridlock on Outer Ring Road (+45 min delay).
- **Impact**: Threatens departure of connecting KSR Bengaluru train.
- **Recovery Strategy**: Advance initial departure by 45 minutes (`earlier_departure`), absorbing the gridlock and preserving the scheduled rail connection with zero additional fare or carbon cost.

---

## 8. API Specification

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/disruptions/health` | Operational health and provider registration status. |
| `GET` | `/api/v1/disruptions/providers` | Capability discovery and live credential status. |
| `GET` | `/api/v1/disruptions` | Query active disruptions (filters: `corridor`, `scenario`, `include_simulated`). |
| `POST` | `/api/v1/disruptions/assess` | Deterministic impact assessment for provided journey. |
| `POST` | `/api/v1/disruptions/recover` | Pareto-ranked multimodal recovery recommendations. |
| `POST` | `/api/v1/journeys/{id}/assess-disruptions` | Alias endpoint for journey disruption assessment. |
| `POST` | `/api/v1/journeys/{id}/recover` | Alias endpoint for journey recovery recommendations. |

---

## 9. Verification Summary

- **Backend Disruption Suite**: 16 passed in 10.89s (`test_disruption_intelligence.py`).
- **Full Backend Suite**: 353 passed in 331.56s (0 regressions).
- **Frontend Suites**: 11/11 passed (`runTests.mjs`, including 12 disruption tests).
- **TypeScript & Linting**: `npx tsc -b` (0 errors), `npx oxlint` (0 errors, 0 warnings), `npx pyright` (0 errors).
- **Production Build**: Built in 3.14s.
- **Canonical Inventory**: `BookingInventory/data/APS-05.db` SHA-256 confirmed unchanged:
  `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A`.
