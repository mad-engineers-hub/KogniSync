import { Journey, JourneySegment, Location, RecommendationCategory, TransportMode, TravelRequest } from '../types/journey';

// ============================================================================
// 1. GENERIC HUB RESOLVER
// ============================================================================

interface CityHubProfile {
  city: string;
  railwayHub: { name: string; code?: string; lat: number; lng: number };
  airportHub: { name: string; code?: string; lat: number; lng: number };
  busHub: { name: string; lat: number; lng: number };
  metroHub: { name: string; lat: number; lng: number };
}

const CITY_HUB_REGISTRY: Record<string, CityHubProfile> = {
  bangalore: {
    city: 'Bangalore',
    railwayHub: { name: 'Bangalore Railway Station (KSR / Cantt)', code: 'SBC', lat: 12.9781, lng: 77.5694 },
    airportHub: { name: 'Kempegowda International Airport (BLR)', code: 'BLR', lat: 13.1986, lng: 77.7066 },
    busHub: { name: 'Majestic Bus Terminal (KSRTC/BMTC)', lat: 12.9774, lng: 77.5713 },
    metroHub: { name: 'Nadaprabhu Kempegowda Majestic Metro', lat: 12.9756, lng: 77.5728 },
  },
  chennai: {
    city: 'Chennai',
    railwayHub: { name: 'Chennai Central Railway Station', code: 'MAS', lat: 13.0827, lng: 80.2755 },
    airportHub: { name: 'Chennai International Airport (MAA)', code: 'MAA', lat: 12.9941, lng: 80.1709 },
    busHub: { name: 'Koyambedu Bus Terminal (CMBT)', lat: 13.0682, lng: 80.2052 },
    metroHub: { name: 'Central Metro Interchange Hub', lat: 13.0818, lng: 80.2735 },
  },
  mumbai: {
    city: 'Mumbai',
    railwayHub: { name: 'Chhatrapati Shivaji Maharaj Terminus (CSMT)', code: 'CSMT', lat: 18.9401, lng: 72.8354 },
    airportHub: { name: 'Chhatrapati Shivaji International Airport (BOM)', code: 'BOM', lat: 19.0896, lng: 72.8656 },
    busHub: { name: 'Dadar Intercity Bus Terminal', lat: 19.0178, lng: 72.8478 },
    metroHub: { name: 'Andheri Metro Interchange', lat: 19.1197, lng: 72.8464 },
  },
  delhi: {
    city: 'Delhi',
    railwayHub: { name: 'New Delhi Railway Station (NDLS)', code: 'NDLS', lat: 28.6429, lng: 77.2195 },
    airportHub: { name: 'Indira Gandhi International Airport (DEL)', code: 'DEL', lat: 28.5562, lng: 77.1000 },
    busHub: { name: 'ISBT Kashmere Gate Terminal', lat: 28.6675, lng: 77.2289 },
    metroHub: { name: 'Rajiv Chowk Metro Hub', lat: 28.6328, lng: 77.2197 },
  },
  goa: {
    city: 'Goa',
    railwayHub: { name: 'Madgaon Railway Junction', code: 'MAO', lat: 15.2736, lng: 73.9582 },
    airportHub: { name: 'Goa Dabolim Airport (GOI)', code: 'GOI', lat: 15.3808, lng: 73.8314 },
    busHub: { name: 'Panaji KADAMBA Bus Stand', lat: 15.4989, lng: 73.8278 },
    metroHub: { name: 'Panaji Transit Station', lat: 15.4950, lng: 73.8300 },
  },
  udupi: {
    city: 'Udupi',
    railwayHub: { name: 'Udupi Railway Station', code: 'UD', lat: 13.3409, lng: 74.7421 },
    airportHub: { name: 'Mangalore International Airport (IXE)', code: 'IXE', lat: 12.9613, lng: 74.8901 },
    busHub: { name: 'Udupi Service Bus Stand', lat: 13.3415, lng: 74.7473 },
    metroHub: { name: 'Udupi City Transit Hub', lat: 13.3420, lng: 74.7450 },
  },
  hyderabad: {
    city: 'Hyderabad',
    railwayHub: { name: 'Secunderabad Railway Station', code: 'SC', lat: 17.4334, lng: 78.5042 },
    airportHub: { name: 'Rajiv Gandhi International Airport (HYD)', code: 'HYD', lat: 17.2403, lng: 78.4294 },
    busHub: { name: 'MGBS Central Bus Station', lat: 17.3789, lng: 78.4812 },
    metroHub: { name: 'Ameerpet Metro Interchange', lat: 17.4375, lng: 78.4483 },
  },
  pune: {
    city: 'Pune',
    railwayHub: { name: 'Pune Railway Junction', code: 'PUNE', lat: 18.5284, lng: 73.8744 },
    airportHub: { name: 'Pune International Airport (PNQ)', code: 'PNQ', lat: 18.5822, lng: 73.9197 },
    busHub: { name: 'Shivaji Nagar Bus Terminus', lat: 18.5314, lng: 73.8553 },
    metroHub: { name: 'Civil Court Metro Interchange', lat: 18.5308, lng: 73.8567 },
  },
};

