# KogniSync Provider Intelligence & Verified Live Data Architecture

**Milestone:** M3.8 — Verified Live Data Integrations & Provider Intelligence  
**Document Version:** 1.0.0  
**Status:** **AUTHORITATIVE ARCHITECTURAL SPECIFICATION**  
**Repository:** `E:\KogniSync\KogniSync`

---

## 1. Executive Summary & Mission

Milestone M3.8 elevates KogniSync from an intelligent disruption modeling system (M3.7) to a production-grade external provider integration layer. The core objective is increasing the **authenticity, freshness, reliability, and operational visibility** of transport telemetry while strictly maintaining the **Zero Fabrication & Inventory Immutability Invariant**.

Where commercial credentials or authorized agency feeds are not present in the runtime environment, the system refuses to fabricate live telemetry; it reports provider status honestly as `BLOCKED` with detailed diagnostic notices and gracefully falls back to deterministic simulation clearly labeled with `SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA`.

### Primary Integration Channels

1. **TomTom Orbis Traffic API v2**: Modern incident details ingestion (`GET https://api.tomtom.com/maps/orbis/traffic/incidents/details?apiVersion=2`) with `TomTom-Api-Key` header authentication, GeoJSON geometry extraction, bounded bbox queries, and delay seconds normalization without qualitative guesswork.
2. **GTFS Realtime Transit Foundation**: Spec-compliant consumer for Trip Updates, Service Alerts, and Vehicle Positions (`https://gtfs.org/documentation/realtime/reference/`) featuring feed header age validation and transparent capability discovery.
3. **Data Freshness & Reliability Engine**: Deterministic multi-tier freshness evaluation (`fresh`, `aging`, `stale`, `expired`, `unknown`) enforcing distinct observation, fetch, and verification timestamps.
4. **Provider Capability & Health Registry**: Dynamic health discovery (`GET /api/v1/disruptions/providers`) exposing operational state, latency, failure counts, and rate limits.

---

## 2. Provider Capability & Operational Verification Matrix

To prevent misleading claims, KogniSync rigorously distinguishes between the six required operational dimensions:

| Dimension | Required Evidence | Verification Method |
| :--- | :--- | :--- |
| **Connector** | Source implementation present | Adapter class implemented and verified via unit tests |
| **Credentials** | Safe presence check | Non-empty API key / token verified without leaking values |
| **Connectivity** | Successful network response | HTTP handshake succeeded within configured timeout window |
| **Provider response** | Validated actual response | Valid schema-conforming payload parsed without error |
| **Live verification** | Actual data validated against provider | Real-world incidents extracted from active network query |
| **Coverage** | Confirmed geographic & mode coverage | Bounded spatial query mapped to active route geometry |

### Provider Operational Evaluation Matrix

| Capability | Connector Implementation | Credential Configuration | Connectivity Status | Live Verified | Current Operational Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TomTom Road Incidents** | Fully implemented (`TomTomOrbisTrafficProvider`) | Absent in local environment (`TOMTOM_API_KEY` unset) | Not configured | Contract Test Verified (mocked Orbis v2 responses) | **BLOCKED** — commercial API credentials required. Fail-closed without live fabrication. |
| **GTFS Trip Updates** | Fully implemented (`GTFSRealtimeProvider`) | Absent in local environment (`GTFS_REALTIME_FEED_URL` unset) | Not configured | Contract Test Verified (mocked GTFS-RT feeds) | **BLOCKED** — authorized regional transit feed unavailable. |
| **GTFS Service Alerts** | Fully implemented (`GTFSRealtimeProvider`) | Absent in local environment (`GTFS_REALTIME_FEED_URL` unset) | Not configured | Contract Test Verified (mocked GTFS-RT feeds) | **BLOCKED** — authorized regional transit feed unavailable. |
| **GTFS Vehicle Positions** | Fully implemented (`GTFSRealtimeProvider`) | Absent in local environment (`GTFS_REALTIME_FEED_URL` unset) | Not configured | Contract Test Verified | **BLOCKED** — authorized regional transit feed unavailable. |
| **Valhalla Road Routing** | Fully implemented (`ValhallaRoutingService`) | Self-hosted local Docker engine (`http://localhost:8002`) | Available | Live Runtime Verified (M3.5.1 / M3.6) | **AVAILABLE** — road routing engine only (does not provide traffic incident feeds). |
| **Deterministic Disruption Simulator** | Fully implemented (`SimulatedDisruptionProvider`) | Not required (internal deterministic scenario generator) | Available | Verified across all test suites | **AVAILABLE** — active in sandbox/demo mode with explicit simulation badges. |

