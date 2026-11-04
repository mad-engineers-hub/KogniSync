# KogniSync — Focused Architecture Audit (M1)

**Audit Target**: KogniSync Autonomous Multimodal Travel Synchronization Engine  
**Working Directory**: `E:\KogniSync\KogniSync`  
**Git Baseline**: Commit [`d57b528`](https://github.com/mad-engineers-hub/KogniSync/commit/d57b528) on branch `main`  
**Audit Scope**: Architecture, Service Boundaries, API Contracts, Database & Migration Strategy, Developer Experience  
**Date**: November 2026  
**Auditor**: Lead Systems Architect  

---

## A. Executive Summary

### Overall Architecture Assessment
KogniSync demonstrates an exceptionally high baseline of engineering quality for a hackathon-originated system. The codebase has cleanly separated modular layers (FastAPI + SQLAlchemy 2.0 Async on the backend, React 19 + TypeScript + TanStack Query + Tailwind CSS v4 on the frontend), adheres to strict data immutability standards for the organizer package (`BookingInventory/`), and features mathematically sound, deterministic algorithms for multimodal optimization and spatial wayfinding.

The project is now transitioning from a rapid-prototype milestone into a durable, long-term engineering portfolio and product foundation. The architectural challenge is not poor code quality—the code is readable, strongly typed, and well-tested—but rather **architectural asymmetry created by hackathon speed**, where client-side offline resilience led to significant business logic (journey synthesis, scheduling, and pricing) residing inside the frontend rather than the backend.

### What is Already Well Designed
- **Zero-LLM Deterministic Optimizer**: The multi-objective scoring formulation (convex normalized combination + Pareto non-dominated vector sorting) is transparent, 100% reproducible, and mathematically rigorous.
- **Organizer Data Immutability**: `BookingInventory/` (14 Tier-1 tables, 28,435 rows, schemas, enums, and tools) is 100% byte-for-byte identical to the organizer release (`E:\BookingInventory.zip`), verified by SHA-256 invariance checks.
- **Provider-Agnostic Spatial Engine**: Clean abstraction for route enrichment that dynamically uses Google Routes API v2 when configured and gracefully falls back to deterministic spherical arc geometry when offline.
- **Repository Concurrency Design**: Data access repositories (`HoldRepository`, `InventoryRepository`) correctly employ SQLAlchemy 2.0 `select(...).with_for_update()`, nested savepoints (`begin_nested()`), and idempotency lookups.
- **Frontend Developer Experience & Performance**: Zero-heap memory exhaustion (Rayon-tuned Vite 8 building in ~1.2s), responsive viewports with 0px horizontal overflow, and comprehensive browser automation suites.

### Most Important Architectural Risks
1. **Frontend-Dominated Business Logic**: Core journey orchestration, schedule generation, and leg pricing are executed inside `frontend/src/api/orchestrationEngine.ts` (~984 lines) rather than by the FastAPI backend.
2. **Missing Core Backend Routes**: The frontend contains client methods for `/api/v1/journeys/search`, `/api/v1/holds`, `/api/v1/bookings`, `/api/v1/payments/process`, and `/api/v1/trips/{tripId}`, but none of these routes are implemented or registered in `backend/app/main.py`. The frontend silently falls back to local simulation.
3. **API Path & Contract Inconsistencies**: Route prefix mismatches (e.g. `/api/ai/...` vs `/api/v1/...`), route path typos (frontend requests `api/v1/routes/enrich` while backend exposes `/api/v1/maps/enrich`), and field-casing mismatches (`snake_case` in Pydantic vs `camelCase` in TypeScript).
4. **Destructive Database Initialization Without Alembic**: `scripts/init_db.py` executes `DROP SCHEMA public CASCADE` on every invocation. No Alembic migration environment is initialized, preventing non-destructive schema evolution.
5. **Underutilized Redis Infrastructure**: Redis 7 is running in Docker and checked in health endpoints, but distributed locks, session caching, and hold TTL timers are not actively backed by Redis.

---

## B. Current Architecture

### System Context & Data Flow

```mermaid
flowchart TD
    subgraph Client ["Frontend (React 19 + TypeScript)"]
        UI["UI Pages & Viewers\n(HomePage, ResultsPage, DetailsPage, XRViewer)"]
        Context["TravelRequestContext\n(URL Sync & Query State)"]
        APIClient["API Client Layer\n(client.ts with USE_MOCK_FALLBACK)"]
        ClientEngine["Client Orchestration Engine\n(orchestrationEngine.ts ~984 lines)"]
        ClientOpt["Client Deterministic Optimizer\n(utils/optimizer.ts)"]
        
        UI --> Context
        Context --> APIClient
        APIClient -- "Offline Fallback" --> ClientEngine
        ClientEngine --> ClientOpt
    end

    subgraph Gateway ["Backend Gateway (FastAPI 0.115)"]
        CORS["CORS Middleware"]
        AIRoute["/api/ai/parse-travel-intent"]
        MapsRoute["/api/v1/maps/enrich"]
        OptRoute["/api/v1/optimizer/optimize"]
        XRRoute["/api/v1/xr/*"]
        HealthRoute["/health*"]
        
        APIClient -- "Live HTTP" --> Gateway
    end

    subgraph Services ["Backend Service Layer"]
        GeminiService["Gemini AI Service\n(gemini.py)"]
        MapsService["Maps Routing Service\n(Google Routes + Fallback)"]
        OptService["Journey Optimizer Service\n(Pareto + Normalization)"]
        XRService["XR Spatial Service\n(Concourse + Wayfinding)"]
        
        AIRoute --> GeminiService
        MapsRoute --> MapsService
        OptRoute --> OptService
        XRRoute --> XRService
    end

    subgraph Persistence ["Persistence & Repositories"]
        Repos["SQLAlchemy 2.0 Repositories\n(Hold, Booking, Inventory, Payment)"]
        AsyncEngine["AsyncSessionLocal (asyncpg)"]
        PG[("PostgreSQL 16 (Port 5434)\nkognisync_db")]
        Redis[("Redis 7 (Port 6380)\nIdle / Health Only")]
        SQLite[("Organizer SQLite (Read-Only)\nAPS-05.db")]
        
        Repos --> AsyncEngine --> PG
        XRService & ConformanceValidator -. "Read-Only" .-> SQLite
    end
```

### Component Structure Overview
- **Backend Directory**:
  - `backend/app/api/routes/`: Route controllers (`ai.py`, `health.py`, `maps.py`, `optimizer.py`, `xr.py`).
  - `backend/app/services/`: Core business logic packages (`ai/`, `maps/`, `optimizer/`, `xr/`).
  - `backend/app/repositories/`: Persistence abstraction for PostgreSQL (`booking_repository.py`, `hold_repository.py`, `inventory_repository.py`, `payment_repository.py`, `user_repository.py`).
  - `backend/app/db/models/`: SQLAlchemy declarative models reflecting the 14 Tier-1 tables.
- **Frontend Directory**:
  - `frontend/src/pages/`: Route-level pages (`HomePage`, `ResultsPage`, `DetailsPage`, `BookingPage`, `ConfirmationPage`, `XRExperiencePage`).
  - `frontend/src/components/`: Modular UI units (booking, details, map, planner, results, trip, xr).
  - `frontend/src/api/`: API integration and fallback mock engines (`client.ts`, `orchestrationEngine.ts`, `routes.ts`, `xr.ts`, `trips.ts`, `booking.ts`).
  - `frontend/src/utils/`: In-process business calculations (`optimizer.ts`, `travelUtils.ts`, `xrMatching.ts`).

---

## C. Findings

| ID | Area | Finding | Severity | Evidence | Recommendation |
|:---|:---|:---|:---:|:---|:---|
| **ARCH-01** | Architecture | **Core Journey Orchestration & Pricing Resides in Frontend**: All multimodal candidate generation, hub snapping, connection buffer calculation, and pricing logic are implemented client-side. Backend has no `/api/v1/journeys/search` route. | **Critical** | [`frontend/src/api/orchestrationEngine.ts#L1-L984`](file:///E:/KogniSync/KogniSync/frontend/src/api/orchestrationEngine.ts#L1-L984), [`frontend/src/api/journey.ts#L12`](file:///E:/KogniSync/KogniSync/frontend/src/api/journey.ts#L12) | Port `orchestrationEngine.ts` into a FastAPI `JourneyOrchestrationService` reading canonical routes from `APS-05.db` / PostgreSQL. Keep client engine strictly as an offline fallback. |
| **ARCH-02** | Optimizer | **Dual-Engine Divergence Risk**: Full multi-objective scoring and Pareto analysis are duplicated in both Python and TypeScript. Subtle heuristics (e.g. `calibrateWeights` in TS) risk divergence. | **High** | [`backend/app/services/optimizer/service.py#L14-L103`](file:///E:/KogniSync/KogniSync/backend/app/services/optimizer/service.py#L14-L103) vs [`frontend/src/utils/optimizer.ts#L425-L528`](file:///E:/KogniSync/KogniSync/frontend/src/utils/optimizer.ts#L425-L528) | Establish the backend optimizer as authoritative for live searches; use frontend optimizer strictly as offline fallback when `USE_MOCK_FALLBACK=true`. |
| **ARCH-03** | API Contract | **Route Path Mismatch on Maps Enrichment**: Frontend calls `api/v1/routes/enrich`, but backend registers `/api/v1/maps/enrich`. The call consistently fails with HTTP 404 and falls back to client geometry. | **High** | Frontend: [`frontend/src/api/routes.ts#L119`](file:///E:/KogniSync/KogniSync/frontend/src/api/routes.ts#L119)<br>Backend: [`backend/app/api/routes/maps.py#L6-L22`](file:///E:/KogniSync/KogniSync/backend/app/api/routes/maps.py#L6-L22) | Align frontend endpoint to `/api/v1/maps/enrich` (or add an alias redirect route in FastAPI). |
| **ARCH-04** | Database | **Destructive Database Initialization Without Alembic Migrations**: `scripts/init_db.py` executes `DROP SCHEMA public CASCADE`. There are no versioned migrations, making it impossible to evolve schema in production. | **High** | [`scripts/init_db.py#L41-L47`](file:///E:/KogniSync/KogniSync/scripts/init_db.py#L41-L47) | Initialize Alembic with an async migration environment. Separate immutable reference schemas from application operational schemas. |
| **ARCH-05** | API Contract | **Inconsistent API Path Versioning**: Route prefixes are fragmented: `/api/ai/parse-travel-intent` (unversioned), `/health*` (root), `/api/v1/maps/*`, `/api/v1/xr/*`, `/api/v1/optimizer/*`. | **Medium** | [`backend/app/api/routes/ai.py#L6`](file:///E:/KogniSync/KogniSync/backend/app/api/routes/ai.py#L6) vs [`backend/app/api/routes/maps.py#L6`](file:///E:/KogniSync/KogniSync/backend/app/api/routes/maps.py#L6) | Prefix all operational API routers under `/api/v1/` (`/api/v1/ai/...`). Keep root `/health` for container orchestration. |
| **ARCH-06** | API Contract | **Pydantic vs TypeScript Serialization Casing**: Backend Pydantic models serialize fields in `snake_case` (e.g., `recommended_journey_id`), while TypeScript interfaces expect `camelCase` (`recommendedJourneyId`). | **Medium** | [`backend/app/services/optimizer/schemas.py#L78-L83`](file:///E:/KogniSync/KogniSync/backend/app/services/optimizer/schemas.py#L78-L83) vs [`frontend/src/types/optimizer.ts#L53-L59`](file:///E:/KogniSync/KogniSync/frontend/src/types/optimizer.ts#L53-L59) | Configure Pydantic `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` to serialize camelCase JSON over the wire. |
| **ARCH-07** | Infrastructure| **Idle Redis Service**: Redis container runs on port 6380, is tested in `/health/redis`, but no business service actually uses it for caching, distributed locks, or hold TTLs. | **Medium** | [`docker-compose.yml#L22-L35`](file:///E:/KogniSync/KogniSync/docker-compose.yml#L22-L35), [`backend/app/api/routes/health.py#L32-L42`](file:///E:/KogniSync/KogniSync/backend/app/api/routes/health.py#L32-L42) | Connect Redis to handle distributed hold TTL countdowns (`SETEX hold:{id} 600`) and API response caching for travel requests. |
| **ARCH-08** | Repositories | **Orphaned Domain Repositories**: `HoldRepository`, `BookingRepository`, `InventoryRepository`, and `PaymentRepository` are implemented and tested, but are never exposed via FastAPI services or routes. | **Medium** | [`backend/app/repositories/booking_repository.py`](file:///E:/KogniSync/KogniSync/backend/app/repositories/booking_repository.py), [`backend/app/repositories/hold_repository.py`](file:///E:/KogniSync/KogniSync/backend/app/repositories/hold_repository.py) | Wire these repositories into a `BookingService` and expose endpoints for `/api/v1/holds` and `/api/v1/bookings`. |
| **ARCH-09** | Testing | **Host Docker Dependency for Repository Tests**: 17 backend tests in `test_repositories.py`, `test_models.py`, and `test_db_initialization.py` fail unless external PostgreSQL and Redis are actively running. | **Low** | [`backend/tests/test_repositories.py`](file:///E:/KogniSync/KogniSync/backend/tests/test_repositories.py) | Add `pytest-asyncio` sqlite-memory fallback or testcontainers fixture for zero-dependency CI test execution. |

---

## D. Architecture Decisions & Recommendations

### 1. Optimizer Ownership
- **Decision**: The **Backend FastAPI service** (`JourneyOptimizerService`) must be authoritative for all production journey ranking, scoring, and explanations.
- **Role of Frontend Implementation**: Retain `frontend/src/utils/optimizer.ts` purely as an **offline client fallback** when `USE_MOCK_FALLBACK=true` (e.g. demo mode or zero-connectivity environments).
- **Smallest Safe Improvement**:
  1. Add camelCase serialization to `backend/app/services/optimizer/schemas.py`.
  2. In `frontend/src/api/journey.ts`, have `searchJourneys` delegate optimization to `POST /api/v1/optimizer/optimize` over HTTP, falling back to `utils/optimizer.ts` on network error.

### 2. Service and Repository Boundaries
- **Route Handlers**: Must be thin controllers responsible strictly for request validation, invoking a domain service, and translating domain exceptions into appropriate HTTP status codes.
- **Domain Services**: Encapsulate end-to-end business use cases (e.g., `JourneyOrchestrationService`, `BookingHoldService`). Services manage transaction boundaries and coordinate multiple repositories.
- **Repositories**: Encapsulate persistence queries only. Must never call `session.commit()` or `session.rollback()`. Use nested savepoints (`begin_nested()`) when handling idempotency conflicts.

### 3. Transport Provider Architecture
- Standardize all transit providers (Air, Rail, Bus, Cab, Metro) behind a unified Python interface:
  ```python
  class TransportProvider(ABC):
      @abstractmethod
      async def search_legs(self, origin: Location, destination: Location, travel_date: date) -> list[TransitLeg]: ...
  ```
- A `TransportProviderRegistry` discovers and queries providers concurrently via `asyncio.gather()`, with timeout protection per provider.

### 4. Booking Transaction Ownership
- The backend must own the distributed hold and checkout state machine:
  $$\text{DRAFT} \longrightarrow \text{HELD (10m TTL in Redis)} \longrightarrow \text{CONFIRMED} \;\; \text{or} \;\; \text{EXPIRED}$$
- Concurrency protection: Use PostgreSQL `SELECT ... FOR UPDATE` on `inventory_calendar` with invariant checking:
  $$\text{booked\_units} + \text{held\_units} \le \text{total\_units}$$
- Idempotency keys must be enforced at both repository level (unique constraint) and Redis level (atomic acquire).

### 5. API Contract Consistency
- **Base URL & Versioning**: All production endpoints must reside under `/api/v1/`. Health checks remain at `/health`.
- **Field Casing**: Standardize on `camelCase` for all JSON payloads over HTTP by configuring Pydantic v2 `to_camel` alias generators.
- **Date/Time Standard**: ISO 8601 strings with timezone offset (`YYYY-MM-DDTHH:MM:SSZ`).
- **Currency**: Explicit `currency: "INR"` with integer or 2-decimal float values.

### 6. Database Migrations Strategy
- Introduce **Alembic** (`backend/alembic/`) targeting `DATABASE_URL`.
- Maintain clear schema separation:
  - `canonical_*` or reference tables seeded from `BookingInventory/data/schema.sql` (read-only reference).
  - `app_*` operational tables (user profiles, search logs, holds, booking state) managed and versioned exclusively via Alembic migrations.

### 7. Error Handling & Structured Logging
- Implement a global FastAPI exception handler returning a standardized RFC 7807 problem details envelope:
  ```json
  {
    "error": {
      "code": "INSUFFICIENT_INVENTORY",
      "message": "Only 1 unit available for selected rail leg.",
      "details": { "segment_id": "seg-102", "available": 1, "requested": 2 }
    }
  }
  ```
- Configure structured JSON logging with correlation IDs (`X-Correlation-ID`) propagated from frontend through backend logs.

---

## E. Prioritized Action Plan

### Milestone 1: API Contract Harmonization & Route Alignment
- **Objective**: Eliminate all silent 404 fallbacks and harmonize naming, paths, and serialization between frontend and backend.
- **Target Files**:
  - `backend/app/api/routes/ai.py` (prefix `/api/v1/ai`)
  - `frontend/src/api/routes.ts` (fix endpoint to `/api/v1/maps/enrich`)
  - `backend/app/services/optimizer/schemas.py` (add `alias_generator = to_camel`)
  - `backend/app/services/maps/schemas.py` (add `alias_generator = to_camel`)
  - `frontend/src/api/client.ts`
- **Expected Benefit**: Live backend communication functions immediately without silent 404 catches; Google Routes live enrichment reaches the frontend seamlessly.
- **Risk**: Very low (client fallbacks remain in place).
- **Estimated Effort**: 3–4 hours.

### Milestone 2: Backend Journey Orchestration & Booking API
- **Objective**: Migrate multimodal journey composition and inventory booking endpoints to the FastAPI backend.
- **Target Files**:
  - `backend/app/services/journey_orchestration.py` (new service ported from `orchestrationEngine.ts`)
  - `backend/app/api/routes/journeys.py` (new route for `/api/v1/journeys/search`)
  - `backend/app/api/routes/booking.py` (new route for `/api/v1/holds` and `/api/v1/bookings`)
  - `backend/app/main.py` (register new routers)
  - `backend/app/repositories/` (connect existing hold & booking repositories)
- **Expected Benefit**: Complete centralization of business logic; mobile apps and external consumers can access journey search and booking directly.
- **Risk**: Medium (requires comprehensive parity tests with existing TypeScript engine).
- **Estimated Effort**: 6–8 hours.

### Milestone 3: Database Migrations & Redis Hold TTL
- **Objective**: Establish non-destructive schema evolution with Alembic and activate Redis for distributed holds.
- **Target Files**:
  - `backend/alembic/` (initialize Alembic async migration environment)
  - `backend/alembic.ini`
  - `backend/app/services/hold_service.py` (connect Redis async client for 10-minute TTL expiry)
  - `scripts/init_db.py` (refactor to non-destructive schema setup)
- **Expected Benefit**: Schema can safely evolve in staging/production without wiping database tables; Redis handles hold expiry automatically.
- **Risk**: Low-Medium.
- **Estimated Effort**: 3–4 hours.

---

## F. What NOT to Change

To protect working features and maintain hackathon compliance, the following systems must **NOT** be refactored or destabilized:

1. **`BookingInventory/` Directory**: Must remain 100% byte-for-byte immutable. Never reformat, move, or rename organizer files.
2. **Deterministic Optimizer Formulations**: The mathematical normalization ($[0.0, 1.0]$ bounds clamping), convex scoring weights, and vector Pareto dominance checks in `scoring.py` / `pareto.py` are sound and must not be altered.
3. **Zero-LLM Decision Rule**: Never allow an LLM to perform scoring, rank journeys, determine winners, or make booking decisions.
4. **Provider-Agnostic Google Routes Layer**: The abstraction in `backend/app/services/maps/` and `frontend/src/api/routes.ts` with local spherical geometry fallback is clean, resilient, and should be preserved.
5. **XR Concourse & AR Wayfinding**: Organizer schema compliance in `backend/app/services/xr/` and the Three.js spherical viewer in `frontend/src/components/xr/` are working flawlessly.
6. **Frontend Offline Client Fallbacks**: Always preserve `USE_MOCK_FALLBACK` code paths so the frontend can function independently for demos or in environments without local backend infrastructure.

---

## G. Final Assessment

| Dimension | Rating | Commentary |
|:---|:---:|:---|
| **Architecture Quality** | **Good (7.5 / 10)** | Clean separation of concerns, strong domain models, excellent mathematical rigor. Held back only by client-side orchestration asymmetry. |
| **Maintainability** | **Good (7.0 / 10)** | Highly readable, well-commented, strongly typed, and formatted. Needs API contract unification to reduce duplicate logic. |
| **Extensibility** | **Good (7.5 / 10)** | Pluggable route providers, modular XR scenes, and clean repository pattern make adding new transport modes straightforward. |
| **Developer Experience** | **Good (8.0 / 10)** | Sub-2-second frontend builds, comprehensive tests, instant offline capability, and transparent logging. |

### Top 5 Recommended Improvements
1. **Fix API Route Typos & Mismatches**: Resolve `/api/v1/routes/enrich` $\rightarrow$ `/api/v1/maps/enrich` and unversioned `/api/ai/` routes immediately.
2. **Harmonize JSON Serialization Casing**: Add `alias_generator = to_camel` to Pydantic schemas so TypeScript receives native `camelCase` properties.
3. **Port Journey Orchestration to Backend**: Move the 984-line `orchestrationEngine.ts` into a FastAPI service to establish backend authority for travel search.
4. **Implement Alembic Migrations**: Replace `DROP SCHEMA public CASCADE` in `init_db.py` with versioned, non-destructive migrations.
5. **Activate Redis for Hold TTLs**: Utilize the running Redis instance for distributed locks and automatic 10-minute hold expiry keys.

### The Single Best Next Implementation Task
> **Milestone 1 — API Contract Harmonization**: Fix the route mismatch on `/api/v1/maps/enrich`, standardize route prefixes under `/api/v1/`, and configure Pydantic with camelCase alias generation. This small, 3-hour task immediately unlocks live backend communication for maps and optimization with zero regression risk.

