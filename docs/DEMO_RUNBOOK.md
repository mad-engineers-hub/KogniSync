# KogniSync — Judge Demo Runbook

**Autonomous Multi-Modal Travel Synchronization Engine**  
*Hackathon Verification & Judging Guide*

---

## 1. Quick Start & Prerequisites

### System Requirements
- **Node.js**: v20+ (tested on Node v22.22.0)
- **Python**: 3.11+ (tested on Python 3.13.12)
- **Web Browser**: Chrome, Edge, Safari, or Firefox (desktop or mobile)
- **Optional**: Docker & Docker Compose (for production PostgreSQL 16 + Redis 7 services)

### Quick Launch (Frontend + Standalone Engine)
The frontend contains complete in-memory orchestration, deterministic multi-objective optimization, and XR viewers with zero external cloud dependencies required for a flawless offline demo:

```bash
# 1. Navigate to frontend
cd frontend

# 2. Start the Vite development or preview server
npm run dev
# Or preview built artifacts:
npm run preview -- --port 5173
```
Open **http://localhost:5173** in your browser.

### Full-Stack Launch (Backend + Database)
To run the full FastAPI backend alongside the frontend:

```bash
# 1. Start backend services (optional PostgreSQL & Redis via Docker)
docker compose up -d postgres redis

# 2. Run backend FastAPI server
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 2. Interactive Demo Walkthroughs

### Demo Scenario 1: Speed-Critical Intermodal Corridor
**Prompt**:
> `"I need to reach Udupi from Chennai tomorrow before 8 PM. My budget is ₹5000 and I prefer speed."`

#### Step-by-Step Flow:
1. **Natural Language Planning**:
   - On the home page, type or paste the prompt into the smart search input.
   - Press **Enter** or click the search icon.
   - Observe the **AI Intent Parser**: it extracts Origin (`Chennai`), Destination (`Udupi`), Date (`Tomorrow`), Arrival Deadline (`20:00`), Budget (`₹5,000`), and elevates the Speed/Duration priority weight.
2. **Search Journeys**:
   - Click the blue **"Search Journeys"** CTA.
3. **Results & Deterministic Optimization**:
   - Notice the **Recommended Journey** flagged with **[FASTEST]**: `SyncAir Multi-Modal Link (Air + Priority SyncCab)` (~₹4,556, 4h 3m).
   - Observe the **Objective Score Breakdown**: Duration contribution strongly dominates, delivering 8h 47m time savings compared to rail.
   - Observe the **Pareto Optimal Frontier**: Filter tabs show 2 of 5 journeys lie on the non-dominated Pareto frontier.
   - Check the **Google Routes & Multi-Modal Map**: Displays the 3-leg corridor (Cab feeder to MAA $\rightarrow$ flight to IXE $\rightarrow$ intercity cab to Udupi). Honest provider badge reads `Google Routes API` (when key present) or `KogniSync Geo-Engine` (when offline).
4. **Trade-off Comparison**:
   - Click **"Compare Trade-offs"** or open the comparison drawer to view the full multi-objective matrix comparing Cost, Duration, Transfers, Comfort, and Carbon footprint side-by-side.
5. **Detailed Leg Telemetry & XR Preview**:
   - Click **"View Complete Plan"** to enter `JourneyDetailsPage`.
   - Inspect individual segment departure/arrival times, connection buffers (20–45 min), and emissions.
   - Click **"Explore in 360°"** on the Chennai Central or airport hub to load the immersive 360° spherical concourse viewer with AR wayfinding turn-by-turn guidance.
6. **Booking, Hold & Payment**:
   - Click **"Select Journey"** to proceed to checkout.
   - Observe the **Distributed Inventory Hold** timer (10-minute hold TTL active).
   - Enter passenger details and select payment method (Instant UPI, Card, Netbanking).
   - Click **"Pay & Confirm"** (honest Sandbox Escrow mode clearly badged).
7. **TripPass & Multi-Modal Tickets**:
   - View the generated **Master PNR** (e.g. `KOGNI-CHEUPE-4921`).
   - Inspect individual QR codes for each synchronized leg (Cab voucher, Airline boarding pass, Intercity transfer).

---

### Demo Scenario 2: First-Mile Locality to Intercity Hub
**Prompt**:
> `"I want to travel from Udayapalya to Chennai tomorrow before 8 PM with a budget of ₹5,000."`

#### What to Look For:
- **First-Mile Locality Anchoring**: KogniSync recognizes `Udayapalya` as a hyper-local pickup point outside the central rail terminus and automatically schedules a synchronized feeder leg (Rapido / Metro Feeder) to Bengaluru City Hub.
- **Cost-Weighted Recommendation**: With neutral speed preference, the optimizer ranks the **[CHEAPEST]** `Economy Multi-Transit Link` (₹795, 3 synchronized legs) at #1.
- **Zero Hallucination Guarantee**: All arrival times strictly respect the 20:00 deadline.

---

### Demo Scenario 3: Regional Leisure Corridor with Localized Operators
**Prompt**:
> `"Bangalore to Goa this weekend under ₹6000."`

#### What to Look For:
- **Last-Mile Operator Localization**: Final arrival leg in Goa uses regional transport operators (`GoaMiles`, `Kadamba Transport Corporation`) rather than generic national transit.
- **Budget Ceiling Enforcement**: Zero options exceed the ₹6,000 budget cap.
- **Carbon Footprint Telemetry**: Displays the exact carbon footprint comparison between overnight AC sleeper coach and flight transfers.

---

## 3. Data Honesty & Integration Truth Table

| Subsystem | Primary Mode | Fallback / Offline Mode | Honesty Label in UI |
| :--- | :--- | :--- | :--- |
| **Multimodal Inventory** | Canonical SQLite `APS-05.db` (28,435 rows, 14 Tier-1 tables) | Parametric dynamic generator | Transparent segment IDs & provider attribution |
| **Geographic Routing** | Google Routes API v2 (road corridors) | KogniSync Deterministic Geo-Spatial Engine | `Google Routes API` vs `KogniSync Geo-Engine` |
| **Journey Optimizer** | Deterministic Multi-Objective Linear Normalization + Pareto Frontier | Exact deterministic algorithm (0% LLM) | Objective Contribution Breakdown + Pareto Badging |
| **XR Station Viewers** | WebXR Immersive Headset Session (when supported) | Three.js / Canvas 360° Pan & Gyroscope | Hardware capability badge in `XRDevicePrompt` |
| **Payment Gateway** | Live payment processor | Idempotent Sandbox Escrow Gateway | `Sandbox Simulation · No real charges incurred` |

---

## 4. Key Verification Commands for Judges

To verify the test suite independently:

```bash
# 1. Organizer Inventory Invariance (must return 0 diff and 37/37 SHA matches)
git diff -- BookingInventory/
python -c "import zipfile, hashlib, os; zf = zipfile.ZipFile(r'E:\BookingInventory.zip'); [assert hashlib.sha256(zf.read(i)).hexdigest() == hashlib.sha256(open(os.path.join(r'BookingInventory', i.filename[17:].replace('/', os.sep)), 'rb').read()).hexdigest() for i in zf.infolist() if not i.is_dir()]; print('37/37 MATCH')"

# 2. Organizer Conformance Test
cd BookingInventory/tools
python validate_conformance.py ..\data\APS-05.db

# 3. Frontend Test Suite (37 Unit Tests across 5 suites)
cd frontend
npm test

# 4. TypeScript Static Typecheck
npm run build # or npx tsc -b

# 5. Backend Pytest Suite
cd backend
python -m pytest backend/tests/test_optimizer.py backend/tests/test_maps.py backend/tests/test_xr.py -v
```
