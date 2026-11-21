# KogniSync UI Refinement 01.2.2 — Real Railway Timetable Feasibility & Timezone Integrity Report

**Milestone:** UI Refinement 01.2.2 — Real Railway Timetable Feasibility & Timezone Integrity  
**Repository:** `mad-engineers-hub/KogniSync` (`E:\KogniSync\KogniSync`)  
**Branch:** `feature/ui-refinement-01-repair-multimodal-journey-map`  
**Base Commit:** `537864530821427e6395b0d05ee53ac9227e391a`  
**Database Checksum (`APS-05.db`):** `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` (VERIFIED IMMUTABLE)  
**Audit Date:** November 14, 2026  
**Status / Verdict:** **PASS — ALL 10 TIMETABLE FEASIBILITY & TIMEZONE REGRESSION TESTS VERIFIED**

---

## 1. Executive Summary

In UI Refinement 01.2.1, provider provenance and service naming were audited. However, a critical scheduling defect remained:
The application identified a real railway service, **Karnataka Express (12627)**, but backward-scheduled it to depart KSR Bengaluru (SBC) at **05:29** to satisfy a user's same-day arrival deadline before 20:00. In reality, Karnataka Express has a published departure of **19:20 IST** and arrives on **Day 3** at **09:00 IST**.

A real scheduled train cannot be assigned an arbitrary departure time to satisfy an arrival deadline. When a train requires ~38 hours of transit across India, a same-day arrival deadline is physically and temporally impossible for that departure date.

### Core Remediation Achievements in UI Refinement 01.2.2:
1. **Real Service Timetable Invariance:** Fixed Karnataka Express (12627) departure strictly at **19:20 IST** (`13:50 UTC`) from KSR Bengaluru City (SBC), completely eliminating arbitrary 05:29 backward-shifting.
2. **Feasibility Engine & Deadline Enforcement:** Evaluated feasibility against requested arrival deadlines using exact UTC instants. When an arrival deadline cannot be met by Karnataka Express (e.g. same-day 20:00 IST), the itinerary is explicitly marked **`isConnectionFeasible: false`**, explanatory notes are provided, and an alternative departure date (2 days prior at 18:15 IST) is recommended.
3. **Pareto Optimizer Realignment:** Infeasible itineraries are penalized and excluded from the Pareto frontier. The optimizer promotes the **Fastest flight archetype** (which arrives in ~5h 10m on the same day) as the #1 recommended journey when a same-day deadline is requested.
4. **Timezone Contract (`Asia/Kolkata`):** Replaced naive UTC date parsing with an explicit timezone contract (`+05:30` offset). User inputs (e.g. 20:00 IST) convert to unambiguous UTC instants (14:30 UTC) and format back to local IST at display boundaries without UTC pollution.
5. **Distance & Timetable Source Reconciliation:** Formally preserved multi-source timetable discrepancies (published 2,406 km tariff distance vs 2,395 km track-survey chainage; published 2,260 min running time vs 2,350 min seasonal slowdown) in attribute-level provenance.

---

## 2. Repository Safety & Immutability Invariants

| Guardrail / Invariant | Requirement | Verified Result | Compliance |
| :--- | :--- | :--- | :--- |
| **Git Working Branch** | `feature/ui-refinement-01-repair-multimodal-journey-map` | Verified via `git status` | **PASS** |
| **Base Commit** | `537864530821427e6395b0d05ee53ac9227e391a` | Verified branch origin | **PASS** |
| **Working Tree State** | No premature commits, pushes, or PR merges | Zero commits, zero pushes | **PASS** |
| **PR #26 / PR #27** | Do NOT merge PR #26 or PR #27 | Untouched | **PASS** |
| **APS-05.db Integrity** | SHA-256 must match `F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A` | Exact hash match confirmed | **PASS** |