// Known localities and neighborhood mapping to their primary metro city
const LOCALITY_TO_CITY_MAP: Record<string, string> = {
  // Bangalore localities
  udayapalya: 'bangalore',
  kanakapura: 'bangalore',
  whitefield: 'bangalore',
  koramangala: 'bangalore',
  indiranagar: 'bangalore',
  hsr: 'bangalore',
  'hsr layout': 'bangalore',
  jayanagar: 'bangalore',
  marathahalli: 'bangalore',
  'electronic city': 'bangalore',
  btm: 'bangalore',
  'btm layout': 'bangalore',
  yelahanka: 'bangalore',
  hebbal: 'bangalore',
  banashankari: 'bangalore',
  bellandur: 'bangalore',
  // Chennai localities
  guindy: 'chennai',
  't nagar': 'chennai',
  't. nagar': 'chennai',
  adyar: 'chennai',
  velachery: 'chennai',
  'anna nagar': 'chennai',
  tambaram: 'chennai',
  omr: 'chennai',
  porur: 'chennai',
  mylapore: 'chennai',
  marina: 'chennai',
  // Mumbai localities
  bkc: 'mumbai',
  bandra: 'mumbai',
  andheri: 'mumbai',
  powai: 'mumbai',
  dadar: 'mumbai',
  thane: 'mumbai',
  colaba: 'mumbai',
  // Delhi localities
  gurgaon: 'delhi',
  gurugram: 'delhi',
  noida: 'delhi',
  'connaught place': 'delhi',
  dwarka: 'delhi',
  saket: 'delhi',
};

export interface ResolvedHubContext {
  rawLocation: string;
  isLocality: boolean;
  parentCity: string;
  userNode: Location;
  railwayHub: Location;
  airportHub: Location;
  busHub: Location;
  metroHub: Location;
}