> [!IMPORTANT]
> **No Masquerading Rule**: A connector existing in the repository does **NOT** indicate live operational data. In absence of valid credentials, the system reports `BLOCKED`, never fabricates incidents, and never sets `is_available: True`.

---

## 3. TomTom Orbis Traffic API v2 Contract

KogniSync integrates with TomTom's next-generation **Orbis Traffic API v2** rather than legacy Traffic API v5 endpoints.

### 3.1 Endpoint & Authentication Contract
- **Endpoint**: `GET https://api.tomtom.com/maps/orbis/traffic/incidents/details`
- **Query Parameter**: `apiVersion=2`
- **Authentication**: `TomTom-Api-Key` HTTP Request Header.
  - *Security Invariant*: API keys are **never** passed in query parameters, logged in plain text, or emitted in error messages. Redacted strings (`<configured:len=N>`) are used in diagnostics.
- **Attributes Header**: Documented attribute selection header:
  ```http
  Attributes: type,geometry,properties{id,iconCategory,magnitudeOfDelay,events{description,code},startTime,endTime,from,to,length,delay,roadNumbers,timeValidity,probabilityOfOccurrence,numberOfReports,lastReportTime}
  ```

### 3.2 Bounding Box & Area Constraints
- **Format**: `bbox=minLon,minLat,maxLon,maxLat` in WGS84 coordinates.
- **Area Limit**: TomTom Orbis enforces a maximum bounding box area of **10,000 km²**.
- **Automated Subbox Splitting**: For long-distance intercity corridors (e.g. Bengaluru to Chennai or Delhi to Mumbai), `split_bounding_box` recursively bisects the bounding box along its longer geographic dimension into subboxes $\le 10,000 \text{ km}^2$.
- **Request Budget**: Clamped to `TOMTOM_MAX_REQUESTS_PER_ASSESSMENT` (default: 5) to prevent API request storms.
- **Deduplication**: Incidents returned across overlapping subboxes are deduplicated by `incident.id`.

### 3.3 Normalization & Zero-Inference Delay
Provider fields are normalized into KogniSync's `DisruptionEvent` domain:
- **Event Type**: Extracted from TomTom `iconCategory`:
  - 1, 10 $\rightarrow$ `accident`
  - 2, 3, 4, 5, 11 $\rightarrow$ `weather` (fog, heavy rain, gale)
  - 6 $\rightarrow$ `traffic_congestion`
  - 7, 14 $\rightarrow$ `road_closure`
  - 8 $\rightarrow$ `road_construction`
- **Severity**: Extracted from `magnitudeOfDelay` (1 $\rightarrow$ `low`, 2 $\rightarrow$ `moderate`, 3 $\rightarrow$ `high`, 4 $\rightarrow$ `critical`).
- **Delay Seconds Invariant**: Delay is recorded **only** when TomTom supplies an explicit `delay` integer in seconds. Qualitative severity never fabricates quantitative delay minutes.
- **Geometry**: Supports GeoJSON `Point` and `LineString` (extracting polyline midpoint and length-based radius).

---

## 4. GTFS Realtime Transit Foundation