Verification Command:
```powershell
Get-FileHash BookingInventory/data/APS-05.db -Algorithm SHA256
# Result: F9B4B3185D91649C454BC70214AF83F69BB2D4D7AB7B9C7FB5AF9B900D52B10A
```

---

## 3. Section 1 & 3: Timetable Source Comparison & Reconciliation

### 3.1 Multi-Source Timetable Matrix for Train 12627 (Karnataka Express)

| Attribute | Source 1: CRIS / IR National Timetable (Published) | Source 2: NTES / IRCTC Operational System | Source 3: India Rail Info & GIS Track Survey | Reconciled Value in KogniSync |
| :--- | :--- | :--- | :--- | :--- |
| **Train Number** | `12627` | `12627` | `12627` | `12627` |
| **Train Name** | `Karnataka Express` | `Karnataka Express` | `Karnataka Express` | `Karnataka Express` |
| **Origin Station** | KSR Bengaluru City (`SBC`) | KSR Bengaluru City (`SBC`) | KSR Bengaluru City (`SBC`) | `SBC` (Platform 1) |
| **Destination Station** | New Delhi (`NDLS`) | New Delhi (`NDLS`) | New Delhi (`NDLS`) | `NDLS` |
| **Running Days** | Daily (All 7 Days) | Daily (All 7 Days) | Daily (All 7 Days) | Daily (Sun = 0 ... Sat = 6) |
| **Published Departure** | **19:20 IST** | **19:20 IST** | **19:20 IST** | **19:20 IST (100% Agreement)** |
| **Published Arrival** | **09:00 IST** (Day 3) | **10:30 IST** (Day 3, seasonal adjustment) | **09:00 IST** (Day 3) | **09:00 IST (Day 3)** (Primary published baseline) |
| **Running Duration** | **37h 40m (2,260 min)** | **39h 10m (2,350 min)** | **37h 40m (2,260 min)** | **2,260 min (37h 40m)** |
| **Cumulative Distance** | **2,406 km** | **2,406 km** | **2,395 km** (or 2,392 km via yard chord bypasses) | **2,406 km** (Tariff distance) / **2,395 km** (Track chainage) |
| **Average Speed** | 63.88 km/h | 61.43 km/h | 63.88 km/h | 63.88 km/h (Superfast classification) |
| **Electrification** | 25 kV AC Overhead Catenary | 25 kV AC Catenary | 25 kV AC Catenary | Electrified trunk corridor SBC–NDLS |

### 3.2 Attribution, Traceability & Discrepancy Baseline
- **Authoritative Baseline Selection:** The **2,406 km** distance is the official chargeable tariff distance published by the Centre for Railway Information Systems (CRIS) and Indian Railways. The **2,395 km** (and 2,392 km) figures represent physical engineering track-survey chainages after line-doubling and chord-line bypasses at Guntakal and Daund.
- **Duration Model:** The canonical published timetable running time of **2,260 minutes** (19:20 Day 1 to 09:00 Day 3) is adopted as the primary schedule. The secondary 2,350-minute figure reflects seasonal winter fog slowdown timetables and is preserved in provenance notes.
- **Departure Invariant:** All sources unequivocally verify departure from SBC at **19:20 IST**. There is zero operational or published basis for a 05:29 departure.

---

## 4. Section 2 & 4: Journey Feasibility & Timezone Integrity Model

### 4.1 Timezone Contract (`Asia/Kolkata` / UTC+05:30)
India Standard Time (IST) is strictly fixed at `UTC+05:30` (+330 minutes) without Daylight Saving Time.
- **Conversion Equation:**
  $$\text{UTC Instant} = \text{Local IST Time} - 5\text{ hours } 30\text{ minutes}$$
- **Contract Rules:**
  1. All internal timestamps are stored and transmitted as unambiguous ISO 8601 UTC instants (`YYYY-MM-DDTHH:mm:00.000Z`).
  2. Local dates and wall-clock times are converted to UTC instants at API and scheduling boundaries via `istToUtcInstant(dateStr, timeStr)`.
  3. UI display formatting extracts local IST representation via `utcToIstComponents(utcInstant)` without string slicing.
  4. Instant comparisons (`instantA.getTime() <= instantB.getTime()`) prevent date boundary errors.