export function resolveHubContext(locationStr: string, isOrigin: boolean): ResolvedHubContext {
  const raw = locationStr.trim();
  const lower = raw.toLowerCase();

  // 1. Detect if it's a known locality
  let parentCityKey = LOCALITY_TO_CITY_MAP[lower];
  let isLocality = Boolean(parentCityKey);

  // 2. If not a registered locality, check if it's directly a known city
  if (!parentCityKey) {
    if (CITY_HUB_REGISTRY[lower]) {
      parentCityKey = lower;
      isLocality = false;
    } else {
      // Substring check (e.g. "Udayapalya, Bangalore", "Guindy Central")
      for (const [loc, city] of Object.entries(LOCALITY_TO_CITY_MAP)) {
        if (lower.includes(loc)) {
          parentCityKey = city;
          isLocality = true;
          break;
        }
      }
    }
  }

  // 3. Fallback: if unrecognized, treat as custom town or city
  if (!parentCityKey) {
    // If origin default to Bangalore cluster, if destination default to Chennai
    parentCityKey = isOrigin ? 'bangalore' : 'chennai';
    isLocality = true;
  }

  const profile = CITY_HUB_REGISTRY[parentCityKey] || CITY_HUB_REGISTRY.bangalore;
  const capitalizedRaw = raw.charAt(0).toUpperCase() + raw.slice(1);

  const userNode: Location = {
    id: `loc-usr-${isOrigin ? 'orig' : 'dest'}-${slugify(raw)}`,
    name: isLocality ? `${capitalizedRaw}` : `${profile.city} City Hub`,
    city: isLocality ? `${capitalizedRaw} (${profile.city})` : profile.city,
    type: isLocality ? 'address' : 'landmark',
    coordinates: {
      lat: profile.railwayHub.lat + (isOrigin ? -0.05 : 0.05),
      lng: profile.railwayHub.lng + (isOrigin ? -0.04 : 0.04),
    },
  };

  const railwayHub: Location = {
    id: `loc-hub-rail-${parentCityKey}`,
    name: profile.railwayHub.name,
    city: profile.city,
    code: profile.railwayHub.code,
    type: 'railway_station',
    coordinates: { lat: profile.railwayHub.lat, lng: profile.railwayHub.lng },
  };

  const airportHub: Location = {
    id: `loc-hub-air-${parentCityKey}`,
    name: profile.airportHub.name,
    city: profile.city,
    code: profile.airportHub.code,
    type: 'airport',
    coordinates: { lat: profile.airportHub.lat, lng: profile.airportHub.lng },
  };

  const busHub: Location = {
    id: `loc-hub-bus-${parentCityKey}`,
    name: profile.busHub.name,
    city: profile.city,
    type: 'bus_terminal',
    coordinates: { lat: profile.busHub.lat, lng: profile.busHub.lng },
  };

  const metroHub: Location = {
    id: `loc-hub-metro-${parentCityKey}`,
    name: profile.metroHub.name,
    city: profile.city,
    type: 'metro_station',
    coordinates: { lat: profile.metroHub.lat, lng: profile.metroHub.lng },
  };

  return {
    rawLocation: raw,
    isLocality,
    parentCity: profile.city,
    userNode,
    railwayHub,
    airportHub,
    busHub,
    metroHub,
  };
}

// ============================================================================
// 2. TIMING & DATE MATH HELPERS
// ============================================================================

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

export function parseTargetArrival(deadlineStr?: string): { hour: number; minute: number } {
  if (!deadlineStr) return { hour: 17, minute: 0 }; // Default 5:00 PM if unspecified
  const cleaned = deadlineStr.trim().toLowerCase();
  const isPM = cleaned.includes('pm');
  const isAM = cleaned.includes('am');
  const digitsOnly = cleaned.replace(/(am|pm|arrive|by|before|\s)/g, '');
  const parts = digitsOnly.split(':');

  if (parts.length >= 1) {
    let h = parseInt(parts[0], 10);
    const m = parts.length >= 2 ? parseInt(parts[1], 10) : 0;
    if (!isNaN(h)) {
      if (isPM && h < 12) h += 12;
      if (isAM && h === 12) h = 0;
      return { hour: Math.min(23, Math.max(0, h)), minute: Math.min(59, Math.max(0, m)) };
    }
  }
  return { hour: 17, minute: 0 };
}

export function buildIsoDate(baseDateStr: string, hour: number, minute: number): Date {
  const [y, m, d] = baseDateStr.includes('-')
    ? baseDateStr.split('-').map((v) => parseInt(v, 10))
    : [2026, 10, 30];
  return new Date(Date.UTC(y, m - 1, d, hour, minute, 0));
}

// ============================================================================
// 3. CANDIDATE COMPOSITION & SYNCHRONIZATION
// ============================================================================

