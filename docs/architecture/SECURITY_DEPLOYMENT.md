# KogniSync Production Security & Deployment Architecture

This document defines the production security standards, configuration requirements, token lifecycles, and operational fail-closed boundaries for KogniSync services.

---

## 1. Required Environment Variables

The table below enumerates all production configuration keys, their security criticality, and default behavior.

| Variable Name | Required in Prod | Description | Safe Failure / Default Behavior |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | **Yes** | Deployment environment (`production`, `development`, `test`). | Defaults to `development`. |
| `JWT_SECRET_KEY` | **Yes** | Symmetric signing key for HS256 JWT tokens. Must be $\ge 32$ bytes. | In `production`, application startup is **aborted** (`RuntimeError`) if missing or $<32$ characters; requests fail closed with HTTP 500. |
| `JWT_ALGORITHM` | No | Cryptographic algorithm for signing and verifying tokens. | Defaults to `HS256`. Token decoding strictly restricts allowed algorithms to this single value. |
| `JWT_ISSUER` | Optional | Expected token issuer claim (`iss`). | If configured, tokens without matching `iss` are rejected with HTTP 401. |
| `JWT_AUDIENCE` | Optional | Expected token audience claim (`aud`). | If configured, tokens without matching `aud` are rejected with HTTP 401. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Token time-to-live for authenticated sessions. | Defaults to `60` minutes. |
| `INTERNAL_API_KEY` | **Yes** | Shared operational key passed via `X-Internal-Key` header for admin routes. | In `production`, operational endpoints return **HTTP 403** immediately if unconfigured or mismatched. |
| `DATABASE_URL` | **Yes** | PostgreSQL connection string (`postgresql+asyncpg://...`). | Required for database initialization and transactional operations. |
| `REDIS_URL` | Optional | Advisory caching and TTL tracking (`redis://...`). | System fails gracefully if Redis is unavailable; PostgreSQL remains authoritative. |

> [!CAUTION]
> Never commit plaintext secrets to source control or CI logs. Secrets must be injected through environment secrets managers (e.g. AWS Secrets Manager, HashiCorp Vault, GitHub Secrets).

---

## 2. JWT Secret Generation & Rotation Guidance

For HMAC SHA-256 (`HS256`), RFC 7518 §3.2 mandates a minimum key length equal to or greater than the hash output (32 bytes / 256 bits).

To generate a cryptographically strong secret for production:
```bash
# Generate 32 cryptographically secure random bytes as a 64-character hexadecimal string:
openssl rand -hex 32

# Or using Python secrets module:
python -c "import secrets; print(secrets.token_hex(32))"
```

### Rotation Strategy
1. Introduce support for dual-key verification before switching issuance keys (key transition period).
2. Issue new tokens with the new secret while allowing verification with previous secret until TTL expiration.
3. Retire the old secret once maximum token TTL has elapsed.

---

## 3. Issuer and Audience Configuration

In federated or multi-service deployments, configure explicit issuer and audience boundaries:
- `JWT_ISSUER`: e.g. `https://auth.kognisync.com`
- `JWT_AUDIENCE`: e.g. `kognisync-booking-service`

When set, the decoder enforces:
1. `iss` claim is present and strictly matches `JWT_ISSUER`.
2. `aud` claim is present and strictly matches `JWT_AUDIENCE`.
3. Discrepancies raise `jwt.InvalidIssuerError` or `jwt.InvalidAudienceError`, resulting in HTTP 401 Unauthorized with standard `WWW-Authenticate` headers.

---

## 4. Internal API Key & Operational Endpoint Protection

Operational endpoints trigger background sweeps or disclose cluster reliability metrics:
- `POST /api/v1/holds/expire` (Sweep expired holds and release inventory)
- `GET /api/v1/reliability/invariant-check` (Audit capacity invariant: `booked_units + held_units <= total_units`)