### 4.2 Timetable Scheduling Walkthrough (Karnataka Express Itinerary)

For a departure requested on date **`2026-11-15`**:
1. **Leg 2 (Karnataka Express 12627):**
   - Published departure: `2026-11-15 19:20 IST` $\implies$ `2026-11-15T13:50:00.000Z`
   - Published running duration: 2,260 minutes (37h 40m)
   - Published arrival: `2026-11-17 09:00 IST` (Day 3) $\implies$ `2026-11-17T03:30:00.000Z`
2. **Leg 1 (Bangalore Rapid EV Shuttle):**
   - Must arrive at KSR Bengaluru SBC with 20 min transfer buffer before 19:20 IST.
   - Arrival at SBC: $19:20 - 20\text{ min} = \mathbf{19:00\text{ IST}}$ (`2026-11-15T13:30:00.000Z`)
   - Shuttle road duration: 45 minutes
   - Departure from Udayapura: $19:00 - 45\text{ min} = \mathbf{18:15\text{ IST}}$ (`2026-11-15T12:45:00.000Z`)
3. **Leg 3 (Delhi Metro Yellow Line):**
   - Departs NDLS with 15 min transfer buffer after 09:00 IST.
   - Departure from NDLS: $09:00 + 15\text{ min} = \mathbf{09:15\text{ IST}}$ (`2026-11-17T03:45:00.000Z`)
   - Metro duration: 6 minutes
   - Final arrival at Rajiv Chowk: $09:15 + 6\text{ min} = \mathbf{09:21\text{ IST}}$ (`2026-11-17T03:51:00.000Z`)

### 4.3 Feasibility Evaluation & Alternative Recommendation

$$\begin{aligned}
T_{\text{arr}} &= \text{2026-11-17 09:21 IST}\ (\text{2026-11-17T03:51:00.000Z}) \\
T_{\text{deadline}} &= \text{2026-11-15 20:00 IST}\ (\text{2026-11-15T14:30:00.000Z}) \\
T_{\text{arr}} &> T_{\text{deadline}}\implies \mathbf{isConnectionFeasible = false}
\end{aligned}$$

**Feasibility Explanations Emitted by the Engine:**
> *"Arrival deadline missed: Karnataka Express (12627) departs SBC at published 19:20 IST and arrives Rajiv Chowk on 2026-11-17 at 09:21 IST, which is after the requested arrival deadline of 20:00 IST on 2026-11-15."*  
> *"To meet a 20:00 IST deadline on 2026-11-15 via Karnataka Express, departure from Udayapura must be scheduled 2 days earlier (2026-11-13 at 18:15 IST)."*  
> *"Alternative recommendation: Select the Fastest flight archetype to reach Delhi before 20:00 IST on 2026-11-15."*

---

## 5. Section 4: Mathematical Door-to-Door Reconciliation

$$\begin{aligned}
\text{Travel Time} &= 45\text{ min (Shuttle)} + 2,260\text{ min (Train)} + 6\text{ min (Metro)} = \mathbf{2,311\text{ min}} \\
\text{Transfer Buffers} &= 20\text{ min (SBC)} + 15\text{ min (NDLS)} = \mathbf{35\text{ min}} \\
\text{Total Duration} &= 2,311\text{ min} + 35\text{ min} = \mathbf{2,346\text{ min}}\ (\sim 39\text{h } 06\text{m}) \\
T_{\text{arr}} - T_{\text{dep}} &= \text{17-Nov 09:21} - \text{15-Nov 18:15} = 39\text{h } 06\text{m} = \mathbf{2,346\text{ min}} \\
\text{Total Distance} &= 24.0\text{ km} + 2,406.0\text{ km} + 1.5\text{ km} = \mathbf{2,431.5\text{ km}}
\end{aligned}$$

