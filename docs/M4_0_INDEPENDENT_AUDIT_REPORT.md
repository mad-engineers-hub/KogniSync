# KogniSync M4.0 — Independent Pre-Merge Security, Correctness & Provider Verification Audit Report

**Audit Target:** PR `#26` (`mad-engineers-hub/KogniSync`) — Milestone M4.0: Authorized Live Transit Feed Activation & Real-Time Multimodal Operations  
**Branch:** `feature/m4-0-live-transit-activation` → `main`  
**Audited Commit (Head SHA):** `b5d35286cb02a2195b5d67f8e9860b36357f2c7c`  
**Base Commit (Base SHA):** `68fb3800ef49c742c84f04a23f89c9b512749ddc`  
**Audit Date:** 2026-11-11  
**Audit Mode:** Strictly Read-Only (no application code, test, configuration, or database files modified)

---

## 1. Executive Summary & Audit Verdict

**OVERALL VERDICT: `FAIL` — Do Not Merge PR `#26` Until High/Medium Findings Are Remediated (Recommended Milestone: M4.0.1)**

Milestone M4.0 establishes a solid, non-deceptive multimodal transit ingestion architecture:
- Replaces the dead M3.9 template (`opendata.benscl.com/gtfs-rt/alerts`, confirmed `HTTP 404`) with documented Indian transit presets (`bmtc_iudx_vehicle_positions` via IUDX cOS NGSI-LD and `delhi_otd_vehicle_positions` via binary GTFS-RT v2.0 `.pb`) that remain fail-closed (`disabled` / `pending_credentials`) without consumer tokens.
- Implements an IUDX NGSI-LD-to-GTFS-RT adapter ([`iudx_adapter.py`](../backend/app/services/disruption/providers/iudx_adapter.py)) whose field mapping successfully normalizes the real live BMTC catalog schema retrieved from `https://cos.iudx.org.in/iudx/cat/v1/item?id=8a9c53c2-7291-454e-b173-2d9bfe893eb1`.
- Preserves SSRF DNS-rebinding IP-pinning (`PinnedIPNetworkBackend` / `PinnedIPAsyncTransport`), cross-origin redirect header/query stripping, `manual_rebooking_required=True` recovery safety invariants, canonical database integrity (`BookingInventory/data/APS-05.db` SHA-256 unchanged), zero committed secrets, and passing CI (`445 passed, 12 skipped`) and frontend test suites (`11/11`).

However, independent inspection and empirical reproduction identified **2 High-severity security defects**, **3 Medium-severity correctness/coverage gaps**, **2 Low-severity findings**, and **2 Informational items**:
- **`H-1` (High):** Raw query-parameter credential leakage (`?key=<SECRET>`) into stdout `INFO` logs via `httpx` when `auth_type="api_key_query"` (affecting Delhi OTD once `DELHI_OTD_API_KEY` is configured). Empirically reproduced with `app.core.logging.setup_logging()`.
- **`H-2` (High):** `POST /api/v1/disruptions/providers/feeds/poll` (with `force=true` cooldown bypass) has zero authentication and zero rate-limiting, enabling unauthenticated outbound request amplification and upstream quota exhaustion/banning once live transit keys are provisioned.
- **`M-1` (Medium):** Feed registry lifecycle gaps — missing outer per-feed concurrency lock in `fetch_feed_events`, `is_deleted` tombstones lingering in `active_map` for 300s (`GTFS_ABSENCE_GRACE_PERIOD_SECONDS`), invalid/expired replacement entities failing to purge stale `active_map` entries (and grace-loop re-emission past `valid_until`), and `freshness_status="fresh"` defaulted when feed timestamp is `None`.
- **`M-2` (Medium):** Binary protobuf `_decode_alert()` omits GTFS-RT tag `5` (`informed_entity`), dropping route/stop/trip selectors on binary `.pb` ServiceAlerts.
- **`M-3` (Medium):** Security/edge-case test gaps (tests currently assert unauthenticated `200` on `/providers/feeds/poll`; missing tests for `httpx` log non-leakage, invalid credential `401` through `poll_all_enabled_feeds()`, mixed public/private DNS through `fetch_feed()`, malformed IUDX `NaN` / coordinate rejections through `GTFSFeedRegistry`, and synthetic-only transit fixtures).

Because `PASS` requires zero unresolved Critical, High, or Medium findings, PR `#26` fails pre-merge readiness and must wait for targeted remediation.

---

## 2. PR Metadata, Git State & Diff Inventory

Verified directly against GitHub PR `#26` and local repository `E:\KogniSync\KogniSync`:

| Property | Verified Value | Match Expected |
| :--- | :--- | :--- |
| PR Number & State | `#26` — `OPEN` | Yes |
| Mergeability | `MERGEABLE` / `mergeStateStatus: CLEAN` | Yes |
| Base Branch & SHA | `main` — `68fb3800ef49c742c84f04a23f89c9b512749ddc` | Yes (`origin/main` identical) |
| Feature Branch & Head SHA | `feature/m4-0-live-transit-activation` — `b5d35286cb02a2195b5d67f8e9860b36357f2c7c` | Yes (`HEAD` identical, 1 commit by `Deekshith2205`) |
| Committed Diff (`origin/main..HEAD`) | `17 files changed, 2272 insertions(+), 302 deletions(-)` | Audited scope |

**Changed Files in Committed PR (`origin/main..HEAD`):**
- Config / Docs: `.env.example` (+10), `docs/M4_0_IMPLEMENTATION_REPORT.md` (+68), `docs/M4_0_PROVIDER_VERIFICATION_REPORT.md` (+84), `docs/architecture/DISRUPTION_INTELLIGENCE.md` (+14/-?)
- Backend Core & API: `backend/app/core/config.py` (+10/-?), `backend/app/api/routes/disruptions.py` (+61/-?)
- Backend Disruption Services & Providers: `backend/app/services/disruption/schemas.py` (+107), `backend/app/services/disruption/providers/gtfs_feed_client.py` (+65/-?), `backend/app/services/disruption/providers/gtfs_realtime.py` (+207/-?), `backend/app/services/disruption/providers/gtfs_registry.py` (+856/-?), `backend/app/services/disruption/providers/iudx_adapter.py` (+270)
- Backend Tests: `backend/tests/test_m4_0_live_transit_operations.py` (+610)
- Frontend: `frontend/src/api/disruptions.ts` (+51/-?), `frontend/src/components/disruption/DisruptionBanner.tsx` (+72/-?), `frontend/src/components/disruption/ProviderIntelligencePanel.tsx` (+42/-?), `frontend/src/tests/disruptionIntelligence.test.ts` (+23/-?), `frontend/src/types/disruption.ts` (+24)

**Secret Scan (`git diff origin/main..HEAD`, 2,272 added lines):** `0` hits across AWS keys, PEM private keys, Google `AIza` keys, GitHub tokens, JWT literals, `Bearer` headers, and hardcoded `api_key`/`auth_token`/`client_secret`/`password` assignments.

---

## 3. CI Run & Independent Local Test Evidence