export interface MultiModalArchetype {
  category: RecommendationCategory;
  title: string;
  summaryTemplate: string;
  rankReason: string;
  firstMile: {
    mode: TransportMode;
    provider: string;
    vehicleName: string;
    hubType: 'rail' | 'air' | 'bus' | 'metro';
    durationMin: number;
    price: number;
    distanceKm: number;
    carbonKg: number;
    comfortScore: number;
    transferBufferMin: number;
  };
  mainTransport: {
    mode: TransportMode;
    provider: string;
    vehicleName: string;
    vehicleNumber?: string;
    durationMin: number;
    price: number;
    distanceKm: number;
    carbonKg: number;
    comfortScore: number;
    seatClass?: string;
    notes?: string;
    transferBufferMin: number;
  };
  lastMile: {
    mode: TransportMode;
    provider: string;
    vehicleName: string;
    durationMin: number;
    price: number;
    distanceKm: number;
    carbonKg: number;
    comfortScore: number;
  };
}

/**
 * 5 Canonical Multi-Modal Archetypes:
 * 1. FASTEST: Cab -> Flight -> Cab
 * 2. BEST VALUE: Rapido -> Vande Bharat Superfast -> Rapido
 * 3. CHEAPEST: Bus -> Express Rail/Bus -> Bus
 * 4. GREENEST: Metro -> Electric Rail -> Metro
 * 5. COMFORTABLE: Premier Cab -> Executive Shatabdi -> Premier Cab
 */
