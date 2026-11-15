# KogniSync M4.0 — Provider Empirical Discovery & Verification Report

**Milestone:** M4.0 — Authorized Live Transit Feed Activation & Real-Time Multimodal Operations  
**Date:** 2026-11-11  
**Branch:** `feature/m4-0-live-transit-activation`  
**Verification Verdict:**  
- **TomTom Orbis Traffic API v2 (Road):** **LIVE VERIFIED (`available`, `provider_live`)**  
- **Public Transit GTFS-RT / IUDX Live Feeds:** **BLOCKED PENDING AGENCY CREDENTIALS** (Full connector, auth, decoding, validation, correlation, and SSRF pipelines implemented and verified; live agency activation awaits consumer registration tokens `BMTC_IUDX_AUTH_TOKEN` / `DELHI_OTD_API_KEY`).

---

## 1. Environment Secret Audit (Presence Only — Zero Secrets Logged)

Local `.env` configuration state audited without printing any secret values:

| Environment Variable | Purpose | Present | Provider Status |
| :--- | :--- | :---: | :--- |
| `TOMTOM_API_KEY` | Road incidents (Orbis v2) | Yes | Operational / Verified Live |
| `GEMINI_API_KEY` | Intent extraction / explanations | Yes | Operational |
| `BMTC_IUDX_AUTH_TOKEN` | IUDX Resource Server JWT (`token` header) | No | Blocked (`pending_credentials`) |
| `IUDX_AUTH_TOKEN` | Generic IUDX consumer JWT fallback | No | Blocked (`pending_credentials`) |
| `DELHI_OTD_API_KEY` | Delhi OTD GTFS-RT query parameter (`?key=...`) | No | Blocked (`pending_credentials`) |
| `GTFS_REALTIME_FEED_URL` | Primary custom GTFS-RT URL override | No | Unconfigured |
| `GTFS_REALTIME_API_KEY` | Primary custom GTFS-RT bearer token | No | Unconfigured |

---

## 2. Empirical Indian Transit Feed Discovery Results

Public catalogues and agency endpoints were queried directly (read-only) to determine legitimate feed availability, wire format, and access control requirements:

| Agency / Ecosystem | Discovered Resource / Endpoint | Protocol & Payload Format | Authentication Requirement | Empirical Probe Observation | Operational Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BMTC (Bengaluru)** | IUDX cOS Resource ID `8a9c53c2-7291-454e-b173-2d9bfe893eb1` (`https://rs.cos.iudx.org.in/ngsi-ld/v1/entities?id=...`) | HTTP JSON (**NGSI-LD**; `tripInfo`, `positionInfo`, `vehicleInfo`, GeoJSON `location`, `observationDateTime`, 10s interval) | `accessPolicy: "SECURE"`, APD `acl-apd.iudx.org.in`, HTTP header `token: <JWT>` | Catalog metadata confirmed HTTP 200; unauthenticated RS probe returned **`401 urn:dx:rs:invalidAuthorizationToken`** | Registered preset `bmtc_iudx_vehicle_positions` (`disabled` / `pending_credentials` until `BMTC_IUDX_AUTH_TOKEN` provided) |
| **Delhi OTD (DIMTS / DTC)** | `https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb` | Binary **GTFS-Realtime v2.0 `.pb`** (`VehiclePositions` only; static GTFS for DMRC/DTC) | Query parameter `?key=<API_KEY>` (`api_key_query`) | Unauthenticated HTTP GET returned **`401 Unauthorized`** | Registered preset `delhi_otd_vehicle_positions` (`disabled` / `pending_credentials` until `DELHI_OTD_API_KEY` provided) |
| **BMRCL / BenSCL (Bengaluru Metro)** | Catalog dataset `7da0557c-...` on IUDX (`benscl`); legacy M3.9 URI `https://opendata.benscl.com/gtfs-rt/alerts` | Static `FILE` / `GSLAYER` schedules & station layers only | IUDX `accessPolicy: "SECURE"` for static catalogue items | Legacy `opendata.benscl.com/gtfs-rt/alerts` returned **HTTP 404**; zero real-time GTFS-RT endpoints published | Legacy broken URL removed from default presets; documented no live BMRCL GTFS-RT feed exists |
| **Other IUDX ITMS Cities (Surat, Chandigarh, Indore, ELCITA)** | Datasets `ee001002-...` (Surat), `0b859393-...` (Chandigarh), `6aba5cf2-...` (Indore), `9643cf83-...` (EC Shuttle) | NGSI-LD JSON (`trip_delay`, `last_stop_id`, GeoJSON `location`) | All `accessPolicy: "SECURE"` requiring IUDX consumer token | Public catalog search for `accessPolicy: "OPEN"` real-time transit returned **`totalHits: 0`** | Supported cleanly by `iudx_adapter.py` via `GTFS_FEEDS_CONFIG_JSON` once tokens supplied |
| **KSRTC (Karnataka State Road Transport)** | Searched `cos.iudx.org.in` and public catalogs | N/A | N/A | IUDX search returned **`totalHits: 0`**; no public GTFS-RT endpoint exists | Not activated; road corridor delays handled via TomTom Orbis v2 (`live_traffic_feed`) |
| **MobilityDatabase Global Catalog** | `MobilityData/mobility-database-catalogs` (`catalogs/sources/gtfs/realtime/` vs `schedule/`) | Registry metadata | N/A | **`0`** Indian feeds in `gtfs/realtime/`; **`20`** Indian feeds in static `gtfs/schedule/` | Confirmed zero unauthenticated open Indian GTFS-RT feeds exist |

