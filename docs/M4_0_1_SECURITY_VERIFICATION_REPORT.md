# KogniSync M4.0.1 Security & Verification Report

**Branch:** `feature/m4-0-1-security-registry-hardening`  
**Base Reference:** `feature/m4-0-live-transit-activation` (`b5d35286cb02a2195b5d67f8e9860b36357f2c7c`)  
**Scope:** Verification evidence for M4.0 independent audit remediations (`H-1`, `H-2`, `M-1`, `M-2`, `M-3`, `L-1`, `L-2`).

---

## 1. Security & Correctness Control Verification Matrix

| Audit ID | Control / Requirement | Enforcement Location | Verified Behavior & Test Coverage |
|---|---|---|---|
| **H-1** | Credential / URL / token log redaction & wire-log suppression | `backend/app/core/logging.py`, `gtfs_feed_client.py`, `gtfs_registry.py` | `httpx`, `httpcore`, `httpcore.http11`, `httpcore.connection` pinned to `WARNING`; `SensitiveDataRedactionFilter` strips query secrets, auth headers, `b'token', b'...'` wire tuples, and URL userinfo; `sanitize_diagnostic_message` scrubs stored exceptions. Verified by `test_h1_no_credential_leakage_across_httpx_httpcore_and_registry_logs[asyncio]`. |
| **H-2** | Fail-closed `POST /providers/feeds/poll`, elevated `force=true`, & rate limiting | `backend/app/core/config.py`, `security.py`, `routes/disruptions.py`, `disruptions.ts`, `ProviderIntelligencePanel.tsx` | Anonymous POST rejected (`401`); invalid/unconfigured keys or unprivileged JWTs rejected (`403`) across all environments; `force=true` gated on `X-Elevated-Key` or `admin`/`superadmin`/`transit:force_poll` JWT; `PollRateLimiter` enforces sliding-window & forced cooldown (`429` + `Retry-After`). Frontend manual refresh reads capabilities (`fetchCapabilities`) and `pollGTFSFeeds` propagates `401`/`403`/`429`. Verified by `test_h2_poll_endpoint_auth_force_privilege_and_rate_limiting`, `test_api_feeds_and_poll_endpoints_sanitized`, and `disruptionIntelligence.test.ts`. |
| **M-1** | Missing-header `"unknown"` freshness, per-feed locks, tombstone/invalid eviction & `valid_until` expiry | `backend/app/services/disruption/providers/gtfs_registry.py` | Missing/unparseable `FeedHeader.timestamp` sets `freshness_status = "unknown"`; `_get_feed_lock` uses `WeakKeyDictionary` per event loop to serialize same-feed polls while keeping distinct feeds parallel; `is_deleted` tombstones and invalid/expired replacement updates evict prior `ent_id` entries (`status = "resolved"`); absence grace enforces `valid_until`. Verified by all 3 `test_m1_*` tests in `test_m4_0_1_security_and_registry_hardening.py`. |
| **M-2** | Official `gtfs-realtime.proto` `Alert` / `EntitySelector` decoding & exact correlation | `gtfs_protobuf.py`, `gtfs_realtime.py`, `gtfs_registry.py` | Tag `5` (`EntitySelector` with `agency_id=1`, `route_id=2`, `route_type=3`, `trip=4`, `stop_id=5`, `direction_id=6`) and official `Alert` wire tags (`cause=6`, `effect=7`, `url=8`, `header_text=10`, `description_text=11`, `severity_level=14`) decoded accurately alongside legacy internal fixtures. Verified against a hand-crafted raw `.pb` payload in `test_m2_handcrafted_official_protobuf_alert_informed_entity_matching[asyncio]`. |
| **L-1** | IUDX `NaN`/`Inf` rejection, per-record isolation & `vehicle_label` preservation | `iudx_adapter.py`, `gtfs_registry.py` | `_safe_finite_float` validates finite floats; invalid items isolated in `normalize_iudx_payload`; `vehicleInfo.vehicle_label` propagated to `vehicleLabel`. Verified by `test_m3_and_l1_nan_inf_iudx_and_vehicle_label_preservation[asyncio]`. |
| **L-2** | Exhaustive status badge lookup & aligned footer text | `ProviderIntelligencePanel.tsx` | Full badge map (`disabled`, `configured`, `stale`, `unreachable`, `invalid_response`, `unknown`), GTFS `blocked` styling + underscore formatting, and aligned operational notice verified by `tsc`, `oxlint`, `vite build`, and `runTests.mjs`. |
| **M-3** | Adversarial malformed inputs, size bounds, redirect SSRF, `429`/`401`/`403` isolation, DNS/CIDR blocks | `test_m4_0_1_security_and_registry_hardening.py` | All 14 specified adversarial edge cases exercised and passing after final edits. |

---

## 2. Cryptographic, Secret & Data Integrity Checks

1. **Diff Secret Scan:** Scanned full `git diff origin/feature/m4-0-live-transit-activation` diff for tokens, passwords, and hardcoded secret patterns; only prose/comment matches (`TomTom Orbis v2` text in `ProviderIntelligencePanel.tsx`) appeared, with zero hardcoded credentials or secrets.
2. **Untouched Restricted Paths:**
   - `git diff BookingInventory/` returned empty.
   - `BookingInventory/data/APS-05.db` SHA-256 verified unchanged at `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A`.
   - `backend/app/api/routes/booking.py` remained unmodified.
   - `frontend/src/components/map/JourneyMap.tsx` remained unmodified (out of scope).

---

## 3. Execution & Environment Caveats

- **Live Provider Verification (`RUN_LIVE_PROVIDER_TESTS=1`):** `21 passed, 0 failed` (`test_m4_0_1_security_and_registry_hardening.py` + `test_m4_0_live_transit_operations.py`), confirming live TomTom routing/disruption readiness and fail-closed `401`/`403` handling against unconfigured/unauthorized transit endpoints without leaking credentials or fabricating live transit incidents.
- **Full Pytest Environment Note:** During local full-suite runs (`436 passed, 2 failed, 32 skipped` and `437 passed, 1 failed, 32 skipped`), live Gemini API tests ran against `.env` (`GEMINI_API_KEY`) and experienced intermittent upstream Gemini HTTP 503 overload / read timeout failures (`test_api_parse_travel_intent`, `test_case_2_chennai_to_delhi_extraction`, `test_intent_test_case_4_context_preservation`), while PostgreSQL (`:5434`) and Redis (`:6380`) tests skipped cleanly because those containers were not started locally. Zero failures occurred in any non-Gemini backend test (`437 passed` in the focused/full offline scope and `157 passed, 1 skipped` across the 11-file core disruption/GTFS/auth/booking suite).
- **GitHub Actions Trigger Note:** `.github/workflows/postgres_integration.yml` triggers on `push` and `pull_request` events targeting `branches: [ main ]`. A remediation PR targeting `feature/m4-0-live-transit-activation` will execute GitHub Actions PostgreSQL/Redis CI once merged into `feature/m4-0-live-transit-activation` / PR `#26`.
