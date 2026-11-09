# Real-Time Journey Disruption Intelligence & Recovery Foundation (Milestone M3.7 & M3.7.1)

## 1. Product Description & Scope

KogniSync provides a **real-time disruption intelligence and multimodal journey recovery foundation**. It bridges live corridor monitoring with multi-modal journey synchronization. Rather than treating static road geometry as live traffic or fabricating real-time congestion, the platform evaluates the cascading impact of verified or simulated incidents along travel corridors and generates Pareto-ranked recovery alternatives.

> **Operational Status**: Live disruption ingestion is ready to connect and pending until an authorized commercial traffic provider is configured and verified. In the interim, the deterministic simulation engine provides repeatable, explicitly badged demonstration and verification scenarios.

The system adheres strictly to the **Zero Fabrication & Inventory Immutability Invariant**:
- Real provider integrations report verified status; missing credentials fail closed with honest `BLOCKED — credentials unavailable` disclosures.
- Valhalla route geometry is never misattributed as a live traffic congestion measurement.
- Deterministic simulation feeds are prominently tagged:
  $$\text{\texttt{SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA}}$$
- Recovery recommendations enforce explicit `manual_rebooking_required: true`; existing bookings and organizer inventory (`BookingInventory/data/APS-05.db`) are never mutated or silently canceled.

---

## 2. Provider Abstraction & Credibility Boundary

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

### 2.1 Provider Operational Dimensions Matrix

To avoid ambiguity between implemented code and operational live data, KogniSync distinguishes across five distinct operational dimensions:

| Dimension | `TomTomOrbisTrafficProvider` (`live_traffic_feed`) | `GTFSRealtimeProvider` (`gtfs_realtime_feed`) | `SimulatedDisruptionProvider` (`simulation_engine`) |
| :--- | :--- | :--- | :--- |
| **1. Connector Implementation** | **Genuinely implemented** (Orbis v2 client, bbox splitter, GeoJSON parser, bounded timeouts) | **Genuinely implemented** (GTFS-RT consumer, trip updates, service alerts, timestamp checks) | **Fully implemented** (Deterministic scenario generator) |
| **2. Credential Configuration** | **Unconfigured** by default (`TOMTOM_API_KEY` absent) | **Unconfigured** by default (`GTFS_REALTIME_FEED_URL` absent) | **None required** (self-contained engine) |
| **3. Connectivity Status** | `unconfigured` (fails closed to prevent spoofing) | `unconfigured` | `available` |
| **4. Live Response Verification** | Contract test verified via mocked Orbis v2 fixtures | Contract test verified via mocked feed fixtures | Unit and integration test verified |
| **5. Production Operational Status** | **BLOCKED** — commercial API credentials required | **BLOCKED** — authorized regional transit feed unavailable | **ACTIVE** in sandbox / demo with mandatory simulation notices |

### 2.2 Reliability & Security Guarantees
1. **Server-Side Credentials**: API keys are accessed only on the backend through secure configuration settings; never exposed in client payloads.
2. **Bounded HTTP Timeouts**: All external calls enforce strict timeouts (3.0 seconds max) and fail closed without crashing request handlers.
3. **No Masquerading**: Failed external requests, HTTP 429 rate limits, and unconfigured credentials return empty incident lists and explicit capability disclosures. Synthetic data is never tagged `provider_live`.

---

## 3. Route-to-Disruption Matching Engine

The matching engine (`RouteDisruptionMatcher`) evaluates incidents against journey legs using pure mathematical calculations without heavy GIS dependencies:

### 3.1 Spatial Tolerances & Authoritative Source of Truth
- **Road Corridor Tolerance (Authoritative Source of Truth)**: Configured as **`road_tolerance_km = 2.0`** (or incident `radius_meters / 1000.0`, whichever is greater) in `RouteDisruptionMatcher`.
  - *Tolerance Boundary Verification*: The boundary is strictly verified by unit tests: an incident at offset $\approx 1.77\text{ km}$ ($0.016^\circ$ latitude offset) matches cleanly because $1.77 \le 2.0\text{ km}$, while an incident at $\approx 2.43\text{ km}$ ($0.022^\circ$ latitude offset) is rejected because $2.43 > 2.0\text{ km}$. Earlier reports mentioning "1.8 km" referenced the test fixture coordinate offset, while the operational source of truth in code and tests is **2.0 km**.
- **Hub Proximity Tolerance**: Default **6.0 km** around origin/destination station coordinates for non-road segments lacking polyline geometry.

