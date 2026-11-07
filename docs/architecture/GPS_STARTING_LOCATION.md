# KogniSync M3.4 — GPS-Based Starting Location Autofill (Web + Mobile)

## 1. Overview & Architectural Goals

The **GPS-Based Starting Location Autofill** subsystem enables users to seamlessly initialize or refine their journey origin using real-time device location detection, while fully preserving manual text input, autocorrect/datalist suggestions, and door-to-door multimodal routing accuracy.

### Scope Boundaries
- **Single-shot detection only**: Invoked strictly on explicit user interaction ("Use my current location").
- **No background tracking**: Never polls or runs continuous background location intervals (`watchPosition`).
- **No coordinate leakage**: Coordinates are never sent to third-party analytics or persisted to user tracking tables.
- **Graceful manual fallback**: In every failure case (denial, timeout, loss of signal, network offline), manual typing remains immediately available and unblocked.

---

## 2. End-to-End Architecture & Flow

```mermaid
flowchart TD
    User["User Interaction"] -->|"Clicks 'Use my current location'"| UI["LocationInput / JourneyPlanner UI"]
    UI -->|"Calls getCurrentLocation()"| LS["LocationService"]
    
    LS -->|"Selects platform provider"| ProviderCheck{"Platform Bridge Available?"}
    ProviderCheck -->|"Native Container Detected"| NativeBridge["NativeLocationBridge"]
    ProviderCheck -->|"Standard Browser / Mobile Web"| BrowserProvider["BrowserLocationProvider"]
    
    BrowserProvider -->|"navigator.geolocation.getCurrentPosition()"| DeviceGPS["Device WGS-84 Sensor"]
    DeviceGPS -->|"Latitude, Longitude, Accuracy, Timestamp"| LS
    
    LS -->|"reverseGeocodeCoordinates(coords)"| Geocoder["Reverse Geocoder Client"]
    Geocoder -->|"GET /api/v1/location/reverse-geocode"| BackendAPI["FastAPI /api/v1/location"]
    
    BackendAPI -->|"Try OSM Nominatim (User-Agent, timeout: 2.5s)"| OSMNominatim["OpenStreetMap Nominatim"]
    OSMNominatim -.->|"Fallback if offline / timeout"| RegionalHub["KogniSync Regional Hub Geo-Matcher"]
    
    BackendAPI -->|"Normalized Location & Attribution"| Geocoder
    Geocoder -->|"LocationResult"| LS
    LS -->|"Populates Origin + Preserves Coordinates"| UI
    UI -->|"TravelRequest payload { origin, originCoordinates }"| Orchestrator["Multimodal Journey Orchestrator"]
```

---

## 3. Platform Support & Mobile Reality Disclosure

### 3.1 Web & Responsive Mobile Web
KogniSync operates as a modern responsive Single-Page Application (SPA) built with Vite, React 19, TypeScript, and Tailwind CSS v4. On all modern mobile browsers (iOS Safari, Android Chrome, Firefox Mobile, Samsung Internet), the browser `navigator.geolocation` API accesses the underlying device GPS with hardware precision, system permission dialogs, and high-accuracy satellite/cellular triangulation.

### 3.2 Native Mobile Bridge (`NativeLocationBridge`)
- **Repository Architecture**: KogniSync does not currently contain a native mobile container directory (`android/`, `ios/`, Capacitor, React Native, or Flutter configuration).
- **Extensible Shared Contract**: The location abstraction defines `PlatformLocationProvider` and implements `NativeLocationBridge`. When embedded in a native WebView shell (e.g., Capacitor, React Native WebView, or Android Native Bridge), the bridge checks `window.__KOGNISYNC_NATIVE_BRIDGE__` without hardcoding fake GPS values or pretending native mobile apps are bundled.

| Platform / Runtime | Implementation Provider | Hardware GPS Support | Status |
| :--- | :--- | :--- | :--- |
| **Desktop Web** (Chrome, Firefox, Safari, Edge) | `BrowserLocationProvider` | Yes (Wi-Fi/IP Geo) | Implemented & Verified |
| **Mobile Web** (iOS Safari, Android Chrome) | `BrowserLocationProvider` | Yes (Hardware GPS / GNSS) | Implemented & Verified |
| **Native Mobile Bridge** (Future wrapper) | `NativeLocationBridge` | Yes (via Bridge) | Contract Defined & Tested |

