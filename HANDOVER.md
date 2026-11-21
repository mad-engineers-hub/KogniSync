# KogniSync — Developer Handover & Engineering Guide

> **Target Audience:** Incoming Software Engineers, DevOps Engineers, and System Architects.  
> **Repository:** `https://github.com/mad-engineers-hub/KogniSync.git`  
> **Primary Branches:** `main` (production-ready trunk), `feature/kognisync-developer-handover` (handover integration)  
> **Canonical Database Checksum (APS-05.db):** `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A`

---

## 1. Executive Summary & Core Invariants

KogniSync is a **high-concurrency, multimodal travel orchestration and distributed booking platform** designed for real-world reliability, sub-second transaction guarantees, and transparent multimodal trip planning across Indian transport corridors.

The platform bridges:
1. **Distributed Concurrency-Safe Booking:** Distributed holds with Redis atomic Lua scripts, idempotency keys, saga line-item compensation, and strict inventory invariants (`booked + held <= total`).
2. **Door-to-Door Multimodal Journey Orchestration:** Dynamic Pareto optimization across 5 canonical travel archetypes (Fastest, Best Value, Cheapest, Greenest, Comfortable) connecting first-mile, trunk intercity corridors, and last-mile urban transit.
3. **Operational Timetable Integrity & Downstream Uncertainty Propagation:** Grounded trunk schedules (e.g., Karnataka Express 12627), official railway operational regulations (SWR PR No. 1404), headway-modeled urban transit connections, and transparent interval propagation (e.g. 09:21–10:56 IST arrival windows).
4. **Intelligent Map Viewport & Route Visualization:** High-performance responsive Leaflet maps with programmatic zoom persistence (`MapViewportManager`), Great-Circle/Valhalla road waypoints, and zero Null-Island coordinate leakage.

### 🛑 Mandatory Organizer Data Immutability Contract
The directory `BookingInventory/` contains the canonical reference dataset, schema definitions, and SQLite database (`BookingInventory/data/APS-05.db`).
- **RULE:** `BookingInventory/` is **100% IMMUTABLE AND READ-ONLY**.
- **NEVER** modify, write to, reformat, migrate, or delete files inside `BookingInventory/`.
- Ensure `APS-05.db` SHA-256 remains strictly: `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A`.

---

## 2. Architectural Evolution (Milestone Roadmap)

| Milestone | Key Capabilities Delivered |
| :--- | :--- |
| **M1** | Distributed booking core, Redis atomic holds, saga compensation coordinator, read-only canonical APS-05 inventory engine. |
| **M2** | Strict idempotency middleware, circuit breakers, self-healing hold reconcilers, and Prometheus observability metrics. |
| **M3.1–M3.4** | Multimodal journey composition, Pareto multi-objective optimization, optional Valhalla OSM routing container profile, client-side fallback routes. |
| **M3.5–M3.9** | Disruption intelligence engine, live GTFS-RT feed activation, SSRF IP-pinned HTTP transport, and strict transit identifier matching. |
| **M4.0.1–M4.0.5** | Dynamic map synchronization, responsive Leaflet layout sizing, Great-Circle route fallbacks, and Null-Island coordinate guards. |
| **M4.1.1** | External airport gateway city semantics (e.g., Udupi traveler origin paired with Mangalore IXE airport location), ungrounded vehicle numbers undefined. |
| **M4.1.2** | `MapViewportManager` architecture, user zoom/pan persistence across React re-renders and polling updates, intentional fit lifecycle. |
| **M4.2 / UI-01.2** | Real timetable integration (12627 Karnataka Express), SWR PR 1404 regulation notices, downstream uncertainty propagation, past departure elimination. |

---

## 3. Technology Stack & Prerequisites

- **Frontend:** React 19, TypeScript 5.8, Vite 8, TailwindCSS 4, Lucide Icons, Leaflet / React-Leaflet.
- **Backend:** Python 3.11+ (tested on Python 3.13), FastAPI, Pydantic v2, SQLAlchemy 2.0 (asyncio), AnyIO.
- **Infrastructure Containers:** Docker & Docker Compose:
  - PostgreSQL 16 (`pgvector/pgvector:pg16`) on host port `5434`
  - Redis 7 (`redis:7-alpine`) on host port `6380` (`${REDIS_PORT:-6380}:6379`)
  - *Optional:* Valhalla OSM Routing Engine on host port `8002`

