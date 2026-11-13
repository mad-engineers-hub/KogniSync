# KogniSync M4.0.1 — Independent Security Audit & CI Validation Report

**Audit Date:** 2026-11-11  
**Audit Scope:** Read-only independent verification of **M4.0.1 remediation PR #27** (`feature/m4-0-1-security-registry-hardening`) targeting **M4.0 PR #26** (`feature/m4-0-live-transit-activation` -> `main`)  
**Repository:** `E:\KogniSync\KogniSync` (`mad-engineers-hub/KogniSync`)  
**PR #26 (Integration PR):** https://github.com/mad-engineers-hub/KogniSync/pull/26  
**PR #27 (Remediation PR):** https://github.com/mad-engineers-hub/KogniSync/pull/27  

---

## Executive Verdict

**VERDICT: `PASS WITH CONDITIONS`**

M4.0.1 (`f32c46564a439bdb76d0b08312bba0c7e42b5016`) successfully remediates the core M4.0 blocking defects across HTTP credential redaction (`H-1`), operational `/poll` authentication and sliding-window rate limiting (`H-2`), cross-event-loop registry locking and expiry eviction (`M-1`), GTFS-RT official protobuf `Alert.informed_entity` decoding (`M-2`), and negative/boundary security test coverage (`M-3`). All 438 offline backend tests pass locally (32 expected skips due to offline PostgreSQL `:5434` / Redis `:6380` / opt-in live switch), all 21 targeted M4.0+M4.0.1 tests pass with `RUN_LIVE_PROVIDER_TESTS=1`, and frontend TypeScript, `oxlint`, production Vite bundle, and all 11 frontend test suites pass with zero secrets embedded in `frontend/dist/`.

However, **unconditional `PASS` cannot be granted** due to:
1. **Zero CI Execution on `f32c465` (Mandatory Merge Blocker for `main`):** `.github/workflows/postgres_integration.yml` triggers exclusively on `branches: [ main ]` (`push` / `pull_request`), leaving PR #27 with `statusCheckRollup=[]` and zero live PostgreSQL 16 / Redis 7 CI runs on the M4.0.1 commit.
2. **Non-Production JWT Fallback Secret on `/poll` (`H-2` High Finding):** Outside `ENVIRONMENT == "production"`, if `JWT_SECRET_KEY` is unset (`None`), `decode_access_token` falls back to the hardcoded source constant `"kognisync_insecure_development_jwt_secret_key_384729"`, allowing an unauthenticated caller to forge an `admin` JWT and receive `200 OK` on `POST /api/v1/disruptions/providers/feeds/poll?force=true` (empirically reproduced).
3. **Additional Hardening & Coverage Gaps (Medium / Low):** Unsanitized parse-error logging in `gtfs_realtime.py`, unredacted post-init custom handlers in `logging.py`, minor regex gaps (`https://SECRET@host`, `?subscription-key=`, JSON-quoted tokens), process-local in-memory rate limiting (`PollRateLimiter`), decoded M-2 selectors (`agency_id`, `route_type`, `trip_id`, `direction_id`) not matched downstream in `RouteDisruptionMatcher`, and mixed-DNS tests covering only `validate_feed_url_ssrf_safety(...)` rather than `SecureGTFSFeedClient.fetch_feed(...)`.

---

## 1. Audit Rules & Integrity Confirmation

- **Strict Read-Only Audit:** No application source files, test suites, `.github/workflows/*`, `.env`, or `BookingInventory/` files were edited.
- **No Git Mutations:** Neither PR #26 nor PR #27 was modified, merged, closed, commented on, or pushed. No commits, rebases, or branch modifications occurred.
- **Zero Secret Exposure:** Real `.env` tokens, API keys, and signing keys were excluded from logs, console outputs, and this report. Synthetic placeholder tokens were used in all adversarial probes.
- **Canonical Database Preserved:** Verified unmodified before and after test execution.

---

## 2. Git, Commit Graph & PR Relationship Verification