---

## 4. Location Service Abstraction Contracts

### 4.1 Typed Schemas (`frontend/src/types/location.ts`)

```typescript
export interface Coordinates {
  lat: number;
  lng: number;
}

export interface GeolocationPositionData {
  coordinates: Coordinates;
  accuracyMeters: number;
  timestamp: number;
}

export type LocationErrorCode =
  | 'PERMISSION_DENIED'
  | 'OS_PERMISSION_DENIED'
  | 'INSECURE_CONTEXT'
  | 'POSITION_UNAVAILABLE'
  | 'TIMEOUT'
  | 'UNSUPPORTED_PLATFORM'
  | 'POOR_ACCURACY'
  | 'REVERSE_GEOCODING_FAILED'
  | 'NETWORK_ERROR';

export interface LocationResult {
  coordinates: Coordinates;
  accuracyMeters: number;
  timestamp: number;
  formattedAddress: string;
  locality?: string;
  city: string;
  state?: string;
  country?: string;
  provider: string;
  attribution?: string;
  isEstimate: boolean;
}
```

### 4.2 Centralized Service (`LocationService`)
- Encapsulates error mapping and state handling outside UI components.
- Single entrypoint: `locationService.getCurrentLocation()`.
- Validates that returned accuracy is surfaced without altering raw coordinates.

---

## 5. Reverse Geocoding & Attribution

### 5.1 Provider Hierarchy
1. **OpenStreetMap Nominatim**:
   - URL: `https://nominatim.openstreetmap.org/reverse`
   - User-Agent: `KogniSync-Transit-Orchestrator/1.0 (internal-demo; contact: dev@kognisync.internal)`
   - Timeout: `2.5s` connect/read timeout.
   - Attribution: `"© OpenStreetMap contributors"`.
2. **KogniSync Regional Hub Geo-Matcher**:
   - Zero-network spatial proximity fallback using great-circle Haversine distance against canonical city hubs (Bangalore, Chennai, Mumbai, Delhi, Goa, Udupi, Mangalore, Kochi, Hyderabad, Jaipur, Mysore).
   - Resolves locality and parent city even when completely offline.
   - Provider tag: `"kognisync_regional_hub"`, attribution: `"KogniSync Regional Geo-Matcher"`.
3. **Client Proximity Fallback**:
   - Pure client-side fall-through if backend service is unreachable.

### 5.2 Preservation of Precision
Reverse-geocoding provides human-readable context (e.g., `"Indiranagar, Bangalore"`) for the input field, but **the exact numeric coordinates (`lat: 12.9352, lng: 77.6245`) are preserved** in `TravelRequest.originCoordinates` and passed to the backend orchestrator and Valhalla first-mile router for door-to-door road calculations.

---

## 6. Error Handling & Global Notification Resilience Matrix (M3.4 / M3.4.1)

All GPS outcomes are presented via an application-level toast overlay (`NotificationProvider` / `GlobalNotificationContainer`). Inline form error banners have been removed to guarantee zero layout shift within the Planner.

| GPS State | Error Code | Canonical Notification Message | Presentation | Dismissal Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Success** | N/A | `"Your current location has been detected and added as your starting point."` | Emerald toast, `role="status"` | Auto-dismisses in 4.5s; dismiss button. Replaces obsolete errors. |
| **OS Location Disabled** | `OS_PERMISSION_DENIED` | `"Device location is turned off. Enable Location services in Windows Settings."` | Rose toast, `role="alert"` | Persistent until dismissed; replaced upon success. |
| **Browser Blocked** | `PERMISSION_DENIED` | `"Location access is blocked. Allow location permission in your browser settings."` | Rose toast, `role="alert"` | Persistent until dismissed; replaced upon success. |
| **Timeout** | `TIMEOUT` | `"Location detection timed out. Please try again."` | Rose toast, `role="alert"` | Persistent until dismissed; replaced upon success. |
| **Position Unavailable** | `POSITION_UNAVAILABLE` | `"Your device could not provide a location. Check your location settings and retry."` | Rose toast, `role="alert"` | Persistent until dismissed; replaced upon success. |
| **Insecure Context** | `INSECURE_CONTEXT` | `"Location detection requires a secure connection (HTTPS or localhost)."` | Rose toast, `role="alert"` | Persistent until dismissed; replaced upon success. |
| **Reverse Geocode Failure**| `REVERSE_GEOCODING_FAILED` | `"Coordinates received, but the place name could not be resolved. You can enter your starting point manually."` | Rose toast, `role="alert"` | Persistent until dismissed; replaced upon success. |
| **Poor Accuracy** | `POOR_ACCURACY` | `"Location detected, but accuracy is limited. Please verify your starting point."` | Amber toast, `role="status"` | Persistent until dismissed; manual refinement unblocked. |
| **User Manual Edit** | N/A | Obsolete GPS notifications evicted via `dismissCategory('gps')`. | Zero layout shift | Coordinates decoupled; in-flight GPS resolution discarded. |

