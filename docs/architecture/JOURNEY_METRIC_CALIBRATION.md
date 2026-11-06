# KogniSync — Journey Metric Calibration & Provenance Architecture

**Document Version:** 1.0.0 (Milestone M2.5)  
**Status:** Authoritative Architectural Standard  
**Scope:** Backend Multimodal Orchestration, Journey Optimizer, and Frontend Trust Model

---

## 1. Executive Overview

KogniSync coordinates door-to-door multimodal journeys across intercity transport corridors (commercial air, high-speed electric rail, superfast express, intercity bus) and urban local connections (cabs, two-wheeler motorcycle taxis / Rapido, city feeder buses, electric metro, pedestrian walking).

Because real-world carrier APIs exhibit varied data access models (some provide live traffic, others provide published timetables, while carrier ticketing requires formal B2B agreements), **KogniSync strictly distinguishes between:**
1. **Provider-Backed Live Attributes** (e.g., live traffic durations from Google Routes API v2).
2. **Deterministic Corridor Estimates** (empirically calibrated parametric models for fares and durations).
3. **Simulated Sandbox Inventory** (local database seat units for concurrency and saga testing).
4. **Unknown / Unverified Attributes** (requiring partner confirmation prior to travel).

> [!IMPORTANT]
> **Cardinal Invariant:** An entire journey is **never labeled live** when only a subset of attributes are provider-backed. If duration is provider-backed while fare is estimated, the journey is explicitly designated as `mixed` provenance, and the UI presents granular attribute badges.

---

## 2. Metric Calibration Assumptions & Formulas

### 2.1 Fare Calibration Model

Fares reflect empirical base rates and per-kilometer tariffs observed across Indian domestic transit corridors.

| Transport Mode | Vehicle / Operator Class | Base Fare ($\text{INR}$) | Marginal Rate ($\text{INR/km}$) | Calibration Source / Benchmark |
| :--- | :--- | :--- | :--- | :--- |
| **Commercial Air** | IndiGo / Domestic Economy Flex | ₹1,800 | ₹2.30 / km | Domestic passenger air routes with 14-day booking horizon |
| **High-Speed Rail** | Indian Railways Vande Bharat (Chair Car) | ₹400 | ₹2.70 / km | Official IRCTC Vande Bharat Executive / CC fare schedules |
| **Superfast Rail** | Superfast Express (Sleeper / 2S Reserved) | ₹150 | ₹1.60 / km | IRCTC standard telescopic passenger tariffs |
| **Electric Rail** | 100% Electric Rail (AC Chair Car) | ₹380 | ₹2.50 / km | IRCTC Shatabdi / Intercity AC Chair Car schedules |
| **Executive Rail** | Executive 1st AC Sleeper / Coupe | ₹700 | ₹3.60 / km | IRCTC 1st AC premium intercity tariff |
| **First/Last Cab** | App-based Cab / Airport Transfer | ₹450 – ₹650 | Flat corridor rate | Urban airport/station transfer flat bands (Bangalore, Chennai, Goa) |
| **First/Last Rapido** | Two-Wheeler Motorcycle Taxi | ₹180 – ₹220 | Flat urban rate | Urban rapid transit feeder benchmarks |
| **Feeder Bus** | BMTC / MTC / Local Municipal Feeder | ₹40 – ₹45 | Flat stage fare | Metropolitan stage carriage published rate cards |
| **Electric Metro** | BMRCL / CMRL Rapid Transit | ₹40 – ₹45 | Distance-tiered token | Standard metropolitan metro rail tariff structures |
| **Pedestrian Walk**| Pedestrian Terminal Walk | ₹0.00 | ₹0.00 / km | Zero financial cost |

#### Limitations & Boundary Disclosures
- Fares are deterministic corridor approximations designed for comparative trade-off optimization.
- They do not account for real-time airline dynamic surge pricing, festive peak Tatkal quotas, or unconfirmed seat availability.
- All fares are flagged with `is_fare_estimated = True` unless a certified direct ticketing integration is active.

---

### 2.2 Travel Duration & Speed Models

Travel durations are computed backward from the user's preferred arrival deadline to ensure punctual arrival:

$$\text{Arrival}_{\text{final}} \le \text{Preferred Arrival Before}$$

$$\text{Departure}_{\text{leg}} = \text{Arrival}_{\text{leg}} - \text{Duration}_{\text{leg}}$$

| Mode | Cruising Speed / Metric | Fixed Buffer | Description |
| :--- | :--- | :--- | :--- |
| **Commercial Air** | $750\text{ km/h}$ cruise | $45\text{ min}$ climb/descent | Direct great-circle air corridor + runway taxi |
| **Vande Bharat Rail**| $80\text{ km/h}$ commercial average | $0\text{ min}$ (included in speed) | $160\text{ km/h}$ peak capable; reflects actual scheduled timetables |
| **Superfast Rail** | $65\text{ km/h}$ commercial average | $0\text{ min}$ | Standard express rail timetable speed |
| **Electric Rail** | $82\text{ km/h}$ commercial average | $0\text{ min}$ | High-efficiency electrified mainline timetable |
| **First/Last Mile**| Provider traffic feed or $25\text{--}35\text{ min}$ | Variable | Road congestion-aware duration via Google Routes API v2 |

---

### 2.3 Transfer Buffers & Connection Invariants

To eliminate missed connections, KogniSync enforces mandatory, non-zero transfer buffers between synchronized segments:

| Intermodal Transfer Node | Buffer Required | Justification |
| :--- | :--- | :--- |
| **Airport Departure Concourse** | **$50\text{ minutes}$** | Check-in deadline, security clearance, boarding gate closure |
| **Airport Arrival to City Transfer** | **$25\text{ minutes}$** | Baggage reclaim, terminal exit, taxi pickup concourse |
| **Railway Junction Transfer** | **$15\text{--}25\text{ minutes}$** | Platform change via foot-over-bridge, luggage transit |
| **Metro / Feeder Bus Intermodal** | **$15\text{ minutes}$** | Fare gate turnstile, concourse traversal, platform headways |

---

### 2.4 Mode-Aware Carbon Emission Calculation

In Milestone M2.5, carbon calculation is mode-aware and physics-anchored:

$$\text{carbon\_kg} = \text{calculate\_calibrated\_segment\_carbon}(\text{mode}, \text{dist}_{\text{resolved}}, \text{dist}_{\text{baseline}}, \text{carbon}_{\text{baseline}})$$

#### Physical Rules
1. **Pedestrian Legs (`walk`)**:
   $$\text{carbon\_kg} = 0.0$$
   Human walking emits zero operational direct greenhouse gases.
2. **Dedicated Transit Corridors (`flight`, `train`, `metro`)**:
   $$\text{carbon\_kg} = \text{round}(\text{carbon}_{\text{baseline}}, 1)$$
   - Road traffic variations reported by road navigation providers (e.g. Google Routes) **must NOT scale** air or rail emissions.
   - Aviation emissions are dominated by takeoff/climb cycles and fixed flight altitudes.
   - Train and metro emissions are dictated by electrified grid efficiency factors and dedicated steel track alignments.
3. **Road Transport Modes (`cab`, `car`, `auto`, `rapido`, `bus`)**:
   $$\text{carbon\_kg} = \text{round}\left(\text{baseline\_carbon} \times \frac{\text{resolved\_distance\_km}}{\text{baseline\_distance\_km}}, 1\right)$$
   Road vehicles burn fuel / draw battery energy in direct proportion to road kilometers traveled. Deviation around road detours or traffic congestion proportionally adjusts emissions.

#### Centralized Emission Benchmarks
- Commercial Flight: $0.082\text{--}0.150\text{ kg CO}_2\text{/pax-km}$
- Dedicated Cab: $0.120\text{--}0.153\text{ kg CO}_2\text{/pax-km}$
- Auto-Rickshaw: $0.075\text{--}0.100\text{ kg CO}_2\text{/pax-km}$
- Motorcycle Taxi (Rapido): $0.045\text{--}0.133\text{ kg CO}_2\text{/pax-km}$
- Public Bus: $0.040\text{--}0.086\text{ kg CO}_2\text{/pax-km}$
- Superfast Rail: $0.024\text{--}0.026\text{ kg CO}_2\text{/pax-km}$
- 100% Electrified Net-Zero Rail: $0.016\text{ kg CO}_2\text{/pax-km}$
- Rapid Metro: $0.020\text{--}0.055\text{ kg CO}_2\text{/pax-km}$
- Walk: $0.000\text{ kg CO}_2\text{/pax-km}$

---

## 3. Data Credibility & Provenance Hierarchy

Each segment and journey exposes an explicit `provenance` block:

```json
{
  "provenance": {
    "overallSourceType": "mixed",
    "isFullyConfirmed": false,
    "hasLiveAttributes": true,
    "hasSimulatedAttributes": true,
    "summary": "Contains both provider-backed attributes and deterministic estimates. Availability is unverified."
  },
  "aiExplanation": {
    "isFareEstimated": true,
    "isDurationEstimated": false,
    "isAvailabilityVerified": false,
    "dataCredibilityNotice": "Transit durations reflect live provider traffic feeds (Google Routes API v2). Fares are deterministic corridor estimates and seat availability is simulated demo inventory requiring live provider confirmation prior to booking."
  }
}
```

### Granular Attribute Provenance States

| Attribute | State when Provider Active | State when Provider Offline | State when Unconfigured |
| :--- | :--- | :--- | :--- |
| **Duration** | `provider_live` (`isEstimate: false`) | `deterministic_estimate` (`isEstimate: true`) | `deterministic_estimate` (`isEstimate: true`) |
| **Distance** | `provider_live` (`isEstimate: false`) | `deterministic_estimate` (`isEstimate: true`) | `deterministic_estimate` (`isEstimate: true`) |
| **Fare** | `deterministic_estimate` (`isEstimate: true`) | `deterministic_estimate` (`isEstimate: true`) | `deterministic_estimate` (`isEstimate: true`) |
| **Inventory / Seats** | `simulated` (`isRealInventory: false`) | `simulated` (`isRealInventory: false`) | `simulated` (`isRealInventory: false`) |

---

## 4. Summary of Invariants

1. **Hard Constraints are Sovereign**: Budget caps and arrival deadlines strictly filter candidates before Pareto scoring. They are never relaxed to force recommendations.
2. **Deterministic Tie-Breaking**: When multiple journeys achieve identical optimization scores, tie-breaking is strictly deterministic: lower cost first, then shorter duration.
3. **Sandbox Booking Isolation**: Local holds in PostgreSQL lock demo inventory only. Real carrier tickets are never claimed without direct carrier ticketing credentials.

