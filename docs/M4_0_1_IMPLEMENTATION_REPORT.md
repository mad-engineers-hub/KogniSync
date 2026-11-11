# KogniSync M4.0.1 Implementation Report — Security, Polling & Registry Hardening

**Branch:** `feature/m4-0-1-security-registry-hardening`  
**Base Commit:** `b5d35286cb02a2195b5d67f8e9860b36357f2c7c` (`origin/feature/m4-0-live-transit-activation`, PR `#26` head)  
**Target PR Base:** `feature/m4-0-live-transit-activation` (keeping PR `#26` open and unmerged against `main` `68fb3800ef49c742c84f04a23f89c9b512749ddc`)  
**Scope:** Focused remediation of Findings `H-1`, `H-2`, `M-1`, `M-2`, `M-3`, `L-1`, and `L-2` from the M4.0 independent audit (`docs/M4_0_INDEPENDENT_AUDIT_REPORT.md`).

---

## 1. Summary of Implemented Remediations

### H-1: Credential, Token, and Feed-URL Log Exposure Elimination
- **`backend/app/core/logging.py`**:
  - Added `sanitize_sensitive_log_text`, `SensitiveDataRedactionFilter`, `_attach_redaction_filter`, `_attach_redaction_filter_to_handler`, and `harden_http_client_logging()`.
  - `harden_http_client_logging()` raises `httpx`, `httpcore`, `httpcore.http11`, and `httpcore.connection` logger levels to `WARNING` (preventing HTTP wire/request URL trace leaks even at root `DEBUG`) and attaches `SensitiveDataRedactionFilter` to loggers and handlers both at module import time and in `setup_logging()`.
  - Redacts query parameters matching secret/token/key patterns, Authorization/API-key headers, HTTP/2 wire header tuples (`b'token', b'...'`), and URL userinfo credentials (`user:pass@host` -> `[REDACTED]@host`).
- **`backend/app/services/disruption/providers/gtfs_feed_client.py`**:
  - Invokes `harden_http_client_logging()` at import time.
  - Expands `sanitize_feed_url` with `SENSITIVE_QUERY_PARAM_TERMS` and URL userinfo stripping (`[REDACTED]@host`).
  - Adds `sanitize_diagnostic_message` to scrub exception strings before storage or logging.
- **`backend/app/services/disruption/providers/gtfs_registry.py`**:
  - Applies `sanitize_diagnostic_message` to exception messages recorded during `PARSE_ERROR`, `poll_all_enabled_feeds`, and `_process_entities`.

### H-2: Fail-Closed Operational Poll Authorization, Rate Limiting & Frontend Alignment
- **`backend/app/core/config.py`**:
  - Added `TRANSIT_POLL_ELEVATED_KEY: str | None = None`, `TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS: int = 10`, `TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS: int = 60`, and `TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS: float = 5.0`.
- **`backend/app/core/security.py`**:
  - Added `TransitPollPrincipal`, `_extract_jwt_privileges`, and `verify_transit_poll_access`.
  - Fails closed across all environments (including development/testing): returns `401` when neither `X-Internal-Key` nor `Authorization` bearer JWT is supplied, and `403` for invalid/unconfigured internal keys or unprivileged JWTs.
  - Grants `can_poll` to a valid `X-Internal-Key` or operator/admin JWT; grants `can_force` (`force=true`) only to `X-Elevated-Key` matching `TRANSIT_POLL_ELEVATED_KEY` or JWT claims carrying `admin`, `superadmin`, or `transit:force_poll`.
  - Existing `backend/app/api/routes/booking.py:verify_operational_access` was left unmodified.
- **`backend/app/api/routes/disruptions.py`**:
  - Added thread-safe sliding-window `PollRateLimiter` (`poll_rate_limiter`) with forced-poll cooldown enforcement returning HTTP `429` and `Retry-After` headers.
  - Wired `verify_transit_poll_access` and elevated `force=true` authorization enforcement into `POST /api/v1/disruptions/providers/feeds/poll`.
- **`frontend/src/api/disruptions.ts`**:
  - Added `TransitPollOperationalAuth` and updated `pollGTFSFeeds` so HTTP `ApiError` responses (`err.status > 0`, e.g., `401`, `403`, `429`) propagate cleanly while genuine offline/network failures (`status === 0`) preserve deterministic offline fallback.
- **`frontend/src/components/disruption/ProviderIntelligencePanel.tsx`**:
  - Updated `handleManualRefresh` to invoke read-only `fetchCapabilities()` instead of issuing an unauthenticated `POST /providers/feeds/poll`.
- **`frontend/src/tests/disruptionIntelligence.test.ts`**:
  - Extended tests with a stubbed `globalThis.fetch` `401` assertion alongside offline fallback verification.