---

## 7. Privacy & Security Guarantees

1. **User-Triggered Execution**: Geolocation is requested **strictly upon user click** on the GPS locate button. No geolocation call occurs on component mount or page load.
2. **Zero Continuous Tracking**: `navigator.geolocation.watchPosition` is strictly prohibited. The system executes a single-shot position acquisition and terminates.
3. **No Storage of Coordinate History**: Raw latitude and longitude are not persisted in database audit trails or user tracking logs.
4. **Development Diagnostics Only**: `[GPS-DIAGNOSTIC]` log statements are guarded by `import.meta.env.DEV` to avoid emitting detailed coordinates or debug statements in production.
5. **Credential Isolation**: External reverse-geocoding APIs and keys are managed server-side; no secrets or tokens are exposed in client frontend bundles.

---

## 8. Verification & Test Evidence

### 8.1 Backend Test Suite (`backend/tests/test_location_service.py`)
- `test_haversine_distance_calculation`: PASS
- `test_reverse_geocode_regional_fallback`: PASS
- `test_reverse_geocode_bounds_validation`: PASS
- `test_api_reverse_geocode_endpoint_success`: PASS
- `test_api_reverse_geocode_invalid_query`: PASS
- `test_journey_search_with_origin_coordinates_preservation`: PASS

### 8.2 Frontend Test Suite (`frontend/src/tests/gpsStartingLocation.test.ts`)
- Test 1: Manual Entry Preservation & Editing: PASS
- Test 2: Browser Geolocation Mocking (Permission Granted): PASS
- Test 3: Reverse Geocoding & Coordinate Preservation: PASS
- Test 4: Browser Permission Denied Error Handling: PASS
- Test 5: OS / System Location Disabled Error Handling (Windows Settings Block): PASS
- Test 6: Insecure Context Error Handling (Non-HTTPS Origin): PASS
- Test 7: Automatic Fallback from High Accuracy to Standard Network Triangulation: PASS
- Test 8: Geolocation Timeout Error Handling: PASS
- Test 9: Position Unavailable Error Handling: PASS
- Test 10: Poor Accuracy Handling: PASS
- Test 11: Reverse Geocoding Failure Resilience: PASS
- Test 12: Privacy Protection (No continuous watchPosition): PASS
- Test 13: Unsupported Platform Fallback: PASS
- Test 14: Native Mobile Bridge Contract Verification: PASS
- Test 15: End-to-End Travel Request Coordinate Preservation: PASS
- Test 16: Race Condition Prevention: Manual Typing Takes Precedence Over Delayed GPS: PASS
- Test 17: Standardized GPS Notification Messages Specification Conformance: PASS
- Test 18: Success Toast Generation & Auto-Dismiss Duration (4.5s): PASS
- Test 19: Distinct Error Notifications across all Failure Modes: PASS
- Test 20: Notification Manual Dismissal: PASS
- Test 21: Auto-Dismiss Timer Eviction Behavior: PASS
- Test 22: Duplicate Notification Suppression for Identical Errors: PASS
- Test 23: Category-Based Replacement (Success Replaces Obsolete Error): PASS
- Test 24: Desktop Single-Line Layout & Styling Contract: PASS
- Test 25: Mobile Responsive Wrapping Layout Contract: PASS
- Test 26: Zero Planner Layout Shift Guarantee (Fixed Overlay): PASS
- Test 27: ARIA Live-Region & Accessibility Semantics: PASS