### 3.1 GitHub Actions CI (`postgres_integration.yml`)
- **Run ID:** `42977141091` ([Job 130378736926](https://github.com/mad-engineers-hub/KogniSync/actions/runs/42977141091/job/130378736926))
- **Commit Audited:** `b5d35286cb02a2195b5d67f8e9860b36357f2c7c` (exact PR `#26` head)
- **Workflow / Job:** `PostgreSQL Integration & Booking Safety Gate` / `PostgreSQL 16 & Redis 7 Integration Tests`
- **Status / Duration:** `SUCCESS` in `1m36s`
- **CI Observed Execution:**
  - Alembic baseline `0001_canonical_baseline` verified 20/20 organizer tables against PostgreSQL 16 + Redis 7.
  - `pytest backend/tests/test_postgres_integration.py -v -rs`: **7 passed in 3.06s**.
  - `pytest backend/tests -v`: **445 passed, 12 skipped in 32.47s** (457 collected).
  - Note: `.github/workflows/` contains only `postgres_integration.yml`; frontend build, lint, type-check, and Node tests do **not** run in GitHub Actions CI.

### 3.2 Independent Local Execution (Re-Executed During Audit)
All local checks ran sequentially inside `E:\KogniSync\KogniSync`:

| Check | Exact Command / Scope | Observed Result |
| :--- | :--- | :--- |
| Backend Full Suite | `.venv\Scripts\python.exe -m pytest backend/tests -rs -v --tb=short` | **425 passed, 32 skipped**, 2 warnings in `391.35s` (457 collected) |
| Opt-In Live Provider Suite | `RUN_LIVE_PROVIDER_TESTS=1 pytest backend/tests/test_m4_0_live_transit_operations.py -v` | **8 passed in 6.24s** (TomTom live query + real BMTC/Delhi 401 checks) |
| Frontend TypeScript | `.\node_modules\.bin\tsc.cmd -b` (`GOMAXPROCS=1`, `RAYON_NUM_THREADS=1`) | **Exit 0** (0 errors) |
| Frontend Linter | `npm run lint` (`oxlint`, `GOMAXPROCS=1`, `RAYON_NUM_THREADS=1`) | **Exit 0** (0 errors, 56 warnings across 122 files, `244ms`) |
| Frontend Production Build | `.\node_modules\.bin\vite.cmd build` | **Exit 0** (2,091 modules built in `2.79s`) |
| Frontend Test Runner | `node scripts/runTests.mjs` | **Exit 0** (**11/11** compiled SSR Node test suites passed offline) |

*(Note: Full skipped-test reconciliation across CI and local runs is documented in Section 11.)*

---

## 4. IUDX NGSI-LD Adapter Correctness ([`iudx_adapter.py`](../backend/app/services/disruption/providers/iudx_adapter.py))

1. **Live BMTC Catalog Schema Verification:**
   Queried `https://cos.iudx.org.in/iudx/cat/v1/item?id=8a9c53c2-7291-454e-b173-2d9bfe893eb1` (`HTTP 200`, `live-bus-position-bmtc`). Its official `dataSample` exposes `tripInfo` (`trip_id`, `route_id: "1663"`, `schedule_relationship`), `positionInfo` (`latitude`, `longitude`, `bearing`), `vehicleInfo` (`vehicle_label: "KA57F4735"`), GeoJSON `location` (`[lng, lat]`), `"timestamp": "1750475254"`, and `"observationDateTime": "2025-07-21T17:07:34+05:30"`.
   - Passing both the raw dict and `{"type": "urn:dx:rs:Success", "results": [real_sample]}` directly through `normalize_iudx_payload()` produced accurate normalized GTFS-RT-shaped JSON (`source_format: "iudx_ngsi_ld"`, `route_id="1663"`, `trip_id="63209143"`, `latitude=12.850806`, `longitude=77.66863`, `bearing=142.52`, `timestamp=1753097854`).
2. **Verified Edge-Case Weaknesses:**
   - **Non-finite numeric crash (`L-1`):** `normalize_iudx_payload({"id": "v2", "delay": float("nan")})` and `parse_timestamp_to_epoch(float("nan"))` both raise `ValueError: cannot convert float NaN to integer`. Because Python's default `json.loads()` accepts `NaN`/`Infinity` tokens and `GTFSFeedRegistry._decode_feed_payload` treats decoder exceptions as feed-level failures, a single malformed `NaN` value fails the entire feed poll rather than dropping one record.
   - **Naive ISO timestamp timezone assumption (`L-1`):** `parse_timestamp_to_epoch("2025-07-21T11:37:34")` assumes UTC (`1753097854`), which would introduce a 5.5-hour offset if any domestic operator omits `+05:30` (BMTC's live sample does include `+05:30`).
   - **`vehicle_label` loss (`L-1`):** `vehicleInfo.vehicle_label` (registration plate `"KA57F4735"` in BMTC's `dataSample`) is omitted from normalized `vehicle.vehicle` (`{"id": "8a9c53c2-..."}`).
   - **Downstream coordinate reliance:** `iudx_adapter.py` emits `(0.0, 0.0)` and out-of-range coordinates into intermediate normalized JSON, relying on downstream checks in `gtfs_registry.py`/`gtfs_realtime.py` to reject invalid entities (`L-1` / `M-3` coverage gap).

---

## 5. Auth, Secret Hygiene & SSRF Transport Security

1. **HIGH (`H-1`): Raw Query-String Credential Exposure via `httpx` INFO Logs**
   - In [`gtfs_feed_client.py:440-465`](../backend/app/services/disruption/providers/gtfs_feed_client.py#L440-L465), when `hop_query_param` is configured (specifically Delhi OTD's `auth_type="api_key_query"`, parameter `"key"`), the raw API key is appended directly to `request_url` and passed to `httpx.AsyncClient(...).get(request_url, headers=hop_headers)`.
   - [`backend/app/core/logging.py:6-16`](../backend/app/core/logging.py#L6-L16) initializes root logging via `logging.basicConfig(level=log_level, ...)` at default `INFO` without raising `httpx` or `httpcore` logger levels to `WARNING` or stripping query secrets.
   - **Empirical Reproduction Output:** Running `setup_logging()` with `httpx.AsyncClient.get('https://otd.delhi.gov.in/...?key=MY_TOP_SECRET_API_KEY')` emits verbatim to stdout:
     `[INFO] httpx: HTTP Request: GET https://otd.delhi.gov.in/...?key=MY_TOP_SECRET_API_KEY "HTTP/1.1 200 OK"`
   - Contrast with [`tomtom_orbis.py:7,337-339`](../backend/app/services/disruption/providers/tomtom_orbis.py#L7), which sends `"TomTom-Api-Key"` exclusively in HTTP headers so `httpx` URL logs never contain secrets.
   - `sanitize_feed_url()` (`gtfs_feed_client.py:122`) redacts `("key", "token", "secret", "auth", "pwd", "password")` for `feed_url_sanitized` API responses and app logs (covering `"key"`), though additional query parameter aliases (`credential`, `signature`, `apiKey` only matches partially depending on exact matching) are outside that list and app-level sanitization never intercepts `httpx` internal request logging.
2. **Preserved SSRF & Redirect Protections (Positive Findings):**
   - `PinnedIPNetworkBackend` and `PinnedIPAsyncTransport` bind the socket to the validated public IPv4/IPv6 while retaining the original `sni_hostname` / `Host` header, mitigating DNS-rebinding TOCTOU.
   - Direct feed fetches in `GTFSRealtimeProvider` route through `SecureGTFSFeedClient`, eliminating pre-M4.0 direct `httpx` client bypass.
   - Cross-origin redirects strip auth headers (`authorization`, `x-api-key`, `token`, `x-auth-token`, `apikey`) and sensitive query params while re-validating SSRF IP rules per hop (`follow_redirects=False`).
   - API status responses sanitize query parameters and omit secret values and environment variable names (verified against `.env`: `BMTC_IUDX_AUTH_TOKEN=False`, `DELHI_OTD_API_KEY=False`).

---

## 6. Polling Endpoint Security Assessment ([`disruptions.py`](../backend/app/api/routes/disruptions.py))

**HIGH (`H-2`): Unauthenticated Outbound Polling Endpoint with Cooldown Bypass (`POST /api/v1/disruptions/providers/feeds/poll`)**
- Observed at [`backend/app/api/routes/disruptions.py:96-110`](../backend/app/api/routes/disruptions.py#L96-L110):
  ```python
  @router.post(
      "/providers/feeds/poll",
      response_model=GTFSFeedListResponse,
      summary="Trigger controlled polling cycle for enabled authorized transit feeds",
  )
  async def poll_registered_gtfs_feeds(
      force: bool = Query(False, description="Bypass per-feed polling cooldown interval when true"),
  ) -> GTFSFeedListResponse:
      await gtfs_feed_registry.poll_all_enabled_feeds(force=force)
      return _build_gtfs_feed_list_response()
  ```
- **Gaps:** Zero FastAPI authentication dependency (contrast [`booking.py:49,206`](../backend/app/api/routes/booking.py#L206), which enforces `dependencies=[Depends(verify_operational_access)]` validating `x-internal-key` against `settings.INTERNAL_API_KEY` on operational POST routes), zero rate-limiting, and public exposure of `force=true` to bypass `polling_interval_seconds`.
- **Frontend Coupling:** [`ProviderIntelligencePanel.tsx:55`](../frontend/src/components/disruption/ProviderIntelligencePanel.tsx#L55) invokes `pollGTFSFeeds(false)` during routine UI panel refresh (`client.ts` sends no `x-internal-key`).
- **Risk:** Once production consumer tokens (`BMTC_IUDX_AUTH_TOKEN`, `DELHI_OTD_API_KEY`) are enabled, any unauthenticated external caller can continuously send `POST /api/v1/disruptions/providers/feeds/poll?force=true`, exhausting upstream rate limits/quotas, triggering HTTP `429`/`403` provider bans, or tying up outbound async connection slots.

---

## 7. GTFS-Realtime Protobuf & Registry Lifecycle Correctness

### 7.1 Protobuf Wire Decoder ([`gtfs_protobuf.py`](../backend/app/services/disruption/providers/gtfs_protobuf.py))
- **MEDIUM (`M-2`): `_decode_alert()` Missing Field Tag `5` (`informed_entity`)**
  At [`gtfs_protobuf.py:312-329`](../backend/app/services/disruption/providers/gtfs_protobuf.py#L312-L329), `_decode_alert` parses tags `1` (`active_period`), `3` (`cause`), `4` (`effect`), `6` (`header_text`), `7` (`description_text`), `10` (`severity_level`), and `11` (`timestamp`), but omits tag `5` (`informed_entity` / `EntitySelector` carrying `route_id`, `stop_id`, `trip`). Binary `.pb` ServiceAlerts therefore lose route/stop/trip targeting metadata, preventing route-matched disruption alerts for binary alert feeds (only JSON ServiceAlerts preserve `informed_entity`).

### 7.2 Registry Lifecycle & Concurrency ([`gtfs_registry.py`](../backend/app/services/disruption/providers/gtfs_registry.py))
- **MEDIUM (`M-1`): Stale/Deleted Entity Retention, Unsynchronized Concurrent Polls & Null-Timestamp Freshness**
  1. `fetch_feed_events` performs network fetches and updates feed status, failure counters, `last_poll_at`, `active_map`, and availability transitions without an outer per-feed asyncio lock, creating interleaved state mutation races under concurrent poll requests.
  2. `if ent.get("is_deleted"): continue` (`gtfs_registry.py:621-622`) skips GTFS-RT cancellation/deletion tombstones rather than removing `ent_id` from `active_map`, causing explicitly deleted entities to linger up to `GTFS_ABSENCE_GRACE_PERIOD_SECONDS` (300s).
  3. Updated entities rejected by validation (e.g., expired `active_period` or invalid coordinates around lines `629-648, 663, 668`) return `None` without evicting pre-existing `active_map[ent_id]`; during subsequent polls, the absence grace loop can re-emit stale entries even when `valid_until` has already elapsed.
  4. Missing feed header timestamps set `status.freshness_status = "fresh"` (`gtfs_registry.py:494-495`) instead of `"unknown"`.

---

## 8. Five-Provider Truthfulness & Live Verification Matrix

Verified runtime `.env` presence booleans (`TOMTOM_API_KEY=True`, `GEMINI_API_KEY=True`; all transit feed env vars `BMTC_IUDX_AUTH_TOKEN`, `IUDX_AUTH_TOKEN`, `DELHI_OTD_API_KEY`, `GTFS_REALTIME_FEED_URL`, `GTFS_REALTIME_API_KEY`, `GTFS_FEEDS_CONFIG_JSON` are `False`) alongside live unauthenticated HTTPS & catalog checks:

| Provider / Agency | Mechanism & Endpoint Verified | Runtime Status | Live Probe / Catalog Evidence Observed | Truthfulness Check |
| :--- | :--- | :--- | :--- | :--- |
| **1. TomTom Orbis Traffic v2** (`live_traffic_feed`) | `https://api.tomtom.com/...` via `TomTom-Api-Key` header | **Configured / Live** (`TOMTOM_API_KEY=True`) | `RUN_LIVE_PROVIDER_TESTS=1` executed real TomTom incident query and passed cleanly | **Pass** (header auth; `unknown` before first verified response; no synthetic traffic) |
| **2. BMTC (Bengaluru Bus)** (`bmtc_iudx_vehicle_positions`) | IUDX cOS NGSI-LD `https://rs.cos.iudx.org.in/ngsi-ld/v1/entities?id=8a9c53c2-7291-454e-b173-2d9bfe893eb1` (`token` header) | **Disabled / `pending_credentials`** (`BMTC_IUDX_AUTH_TOKEN=False`) | Catalog `cos.iudx.org.in` item `HTTP 200` confirmed live 10s schema (`accessPolicy: SECURE`); unauthenticated RS probe returned `HTTP 401` (`urn:dx:rs:invalidAuthorizationToken`) | **Pass** (fail-closed; accurately reflects consumer token blocker) |
| **3. Delhi OTD (DIMTS/DTC)** (`delhi_otd_vehicle_positions`) | GTFS-RT v2.0 binary `.pb` `https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb` (`?key=` query) | **Disabled / `pending_credentials`** (`DELHI_OTD_API_KEY=False`) | Homepage `otd.delhi.gov.in` `HTTP 200`; unauthenticated `.pb` probe returned `HTTP 401 Authorization Required` (nginx) | **Pass** on status; **High `H-1` blocker** if key configured without fixing `httpx` INFO logging |
| **4. BMRCL / BenSCL (Bengaluru Metro)** | Audited against `cos.iudx.org.in` + legacy `opendata.benscl.com/gtfs-rt/alerts` | **Unconfigured / Unavailable** (legacy template removed) | Legacy `opendata.benscl.com/gtfs-rt/alerts` returned `HTTP 404`; IUDX `tags=[[BMRCL]]` (`e01fd385-...` / `9588656f-...`) exposes `resourceType: FILE` only — zero real-time GTFS-RT feeds published | **Pass** (honestly documents lack of public live GTFS-RT endpoint) |
| **5. KSRTC & Indian Railways** | Audited via IUDX catalog & public documentation | **Unconfigured / Unavailable** (zero fabricated adapters) | `cos.iudx.org.in` `tags=[[KSRTC]]` returned `totalHits: 0`; no open public official IRCTC/CRIS/KSRTC machine GTFS-RT stream exists without partner onboarding | **Pass** (deterministic/simulated estimates only, explicitly tagged) |

---

## 9. Journey Impact Assessment & Booking/Recovery Safety

Inspected [`matcher.py`](../backend/app/services/disruption/matcher.py), [`assessment.py`](../backend/app/services/disruption/assessment.py), and [`recovery.py`](../backend/app/services/disruption/recovery.py):
- **Provenance Isolation:** Confirmed `JourneyImpactAssessor` distinguishes `provider_live`, `deterministic_estimate`, `simulated`, and `unknown`, never upgrading simulated or estimated delays to `provider_live`.
- **Exact Transit Matching:** Confirmed `RouteDisruptionMatcher` retains M3.9.1 normalized/tokenized route & stop matching rather than arbitrary substring collisions.
- **Recovery & Booking Safety:** Confirmed `JourneyRecoveryEngine` and [`schemas.py`](../backend/app/services/disruption/schemas.py) enforce `manual_rebooking_required: bool = True` and `is_availability_verified=False` on all generated recovery recommendations, never mutating active bookings/holds or touching `APS-05.db`.
- **Caveat (`M-1` / `M-2`):** Downstream accuracy for live transit disruptions is impacted when binary `.pb` alerts lose `informed_entity` targeting (`M-2`) or deleted/expired disruptions linger in `active_map` (`M-1`).

---

## 10. Frontend Provenance & Diagnostics Audit

Inspected [`DisruptionBanner.tsx`](../frontend/src/components/disruption/DisruptionBanner.tsx), [`ProviderIntelligencePanel.tsx`](../frontend/src/components/disruption/ProviderIntelligencePanel.tsx), [`disruptions.ts`](../frontend/src/api/disruptions.ts), [`disruption.ts`](../frontend/src/types/disruption.ts), and [`client.ts`](../frontend/src/api/client.ts):
- **Dynamic Source Attribution:** `DisruptionBanner.tsx` replaces the prior hardcoded TomTom label with `deriveLiveProviderLabel`, distinguishing road (`TomTom Orbis v2`) vs transit (`Authorized GTFS-RT/IUDX`) vs combined multimodal sources cleanly and rendering observation timestamp, freshness status, and transfer risk badges.
- **Offline Fallback Honesty:** In `disruptions.ts:20-75`, offline fallback for `getGTFSFeeds()` returns `bmtc_iudx_vehicle_positions` and `delhi_otd_vehicle_positions` with `enabled: false`, `authorizationStatus: 'pending_credentials'`, `connectivityStatus: 'disabled'`, `freshnessStatus: 'unknown'`, and `totalOperational: 0` (zero fake live data).
- **UI Polling Coupling (`H-2` impact):** `ProviderIntelligencePanel.tsx:55` issues unauthenticated `POST /api/v1/disruptions/providers/feeds/poll?force=false` (`pollGTFSFeeds(false)`) when the user clicks refresh.
- **UI Copy Drift (`L-2`):** `ProviderIntelligencePanel.tsx:91-97, 357-360` renders `'unknown'`/`'disabled'` status badges as `UNCONFIGURED`, while its footer prose says the system reports `BLOCKED`.
- **Pre-Existing Map Popup Provenance (`I-1`, Out-of-PR Scope):** Pre-existing M3.7 [`frontend/src/components/map/JourneyMap.tsx:560,591`](../frontend/src/components/map/JourneyMap.tsx) (verified untouched in PR `#26`: `git diff origin/main..HEAD` empty) computes `const isSim = ev.provenance === 'simulated'` and displays `${isSim ? 'SIMULATED' : 'LIVE'}` on incident popups, which would label `deterministic_estimate` or `unknown` events as `LIVE` in the map view.

---

## 11. Test Coverage & Skipped-Test Disclosure

### 11.1 Complete Skipped-Test Reconciliation (No Silent Skips)
- **Total Collected:** `457` backend test items across CI and local runs.
- **CI Skipped (12 items — `postgres_integration.yml` passes all 31 PG/Redis items):**
  - `test_ai_endpoint.py::test_api_parse_travel_intent` (1): requires live `GEMINI_API_KEY` (absent in CI).
  - `test_ai_intent.py::test_intent_test_case_1..5` (5): require live `GEMINI_API_KEY` (absent in CI).
  - `test_journey_flow_cases.py::test_case_1..5` (5): require live `GEMINI_API_KEY` (absent in CI).
  - `test_m4_0_live_transit_operations.py::test_live_provider_endpoints_smoke[asyncio]` (1): opt-in (`RUN_LIVE_PROVIDER_TESTS=1` unset in CI).
- **Local Skipped (32 items — local `.env` has `GEMINI_API_KEY=True` so all 11 Gemini AI tests PASSED locally, while local Docker Postgres `:5434` and Redis `:6380` are stopped):**
  - `test_canonical_init.py` (7): `Live PostgreSQL service not available on port 5434.`
  - `test_db_initialization.py` (1): `PostgreSQL service unreachable on localhost:5434`
  - `test_health.py` (2): 1 PostgreSQL unreachable (`:5434`), 1 Redis unreachable (`:6380`)
  - `test_m4_0_live_transit_operations.py` L583 (1): `Opt-in live integration verification requires RUN_LIVE_PROVIDER_TESTS=1` (independently executed with `RUN_LIVE_PROVIDER_TESTS=1` → **8 passed in 6.24s**)
  - `test_models.py` (2): `PostgreSQL database unreachable at ...@localhost:5434/kognisync_db`
  - `test_postgres_integration.py` (7): `PostgreSQL integration target unreachable at ...@localhost:5434/kognisync_db`
  - `test_repositories.py` (12): `PostgreSQL database unreachable at ...@localhost:5434/kognisync_db`
- **Frontend Tests (`11/11` SSR Node suites):** Compiled and passed offline cleanly (`node scripts/runTests.mjs`); `disruptionIntelligence.test.ts` exercises offline fallbacks when the FastAPI backend is stopped (`status: 0` warnings logged as expected for fallback verification).

### 11.2 Security & Functional Coverage Gaps (`M-3`)
1. `test_m4_0_live_transit_operations.py` asserts unauthenticated `200 OK` on `POST /api/v1/disruptions/providers/feeds/poll` instead of enforcing auth.
2. Zero assertions verifying `httpx` / `httpcore` INFO logs do not emit query-parameter tokens (`?key=...`).
3. Zero end-to-end tests verifying HTTP `401` invalid-credential handling for `api_key_query` and `api_key_header` through `poll_all_enabled_feeds()` / `/poll`.
4. Zero end-to-end `GTFSFeedRegistry` tests covering malformed IUDX NGSI-LD error objects, `(0.0, 0.0)` / out-of-bounds IUDX coordinates, or `NaN` numeric values.
5. Zero tests verifying mixed public + private DNS A/AAAA resolution rejection through full `SecureGTFSFeedClient.fetch_feed()`.
6. All M4.0 `.pb` and IUDX transit payload test vectors are self-authored synthetic fixtures (legitimate pending agency credentials, but unverified against real agency protobuf/IUDX wire traffic).

---

## 12. Canonical Database & Repository Integrity

- `git diff origin/main -- BookingInventory/`: **Empty** (zero changes).
- `BookingInventory/data/APS-05.db` SHA-256 (re-verified after all local backend & frontend test executions):
  `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` (**Exact match**).
- Working-tree state discrepancy at PR `HEAD`: `git status --short` reported `M docs/M4_0_IMPLEMENTATION_REPORT.md` (1 uncommitted trailing blank line added locally relative to committed `7aec8e4` in PR `#26`, `@@ -66,3 +66,4 @@`); no source, test, or config files were dirtied locally.

---

## 13. Severity-Ranked Findings Register

| ID | Severity | Location & Evidence | Impact | Required Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **`H-1`** | **High** | [`gtfs_feed_client.py:440-465`](../backend/app/services/disruption/providers/gtfs_feed_client.py#L440-L465), [`logging.py:6-16`](../backend/app/core/logging.py#L6-L16). Reproduced `httpx` logging `[INFO] httpx: HTTP Request: GET ...?key=MY_TOP_SECRET_API_KEY "HTTP/1.1 200 OK"`. | Leaks raw `DELHI_OTD_API_KEY` (and any future query-param credential) verbatim to stdout/container log sinks on every poll once configured. | Set `httpx` and `httpcore` logger levels to `WARNING` (plus log filter/redaction on URLs and exceptions), extend `sanitize_feed_url()` secret param patterns (`credential`, `signature`), and add a `caplog` non-leakage test. |
| **`H-2`** | **High** | [`disruptions.py:96-110`](../backend/app/api/routes/disruptions.py#L96-L110), [`ProviderIntelligencePanel.tsx:55`](../frontend/src/components/disruption/ProviderIntelligencePanel.tsx#L55). Contrast [`booking.py:49,206`](../backend/app/api/routes/booking.py#L206). | Any anonymous external request to `POST .../providers/feeds/poll?force=true` bypasses per-feed cooldowns and triggers unconstrained outbound provider fetches, risking API quota exhaustion and upstream bans. | Protect `POST .../feeds/poll` with `verify_operational_access` (`x-internal-key`) and enforce server-side min poll interval/rate limit; run scheduled polling server-side while keeping UI refresh read-only (`GET .../feeds`). |
| **`M-1`** | **Medium** | [`gtfs_registry.py:494-495`](../backend/app/services/disruption/providers/gtfs_registry.py#L494-L495), [`L621-674`](../backend/app/services/disruption/providers/gtfs_registry.py#L621-L674). | Concurrent polls lack an outer per-feed lock; `is_deleted: true` entities stay active 300s; rejected replacement entities aren't evicted and can re-emit past `valid_until`; missing header timestamp reports `"fresh"` instead of `"unknown"`. | Add per-feed `asyncio.Lock` around full poll/state update; immediately evict `is_deleted` and invalid/expired updates from `active_map`; filter grace re-emission by `valid_until > now`; set `"unknown"` when header timestamp is absent. |
| **`M-2`** | **Medium** | [`gtfs_protobuf.py:312-329`](../backend/app/services/disruption/providers/gtfs_protobuf.py#L312-L329). | Binary `.pb` `ServiceAlert` decoder omits tag `5` (`informed_entity`), discarding `route_id`, `stop_id`, and `trip` targeting metadata on protobuf alert feeds. | Decode tag `5` (`EntitySelector`: fields `1` `agency_id`, `2` `route_id`, `3` `route_type`, `4` `trip`, `5` `stop_id`) in `_decode_alert()` and add binary alert route-matching tests. |
| **`M-3`** | **Medium** | [`test_m4_0_live_transit_operations.py`](../backend/tests/test_m4_0_live_transit_operations.py). | Tests assert unauthenticated `200` on `/poll`, rely purely on self-authored fixtures, and omit tests for `httpx` log redaction, `/poll` `401` credential errors, mixed public/private DNS `fetch_feed()`, and malformed/`NaN` IUDX registry handling. | Update `/poll` tests for `401`/`403` enforcement; add regression tests for log redaction, query/header `401` via registry poll, mixed DNS resolution rejection, and malformed/NaN IUDX payloads. |
| **`L-1`** | **Low** | [`iudx_adapter.py`](../backend/app/services/disruption/providers/iudx_adapter.py) (reproduced `ValueError` on `float("nan")`, UTC naive assumption, dropped `vehicleInfo.vehicle_label`), [`gtfs_feed_client.py:122`](../backend/app/services/disruption/providers/gtfs_feed_client.py#L122). | Single `NaN` value fails the full feed normalization batch; naive ISO timestamps assume UTC; vehicle license label (`vehicle_label`) omitted from vehicle metadata. | Guard numeric/timestamp parsing with `math.isfinite()` and per-record fault isolation; map `vehicle_label`; review naive timestamp policy if IST-naive feeds are onboarded. |
| **`L-2`** | **Low** | [`ProviderIntelligencePanel.tsx:91-97,357-360`](../frontend/src/components/disruption/ProviderIntelligencePanel.tsx#L91-L97); `M docs/M4_0_IMPLEMENTATION_REPORT.md` trailing blank line. | Panel displays `UNCONFIGURED` badge on `'disabled'`/`'unknown'` presets while footer text cites `BLOCKED`; local working tree has 1 uncommitted blank line in implementation report. | Align panel badge and footer wording (`DISABLED` / `PENDING CREDENTIALS` vs `BLOCKED`); normalize `docs/M4_0_IMPLEMENTATION_REPORT.md` in PR commit. |
| **`I-1`** | **Info** | [`JourneyMap.tsx:560,591`](../frontend/src/components/map/JourneyMap.tsx) (pre-existing M3.7, zero M4.0 diff); `.github/workflows/`. | Pre-existing map popup binary condition renders `LIVE` for non-`'simulated'` events (`deterministic_estimate`/`unknown`); GitHub CI lacks frontend test/lint workflow. | Track map popup provenance pill fix (`deterministic_estimate` / `unknown` states) and frontend CI job in a follow-up cleanup. |

---

## 14. Explicit Merge Recommendation

**DO NOT MERGE PR `#26` in its current state (`b5d35286cb02a2195b5d67f8e9860b36357f2c7c`).**

Recommend opening a focused **M4.0.1 Security & Registry Hardening** remediation pass on `feature/m4-0-live-transit-activation` to resolve **`H-1`**, **`H-2`**, **`M-1`**, **`M-2`**, and **`M-3`** (plus optionally `L-1`/`L-2`), re-running full backend + CI + frontend verification, and conducting a targeted re-audit before merging to `main`.