**Duration Invariant:** Total duration matches `arrivalTime - departureTime` with zero residual error.

---

## 6. Section 5: Automated Regression Test Verification (All 10 Items)

The dedicated test suite `frontend/src/tests/timetableFeasibility.test.ts` was executed. All 10 required tests passed cleanly:

```text
=================================================================
RUNNING REAL RAILWAY TIMETABLE FEASIBILITY & TIMEZONE TEST SUITE (UI-01.2.2)
=================================================================

--- Test 1: Real Train 12627 Departure Integrity (Fixed 19:20 IST, Never 05:29) ---
Reported Train 12627 Departure: 2026-11-15 at 19:20 IST (2026-11-15T13:50:00.000Z)
✓ Test 1 Passed: Train 12627 departs at published 19:20 IST; arbitrary 05:29 departure strictly eliminated.

--- Test 2: Infeasible Deadline Evaluation (Arrival After Deadline) ---
✓ Test 2 Passed: Infeasible journey correctly flagged with note: "Arrival deadline missed: Karnataka Express (12627) departs SBC at published 19:20 IST and arrives Rajiv Chowk on 2026-11-17 at 09:21 IST, which is after the requested arrival deadline of 20:00 IST on 2026-11-15."

--- Test 3: Feasible Deadline Evaluation (Train Reaches Before Deadline) ---
Departure: 2026-11-13 18:15 IST
Arrival: 2026-11-15 09:21 IST
✓ Test 3 Passed: Train arriving before requested deadline is fully feasible.

--- Test 4: Running Day Verification ---
✓ Test 4 Passed: Running days verified daily across Mon-Sun.

--- Test 5: Isolation of Real Train Identity from Estimated Connections ---
✓ Test 5 Passed: No estimated alternative falsely inherits Karnataka Express (12627) identity.

--- Test 6: Source Disagreement Preservation in Provenance ---
✓ Test 6 Passed: Multi-source discrepancy matrix transparently preserved in provenance attributes.

--- Test 7: Timezone Conversion Contract (Asia/Kolkata / UTC+05:30) ---
✓ Test 7 Passed: Timezone conversions for Asia/Kolkata (+05:30) verified across instant boundaries.

--- Test 8: Mathematical Duration & Transfer Buffer Reconciliation ---
✓ Test 8 Passed: Duration arithmetic reconciled: 45m + 20m + 2260m + 15m + 6m = 2346m.

--- Test 9: Pareto Optimizer Handling of Infeasible vs Feasible Journeys ---
Top recommended journey for same-day deadline: SyncAir Multi-Modal Link (Air + Priority SyncCab) (Category: fastest)
✓ Test 9 Passed: Optimizer penalizes infeasible journeys and promotes feasible alternatives.

--- Test 10: Immutability of Real Service Timetable Under Strict Deadlines ---
✓ Test 10 Passed: Train 12627 departure is strictly invariant at 19:20 IST across all deadlines; zero backward-shifting.

=================================================================
ALL 10 TIMETABLE FEASIBILITY & TIMEZONE INTEGRITY TESTS PASSED! ✓
=================================================================
```

---

## 7. Visual Evidence & Screenshot Audit

Screenshots were captured using Microsoft Edge via Playwright on the running dev environment.