### 4.1 Specification Compliance
KogniSync implements standard entity consumers conforming to the [GTFS Realtime specification](https://gtfs.org/documentation/realtime/reference/):
1. **Trip Updates**: Normalizes `schedule_relationship: CANCELED` to `service_cancellation` (critical) and positive `delay` seconds into `transport_delay`. Delays $< 5$ minutes are suppressed to prevent alert noise.
2. **Service Alerts**: Normalizes `header_text`, `description_text`, `cause`, and `effect` (`NO_SERVICE` $\rightarrow$ critical cancellation; `SIGNIFICANT_DELAYS` $\rightarrow$ high delay).
3. **Vehicle Positions**: Ingests vehicle coordinates and observation timestamps for future active telemetry tracking.

### 4.2 Regional Public Transit Realities & Authorization
- Transport agencies in primary demonstration corridors (BMTC, BMRCL, Indian Railways/NTES) do not publish open, unauthenticated, commercial-use GTFS-RT protobuf endpoints.
- In accordance with the engineering gate, KogniSync implements the adapter and contract tests, but reports live verification as **`BLOCKED — authorized GTFS Realtime feed unavailable`**.

### 4.3 Stale Feed Protection
- Validates the `header.timestamp` on every response.
- If the feed header age exceeds `MAX_GTFS_FEED_AGE_SECONDS` (600s / 10 min), the feed is rejected as stale to prevent displaying outdated service advisories.

---

## 5. Data Freshness & Reliability Engine

Data freshness is evaluated deterministically in `backend/app/services/disruption/freshness.py`.

### 5.1 Freshness Classification Matrix

| Data Type | Fresh Threshold | Aging Threshold | Stale Threshold | Action on Stale |
| :--- | :--- | :--- | :--- | :--- |
| **Road Incidents** (TomTom) | $\le 1800\text{ s}$ (30 min) | $\le 3600\text{ s}$ (60 min) | $> 3600\text{ s}$ (60 min) | Excluded from active hazard polyline & alerts |
| **Service Alerts** (Transit) | $\le 3600\text{ s}$ (60 min) | $\le 7200\text{ s}$ (120 min) | $> 7200\text{ s}$ (120 min) | Marked with `STALE OBSERVATION` warning |
| **Trip Updates** (GTFS-RT) | $\le 300\text{ s}$ (5 min) | $\le 600\text{ s}$ (10 min) | $> 600\text{ s}$ (10 min) | Rejected from delay calculations |
| **Vehicle Positions** (GPS) | $\le 60\text{ s}$ (1 min) | $\le 180\text{ s}$ (3 min) | $> 180\text{ s}$ (3 min) | Rejected from live positioning |

### 5.2 Timestamp Semantics
To prevent cache masquerading, the architecture tracks three distinct timestamps:
- `observed_at`: The instant external sensors or agencies recorded the physical event.
- `fetched_at`: The instant KogniSync queried the external provider.
- `last_verified_at`: The instant KogniSync confirmed the incident remained active.

### 5.3 Clock Skew & Expiration
- **Clock Drift**: Future timestamps within $+120\text{ s}$ are clamped to age zero (tolerating standard NTP clock drift). Timestamps $> 120\text{ s}$ in the future are classified as `unknown` anomaly.
- **Expiration**: Events with `valid_until < now` or `status: resolved` are classified as `expired` and strictly pruned from journey impact evaluation.

---

## 6. Provider Reliability & Resilience

External network calls adhere to defensive patterns to isolate failures:
1. **Bounded Timeouts**: Connect timeout clamped to 1.5s; total read timeout clamped to 3.0s.
2. **Exponential Backoff**: Up to 2 retries on transient HTTP 5xx errors ($0.5\text{ s} \times 2^{\text{attempt}}$).
3. **No Retries on Auth Failures**: HTTP 401 and 403 immediately transition the provider to `blocked` without retrying.
4. **Rate Limit Handling**: HTTP 429 parses the `Retry-After` header and transitions status to `rate_limited`.
5. **Failure Isolation**: An exception or network failure in one provider (e.g. TomTom) is caught and logged; it never prevents queries to other registered providers (e.g. Simulator).

---

## 7. Attribute-Level Provenance Tracking

Live provider telemetry does not grant live status to downstream calculated fields:

| Journey / Disruption Attribute | Live Provider Input | Propagated Attribute Provenance | Invariant Rule |
| :--- | :--- | :--- | :--- |
| **Incident Point & Geometry** | Validated TomTom GeoJSON | `provider_live` | Preserves exact provider coordinates |
| **Incident Title & Cause** | Validated TomTom / GTFS text | `provider_live` | Attributed to provider source |
| **Delay Propagation Across Journey** | External delay seconds | `deterministic_estimate` | **Never** promoted to `provider_live` |
| **Highway Detour Duration** | Recomputed road route | `deterministic_estimate` | Requires verified Valhalla session |
| **Rail / Flight Recovery Alternatives** | Timetable scheduling | `deterministic_estimate` | **Unverified external seat inventory** |
| **Ticket Reservation Status** | Unverified GDS / IRCTC | `unknown` | `manual_rebooking_required = true` |

---

## 8. Frontend Provider Intelligence Experience

The user interface (`frontend/src/components/disruption/ProviderIntelligencePanel.tsx`) provides transparent operational visibility:
- **Provider Status Pills**: Displays real-time operational badges (`AVAILABLE`, `BLOCKED`, `RATE LIMITED`, `DEGRADED`, `UNCONFIGURED`).
- **Interactive Refresh**: Manual refresh button triggers bounded re-validation without unbounded polling loops.
- **Expanded Diagnostic Drawer**: Discloses observation timestamps, latency in milliseconds, supported modes, geographic coverage, and diagnostic failure reasons.
- **Truth Invariant Banners**: Displays contextual notices matching the operational state:
  - `LIVE PROVIDER DATA — TomTom Orbis v2`
  - `SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA`
  - `ESTIMATED IMPACT — BASED ON PROVIDER INCIDENT`
  - `STALE PROVIDER OBSERVATION — VERIFY BEFORE TRAVEL`
  - `BLOCKED — credentials unavailable (commercial TOMTOM_API_KEY required)`

---

## 9. Milestone M3.8.3 Remediation & Protocol Conformance

### 9.1 TomTom Connectivity State Machine Hardening
Prior to Milestone M3.8.3, `TomTomOrbisTrafficProvider.get_connectivity_status()` returned `"available"` immediately whenever configured, even before any live network handshake had succeeded.

In Milestone M3.8.3, the provider lifecycle enforces a verified four-phase state machine:
1. **Unconfigured**: `TOMTOM_TRAFFIC_ENABLED=False` or `TOMTOM_API_KEY` absent $\rightarrow$ status `"unconfigured"`.
2. **Configured, Unverified**: `TOMTOM_API_KEY` present but `_last_successful_request is None` $\rightarrow$ status `"unknown"`, notice `"Configured — awaiting initial live connection verification."`, provenance `"unknown"`. `is_available()` remains `True` so the provider is permitted to execute its initial handshake.
3. **Operational**: Valid HTTP 200 response parsed $\rightarrow$ status `"available"`, notice `"Connected to TomTom Orbis Traffic API v2..."`, provenance `"provider_live"`.
4. **Degraded / Rate Limited**: 3 consecutive network failures trigger `"degraded"`; HTTP 429 triggers `"rate_limited"`. A subsequent valid HTTP 200 resets `consecutive_failure_count` to zero and restores `"available"` status.

### 9.2 Official GTFS-Realtime Protocol Buffers Tag Conformance
KogniSync's zero-dependency pure-Python Protocol Buffers decoder and encoder (`gtfs_protobuf.py`) conforms strictly to official Google Transit `gtfs-realtime.proto` tag definitions:

| Message | Field Name | Official Tag | Wire Type | Type |
| :--- | :--- | :--- | :--- | :--- |
| **TripDescriptor** | `trip_id` | **1** | WIRE_LENGTH_DELIMITED | string |
| | `start_time` | **2** | WIRE_LENGTH_DELIMITED | string |
| | `start_date` | **3** | WIRE_LENGTH_DELIMITED | string |
| | `schedule_relationship` | **4** | WIRE_VARINT | enum |
| | `route_id` | **5** | WIRE_LENGTH_DELIMITED | string |
| | `direction_id` | **6** | WIRE_VARINT | uint32 |
| **StopTimeUpdate** | `stop_sequence` | **1** | WIRE_VARINT | uint32 |
| | `arrival` | **2** | WIRE_LENGTH_DELIMITED | StopTimeEvent |
| | `departure` | **3** | WIRE_LENGTH_DELIMITED | StopTimeEvent |
| | `stop_id` | **4** | WIRE_LENGTH_DELIMITED | string |
| | `schedule_relationship` | **5** | WIRE_VARINT | enum |
| **TripUpdate** | `trip` | **1** | WIRE_LENGTH_DELIMITED | TripDescriptor |
| | `stop_time_update` | **2** | WIRE_LENGTH_DELIMITED | repeated StopTimeUpdate |
| | `vehicle` | **3** | WIRE_LENGTH_DELIMITED | VehicleDescriptor |
| | `timestamp` | **4** | WIRE_VARINT | uint64 |
| | `delay` | **5** | WIRE_VARINT | int32 |
| **VehiclePosition** | `trip` | **1** | WIRE_LENGTH_DELIMITED | TripDescriptor |
| | `position` | **2** | WIRE_LENGTH_DELIMITED | Position |
| | `current_stop_sequence`| **3** | WIRE_VARINT | uint32 |
| | `current_status` | **4** | WIRE_VARINT | enum |
| | `timestamp` | **5** | WIRE_VARINT | uint64 |
| | `congestion_level` | **6** | WIRE_VARINT | enum |
| | `stop_id` | **7** | WIRE_LENGTH_DELIMITED | string |
| | `vehicle` | **8** | WIRE_LENGTH_DELIMITED | VehicleDescriptor |
| | `occupancy_status` | **9** | WIRE_VARINT | enum |
| **VehicleDescriptor** | `id` | **1** | WIRE_LENGTH_DELIMITED | string |
| | `label` | **2** | WIRE_LENGTH_DELIMITED | string |
| | `license_plate` | **3** | WIRE_LENGTH_DELIMITED | string |

### 9.3 Corrupt Feed False Success Prevention
In `GTFSRealtimeProvider.fetch_disruptions()`:
- Payloads are decoded and validated **before** calling `_record_success()`.
- HTTP 200 responses containing truncated varints, truncated length-delimited fields, unsupported wire types, or invalid JSON invoke `_record_failure(200, ...)` without updating `_last_successful_request` or resetting the failure counter.
- Valid empty feeds (valid header, 0 entities) record genuine success and transition the provider to `"available"`.