| Item | Verified Value |
|---|---|
| PR #26 (`M4.0`) | `OPEN`, `mergeable=MERGEABLE`, `isDraft=false`, `feature/m4-0-live-transit-activation` (`b5d35286cb02a2195b5d67f8e9860b36357f2c7c`) -> `main` (`68fb3800ef49c742c84f04a23f89c9b512749ddc`) |
| PR #26 CI Status | Green CheckRun `42977141091` / Job `130378736926` (`SUCCESS`, `2026-11-11T07:07:00Z`) on prior commit `b5d3528` only |
| PR #27 (`M4.0.1`) | `OPEN`, `mergeable=MERGEABLE`, `isDraft=false`, `feature/m4-0-1-security-registry-hardening` (`f32c46564a439bdb76d0b08312bba0c7e42b5016`) -> `feature/m4-0-live-transit-activation` (`b5d35286cb02a2195b5d67f8e9860b36357f2c7c`) |
| PR #27 CI Status | `statusCheckRollup=[]` (**0 GitHub Actions runs on `f32c465`**) |
| Diff Stat (`b5d3528..f32c465`) | `16 files changed, 2305 insertions(+), 297 deletions(-)` |

**Verified Commit History (`git log --oneline --decorate -n 6`):**
- `f32c465` `(HEAD -> feature/m4-0-1-security-registry-hardening, origin/feature/m4-0-1-security-registry-hardening)` `fix(disruption): M4.0.1 security, polling authorization, and registry hardening`
- `b5d3528` `(origin/feature/m4-0-live-transit-activation, feature/m4-0-live-transit-activation)` `M4.0: Authorized Live Transit Feed Activation & Real-Time Multimodal Operations`
- `68fb380` `(origin/main, origin/HEAD, main)` `fix(disruption): M3.9.1 SSRF IP-pinned transport & exact transit identifier matching (#25)`
- `a66084e` `feat(disruption): M3.9 authorized GTFS-RT onboarding, SSRF hardening, and multimodal synchronization (#24)`
- `1db7ee4` `M3.8: Verified Live Data Integrations & Provider Intelligence (#23)`
- `3829c02` `feat(disruption): Real-Time Journey Intelligence & Disruption Awareness (Milestone M3.7) (#22)`

**Exact PR #27 Changed Files (`git diff --name-status b5d3528..f32c465`):**
- Modified (`M`): `backend/app/api/routes/disruptions.py`, `backend/app/core/config.py`, `backend/app/core/logging.py`, `backend/app/core/security.py`, `backend/app/services/disruption/providers/gtfs_feed_client.py`, `backend/app/services/disruption/providers/gtfs_protobuf.py`, `backend/app/services/disruption/providers/gtfs_realtime.py`, `backend/app/services/disruption/providers/gtfs_registry.py`, `backend/app/services/disruption/providers/iudx_adapter.py`, `backend/tests/test_m4_0_live_transit_operations.py`, `frontend/src/api/disruptions.ts`, `frontend/src/components/disruption/ProviderIntelligencePanel.tsx`, `frontend/src/tests/disruptionIntelligence.test.ts`
- Added (`A`): `backend/tests/test_m4_0_1_security_and_registry_hardening.py`, `docs/M4_0_1_IMPLEMENTATION_REPORT.md`, `docs/M4_0_1_SECURITY_VERIFICATION_REPORT.md`

---

## 3. H-1 — Credential and URL Log Redaction Verification

### Inspected Modules
- `backend/app/core/logging.py` (lines 1-90)
- `backend/app/services/disruption/providers/gtfs_feed_client.py` (lines 1-610)
- `backend/app/services/disruption/providers/gtfs_registry.py` (lines 1-1166)
- `backend/app/services/disruption/providers/gtfs_realtime.py` (lines 1-807)
- `backend/app/main.py` (lines 1-80)

### Empirical Adversarial Probe Results
1. **Live `httpx` + `httpcore` Transport Probes (Part 1):**
   - Executed real requests containing query secrets (`?key=...`, `?auth_token=...`), custom auth header (`token`), `Authorization: Bearer ...`, and HTTP `302 Location` redirects containing `?auth_token=SYNTH_REDIR_LOC_777`.
   - Observed **zero secret leakage** across pre-init and post-init root handlers under both default suppressed `httpx`/`httpcore` (`WARNING`) and forced `DEBUG` on `httpx` / `httpcore.http11`.