### M-1: Registry Freshness, Per-Feed Locking, Tombstone/Invalid Eviction & Expiry Grace
- **`backend/app/services/disruption/providers/gtfs_registry.py`**:
  - Missing or unparseable `FeedHeader.timestamp` sets `status.last_feed_header_timestamp = None` and `status.freshness_status = "unknown"` (never `"fresh"`).
  - Replaced unsafe single-loop locking with loop-safe per-feed locks via `weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]]` (`_get_feed_lock`). `_poll_single_feed` acquires the per-feed lock before checking cooldown or calling `_fetch_feed_events_locked`, serializing concurrent polls for the same feed while letting distinct feeds execute concurrently.
  - `_process_entities` immediately evicts `is_deleted` tombstones and any invalid/expired/cleared replacement update (or normalization failure) for an existing `ent_id` from `active_map` and `absence_map`, setting `status = "resolved"`.
  - Absence-grace retention and `_filter_unexpired_events` enforce `valid_until` expiry prior to event emission.

### M-2 & L-1: Official `gtfs-realtime.proto` `Alert` / `EntitySelector` Wire Decoding & IUDX Hardening
- **`backend/app/services/disruption/providers/gtfs_protobuf.py`**:
  - Added `_decode_entity_selector` and `_encode_entity_selector` supporting `agency_id=1`, `route_id=2`, `route_type=3`, `trip=4` (`TripDescriptor`), `stop_id=5`, and `direction_id=6`.
  - Updated `_decode_alert` to decode tag `5` (`informed_entity`) and discriminate `(tag, wire_type)` pairs across both official `gtfs-realtime.proto` tags (`active_period=1`, `informed_entity=5`, `cause=6/varint`, `effect=7/varint`, `url=8`, `header_text=10/bytes`, `description_text=11/bytes`, `severity_level=14/varint`) and legacy internal M3.8.2 test fixtures (`cause=3`, `effect=4`, `header_text=6`, `description_text=7`, `severity_level=10`).
  - Updated `_encode_alert` to emit official `gtfs-realtime.proto` field numbers (`1, 5, 6, 7, 8, 10, 11, 14`).
- **`backend/app/services/disruption/providers/gtfs_realtime.py`**:
  - Extracts nested `informed_entity` fields (`trip.route_id`, `trip.trip_id`, `agency_id`, `route_type`, `direction_id`) into `DisruptionEvent` and `correlation_metadata`.
- **`backend/app/services/disruption/providers/gtfs_registry.py`**:
  - Preserves `routeTypes` and `directionIds` in `_normalize_alert`, and `vehicleLabel` and `licensePlate` in `_normalize_vehicle`.
- **`backend/app/services/disruption/providers/iudx_adapter.py`**:
  - Added `_safe_finite_float` (`math.isfinite`) across coordinates, timestamps, speed, bearing, and delay so `NaN`/`±Inf` values never poison downstream JSON or state.
  - Isolated per-record normalization failures inside `normalize_iudx_payload`.
  - Preserved `vehicleInfo.vehicle_label` (**L-1**) and documented naive ISO-8601 UTC normalization behavior.

### L-2: UI Status Badge Lookup & Operational Notice Alignment
- **`frontend/src/components/disruption/ProviderIntelligencePanel.tsx`**:
  - Replaced switch-based badge styling in `getStatusBadge` with a complete lookup map covering `disabled`, `configured`, `stale`, `unreachable`, `invalid_response`, and `unknown`.
  - Updated GTFS feed status badge styling for `blocked` and formatted underscores with `replace('_', ' ')`.
  - Aligned footer disclaimer notice to reflect authenticated operational polling constraints.

### M-3: Regression Coverage Extensions
- **`backend/tests/test_m4_0_1_security_and_registry_hardening.py`** (new, 13 tests): covers `H-1`, `H-2`, `M-1`, `M-2` (including a hand-crafted raw binary `.pb` fixture built without `encode_gtfs_feed`), `L-1`, and all 14 `M-3` regression scenarios (malformed protobuf/JSON, IUDX error envelopes, oversized Content-Length and streamed body rejection, redirect SSRF & cross-origin credential stripping, partial valid/invalid entity isolation, missing timestamps, `NaN`/`Inf` IUDX inputs, upstream `429` `Retry-After` & `401`/`403` isolation/recovery, DNS failures, and private IPv4/IPv6 CIDR targets).
- **`backend/tests/test_m4_0_live_transit_operations.py`**: updated `test_api_feeds_and_poll_endpoints_sanitized` to verify unauthenticated `401`, authorized `200` via `X-Internal-Key`, and `poll_rate_limiter.reset()`.

### Out-of-Scope Note
- `frontend/src/components/map/JourneyMap.tsx` (pre-existing M3.7 code) was intentionally left untouched as out of scope for M4.0.1.

---

## 2. Modified & Added Files (M4.0.1 Scope)