### 3.2 Matching Dimensions
1. **Transport Mode Compatibility**: Incidents are mode-filtered (`cab`, `bus`, `auto`, `rapido`, `train`, `metro`, `flight`). Road accidents do not match train or flight legs.
2. **Temporal Validity**:
   - Resolved events (`status: "resolved"`) are immediately excluded.
   - Expired events (`valid_until < now` or `valid_until < segment.departure_time`) are excluded.
   - Future scheduled events whose start time (`valid_from`) is after segment arrival are excluded.
3. **Exact Polyline Geometry Matching**:
   - Decodes segment `encoded_polyline` (precision 6 for Valhalla, 5 for Google).
   - Computes minimum perpendicular distance between incident point $P$ and route segment $AB$:
     $$\text{dist} = \text{point\_to\_segment\_distance\_km}(P, A, B)$$
   - Marks match as `exact_geometry` if $\text{dist} \le \text{road\_tolerance\_km}$.
4. **Hub Endpoint Proximity Fallback**:
   - Checks Haversine distance to origin/destination coordinates within 6.0 km (`hub_approximate`).

---

## 4. Event Freshness & Lifecycle Behavior

| Event Lifecycle State | Determination Rule | Display Behavior |
| :--- | :--- | :--- |
| **Current Observation** | Provider observation with `observed_at` $\le 60$ minutes ago and valid credentials | Displayed as active live incident (`provider_live`) |
| **Stale Observation** | Live provider observation older than 60 minutes without fresh verification | Flagged with data freshness warning notice |
| **Simulated Event** | Generated by `SimulatedDisruptionProvider` | Prominently displays `SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA` |
| **Expired Event** | `valid_until` has elapsed in wall-clock time | Excluded from active journey impact assessments |
| **Resolved Event** | `status == "resolved"` | Immediately purged from route matching |
| **Unknown Status** | Missing timestamps or unparseable metadata | Safely defaulted to `unknown` with fallback handling |

> **Operational Guard**: KogniSync does not perform unthrottled continuous background polling. Disruption telemetry is evaluated upon request or explicit user refresh (`POST /assess`, UI refresh CTA).

---

## 5. Pure Impact Assessment & Connection Risk

The impact assessor (`JourneyImpactAssessor`) evaluates cascading consequences:

1. **Segment Delay Slip**:
   $$\text{estimatedArrivalTime} = \text{originalArrivalTime} + \Delta t_{\text{delay}}$$
2. **Transfer Buffer Erosion**:
   $$\text{availableBufferMinutes} = \frac{\text{nextDepartureMs} - \text{estimatedArrivalMs}}{60000}$$
   $$\text{bufferReductionMinutes} = \max(0, \text{requiredBufferMinutes} - \text{availableBufferMinutes})$$
3. **Connection Risk Classification**:
   - `safe`: $\text{availableBufferMinutes} \ge \text{requiredBufferMinutes}$ ($\ge 15$ min).
   - `at_risk`: $5 \le \text{availableBufferMinutes} < \text{requiredBufferMinutes}$ (tight connection).
   - `critical`: $0 \le \text{availableBufferMinutes} < 5$ (high likelihood of missed connection).
   - `missed_estimated`: $\text{availableBufferMinutes} < 0$ or scheduled departure time has already elapsed in wall-clock time.
4. **Semantic Integrity of `missed_estimated`**:
   - `missed_estimated` indicates that predicted delay pushes arrival beyond scheduled departure. It **does not** imply a confirmed real-world carrier cancellation.
5. **Completed Progress Immutability**:
   - Segments already marked completed by the passenger (`progress.completedSegmentIds`) remain immutable and can never be retroactively marked as disrupted or missed.

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
          [manual_rebooking_required: true]