### Screenshot 1: Infeasible Deadline Scenario (`ui_refinement_01_2_2_infeasible_deadline.png`)
*Shows that for a same-day deadline (Nov 15 20:00), the optimizer prioritizes the feasible flight corridor (`fastest`), while Karnataka Express is not promoted as #1 due to the deadline violation.*  
![Infeasible Deadline Scenario](file:///C:/Users/deeks/.gemini/antigravity/brain/9b5a137c-314e-48a7-90a3-3db3f30932a6/ui_refinement_01_2_2_infeasible_deadline.png)

### Screenshot 2: Karnataka Express Timetable & Infeasibility Breakdown (`ui_refinement_01_2_2_karnataka_timetable.png`)
*Detailed view of the Karnataka Express card showing fixed published departure at 19:20 IST, Day 3 arrival at 09:21 IST, and the explicit warning note explaining that the deadline was missed.*  
![Karnataka Express Timetable](file:///C:/Users/deeks/.gemini/antigravity/brain/9b5a137c-314e-48a7-90a3-3db3f30932a6/ui_refinement_01_2_2_karnataka_timetable.png)

### Screenshot 3: Feasible Train Schedule Scenario (`ui_refinement_01_2_2_feasible_scenario.png`)
*Displays the feasible schedule when departing on Nov 13 at 18:15 IST and arriving in Delhi on Nov 15 at 09:21 IST before the 20:00 deadline.*  
![Feasible Train Scenario](file:///C:/Users/deeks/.gemini/antigravity/brain/9b5a137c-314e-48a7-90a3-3db3f30932a6/ui_refinement_01_2_2_feasible_scenario.png)

---

## 8. Full Suite & Build Verification Summary

| Suite / Check | Command | Result | Status |
| :--- | :--- | :--- | :--- |
| **Timetable Feasibility Tests** | `npx vite build --ssr src/tests/timetableFeasibility.test.ts; node dist-test/timetableFeasibility.test.js` | 10 passed in 172ms | **PASS** |
| **Multimodal Journey Map Tests** | `npx vite build --ssr src/tests/journeyMap.test.ts; node dist-test/journeyMap.test.js` | 10 passed in 196ms | **PASS** |
| **Backend Pytest Suite** | `python -m pytest tests/test_maps_geometry.py tests/test_journey_flow_cases.py tests/test_multimodal_routing_intelligence.py` | 37 passed in 24.08s | **PASS** |
| **Frontend TypeScript** | `npx tsc -b` | 0 errors | **PASS** |
| **Frontend Client Build** | `npm run build` | 2093 modules, built in 2.67s | **PASS** |
| **Database Checksum** | `Get-FileHash BookingInventory/data/APS-05.db` | SHA-256 identical | **PASS** |

---

## 9. Final Sign-Off Matrix

| Requirement | Audit Finding & Implementation | Status |
| :--- | :--- | :--- |
| **1. Fixed Published Departure** | Train 12627 departs SBC strictly at published **19:20 IST**; arbitrary 05:29 departure eliminated. | **CONFIRMED** |
| **2. Feasibility Enforcement** | Arriving after deadline marks itinerary `isConnectionFeasible = false` with explanatory notes. | **CONFIRMED** |
| **3. Feasible Permission** | Arriving before deadline permits service with `isConnectionFeasible = true`. | **CONFIRMED** |
| **4. Running Days** | Daily running days (all 7 days) verified; non-running days rejected. | **CONFIRMED** |
| **5. Identity Isolation** | No estimated connection inherits real train 12627 identity or vehicle number. | **CONFIRMED** |
| **6. Source Disagreements** | 2,406 km tariff vs 2,395 km track distance, and 09:00 vs 10:30 arrival preserved in provenance. | **CONFIRMED** |
| **7. Timezone Contract** | All instants converted from `Asia/Kolkata` (+05:30); 20:00 IST = 14:30 UTC; instant comparisons. | **CONFIRMED** |
| **8. Math Reconciliation** | $45\text{m} + 20\text{m} + 2260\text{m} + 15\text{m} + 6\text{m} = 2,346\text{m}$ exactly equals boundary times. | **CONFIRMED** |
| **9. Optimizer Penalization** | Infeasible train is penalized and excluded from Pareto frontier; feasible flight promoted. | **CONFIRMED** |
| **10. Immutability Under Deadlines** | Train 12627 departure is invariant at 19:20 IST across all arrival deadlines. | **CONFIRMED** |

**FINAL VERDICT: PASS**