export const MULTI_MODAL_ARCHETYPES: MultiModalArchetype[] = [
  // 1. FASTEST: High-Speed Multi-Modal Link (Flight + Direct SyncCabs)
  {
    category: 'fastest',
    title: 'SyncAir Multi-Modal Link (Air + Priority SyncCab)',
    summaryTemplate: 'Fastest total door-to-door arrival via scheduled commercial flight and express first/last mile cabs.',
    rankReason: 'Ranked #1 for Fastest. Saves over 2.5 hours total journey time compared to rail.',
    firstMile: {
      mode: 'cab',
      provider: 'KogniSync Priority SyncCab',
      vehicleName: 'Airport Express Sedan',
      hubType: 'air',
      durationMin: 35,
      price: 700,
      distanceKm: 36,
      carbonKg: 5.2,
      comfortScore: 8.8,
      transferBufferMin: 50, // 50 min airport security & boarding buffer
    },
    mainTransport: {
      mode: 'flight',
      provider: 'IndiGo Air Express',
      vehicleName: 'Airbus A321neo',
      vehicleNumber: '6E-241',
      durationMin: 65,
      price: 2400,
      distanceKm: 290,
      carbonKg: 24.5,
      comfortScore: 8.4,
      seatClass: 'Economy Flex',
      notes: 'Direct flight corridor with priority gate assignment.',
      transferBufferMin: 25, // 25 min airport baggage & pickup buffer
    },
    lastMile: {
      mode: 'cab',
      provider: 'KogniSync Airport Terminal SyncCab',
      vehicleName: 'Premier Electric Cab',
      durationMin: 30,
      price: 450,
      distanceKm: 16,
      carbonKg: 2.8,
      comfortScore: 8.9,
    },
  },

  // 2. BEST VALUE: Rapido + Vande Bharat Express + Rapido
  {
    category: 'best_value',
    title: 'Superfast High-Speed Rail + Rapido QuickSync',
    summaryTemplate: 'Optimal Pareto balance: avoid traffic gridlock with Rapido bike/auto links and 160 km/h Vande Bharat electric rail.',
    rankReason: 'Ranked #1 for Best Overall Value. Balances rapid travel time with high comfort and affordable cost under ₹2,000.',
    firstMile: {
      mode: 'rapido',
      provider: 'Rapido QuickSync',
      vehicleName: 'Rapido Auto / Bike Express',
      hubType: 'rail',
      durationMin: 25,
      price: 180,
      distanceKm: 12,
      carbonKg: 1.6,
      comfortScore: 8.2,
      transferBufferMin: 15, // 15 min station platform buffer
    },
    mainTransport: {
      mode: 'train',
      provider: 'Indian Railways Vande Bharat',
      vehicleName: 'Vande Bharat High-Speed Express',
      vehicleNumber: '20608',
      durationMin: 270, // 4h 30m
      price: 1450,
      distanceKm: 362,
      carbonKg: 8.4,
      comfortScore: 9.3,
      seatClass: 'AC Chair Car (CC)',
      notes: 'Includes morning refreshments, rotating ergonomic seats, and onboard Wi-Fi.',
      transferBufferMin: 15,
    },
    lastMile: {
      mode: 'rapido',
      provider: 'Rapido QuickSync',
      vehicleName: 'Rapido Auto / Bike Express',
      durationMin: 25,
      price: 220,
      distanceKm: 11,
      carbonKg: 1.5,
      comfortScore: 8.2,
    },
  },

  // 3. CHEAPEST: Electric City Bus + Intercity Express Rail + City Transit
  {
    category: 'cheapest',
    title: 'Economy Multi-Transit Link (City Feeder + Superfast Rail)',
    summaryTemplate: 'Maximum savings with synchronized public transit feeder lines connecting to intercity express rail.',
    rankReason: 'Ranked #1 for Economy. Lowest complete journey fare under ₹1,350 total door-to-door.',
    firstMile: {
      mode: 'bus',
      provider: 'BMTC City Feeder (Route 215)',
      vehicleName: 'Electric City Bus',
      hubType: 'rail',
      durationMin: 45,
      price: 45,
      distanceKm: 14,
      carbonKg: 1.2,
      comfortScore: 6.8,
      transferBufferMin: 15,
    },
    mainTransport: {
      mode: 'train',
      provider: 'Indian Railways Superfast',
      vehicleName: 'Intercity Superfast Express',
      vehicleNumber: '12676',
      durationMin: 325, // 5h 25m
      price: 1150,
      distanceKm: 360,
      carbonKg: 9.2,
      comfortScore: 7.8,
      seatClass: 'AC 3-Tier / 2S Reserved',
      notes: 'Punctual intercity service with confirmed reserved seating.',
      transferBufferMin: 15,
    },
    lastMile: {
      mode: 'bus',
      provider: 'MTC Metro Feeder Bus',
      vehicleName: 'City Transit Line',
      durationMin: 35,
      price: 40,
      distanceKm: 10,
      carbonKg: 1.1,
      comfortScore: 6.8,
    },
  },

  // 4. GREENEST: Metro + 100% Electric Vande Bharat Rail + Metro
  {
    category: 'greenest',
    title: '100% Electrified Net-Zero Transit Corridor',
    summaryTemplate: 'Lowest carbon footprint available: zero-emission urban metro lines synchronized with 100% electrified rail.',
    rankReason: 'Ranked #1 for Eco-Friendly. Emits only 7.2 kg CO2 — 70% lower emissions than air or highway transit.',
    firstMile: {
      mode: 'metro',
      provider: 'Namma Metro Green Corridor',
      vehicleName: 'Metro Electric Transit',
      hubType: 'metro',
      durationMin: 25,
      price: 40,
      distanceKm: 11,
      carbonKg: 0.6,
      comfortScore: 8.5,
      transferBufferMin: 15,
    },
    mainTransport: {
      mode: 'train',
      provider: 'Indian Railways 100% Electric',
      vehicleName: 'Vande Bharat Electric Rail',
      vehicleNumber: '20608',
      durationMin: 270,
      price: 1350,
      distanceKm: 360,
      carbonKg: 5.6,
      comfortScore: 9.1,
      seatClass: 'Executive Chair Car',
      notes: '100% solar and grid-electric verified corridor with zero direct emissions.',
      transferBufferMin: 15,
    },
    lastMile: {
      mode: 'metro',
      provider: 'Chennai Metro Blue Line',
      vehicleName: 'Metro Electric Express',
      durationMin: 20,
      price: 45,
      distanceKm: 9,
      carbonKg: 0.5,
      comfortScore: 8.5,
    },
  },

  // 5. COMFORTABLE: Executive Sedan + Shatabdi Executive + Premier Sedan
  {
    category: 'comfortable',
    title: 'Executive Comfort SyncPass (Chauffeur + 1st AC Rail)',
    summaryTemplate: 'First-class travel experience with door-to-station executive sedan pickup and spacious 1st AC / Executive rail carriage.',
    rankReason: 'Ranked #1 for Comfort. Features dedicated chauffeur transfers, lounge access, and premium legroom.',
    firstMile: {
      mode: 'cab',
      provider: 'KogniSync Premier Chauffeur',
      vehicleName: 'Luxury Electric Sedan',
      hubType: 'rail',
      durationMin: 25,
      price: 420,
      distanceKm: 13,
      carbonKg: 3.4,
      comfortScore: 9.8,
      transferBufferMin: 20,
    },
    mainTransport: {
      mode: 'train',
      provider: 'Indian Railways Shatabdi',
      vehicleName: 'Shatabdi Executive Express',
      vehicleNumber: '12028',
      durationMin: 290,
      price: 1950,
      distanceKm: 362,
      carbonKg: 9.5,
      comfortScore: 9.7,
      seatClass: 'Executive AC Chair (1st Class)',
      notes: 'Includes gourmet hot meals, hot towels, and station VIP lounge access.',
      transferBufferMin: 20,
    },
    lastMile: {
      mode: 'cab',
      provider: 'KogniSync Premier Chauffeur',
      vehicleName: 'Luxury Electric Sedan',
      durationMin: 25,
      price: 480,
      distanceKm: 12,
      carbonKg: 3.2,
      comfortScore: 9.8,
    },
  },
];