```

### 6.1 Candidate Feasibility & Attribute Provenance Matrix

| Candidate Attribute | Alternative Transport Mode (Rail) | Same-Mode Highway Detour (Road) | Earlier Schedule Advance |
| :--- | :--- | :--- | :--- |
| **Route Geometry** | `deterministic_estimate` (schematic corridor) | `deterministic_estimate` (offset highway corridor) | `deterministic_estimate` (identical corridor) |
| **Transport Mode** | `deterministic_estimate` (mode shift to rail) | `deterministic_estimate` (same road vehicle) | `deterministic_estimate` (same modes) |
| **Departure Time** | `deterministic_estimate` (scheduled station time) | `deterministic_estimate` (original departure) | `deterministic_estimate` (advanced by $\Delta t + 15$m) |
| **Arrival Time** | `deterministic_estimate` ($\text{dep} + \text{duration}$) | `deterministic_estimate` ($\text{dep} + \text{duration}$) | `deterministic_estimate` ($\text{dep} + \text{duration}$) |
| **Duration** | `deterministic_estimate` (rail speed model) | `deterministic_estimate` ($+45$m detour model) | `deterministic_estimate` (identical duration) |
| **Fare** | `deterministic_estimate` (rail rate model) | `deterministic_estimate` ($+₹450$ detour mileage) | `deterministic_estimate` (identical fare) |
| **Carbon Estimate** | `deterministic_estimate` ($-65\%$ electrified rail) | `deterministic_estimate` ($+5.2$ kg detour CO₂) | `deterministic_estimate` (identical carbon) |
| **Timetable / Schedule** | `unknown` (requires IRCTC check) | `deterministic_estimate` (on-demand cab) | `deterministic_estimate` (user-initiated) |
| **Seat Inventory** | `unknown` (`is_availability_verified: False`) | `unknown` (on-demand booking) | `unknown` (existing booking or unheld) |

### 6.2 Earlier Departure Invariant
- **Traveler Underway Guard**: Earlier departure is **only** recommended when the first segment has not yet started. If scheduled departure has already elapsed or the passenger is underway, the engine suppresses earlier departure recommendations.

### 6.3 Alternative Transport Inventory Status & Provenance Distinctions

To ensure audit accuracy and avoid conflating database records with live reality, the architecture establishes strict semantic distinctions for alternative transport inventory:

1. **Inventory Record Exists**: Only flight and hotel inventory tables exist in the canonical organizer database (`APS-05.db`). Railway lines and bus services do **NOT** exist in `APS-05.db`.
2. **Service or Trip is Scheduled**: Train timetables (e.g. Vande Bharat Express) and bus timings are deterministic schedule models derived from transit timetable references.
3. **Seats are Available (Local Ledger)**: `total_units - booked_units - held_units` in local SQLite/PostgreSQL tables reflects local platform capacity only.
4. **Seats are Held / Booked**: Represents local platform reservation holds and confirmed booking records.
5. **External Provider Inventory is Verified**: **Currently UNVERIFIED / NOT CONNECTED**. KogniSync does not maintain a live bidirectional GDS, airline API, or Indian Railways (IRCTC/CRIS) seat inventory reservation feed. A stored local inventory row is **never** treated as proof of real-world carrier availability.

### 6.4 What Recovery Recommendations Cannot Guarantee
1. **No Guaranteed Seat Inventory**: Recovery alternatives represent mathematically feasible routing corridors. They do not hold or lock unconfirmed carrier inventory.
2. **No Automatic Carrier Mutation**: In accordance with consumer travel protections, existing bookings and payment transactions are never automatically cancelled, modified, or re-charged.
3. **Manual Rebooking Mandatory**: Every recommendation requires explicit user review and confirmation (`manual_rebooking_required: true`).

---

## 7. Demonstration Scenarios

### Scenario 1: NH-75 Shiradi Ghat Landslide (Chennai → Bengaluru → Mangaluru → Udupi)
- **Incident**: Mudslide blocks NH-75 carriageways between Sakleshpur and Gundya (+180 min road delay).
- **Impact**: Road cab/bus leg delayed by 3 hours, completely eliminating transfer buffer at Mangaluru Central.
- **Recovery Strategy 1 (Primary)**: Mode shift to electrified rail (`alternative_transport_mode` via Karwar Express / Vande Bharat). Eliminates road closure delay, reduces fare by ~30%, and cuts carbon emissions by ~65%. Explicitly disclosed as an estimated alternative requiring IRCTC schedule confirmation.
- **Recovery Strategy 2**: Highway detour via NH-73 Charmadi Ghat (`reroute_same_mode`), adding 45 minutes and ₹450 fuel/toll. Explicitly disclosed as a deterministic detour estimate (`is_live_geometry: false`).

### Scenario 2: Bengaluru Silk Board Gridlock
- **Incident**: Waterlogging and flyover gridlock on Outer Ring Road (+45 min delay).
- **Impact**: Threatens departure of connecting KSR Bengaluru train.
- **Recovery Strategy**: Advance initial departure by 45 minutes (`earlier_departure`), absorbing the gridlock and preserving the scheduled rail connection with zero additional fare or carbon cost. Disabled if journey departure has elapsed.

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

- **Backend Disruption Suite**: 23 passed (`test_disruption_intelligence.py`).
- **Full Backend Suite**: 360 passed, 0 failures, 0 regressions.
- **Frontend Suites**: 11/11 passed (`runTests.mjs`, including 12 disruption tests).
- **TypeScript & Linting**: `npx tsc -b` (0 errors), `npx oxlint` (0 errors), `npx pyright` (0 errors).
- **Production Build**: Built in 1.72s.
- **Canonical Inventory**: `BookingInventory/data/APS-05.db` SHA-256 confirmed unchanged:
  `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A`.
