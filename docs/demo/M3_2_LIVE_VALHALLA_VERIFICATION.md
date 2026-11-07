# KogniSync M3.2 — Live Valhalla Deployment & Regional Routing Validation

**Milestone**: M3.2 — Live Valhalla Deployment & Regional Routing Validation  
**Date**: November 7, 2026  
**Environment**: Windows 11 Pro / WSL2 Ubuntu / Docker Desktop 29.9.2  
**Target Routing Scope**: Southern India Demonstration Corridors (Chennai, Bengaluru, Mangaluru, Udupi)  
**Valhalla Status**: **LIVE & OPERATIONAL** (`http://localhost:8002`)  

---

## 1. Executive Summary & Verification Matrix

This document provides empirical evidence verifying the deployment of the self-hosted **Valhalla OpenStreetMap (OSM) routing engine** and its end-to-end integration into KogniSync.

In accordance with milestone rules, this document strictly separates and establishes the differences between:
1. **Adapter Implemented & Unit-Tested** (`ValhallaTransportAdapter` unit tests).
2. **Valhalla Container Running** (`kognisync-valhalla` container healthy).
3. **OSM Tiles Successfully Imported** (1,427 routing tiles across levels 0, 1, 2 generated and loaded).
4. **Real Valhalla HTTP Routing Request Successful** (Live 200 OK responses with real road network distances, durations, and spatial polylines).
5. **KogniSync End-to-End Integration Verified** (Live journey orchestration, proportional carbon scaling, and granular provenance).

### Evidence Classification Summary

| Component / Capability | Status | Evidence Classification | Details |
| :--- | :---: | :---: | :--- |
| **Valhalla Container Readiness** | **PASS** | `VERIFIED LIVE` | Container `kognisync-valhalla` running, port 8002 healthy, `/status` returns HTTP 200 with version `3.5.1`. |
| **OSM Southern Zone Dataset** | **PASS** | `VERIFIED LIVE` | Geofabrik `southern-zone-latest.osm.pbf` (559,359,643 bytes) MD5 verified: `841dccd7f4e931cc6f1e36091beca002`. |
| **Hierarchical Tile Build** | **PASS** | `VERIFIED LIVE` | 1,427 tiles across levels 0, 1, 2 tarred to `/custom_files/valhalla_tiles.tar` (1.2 GB). |
| **Direct Driving Routes** | **PASS** | `VERIFIED LIVE` | Real HTTP 200 OK routing for Chennai $\leftrightarrow$ Bengaluru, Bengaluru $\leftrightarrow$ Mangaluru, Mangaluru $\leftrightarrow$ Udupi. |
| **Direct Walking Route** | **PASS** | `VERIFIED LIVE` | Real HTTP 200 OK pedestrian routing in Mangaluru (4.04 km, 47.6 min). |
| **Direct Two-Wheeler Route** | **PASS** | `VERIFIED LIVE` | Real HTTP 200 OK motorcycle costing for Bengaluru hub feeder (2.02 km, 3.5 min). |
| **KogniSync Providers API** | **PASS** | `VERIFIED LIVE` | `GET /api/v1/journeys/providers` surfaces Valhalla with `liveVerificationStatus: PASS` and `isAvailable: true`. |
| **KogniSync Live Journey Search** | **PASS** | `VERIFIED LIVE` | Search generates multi-modal journeys with `provider_live` road metrics from Valhalla. |
| **Pareto Determinism** | **PASS** | `VERIFIED LIVE` | Repeated identical requests produce 100% identical journey IDs, prices, and durations. |
| **Hard Constraints (Budget/Deadline)** | **PASS** | `VERIFIED LIVE` | Hard ₹2,000 budget cap and 18:00 arrival deadline strictly enforced. |
| **Failure & Fallback Gracefulness** | **PASS** | `VERIFIED BY AUTOMATED TEST` | Unavailable ports, timeouts, ocean coordinates, and disabled modes degrade cleanly to calibrated deterministic corridors. |
| **Real-time Live Traffic Congestion** | **ESTIMATED** | `REPORTED` | Static OSM speed limits and roadway classifications; real-time jam telemetry is not provided by static extracts. |
| **Public Transit Bus Schedules** | **ESTIMATED** | `REPORTED` | Bus-as-auto computes physical road corridor distance/duration; it does NOT query live bus timetables or GTFS routes. |
| **Carrier Seats & Payment Locks** | **SIMULATED** | `REPORTED` | Seat availability remains demo fleet simulation; booking holds remain sandbox Redis holds without live card charges. |

---