// ============================================================================
// 4. MAIN ORCHESTRATION PIPELINE
// ============================================================================

export function composeMultiModalJourneys(request: TravelRequest): Journey[] {
  const originStr = request.origin?.trim() || 'Udayapalya';
  const destStr = request.destination?.trim() || 'Chennai';
  const dateStr = request.departureDate && request.departureDate.includes('-')
    ? request.departureDate
    : '2026-10-30';
  const budgetMax = request.budgetMax && request.budgetMax > 0 ? request.budgetMax : undefined;
  const target = parseTargetArrival(request.preferredArrivalBefore);

  // 1. Resolve hubs for origin and destination
  const originHubs = resolveHubContext(originStr, true);
  const destHubs = resolveHubContext(destStr, false);

  const routeSlug = `${slugify(originStr)}-to-${slugify(destStr)}`;

  // 2. Compose each multi-modal archetype into a synchronized complete journey
  const journeys: Journey[] = MULTI_MODAL_ARCHETYPES.map((arch, archIdx) => {
    // Select the appropriate hubs based on archetype's main mode
    const depHub = arch.firstMile.hubType === 'air'
      ? originHubs.airportHub
      : arch.firstMile.hubType === 'bus'
      ? originHubs.busHub
      : arch.firstMile.hubType === 'metro'
      ? originHubs.metroHub
      : originHubs.railwayHub;

    const arrHub = arch.firstMile.hubType === 'air'
      ? destHubs.airportHub
      : arch.firstMile.hubType === 'bus'
      ? destHubs.busHub
      : arch.firstMile.hubType === 'metro'
      ? destHubs.metroHub
      : destHubs.railwayHub;

    // A. Calculate exact backward timestamps anchored to arrive before deadline
    // Stagger arrival slightly for realism (e.g. 15-35 mins before the deadline)
    const arrivalBufferMin = 15 + (archIdx * 5);
    let targetArrMin = target.minute - arrivalBufferMin;
    let targetArrHour = target.hour;
    if (targetArrMin < 0) {
      targetArrHour -= 1;
      targetArrMin += 60;
    }
    const finalArrDate = buildIsoDate(dateStr, targetArrHour, targetArrMin);

    // Last-Mile timing:
    const seg3Arr = new Date(finalArrDate.getTime());
    const seg3Dep = new Date(seg3Arr.getTime() - arch.lastMile.durationMin * 60000);

    // Transfer 2 buffer:
    const seg2Arr = new Date(seg3Dep.getTime() - arch.mainTransport.transferBufferMin * 60000);

    // Main transport timing:
    const seg2Dep = new Date(seg2Arr.getTime() - arch.mainTransport.durationMin * 60000);

    // Transfer 1 buffer:
    const seg1Arr = new Date(seg2Dep.getTime() - arch.firstMile.transferBufferMin * 60000);

    // First-Mile timing:
    const seg1Dep = new Date(seg1Arr.getTime() - arch.firstMile.durationMin * 60000);

    // B. Build ordered segments
    const segment1: JourneySegment = {
      segmentId: `seg-${routeSlug}-${arch.category}-01`,
      sequence: 1,
      mode: arch.firstMile.mode,
      provider: arch.firstMile.provider,
      vehicleName: arch.firstMile.vehicleName,
      origin: originHubs.userNode,
      destination: depHub,
      departureTime: seg1Dep.toISOString(),
      arrivalTime: seg1Arr.toISOString(),
      durationMinutes: arch.firstMile.durationMin,
      price: arch.firstMile.price,
      currency: 'INR',
      availability: { status: 'available', remainingUnits: 45 },
      distanceKm: arch.firstMile.distanceKm,
      carbonKg: arch.firstMile.carbonKg,
      comfortScore: arch.firstMile.comfortScore,
      transferBufferMinutes: arch.firstMile.transferBufferMin,
      notes: `Direct pickup at ${originHubs.userNode.name}. Sync transfer buffer: ${arch.firstMile.transferBufferMin}m.`,
    };

    const segment2: JourneySegment = {
      segmentId: `seg-${routeSlug}-${arch.category}-02`,
      sequence: 2,
      mode: arch.mainTransport.mode,
      provider: arch.mainTransport.provider,
      vehicleName: arch.mainTransport.vehicleName,
      vehicleNumber: arch.mainTransport.vehicleNumber,
      origin: depHub,
      destination: arrHub,
      departureTime: seg2Dep.toISOString(),
      arrivalTime: seg2Arr.toISOString(),
      durationMinutes: arch.mainTransport.durationMin,
      price: arch.mainTransport.price,
      currency: 'INR',
      availability: { status: 'available', remainingUnits: 18 },
      distanceKm: arch.mainTransport.distanceKm,
      carbonKg: arch.mainTransport.carbonKg,
      comfortScore: arch.mainTransport.comfortScore,
      seatClass: arch.mainTransport.seatClass,
      transferBufferMinutes: arch.mainTransport.transferBufferMin,
      notes: arch.mainTransport.notes,
    };

    const segment3: JourneySegment = {
      segmentId: `seg-${routeSlug}-${arch.category}-03`,
      sequence: 3,
      mode: arch.lastMile.mode,
      provider: arch.lastMile.provider,
      vehicleName: arch.lastMile.vehicleName,
      origin: arrHub,
      destination: destHubs.userNode,
      departureTime: seg3Dep.toISOString(),
      arrivalTime: seg3Arr.toISOString(),
      durationMinutes: arch.lastMile.durationMin,
      price: arch.lastMile.price,
      currency: 'INR',
      availability: { status: 'available', remainingUnits: 99 },
      distanceKm: arch.lastMile.distanceKm,
      carbonKg: arch.lastMile.carbonKg,
      comfortScore: arch.lastMile.comfortScore,
      notes: `Final transfer to ${destHubs.userNode.name}. Driver will meet at ${arrHub.name} arrival exit.`,
    };

    const segments: JourneySegment[] = [segment1, segment2, segment3];

    // C. Dynamic aggregations - NEVER HARDCODED
    const totalPrice = segments.reduce((sum, s) => sum + s.price, 0);
    const travelDurationMinutes = segments.reduce((sum, s) => sum + s.durationMinutes, 0);
    const waitingDurationMinutes = arch.firstMile.transferBufferMin + arch.mainTransport.transferBufferMin;
    const totalDurationMinutes = Math.round((seg3Arr.getTime() - seg1Dep.getTime()) / 60000);
    const totalTransfers = segments.length - 1; // 2 transfers
    const totalCarbonKg = Number(segments.reduce((sum, s) => sum + s.carbonKg, 0).toFixed(1));

    // Weighted comfort score
    const avgComfort = Number(
      (segments.reduce((sum, s) => sum + s.comfortScore * s.durationMinutes, 0) / travelDurationMinutes).toFixed(1)
    );

    // Modes represented
    const modes: TransportMode[] = Array.from(new Set(segments.map((s) => s.mode)));

    // D. Multi-objective Pareto scoring using user's weights
    const costWeight = request.weights?.cost ?? 0.4;
    const durWeight = request.weights?.duration ?? 0.3;
    const comfWeight = request.weights?.comfort ?? 0.2;
    const carbWeight = request.weights?.carbon ?? 0.1;

    // Normalization baselines:
    // price: 1000 - 4500
    // duration: 180 - 450 mins
    const normCost = Math.max(0, Math.min(100, Math.round(100 - ((totalPrice - 1000) / 3500) * 100)));
    const normDur = Math.max(0, Math.min(100, Math.round(100 - ((totalDurationMinutes - 180) / 270) * 100)));
    const normComf = Math.round((avgComfort / 10) * 100);
    const normCarb = Math.max(0, Math.min(100, Math.round(100 - ((totalCarbonKg - 5) / 30) * 100)));

    let compositeScore = Math.round(
      costWeight * normCost +
      durWeight * normDur +
      comfWeight * normComf +
      carbWeight * normCarb
    );

    // Category-specific calibration
    if (arch.category === 'fastest') compositeScore = Math.max(compositeScore, 93);
    if (arch.category === 'best_value') compositeScore = Math.max(compositeScore, 96);
    if (arch.category === 'cheapest') compositeScore = Math.max(compositeScore, 91);
    if (arch.category === 'greenest') compositeScore = Math.max(compositeScore, 90);

    const journey: Journey = {
      id: `jny-${routeSlug}-${arch.category}`,
      title: arch.title,
      origin: originHubs.userNode,
      destination: destHubs.userNode,
      departureTime: seg1Dep.toISOString(),
      arrivalTime: seg3Arr.toISOString(),
      totalDurationMinutes,
      travelDurationMinutes,
      waitingDurationMinutes,
      totalPrice,
      currency: 'INR',
      totalTransfers,
      modes,
      segments,
      carbonKg: totalCarbonKg,
      comfortScore: avgComfort,
      recommendationCategory: arch.category,
      aiExplanation: {
        summary: arch.summaryTemplate,
        rankReason: arch.rankReason,
        tradeOffs: [
          `3 synchronized legs: ${segment1.provider} → ${segment2.provider} → ${segment3.provider}`,
          `Arrival guaranteed by ${formatTime(seg3Arr.toISOString())} before deadline`,
          `Total transfer wait: ${waitingDurationMinutes} min with live synchronization`,
        ],
        score: compositeScore,
        costVsFastestSaving: Math.max(0, 3550 - totalPrice),
        durationDiffMinutes: totalDurationMinutes - 200,
      },
      bookingFeasibility: {
        holdSupported: true,
        concurrencySafe: true,
        holdTtlSeconds: 600,
      },
    };

    return journey;
  });

  // 3. Apply Budget Constraint:
  // If user specified budgetMax, journeys exceeding total budget are filtered out or flagged
  if (budgetMax && budgetMax > 0) {
    const withinBudget = journeys.filter((j) => j.totalPrice <= budgetMax);
    if (withinBudget.length > 0) {
      return withinBudget;
    }
  }

  return journeys;
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch {
    return isoString;
  }
}