2. **Identified Residual Gaps (Empirical Part 1 & Part 2):**
   - **Post-init / custom non-registered handlers leak (`Medium`):** `harden_http_client_logging()` (`logging.py:58-73`) attaches `SensitiveDataRedactionFilter` only to pre-existing handlers on `("", "kognisync", "uvicorn.access", "uvicorn.error", "httpx", "httpcore", "httpcore.http11", "httpcore.connection")`. Any handler added to `root` or third-party loggers *after* `setup_logging()` (verified empirically via `post_only_handler` and `audit.post_init_custom`) does **not** carry the redaction filter and emitted raw `SYNTH_AUTH_TOKEN_PARAM_333` and `POST_INIT_HANDLER_LEAK_777`. If `httpcore.http2` is raised to `DEBUG` without a filtered handler, `httpcore.http2` also emits raw header tuples (`H2_SECRET_888` observed when `root` used an unfiltered post-init handler).
   - **Raw parse exception logging (`Medium`):** `gtfs_realtime.py:341, 402, 429` log `{parse_err}`, `{json_err}`, and `{pb_err}` without `sanitize_diagnostic_message(...)`.
   - **Sanitizer regex blind spots (`Low`):** `sanitize_sensitive_log_text` (`logging.py:6-15`) did not redact:
     - Single-token URL userinfo without `:password` (`https://SECRET@host` leaked on all handlers and `sanitize_sensitive_log_text`),
     - Hyphenated query key `?subscription-key=SECRET2` inside `sanitize_sensitive_log_text` (handled safely on parsed URLs by `gtfs_feed_client.sanitize_feed_url`, missed by `logging.py`'s regex),
     - JSON-style quoted secrets `{"token": "SECRET6", "x-api-key": "SECRET7"}`.

---

## 4. H-2 — Operational `/poll` Authorization & Rate Limiting Verification

### Inspected Modules
- `backend/app/core/security.py` (lines 1-264)
- `backend/app/core/config.py` (lines 1-114)
- `backend/app/api/routes/auth.py` (lines 1-70)
- `backend/app/api/routes/disruptions.py` (lines 1-277)

### Empirical Adversarial Probe Results
- **Demo token rejection:** `POST /api/v1/auth/demo-token` issues `usr_demo_*` without elevated roles/scopes -> `POST /api/v1/disruptions/providers/feeds/poll` returns **`403`** (`Observed: 403`).
- **Cryptographic JWT verification:** Forged admin JWT signed with wrong secret returns **`401`** (`Observed: 401`).
- **`force=true` bypass resistance:** Sending `?force=true` after exhausting the sliding-window limit returns **`429`** (`Observed: 429`).
- **Concurrency atomicity:** 12-request concurrent burst against `max_requests=4` yielded exact status distribution **`{200: 4, 429: 8}`** (`PollRateLimiter` guarded by `threading.Lock`).
- **Global cross-principal ceiling:** With `max=3` per principal and `global=6`, `op1` received `[200, 200, 200]`, `op2` received `[200, 200, 200]`, and `op3` first request received **`429`**.

### Identified Findings
1. **Non-Production Hardcoded JWT Fallback Secret (`High`, `security.py:47-48, 241-250`):**
   - While `ENVIRONMENT == "production"` enforces secret configuration in `main.py` lifespan and returns `500` in `get_jwt_secret()`, when `ENVIRONMENT != "production"` and `JWT_SECRET_KEY=None`, `get_jwt_secret()` returns `"kognisync_insecure_development_jwt_secret_key_384729"`.
   - Empirically confirmed: an `admin` JWT signed with that constant against `JWT_SECRET_KEY=None` in non-production returned **`200 OK`** on `/poll` (whereas `X-Internal-Key` fails closed even in development when unset).
2. **Single-Worker In-Memory Rate Limiter & Key Retention (`Medium`, `disruptions.py:101-156`):**
   - `PollRateLimiter` and `GTFSFeedRegistry._last_poll_epoch` are process-local in-memory structures. Current launch scripts (`scripts/start_backend.bat`, `scripts/start_kognisync.ps1`) run single-worker Uvicorn, where behavior matches single-process tests; scaling to `--workers N` or multiple pods multiplies effective poll quotas and bypasses cooldown serialization across workers unless moved to Redis. Additionally, `_requests_by_principal` retains keys for unique `jwt:<sub>` callers after timestamp deques empty.

---

## 5. M-1 — Registry Concurrency, Freshness & Eviction Verification

### Inspected Modules
- `backend/app/services/disruption/providers/gtfs_registry.py` (lines 1-1166)
- `backend/app/services/disruption/providers/iudx_adapter.py` (lines 1-299)

### Empirical Probe Results
- **Cross-Event-Loop Locks (`_get_feed_lock`):** Invoking polls across two separate asyncio event loops and running GC confirmed zero stale loop entries retained (`Cross-loop WeakKeyDict lock count after GC (loop1=0, loop2=0)`).
- **Timestamp / Freshness Fail-Safe:** Unparseable/missing timestamps in `parse_timestamp_to_epoch` returned `ts=None` without raising and resulted in `freshness="unknown"`.
- **Expiry Grace Eviction:** Feeding an alert with imminent `valid_until` returned `active=1` initially, then after `valid_until` elapsed returned `0` events and cleared the cooldown cache (`returned=0, cached_len=0`).
- **Tombstone & Error Isolation:** Verified via unit tests (`test_m1_tombstone_invalid_replacement_and_valid_until_grace_eviction`, `test_m3_upstream_429_retry_after_401_403_and_isolation_recovery`) and empirical M-3 malformed frames.

---

## 6. M-2 — GTFS-RT Protobuf Alert `informed_entity` Decoding & Correlation Verification

### Inspected Modules
- `backend/app/services/disruption/providers/gtfs_protobuf.py` (lines 1-688)
- `backend/app/services/disruption/providers/gtfs_realtime.py` (lines 1-807)
- `backend/app/services/disruption/matcher.py` (lines 1-505)
- `backend/app/services/disruption/assessment.py` (lines 1-356)
- `backend/app/services/journey/schemas.py` (lines 1-420)

### Empirical Probe Results (9 Synthesized Protobuf Frames + Matcher/Assessor)
1. **Protobuf Decoding (`decode_gtfs_feed`):**
   - Official wire-format `Alert` field 5 `informed_entity` (`EntitySelector` fields `agency_id`, `route_id`, `route_type`, `trip { trip_id, route_id, direction_id }`, `stop_id`, `direction_id`) decoded all 7 entities accurately while skipping unknown protobuf tags cleanly.
   - Malformed payloads failed cleanly:
     - `truncated_varint` -> `ValueError: Truncated protobuf varint in feed stream`
     - `len_overrun` -> `ValueError: Truncated length-delimited field of length 127`
     - `bad_wire_type_6` -> `ValueError: Unsupported wire type 6 for tag 1`
     - `invalid_utf8_in_id` -> decoded entity id safely with UTF-8 replacement (`''`).
2. **End-to-End Propagation vs Partial Matcher Gap (`Medium` Finding):**
   - **Working End-to-End:** Top-level `route_id` (`KIA-7A`), nested `trip.route_id` (`R-300`), and `stop_id` (`METRO-MGR`) populate `DisruptionEvent.route_ids` / `stop_ids`, match in `RouteDisruptionMatcher` (`route_id_exact`, `stop_id_exact`), and drive `JourneyImpactAssessor` (`ent-multi_selectors`: `is_disrupted=True, delay=120, affected=1, active_ids=['ent-multi_selectors']`).
   - **Not Matched Downstream:** Entities populated solely with `agency_id` (`AGENCY-KA-BMTC`), `route_type` (`1`), `trip.trip_id` (`TRIP-IND-42`), or `direction_id` (`0`) are decoded into `DisruptionEvent.trip_ids` and `correlation_metadata` (`agencyIds`, `routeTypes`, `directionIds`), **but `RouteDisruptionMatcher.match_event_to_segment` (`matcher.py:183-375`) checks only `route_ids`, `stop_ids`, and spatial fields**, returning `match=None` (`JourneySegmentSchema` also has no `trip_id` field).

---

## 7. M-3 — Boundary, Negative & Mixed-DNS Security Test Coverage

- Verified `test_m4_0_1_security_and_registry_hardening.py` (13 test functions) covers log redaction, cross-loop/concurrent poll locking, tombstone & expiry eviction, handcrafted protobuf `informed_entity`, malformed protobuf/JSON/IUDX envelopes, oversized Content-Length/body streaming cutoff, cross-origin redirect SSRF & header stripping, partial valid+invalid entities, `NaN`/`Inf` rejection, `429 Retry-After` / `401` / `403` isolation, `/poll` auth & concurrency limits, and private IPv4/IPv6 rejections.
- **Finding (`Low`, Incomplete Mixed-DNS Call-Path Test):** Both `test_m3_dns_failure_and_ipv4_ipv6_private_targets` (`test_m4_0_1_security_and_registry_hardening.py:969-990`) and `test_m1_dns_returns_mixture_fails_closed` (`test_gtfs_feed_onboarding_and_security.py:469-481`) invoke `validate_feed_url_ssrf_safety(...)` directly rather than `SecureGTFSFeedClient.fetch_feed(...)`.
- **Empirical Runtime Confirmation:** Calling actual `SecureGTFSFeedClient.fetch_feed("mixed_dns", "https://mixed-host.example/feed")` with mocked `socket.getaddrinfo` returning `93.184.216.34` + `127.0.0.1` **did fail closed** with `GTFSFeedSecurityError: SSRF validation rejected target: SSRF Protection: Target IP address '127.0.0.1' is within private/internal/non-public range.`

---

## 8. CI Workflow Analysis

- `.github/workflows/postgres_integration.yml` (`PostgreSQL Integration & Booking Safety Gate`, ID `407226540`) is the sole workflow in `.github/workflows/` and triggers only on:
  ```yaml
  on:
    push:
      branches: [ main ]
    pull_request:
      branches: [ main ]
  ```
- **Impact:** PR #27 targets `feature/m4-0-live-transit-activation` (not `main`) and therefore has **0 CI runs** on commit `f32c465`. Only once PR #27 is merged into `feature/m4-0-live-transit-activation` (or triggers are extended on a workflow change) will GitHub Actions execute the PG16 + Redis 7 suite on the PR #26 integration branch before `main`.
- **Note on `GEMINI_API_KEY`:** CI omits `GEMINI_API_KEY`; live Gemini calls depend on `.env` in local runs (all local Gemini intent tests passed deterministically during this audit).

---

## 9. Independently Executed Backend Test Results

| Run | Command / Scope | Observed Result | Notes / Skip Root Causes |
|---|---|---|---|
| **Focused Security, Disruption, Auth & Booking Suite** (offline default) | `pytest` on 16 files (`test_m4_0_1_security_and_registry_hardening.py`, `test_m4_0_live_transit_operations.py`, `test_gtfs_*`, `test_disruption_intelligence.py`, `test_provider_intelligence.py`, `test_journey_live_disruption_integration.py`, `test_tomtom_provider.py`, `test_auth.py`, `test_booking_api.py`, `test_hold_expiration.py`, `test_demo_reset_safety.py`, `test_canonical_init.py`, `test_config.py`, `test_live_provider_verification.py`) | **`201 passed, 8 skipped`** in `134.00s` (`exit 0`) | 7 skips in `test_canonical_init.py` (PostgreSQL `:5434` unreachable locally); 1 skip in `test_m4_0_live_transit_operations.py:598` (`RUN_LIVE_PROVIDER_TESTS=1` unset) |
| **Live-Gated M4.0 + M4.0.1 Suite** (`RUN_LIVE_PROVIDER_TESTS=1`) | `pytest` on `test_m4_0_1_security_and_registry_hardening.py` + `test_m4_0_live_transit_operations.py` | **`21 passed, 0 skipped`** in `24.24s` (`exit 0`) | `test_live_provider_endpoints_smoke[asyncio]` executed and passed (TomTom live / Indian agency presets fail closed without tokens) |
| **Full Backend Suite** | `pytest backend/tests -v -rs` (470 collected) | **`438 passed, 32 skipped`** in `625.71s` (`exit 0`) | Zero failures. All 32 skips verified verbatim: `test_canonical_init.py` (7), `test_db_initialization.py` (1), `test_health.py` (2: PG `:5434` + Redis `:6380`), `test_m4_0_live_transit_operations.py` (1: `RUN_LIVE_PROVIDER_TESTS`), `test_models.py` (2), `test_postgres_integration.py` (7), `test_repositories.py` (12) |

---

## 10. Independently Executed Frontend Verification & Bundle Secret Audit

All frontend checks ran sequentially with `$env:GOMAXPROCS="1"; $env:RAYON_NUM_THREADS="1"`:

| Check | Command | Observed Result |
|---|---|---|
| TypeScript | `.\node_modules\.bin\tsc.cmd -b` | **`exit 0`** (0 errors) |
| Linter | `npm run lint` (`oxlint`) | **`exit 0`** (`Found 56 warnings and 0 errors`) |
| Production Build | `.\node_modules\.bin\vite.cmd build` | **`exit 0`** (`dist/index.html` 1.48 kB, `dist/assets/index-aGR2-5jI.css` 114.15 kB, `dist/assets/index-BTZLAjI5.js` 883.79 kB, built in `6.14s`) |
| Test Runner | `node scripts/runTests.mjs` | **`exit 0`**: all 11 suites passed (`12` multimodal, E2E flow succeeded, `9` XR, `8` map M3.5, `8/8` optimizer, `3/3` API contracts, `9` trust-aware, M3.3 routing, `27` GPS M3.4/M3.4.1, M3.6 navigation, M3.7-M4.0 disruption intelligence & M4.0.1 transit feed diagnostics/poll contract) |
| Bundle Secret Scan | `Select-String` across `frontend/dist/` | **Zero embedded secrets.** Only benign matches were Leaflet CSS `OTransition` substring (`index-BTZLAjI5.js` L11) and descriptive UI status notice `commercial TOMTOM_API_KEY required` (`index-BTZLAjI5.js` L93). Zero `INTERNAL_API_KEY`, `JWT_SECRET`, `Bearer` tokens, or hardcoded credentials present. |

Verified `ProviderIntelligencePanel.tsx` uses explicit `AVAILABLE`, `DEGRADED`, `UNCONFIGURED`, and `pending_credentials` states without triggering privileged `/poll` mutations automatically on page load (`disruptions.ts` sends `X-Internal-Key` only if caller explicitly passes `operationalAuth.internalKey`).

---

## 11. `BookingInventory/` Immutability & Working Tree Check

- **`git diff BookingInventory/`:** Empty (zero changes).
- **`BookingInventory/data/APS-05.db` SHA-256:** `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` (exact match).
- **`git status -uall --short`:** Pre-existing working tree noise consists only of 1 trailing blank line each in `docs/M4_0_1_IMPLEMENTATION_REPORT.md` and `docs/M4_0_1_SECURITY_VERIFICATION_REPORT.md`, plus untracked `docs/M4_0_INDEPENDENT_AUDIT_REPORT.md`, alongside this new report `docs/M4_0_1_INDEPENDENT_AUDIT_REPORT.md`. `frontend/dist/` and `frontend/dist-test/` remain gitignored.

---

## 12. Audit Findings Summary by Severity

### Critical
- None found.

### High
1. **[HIGH-01 / CI Blocker] Zero CI Validation on M4.0.1 Commit `f32c465`:** PR #27 targets `feature/m4-0-live-transit-activation`, whereas `.github/workflows/postgres_integration.yml` runs only on `branches: [ main ]`. Live PostgreSQL 16 + Redis 7 integration (`31` skipped local DB/Redis tests) has not executed against M4.0.1 changes.
2. **[HIGH-02 / H-2 Auth] Non-Production Hardcoded JWT Fallback Secret Allows Forged Admin `/poll` Calls (`backend/app/core/security.py:47-48, 241-250`):** Outside `ENVIRONMENT == "production"`, if `JWT_SECRET_KEY` is omitted, `decode_access_token` uses hardcoded `"kognisync_insecure_development_jwt_secret_key_384729"`. Empirically verified returning `200 OK` on `/api/v1/disruptions/providers/feeds/poll?force=true`. Privileged poll authorization should fail closed whenever `JWT_SECRET_KEY` is unset (matching `X-Internal-Key`), regardless of environment.

### Medium
3. **[MED-01 / H-1 Redaction] Unsanitized Parse Error Logs in `gtfs_realtime.py` (`lines 341, 402, 429`):** Logs `{parse_err}`, `{json_err}`, and `{pb_err}` directly without `sanitize_diagnostic_message(...)`.
4. **[MED-02 / H-1 Logging Scope] Post-Init Handlers and Custom Third-Party Loggers Bypass `SensitiveDataRedactionFilter` (`backend/app/core/logging.py:58-73`):** `harden_http_client_logging()` attaches redaction filters only to handlers already attached at init time; late-attached root handlers or third-party handlers with `propagate=False` (or `httpcore.http2` if explicitly raised to `DEBUG` without filtered handlers) leak unredacted URLs/headers.
5. **[MED-03 / M-2 Downstream Scope] Decoded `agency_id`, `route_type`, `trip_id`, and `direction_id` Selectors Not Matched Downstream (`backend/app/services/disruption/matcher.py:183-375`):** Although decoded and preserved in `DisruptionEvent.trip_ids` and `correlation_metadata`, `RouteDisruptionMatcher` evaluates only `route_ids`, `stop_ids`, and spatial fields, causing agency-only, route-type-only, trip-only, and direction-only GTFS-RT alerts to yield `match=None`.
6. **[MED-04 / H-2 Scaling] Process-Local Rate Limiter & Unbounded Principal Key Dict (`backend/app/api/routes/disruptions.py:101-156`):** `PollRateLimiter` and cooldown state reside only in process memory (safe in current single-worker launch scripts, multiplied by worker count if scaled horizontally) and `_requests_by_principal` never prunes drained keys.

### Low
7. **[LOW-01 / H-1 Regex Edge Cases] `sanitize_sensitive_log_text` Blind Spots (`backend/app/core/logging.py:6-15`):** Misses userinfo without `:password` (`https://SECRET@host`), hyphenated query parameters (`?subscription-key=SECRET`), and JSON-quoted secret strings (`{"token": "...", "x-api-key": "..."}`).
8. **[LOW-02 / M-3 Test Scope] Mixed-DNS Tests Bypass `SecureGTFSFeedClient.fetch_feed()`:** `test_m3_dns_failure_and_ipv4_ipv6_private_targets` and `test_m1_dns_returns_mixture_fails_closed` assert only `validate_feed_url_ssrf_safety(...)` directly rather than `fetch_feed(...)` (though independent audit probing confirmed `fetch_feed(...)` does fail closed).

### Informational
9. **[INFO-01] Working Tree & Existing Lint Baseline:** Pre-existing 1-line trailing-newline diffs exist in `docs/M4_0_1_IMPLEMENTATION_REPORT.md` and `docs/M4_0_1_SECURITY_VERIFICATION_REPORT.md`; `oxlint` reports `56` pre-existing unused-var warnings (`0` errors) across older test/utility files alongside `dist/` warnings check.

---

## 13. Integration Recommendation

1. **Do NOT merge PR #26 into `main` directly in its current state.**
2. **PR #27 -> PR #26 Integration Path (`PASS WITH CONDITIONS`):**
   - **Recommended Option A (Harden First on `PR #27`):** Fix `[HIGH-02]` (fail-closed `verify_transit_poll_access` when `JWT_SECRET_KEY` is unconfigured), `[MED-01]` (`sanitize_diagnostic_message` in `gtfs_realtime.py`), `[LOW-01]` (`logging.py` regex patterns), `[LOW-02]` (`fetch_feed` mixed-DNS test), and either wire/document `[MED-03]` (`agencyIds`/`routeTypes` matching scope), then merge PR #27 -> PR #26 so GitHub Actions `postgres_integration.yml` runs on the combined PR #26 head before `main` merge.
   - **Option B (CI Validation First on PR #26):** Merge PR #27 into PR #26 (`feature/m4-0-live-transit-activation`) strictly to trigger GitHub Actions PG16 + Redis 7 verification on PR #26, **holding PR #26 -> `main` merge** until CI turns green **and** `[HIGH-02]`, `[MED-01]`, `[LOW-01]`/`[LOW-02]` are resolved (or formally triaged with tracked follow-up tickets) on PR #26 prior to `main` merge.