## 2. Phase 1 — Environment Preflight & Resource Audit

Conducted prior to data acquisition and deployment:

```powershell
docker info
Get-PSDrive -PSProvider FileSystem
Test-NetConnection -ComputerName 127.0.0.1 -Port 8002
```

### Preflight Measurements

| Dimension | Measured Value | Minimum Required | Safety Evaluation |
| :--- | :--- | :--- | :--- |
| **Docker Desktop Version** | 4.98.0 | $\ge 4.25$ | **PASS** |
| **Docker Server Version** | 29.9.2 (containder b7a2526) | $\ge 24.0$ | **PASS** |
| **Docker Compose Version** | v5.6.1 | $\ge 2.20$ | **PASS** |
| **Docker WSL2 RAM Allocation** | **3.489 GiB** (`3,746,779,136` bytes) | $\ge 3.0\text{ GiB}$ | **PASS** |
| **WSL2 Swap Allocation** | **1.000 GiB** (Total VM: 4.59 GiB) | $\ge 1.0\text{ GiB}$ | **PASS** (Safety buffer against OOM) |
| **Host Disk Space (C:)** | 19.77 GB free | $\ge 10\text{ GB}$ | **PASS** |
| **Host Disk Space (E: Workspace)** | **95.45 GB free** | $\ge 15\text{ GB}$ | **PASS** (Staging and persistent volume host) |
| **Existing Containers** | `kognisync-postgres` (65.4 MiB RAM), `kognisync-redis` (4.6 MiB RAM) | Running | **PASS** (Existing databases untouched) |
| **Port 8002 Availability** | Free (`TcpTestSucceeded: False`) | Free | **PASS** |

---

## 3. Phase 2 — Regional OpenStreetMap Extract Selection & Verification

To satisfy the demonstration corridor requirements (Chennai, Bengaluru, Mangaluru, Udupi) within the developer environment constraints:

* **Regional Scope Investigation**:
  - Investigated Geofabrik India sub-regional splits: Northern (214 MB), Western (211 MB), Eastern (236 MB), Central (335 MB), and Southern Zone (533 MB).
  - Southern Zone is the **sole** sub-region covering both Karnataka (Bengaluru, Mangaluru, Udupi) and Tamil Nadu (Chennai).
* **Authoritative Source**: Geofabrik Download Server (`download.geofabrik.de`).
* **Source URL**: `https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf`  
  (Canonical archive redirect: `https://download.geofabrik.de/asia/india/southern-zone-261105.osm.pbf`)
* **Timestamp**: `Fri, 06 Nov 2026 17:54:53 GMT` (OSM data up to `2026-11-05T21:23:02Z`).
* **Exact File Size**: **`559,359,643` bytes** (~533.4 MB).
* **Integrity Checksums**:
  - Published Geofabrik MD5: `841dccd7f4e931cc6f1e36091beca002`
  - Downloaded File MD5: `841DCCD7F4E931CC6F1E36091BECA002` (**100% MATCH**)
  - Computed SHA-256: `A7C13C383A1A44F1A7F19CE3522C225834550CBC55D5CFBFECABA51355FC1B70`
* **Licensing & Attribution**:
  - Open Database License (ODbL) 1.0 by OpenStreetMap contributors.
  - Required attribution: *"Map data © OpenStreetMap contributors"*.

---

## 4. Phase 3 — Container Deployment & Hierarchical Tile Import

### 4.1 Pinned Docker Image
To eliminate risks of non-deterministic behavior from unpinned tags:
- **Image**: `ghcr.io/gis-ops/docker-valhalla/valhalla:latest`
- **Pinned Digest**: `sha256:060da5b92e6024a67f65135c236d918b021d63e73d1808a0d55b7e7cbd17240c`
- **Valhalla Core Version**: `3.5.1`

### 4.2 Resource Configuration (`docker-compose.yml`)
- `profiles: ["valhalla"]` (decoupled from standard `start.bat`)
- `build_elevation=False` (prevents downloading gigabytes of raster DEM tiles)
- `build_admins=False` (eliminates heavy administrative polygon extraction)
- `build_time_zones=False` (eliminates timezone boundary extraction)
- `server_threads=2` (limits concurrency to prevent memory thrashing)
- `use_tiles_ignore_pbf=True` (ensures fast restarts without rebuilding existing tiles)
- Dedicated Volume: `valhalla_data` (`kognisync_valhalla_data`)

### 4.3 Tile Generation & Resource Footprint