Modified tracked files (13):
- `backend/app/api/routes/disruptions.py`
- `backend/app/core/config.py`
- `backend/app/core/logging.py`
- `backend/app/core/security.py`
- `backend/app/services/disruption/providers/gtfs_feed_client.py`
- `backend/app/services/disruption/providers/gtfs_protobuf.py`
- `backend/app/services/disruption/providers/gtfs_realtime.py`
- `backend/app/services/disruption/providers/gtfs_registry.py`
- `backend/app/services/disruption/providers/iudx_adapter.py`
- `backend/tests/test_m4_0_live_transit_operations.py`
- `frontend/src/api/disruptions.ts`
- `frontend/src/components/disruption/ProviderIntelligencePanel.tsx`
- `frontend/src/tests/disruptionIntelligence.test.ts`

New files (3):
- `backend/tests/test_m4_0_1_security_and_registry_hardening.py`
- `docs/M4_0_1_IMPLEMENTATION_REPORT.md`
- `docs/M4_0_1_SECURITY_VERIFICATION_REPORT.md`

Excluded / Untouched:
- `BookingInventory/` and `BookingInventory/data/APS-05.db` (unmodified)
- `docs/M4_0_INDEPENDENT_AUDIT_REPORT.md` (pre-existing untracked read-only audit artifact from PR `#26`; excluded from M4.0.1 commits)

---

## 3. Observed Verification Results (Post-Final Code Edits)

### Backend Targeted & Focused Suites
1. **M4.0 + M4.0.1 Suite (offline default):**
   - Command: `pytest backend/tests/test_m4_0_1_security_and_registry_hardening.py backend/tests/test_m4_0_live_transit_operations.py -v --tb=short -rs`
   - Result: `20 passed, 1 skipped [RUN_LIVE_PROVIDER_TESTS!=1], 0 failed` (`11.13s`).
2. **M4.0 + M4.0.1 Suite (`RUN_LIVE_PROVIDER_TESTS=1`):**
   - Command: `$env:RUN_LIVE_PROVIDER_TESTS="1"; pytest backend/tests/test_m4_0_1_security_and_registry_hardening.py backend/tests/test_m4_0_live_transit_operations.py -v --tb=short -rs`
   - Result: `21 passed, 0 failed` (`25.17s`), exercising live TomTom feed health and live BMTC/Delhi fail-closed `401`/`403` behavior.
3. **Focused Disruption, GTFS, Auth & Booking Suite (11 files):**
   - Command: `pytest backend/tests/test_m4_0_1_security_and_registry_hardening.py backend/tests/test_m4_0_live_transit_operations.py backend/tests/test_gtfs_feed_onboarding_and_security.py backend/tests/test_gtfs_lifecycle_and_multimodal_sync.py backend/tests/test_gtfs_provider.py backend/tests/test_disruption_intelligence.py backend/tests/test_data_freshness.py backend/tests/test_provider_intelligence.py backend/tests/test_journey_live_disruption_integration.py backend/tests/test_auth.py backend/tests/test_booking_api.py -v --tb=short -rs`
   - Result: `157 passed, 1 skipped [RUN_LIVE_PROVIDER_TESTS=1 opt-in live test], 0 failed` (`104.91s`).

### Full Backend Suite (`pytest backend/tests`)
Note: `Settings` loads `.env` (`GEMINI_API_KEY`) locally, so external Gemini API tests execute during local full-suite runs; local PostgreSQL (`:5434`) and Redis (`:6380`) services were not running in this Windows session, causing PG/Redis integration tests to skip with explicit skip reasons.
- **Run 1 (standard env):** `436 passed, 2 failed, 32 skipped` (`1941.87s`). Both failures were transient external Gemini API faults (`test_ai_endpoint.py::test_api_parse_travel_intent` HTTP 503 overload; `test_journey_flow_cases.py::test_case_2_chennai_to_delhi_extraction` read timeout).
- **Run 2 (with `INTERNAL_API_KEY` and `JWT_SECRET_KEY` set):** `437 passed, 1 failed, 32 skipped` (`799.22s`). The sole failure was transient external Gemini HTTP 503 overload in `test_ai_intent.py::test_intent_test_case_4_context_preservation`. Zero non-AI failures occurred across all 437 non-Gemini tests.

### Frontend Sequential Checks (`$env:GOMAXPROCS="1"; $env:RAYON_NUM_THREADS="1"`)
- TypeScript typecheck (`.\node_modules\.bin\tsc.cmd -b`): exit code `0`.
- Linter (`npm run lint` / `oxlint`): exit code `0` (`56` pre-existing warnings, `0` errors across `122` files).
- Production bundle build (`.\node_modules\.bin\vite.cmd build`): exit code `0` (`2091 modules transformed`, built in `4.47s`).
- Frontend test runner (`node scripts/runTests.mjs`): exit code `0` (all `11` suites passed, including `disruptionIntelligence.test.js`).

### Database & Workspace Integrity
- `git diff BookingInventory/`: empty (no modifications).
- `BookingInventory/data/APS-05.db` SHA-256: `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` (matches canonical baseline).