### Protection Rules
1. **Header Requirement**: Callers must supply `X-Internal-Key: <secret>`.
2. **Constant-Time Comparison**: Evaluated using `secrets.compare_digest` to prevent side-channel timing attacks.
3. **Fail-Closed Semantics**: If `INTERNAL_API_KEY` is empty or unset in `production`, endpoints immediately deny access with HTTP 403 Forbidden.
4. **Log Redaction**: Key values are never logged; failed access attempts log warnings with client IP without logging the submitted header value.

---

## 5. Demo-Token Restrictions & Development Mode Isolation

For seamless developer experience and frontend demonstration, KogniSync provides `POST /api/v1/auth/demo-token`.

### Production Safeguards
1. **Strict Production Disabling**: If `ENVIRONMENT == "production"`, `POST /api/v1/auth/demo-token` returns `404 Not Found` (endpoint completely unexposed).
2. **Identity Whitelisting**: Refuses arbitrary user identities. Only designated demo accounts (`usr_demo_*`) can receive tokens. Requests specifying arbitrary user IDs (e.g. `usr_test_alice`) return `403 Forbidden`.
3. **Explicit Short TTL**: Demo tokens have an enforced TTL of 15 minutes (900 seconds) rather than persistent lifespans.
4. **Zero Ownership Bypass**: A demo token identifies the caller as `usr_demo_*`. It cannot be used to retrieve, cancel, or confirm holds and bookings created by other users; unowned lookups return `404 Not Found`.

---

## 6. Frontend Token Handling & Storage Limitations

### Current Local Development Model
- The frontend client (`frontend/src/api/client.ts`) stores the bearer token in browser `localStorage` under `kognisync_auth_token`.
- On API calls to `/holds` and `/bookings`, it injects `Authorization: Bearer <token>`.
- In development/demo mode, `ensureDemoToken()` requests a temporary demo token.
- If a server responds with HTTP 401, the client automatically purges `kognisync_auth_token` from `localStorage` to prevent looping on expired credentials.

### Storage Limitations & XSS Risks
> [!WARNING]
> Storing tokens in `localStorage` makes them accessible to JavaScript running within the page context. If the web application is compromised via Cross-Site Scripting (XSS), tokens can be extracted.

### Future Production Session Strategy (Roadmap)
For production deployments exposed to real users:
1. **HttpOnly SameSite Cookies**: Shift token delivery to `HttpOnly`, `Secure`, `SameSite=Strict` (or `Lax`) cookies, inaccessible to document scripts.
2. **CSRF Protection**: Pair session cookies with double-submit CSRF tokens or custom request headers (`X-Requested-With`) for state-modifying requests.
3. **OAuth2 / OIDC Authorization Code Flow with PKCE**: Replace local token generation with an enterprise Identity Provider (e.g. Google Cloud Identity, Auth0, Keycloak).

---

## 7. Deployment Checks & Safe Failure Behavior

### Application Startup Gate (`lifespan`)
During startup, FastAPI's `lifespan` context manager performs mandatory environment assertions:
```python
if settings.ENVIRONMENT == "production":
    if not settings.JWT_SECRET_KEY or len(settings.JWT_SECRET_KEY.strip()) < 32:
        raise RuntimeError("Startup aborted: JWT_SECRET_KEY must be configured with >= 32 characters in production.")
    if not settings.INTERNAL_API_KEY or len(settings.INTERNAL_API_KEY.strip()) < 16:
        raise RuntimeError("Startup aborted: INTERNAL_API_KEY must be configured in production.")
```
If misconfigured, container orchestration (e.g. Kubernetes, ECS, Docker Compose) fails health checks immediately, blocking traffic routing to misconfigured instances.

### Anti-Enumeration ID Protection
When an authenticated user requests a resource (hold or booking) owned by another user identity:
- The endpoint responds with **`404 Not Found`** rather than `403 Forbidden`.
- This ensures an attacker cannot probe sequential or UUID IDs to confirm whether resources exist.