```
Initial Graph Stage (build):
  - Way parsing: 559 MB PBF read
  - Nodes: 6,120,184
  - Directed Edges: 15,545,402
  - EdgeInfo Count: 7,823,716
  - Raw Level 2 Tiles: 1,037 tiles

Hierarchical Graph Enhancement Stage (enhance):
  - Shortcuts on Level 1: 296,918 shortcuts superseding 1,993,782 edges
  - Shortcuts on Level 0: 52,976 shortcuts superseding 769,898 edges
  - Turn Restrictions added across Levels 0, 1, 2
  - Final Total Tiles: 1,427 tiles across levels 0, 1, 2

Tarring & Packing:
  - Output Archive: /custom_files/valhalla_tiles.tar (1.2 GB)
```

* **Storage Consumption in Volume**:
  - `southern-zone-latest.osm.pbf`: 534 MB
  - `valhalla_tiles.tar`: 1.2 GB
  - Total Volume Storage: **1.7 GB**
* **Runtime Resource Consumption (`docker stats`)**:
  - Active Memory: **~503 MiB** (~14.1% of Docker RAM limit)
  - Idle CPU: **0.28%**

---

## 5. Phase 4 — Direct Live Routing Verification

Direct HTTP requests executed against `http://localhost:8002/route` using canonical regional coordinates:

| Route & Mode | Origin Coordinates | Destination Coordinates | Costing Profile | Distance (km) | Duration (min) | Spatial Polyline | Response Time | HTTP Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Chennai $\rightarrow$ Bengaluru** | `13.0827, 80.2755` | `12.9781, 77.5694` | `auto` | **328.52 km** | **239.7 min** (3h 59m) | Available | 2385 ms | **200 OK** |
| **Bengaluru $\rightarrow$ Mangaluru** | `12.9781, 77.5694` | `12.8631, 74.8427` | `auto` | **352.27 km** | **268.9 min** (4h 28m) | Available | 739 ms | **200 OK** |
| **Mangaluru $\rightarrow$ Udupi** | `12.8631, 74.8427` | `13.3409, 74.7421` | `auto` | **59.31 km** | **50.9 min** | Available | 271 ms | **200 OK** |
| **Udupi $\rightarrow$ Mangaluru** | `13.3409, 74.7421` | `12.8631, 74.8427` | `auto` | **58.88 km** | **48.2 min** | Available | 47 ms | **200 OK** |
| **Mangaluru Central $\rightarrow$ KSRTC Bus Stand** | `12.8631, 74.8427` | `12.8872, 74.8492` | `pedestrian` | **4.04 km** | **47.6 min** | Available | 14 ms | **200 OK** |
| **Bengaluru Station $\rightarrow$ Majestic Concourse** | `12.9781, 77.5694` | `12.9774, 77.5713` | `motorcycle` | **2.02 km** | **3.5 min** | Available | 215 ms | **200 OK** |

All returned routes represent physical OpenStreetMap road network calculations with positive, plausible metrics and valid shape geometries.

---

## 6. Phase 5 — KogniSync End-to-End Journey Integration

Executed through the running FastAPI application with `.env` configured:
```env
VALHALLA_ENABLED=True
VALHALLA_BASE_URL=http://localhost:8002
VALHALLA_TIMEOUT_SECONDS=4.0
```

### 6.1 Provider Health Endpoint
Querying `GET /api/v1/journeys/providers`:
```json
{
  "providerId": "valhalla",
  "name": "Valhalla OSM Routing Engine",
  "supportedModes": ["auto", "bus", "cab", "rapido", "walk"],
  "isAvailable": true,
  "isLiveAuthenticated": true,
  "timeoutSeconds": 4.0,
  "liveVerificationStatus": "PASS"
}
```

### 6.2 Live Journey Search Provenance Verification
Querying `POST /api/v1/journeys/search` for Chennai $\rightarrow$ Bengaluru:

| Journey Recommendation | Segment 0 (First Mile) | Segment 1 (Intercity Corridor) | Segment 2 (Last Mile) | Overall Journey Provenance | `isFullyConfirmed` |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Fastest (Air + Cab)** | `cab`: 13.3 km, 16 min (`provider_live`) | `flight`: 350 km, 73 min (`deterministic_estimate`) | `cab`: 29.8 km, 29 min (`provider_live`) | `mixed` | **`False`** |
| **Best Value (Vande Bharat + Rapido)** | `rapido`: 7.0 km, 9 min (`provider_live`) | `train`: 350 km, 262 min (`deterministic_estimate`) | `rapido`: 9.7 km, 12 min (`provider_live`) | `mixed` | **`False`** |
| **Cheapest (City Bus + Rail)** | `bus`: 7.0 km, 9 min (`provider_live`) | `train`: 350 km, 323 min (`deterministic_estimate`) | `bus`: 9.7 km, 12 min (`provider_live`) | `mixed` | **`False`** |
| **Comfortable (Chauffeur + 1st AC)** | `cab`: 7.0 km, 9 min (`provider_live`) | `train`: 350 km, 269 min (`deterministic_estimate`) | `cab`: 9.7 km, 12 min (`provider_live`) | `mixed` | **`False`** |
| **Greenest (100% Electric Rail Corridor)** | `metro`: 11.0 km, 25 min (`deterministic_estimate`) | `train`: 350 km, 256 min (`deterministic_estimate`) | `metro`: 9.0 km, 20 min (`deterministic_estimate`) | `deterministic_estimate` | **`False`** |

### 6.3 Granular Attribute-Level Provenance Invariant
For road segments resolved via Valhalla:
- `duration`: `source_type="provider_live"`, `is_estimate=False`, `provider_name="Valhalla OSM Routing Engine"`
- `distance`: `source_type="provider_live"`, `is_estimate=False`, `provider_name="Valhalla OSM Routing Engine"`
- `fare`: `source_type="deterministic_estimate"`, `is_estimate=True` (Corridor tariff model)
- `availability`: `source_type="simulated"`, `is_estimate=True` (Demo fleet capacity)
- `carbon`: `source_type="deterministic_estimate"`, `is_estimate=True` (Proportionally scaled by road distance)
- **Trust Guarantee**: `is_fully_confirmed` strictly remains **`False`**.

### 6.4 Optimization Determinism & Constraint Preservation
- **Pareto Determinism**: Verified across repeated identical queries; returned journey IDs, scores, prices, and durations match 100%.
- **Budget Constraint**: When `budget_max=2000.0` was passed, all returned options strictly adhered to $\le \text{₹}2,000$.
- **Deadline Constraint**: When `preferred_arrival_before="18:00"` was passed, all returned options arrived before 18:00.

---

## 7. Phase 6 — Failure and Recovery Testing

| Test Scenario | Trigger Condition | System Behavior | Fallback Status | Result |
| :--- | :--- | :--- | :--- | :---: |
| **Valhalla Unavailable (503)** | Upstream server error / mock 503 | Search succeeds with calibrated corridor models | `unavailable_fallback_deterministic` | **PASS** |
| **Valhalla Disabled** | `VALHALLA_ENABLED=False` | Valhalla bypassed gracefully | `unconfigured_fallback_deterministic` | **PASS** |
| **Invalid Coordinates** | Lat/Lng in open ocean (`0.0, 0.0`) | Valhalla reports no feasible road route (error 170/171) | `empty_fallback_deterministic` | **PASS** |
| **Unsupported Mode** | `flight`, `train`, `metro` | Rejects with `ProviderErrorCode.UNSUPPORTED_MODE` | N/A (Handled by scheduled corridor synthesizer) | **PASS** |
| **Request Timeout** | Response takes $>4.0\text{s}$ (or SLA bound) | Circuit breaks request and logs timeout | `timeout_fallback_deterministic` | **PASS** |
| **Container Restart** | `docker restart kognisync-valhalla` | Tiles reload from tar in <3s; API resumes live queries | `active_live` | **PASS** |

---

## 8. Authoritative Disclosure: Explicit Limitations

To maintain uncompromising trust and transparency:
1. **Static Speed Limits vs. Live Traffic**: Valhalla computes travel times using OpenStreetMap roadway tags (`maxspeed`, road classifications, junction penalties). It does **not** consume live floating-car GPS probe feeds or real-time road jam data.
2. **Bus-as-Auto Semantics**: In KogniSync, the `bus` mode queries Valhalla with `auto` costing to calculate physical road network distance and vehicular corridor travel times. It does **not** query or model scheduled public bus routes, fixed bus line timetables, or live bus GPS locations (which require GTFS transit engines).
3. **Synthetic Timetables & Seats**: Indian Railways schedules and airline flights are synthesized backward from arrival deadlines; seat inventory is synthetic demo capacity (`is_real_inventory: False`).
4. **Sandbox Booking Simulation**: Booking holds in Redis and booking records in PostgreSQL are demonstration sandboxes with no live monetary transactions.

---

## 9. Organizer Database Integrity Confirmation

* Canonical database path: `BookingInventory/data/APS-05.db`
* SHA-256 Checksum:
  `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A`
* `BookingInventory/` status: **Untouched and 100% verified intact**.