---

## 3. Onboarding Guide (Activating Live Transit Once Credentials Are Obtained)

KogniSync enforces **Zero Fabrication**: no unconfigured feed is ever presented as `available` or `provider_live`. Operators can activate live transit ingestion solely by setting valid environment variables in `.env` (never committed to Git):

### Option A: Activating Built-In Indian Agency Presets
1. **BMTC Bengaluru Live Bus Telemetry (IUDX cOS)**
   - Register at https://cos.iudx.org.in/ and obtain a consumer consent/access JWT for dataset `8a9c53c2-7291-454e-b173-2d9bfe893eb1`.
   - Set in `.env`:
     ```env
     BMTC_IUDX_AUTH_TOKEN=<your_iudx_consumer_jwt>
     ```
   - `GTFSFeedRegistry` automatically enables `bmtc_iudx_vehicle_positions` (`api_key_header` using header `token`, format `iudx_ngsi_ld`).

2. **Delhi Open Transit Data (GTFS-RT Binary `.pb`)**
   - Register at https://otd.delhi.gov.in/ and request an API key.
   - Set in `.env`:
     ```env
     DELHI_OTD_API_KEY=<your_delhi_otd_key>
     ```
   - `GTFSFeedRegistry` automatically enables `delhi_otd_vehicle_positions` (`api_key_query` using param `key`, format `gtfs_rt`).

### Option B: Custom Multi-Feed JSON (`GTFS_FEEDS_CONFIG_JSON`)
```env
GTFS_FEEDS_CONFIG_JSON=[{"feed_id":"surat_iudx","operator_name":"Surat Sitilink","display_name":"Surat Live Transit (IUDX)","geographic_coverage":"Surat","feed_url":"https://rs.cos.iudx.org.in/ngsi-ld/v1/entities?id=ee001002-0000-0000-0000-000000000000","auth_type":"api_key_header","auth_header_name":"token","auth_token_env_var":"IUDX_AUTH_TOKEN","provider_format":"iudx_ngsi_ld","entity_types":["vehicle_positions","trip_updates"],"enabled":true}]
```

### Verification Checklist After Onboarding
1. Restart backend service and call `POST /api/v1/disruptions/providers/feeds/poll?force=true`.
2. Inspect `GET /api/v1/disruptions/providers/feeds`:
   - `connectivityStatus` must transition from `configured` to `available` **only after** HTTP 200 + decoded valid payload + fresh header timestamp.
   - HTTP 401/403 must transition to `blocked` (`authorizationStatus: "unauthorized" | "forbidden"`).
   - Confirm zero secret substrings appear anywhere in API payloads (`feedUrlSanitized` redacts query keys).

---

## 4. Live Network Smoke Test Evidence

Verified via `RUN_LIVE_PROVIDER_TESTS=1 pytest backend/tests/test_m4_0_live_transit_operations.py::test_live_provider_endpoints_smoke`:
- **TomTom Orbis v2 (`LiveTrafficIncidentProvider`):** Live query over Bengaluru bbox `(77.55, 12.90, 77.65, 13.00)` returned HTTP 200, transitioned `connectivity_status -> "available"`, updated `last_successful_request`, and stamped `provenance="provider_live"`.
- **BMTC IUDX Resource Server:** Direct probe without credentials confirmed upstream enforces `401 Unauthorized` (`fail-closed`).
- **Delhi OTD VehiclePositions.pb:** Direct probe without key confirmed upstream enforces `401 Unauthorized` (`fail-closed`).