---

## 4. Quick Start & Service Execution

### Step 1: Clone and Set Up Environment
```bash
git clone https://github.com/mad-engineers-hub/KogniSync.git
cd KogniSync

# Start infrastructure containers
docker compose up -d

# Verify container readiness
docker ps --filter "name=kognisync"
```

### Step 2: Backend Setup
```bash
cd backend
python -m venv .venv

# Windows Powershell
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

# Run FastAPI development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Health checks:
- Application Health: `http://localhost:8000/health`
- Database Connectivity: `http://localhost:8000/health/db`
- Redis Connectivity: `http://localhost:8000/health/redis`

### Step 3: Frontend Setup
```bash
cd frontend
npm install

# Start Vite development server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 5. Automated Verification & Quality Gates

### Backend Test Suite
Run the 14-test journey orchestration suite (100% hermetic, zero mock leakage):
```bash
cd backend
pytest tests/test_journey_orchestration.py -v
```
Run the full backend test suite:
```bash
pytest -v
```

### Frontend Test Suite & Build Verification
The frontend contains 18 comprehensive Vite SSR test suites testing optimization, routing, map persistence, and timetable feasibility:
```bash
cd frontend

# Run all 18 test suites
node scripts/runTests.mjs

# Typecheck with TypeScript Compiler
npx tsc -b

# Production bundle build
npm run build
```

---

## 6. Key Subsystems & Source Walkthrough

### A. Viewport Persistence Engine (`frontend/src/components/map/MapViewportManager.ts`)
Leaflet maps by default invoke `map.fitBounds()` unconditionally during data refreshes or component re-renders, causing disorienting map jumps when the user has panned or zoomed into an origin or transfer station.
- **Mechanism:** `MapViewportManager` tracks `userHasAdjusted`, suppressing programmatic re-centering during background polling or route geometry enrichment.
- **Intentional Fitting:** Programmatic centering triggers exclusively on initial journey load, explicit user route selection, or clicking "Fit Whole Route".

### B. Timetable Feasibility & Uncertainty Propagation (`frontend/src/utils/timezone.ts`)
- **Published Timetable Anchoring:** Commercial train services (e.g. 12627) are anchored to authoritative published departures (19:20 IST daily from KSR Bengaluru).
- **En-Route Regulations:** Date-specific railway circulars (e.g., SWR PR No. 1404) attach structured regulation notices without falsely asserting guaranteed terminal delays.
- **Downstream Window Propagation:** Connecting urban transit (Delhi Metro) accounts for train arrival bounds (09:00–10:30 IST), platform egress (15m), and frequency-based headway waits (0–5m), correctly projecting Rajiv Chowk arrival between 09:21 and 10:56 IST.

### C. Airport Gateway Semantics (`frontend/src/api/orchestrationEngine.ts`, `backend/app/services/journey/hubs.py`)
- For cities without local commercial airports (e.g. Udupi), the hub context assigns:
  `hasLocalAirport: false`, `isAirportGateway: true`, `airportGatewayCity: 'Mangalore'`, `airportHub.code: 'IXE'`.
- The traveller's origin/destination remains Udupi, while the flight endpoint is correctly grounded at Mangalore International Airport (IXE), linked via a 56.4km road transfer.

---

## 7. Operational Boundaries & Data Credibility Standards

1. **Provider-Live vs. Deterministic Estimates:**
   - Provider availability is categorized into `provider_live` (verified carrier API), `deterministic_estimate` (corridor speed and distance modeling), and `simulated` (synthetic test inventory).
   - Unverified flights or trains MUST NOT invent synthetic flight numbers (`vehicleNumber: undefined`) or fabricate artificial seat inventory (`remainingUnits: undefined`).
2. **Canonical APS-05 Isolation:**
   - Production operations must query `BookingInventory/data/APS-05.db` strictly via read-only connections. Write mutations belong solely to application databases (`kognisync_db`).

---

## 8. Git Safety & Contribution Guidelines

- **Never force push (`git push -f`)** to remote branches.
- **Never push directly to `main`**. All changes must land via feature branches and Pull Requests.
- **Never commit credentials, `.env` files, or local logs.**
- Always run `node scripts/runTests.mjs` and `pytest tests/test_journey_orchestration.py` before proposing commits.
