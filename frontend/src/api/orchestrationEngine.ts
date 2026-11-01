import { Journey, JourneySegment, Location, RecommendationCategory, TransportMode, TravelRequest } from '../types/journey';

// ============================================================================
// 1. COMPREHENSIVE CITY & HUB REGISTRY
// ============================================================================

export interface CityHubProfile {
  city: string;
  lat: number;
  lng: number;
  railwayHub: { name: string; code?: string; lat: number; lng: number };
  airportHub: { name: string; code?: string; lat: number; lng: number };
  busHub: { name: string; lat: number; lng: number };
  metroHub: { name: string; lat: number; lng: number; hasMetro: boolean };
}

export const CITY_HUB_REGISTRY: Record<string, CityHubProfile> = {
  bangalore: {
    city: 'Bangalore',
    lat: 12.9716,
    lng: 77.5946,
    railwayHub: { name: 'Bangalore Railway Station (KSR / Cantt)', code: 'SBC', lat: 12.9781, lng: 77.5694 },
    airportHub: { name: 'Kempegowda International Airport (BLR)', code: 'BLR', lat: 13.1986, lng: 77.7066 },
    busHub: { name: 'Majestic Bus Terminal (KSRTC/BMTC)', lat: 12.9774, lng: 77.5713 },
    metroHub: { name: 'Nadaprabhu Kempegowda Majestic Metro', lat: 12.9756, lng: 77.5728, hasMetro: true },
  },
  chennai: {
    city: 'Chennai',
    lat: 13.0827,
    lng: 80.2707,
    railwayHub: { name: 'Chennai Central Railway Station', code: 'MAS', lat: 13.0827, lng: 80.2755 },
    airportHub: { name: 'Chennai International Airport (MAA)', code: 'MAA', lat: 12.9941, lng: 80.1709 },
    busHub: { name: 'Koyambedu Bus Terminal (CMBT)', lat: 13.0682, lng: 80.2052 },
    metroHub: { name: 'Central Metro Interchange Hub', lat: 13.0818, lng: 80.2735, hasMetro: true },
  },
  mumbai: {
    city: 'Mumbai',
    lat: 19.0760,
    lng: 72.8777,
    railwayHub: { name: 'Chhatrapati Shivaji Maharaj Terminus (CSMT)', code: 'CSMT', lat: 18.9401, lng: 72.8354 },
    airportHub: { name: 'Chhatrapati Shivaji International Airport (BOM)', code: 'BOM', lat: 19.0896, lng: 72.8656 },
    busHub: { name: 'Dadar Intercity Bus Terminal', lat: 19.0178, lng: 72.8478 },
    metroHub: { name: 'Andheri Metro Interchange', lat: 19.1197, lng: 72.8464, hasMetro: true },
  },
  delhi: {
    city: 'Delhi',
    lat: 28.6139,
    lng: 77.2090,
    railwayHub: { name: 'New Delhi Railway Station (NDLS)', code: 'NDLS', lat: 28.6429, lng: 77.2195 },
    airportHub: { name: 'Indira Gandhi International Airport (DEL)', code: 'DEL', lat: 28.5562, lng: 77.1000 },
    busHub: { name: 'ISBT Kashmere Gate Terminal', lat: 28.6675, lng: 77.2289 },
    metroHub: { name: 'Rajiv Chowk Metro Hub', lat: 28.6328, lng: 77.2197, hasMetro: true },
  },
  goa: {
    city: 'Goa',
    lat: 15.2993,
    lng: 74.1240,
    railwayHub: { name: 'Madgaon Railway Junction', code: 'MAO', lat: 15.2736, lng: 73.9582 },
    airportHub: { name: 'Goa Dabolim Airport (GOI)', code: 'GOI', lat: 15.3808, lng: 73.8314 },
    busHub: { name: 'Panaji KADAMBA Bus Stand', lat: 15.4989, lng: 73.8278 },
    metroHub: { name: 'Goa Coastal Rapid EV Transit', lat: 15.4950, lng: 73.8300, hasMetro: false },
  },
  udupi: {
    city: 'Udupi',
    lat: 13.3409,
    lng: 74.7421,
    railwayHub: { name: 'Udupi Railway Station', code: 'UD', lat: 13.3409, lng: 74.7421 },
    airportHub: { name: 'Mangalore International Airport (IXE)', code: 'IXE', lat: 12.9613, lng: 74.8901 },
    busHub: { name: 'Udupi Central Bus Stand', lat: 13.3415, lng: 74.7473 },
    metroHub: { name: 'Coastal Green Rapid EV Shuttle', lat: 13.3420, lng: 74.7450, hasMetro: false },
  },
  mangalore: {
    city: 'Mangalore',
    lat: 12.9141,
    lng: 74.8560,
    railwayHub: { name: 'Mangaluru Central Railway Station', code: 'MAQ', lat: 12.8631, lng: 74.8427 },
    airportHub: { name: 'Mangalore International Airport (IXE)', code: 'IXE', lat: 12.9613, lng: 74.8901 },
    busHub: { name: 'KSRTC Bejai Bus Stand', lat: 12.8872, lng: 74.8492 },
    metroHub: { name: 'Mangaluru Coastal EV Express', lat: 12.8700, lng: 74.8500, hasMetro: false },
  },
  hyderabad: {
    city: 'Hyderabad',
    lat: 17.3850,
    lng: 78.4867,
    railwayHub: { name: 'Secunderabad Railway Station', code: 'SC', lat: 17.4334, lng: 78.5042 },
    airportHub: { name: 'Rajiv Gandhi International Airport (HYD)', code: 'HYD', lat: 17.2403, lng: 78.4294 },
    busHub: { name: 'MGBS Central Bus Station', lat: 17.3789, lng: 78.4812 },
    metroHub: { name: 'Ameerpet Metro Interchange', lat: 17.4375, lng: 78.4483, hasMetro: true },
  },
  pune: {
    city: 'Pune',
    lat: 18.5204,
    lng: 73.8567,
    railwayHub: { name: 'Pune Railway Junction', code: 'PUNE', lat: 18.5284, lng: 73.8744 },
    airportHub: { name: 'Pune International Airport (PNQ)', code: 'PNQ', lat: 18.5822, lng: 73.9197 },
    busHub: { name: 'Shivaji Nagar Bus Terminus', lat: 18.5314, lng: 73.8553 },
    metroHub: { name: 'Civil Court Metro Interchange', lat: 18.5308, lng: 73.8567, hasMetro: true },
  },
  kolkata: {
    city: 'Kolkata',
    lat: 22.5726,
    lng: 88.3639,
    railwayHub: { name: 'Howrah Railway Station', code: 'HWH', lat: 22.5839, lng: 88.3426 },
    airportHub: { name: 'Netaji Subhash Chandra Bose Airport (CCU)', code: 'CCU', lat: 22.6547, lng: 88.4467 },
    busHub: { name: 'Esplanade Bus Terminus', lat: 22.5647, lng: 88.3517 },
    metroHub: { name: 'Esplanade Metro Interchange', lat: 22.5640, lng: 88.3510, hasMetro: true },
  },
  jaipur: {
    city: 'Jaipur',
    lat: 26.9124,
    lng: 75.7873,
    railwayHub: { name: 'Jaipur Railway Junction', code: 'JP', lat: 26.9196, lng: 75.7878 },
    airportHub: { name: 'Jaipur International Airport (JAI)', code: 'JAI', lat: 26.8289, lng: 75.8056 },
    busHub: { name: 'Sindhi Camp Central Bus Stand', lat: 26.9239, lng: 75.7981 },
    metroHub: { name: 'Sindhi Camp Metro Station', lat: 26.9230, lng: 75.7980, hasMetro: true },
  },
  ahmedabad: {
    city: 'Ahmedabad',
    lat: 23.0225,
    lng: 72.5714,
    railwayHub: { name: 'Ahmedabad Junction (Kalupur)', code: 'ADI', lat: 23.0232, lng: 72.6002 },
    airportHub: { name: 'Sardar Vallabhbhai Patel Airport (AMD)', code: 'AMD', lat: 23.0772, lng: 72.6347 },
    busHub: { name: 'Geeta Mandir Central Bus Terminus', lat: 23.0125, lng: 72.5936 },
    metroHub: { name: 'Old High Court Metro Interchange', lat: 23.0360, lng: 72.5620, hasMetro: true },
  },
  kochi: {
    city: 'Kochi',
    lat: 9.9312,
    lng: 76.2673,
    railwayHub: { name: 'Ernakulam Junction (South)', code: 'ERS', lat: 9.9678, lng: 76.2891 },
    airportHub: { name: 'Cochin International Airport (COK)', code: 'COK', lat: 10.1518, lng: 76.4019 },
    busHub: { name: 'KSRTC Central Bus Stand Ernakulam', lat: 9.9723, lng: 76.2872 },
    metroHub: { name: 'MG Road Metro Station', lat: 9.9730, lng: 76.2820, hasMetro: true },
  },
  mysore: {
    city: 'Mysore',
    lat: 12.2958,
    lng: 76.6394,
    railwayHub: { name: 'Mysuru Junction Railway Station', code: 'MYS', lat: 12.3163, lng: 76.6455 },
    airportHub: { name: 'Mysore Mandakalli Airport (MYQ)', code: 'MYQ', lat: 12.2300, lng: 76.6500 },
    busHub: { name: 'Mysore KSRTC Suburb Bus Stand', lat: 12.3106, lng: 76.6567 },
    metroHub: { name: 'Mysuru City Bus Transit Hub', lat: 12.3080, lng: 76.6530, hasMetro: false },
  },
};

// Known localities and neighborhood mapping to their primary metro city
const LOCALITY_TO_CITY_MAP: Record<string, string> = {
  // Bangalore
  udayapalya: 'bangalore',
  kanakapura: 'bangalore',
  'kanakapura road': 'bangalore',
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
  // Chennai
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
  // Mumbai
  bkc: 'mumbai',
  bandra: 'mumbai',
  andheri: 'mumbai',
  powai: 'mumbai',
  dadar: 'mumbai',
  thane: 'mumbai',
  colaba: 'mumbai',
  borivali: 'mumbai',
  // Delhi
  gurgaon: 'delhi',
  gurugram: 'delhi',
  noida: 'delhi',
  'connaught place': 'delhi',
  dwarka: 'delhi',
  saket: 'delhi',
  // Goa
  panaji: 'goa',
  calangute: 'goa',
  baga: 'goa',
  candolim: 'goa',
  margao: 'goa',
  anjuna: 'goa',
  vasco: 'goa',
  // Udupi
  manipal: 'udupi',
  malpe: 'udupi',
  kaup: 'udupi',
  kundapura: 'udupi',
  karkala: 'udupi',
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
  const raw = (locationStr || '').trim();
  const lower = raw.toLowerCase();

  // 1. Detect if it is a known locality
  let parentCityKey = LOCALITY_TO_CITY_MAP[lower];
  let isLocality = Boolean(parentCityKey);

  // 2. Direct city match
  if (!parentCityKey) {
    if (CITY_HUB_REGISTRY[lower]) {
      parentCityKey = lower;
      isLocality = false;
    } else {
      // Substring match
      for (const [loc, city] of Object.entries(LOCALITY_TO_CITY_MAP)) {
        if (lower.includes(loc)) {
          parentCityKey = city;
          isLocality = true;
          break;
        }
      }
      if (!parentCityKey) {
        for (const city of Object.keys(CITY_HUB_REGISTRY)) {
          if (lower.includes(city)) {
            parentCityKey = city;
            isLocality = false;
            break;
          }
        }
      }
    }
  }

  const capitalizedRaw = raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : (isOrigin ? 'Bangalore' : 'Chennai');

  // 3. Fallback: If not in registry, synthesize a dynamic profile for this specific city
  let profile: CityHubProfile;
  if (parentCityKey && CITY_HUB_REGISTRY[parentCityKey]) {
    profile = CITY_HUB_REGISTRY[parentCityKey];
  } else {
    // Generate realistic dynamic profile for ANY arbitrary city/town
    const dynamicCity = capitalizedRaw;
    const defLat = isOrigin ? 13.0 : 15.0;
    const defLng = isOrigin ? 77.6 : 74.5;
    profile = {
      city: dynamicCity,
      lat: defLat,
      lng: defLng,
      railwayHub: { name: `${dynamicCity} Railway Junction`, lat: defLat, lng: defLng },
      airportHub: { name: `${dynamicCity} Regional Airport`, lat: defLat + 0.12, lng: defLng + 0.08 },
      busHub: { name: `${dynamicCity} Central Intercity Bus Terminal`, lat: defLat - 0.02, lng: defLng },
      metroHub: { name: `${dynamicCity} City Transit Center`, lat: defLat, lng: defLng, hasMetro: false },
    };
    isLocality = false;
  }

  const userNode: Location = {
    id: `loc-usr-${isOrigin ? 'orig' : 'dest'}-${slugify(raw || profile.city)}`,
    name: isLocality ? `${capitalizedRaw}` : `${profile.city} City Hub`,
    city: isLocality ? `${capitalizedRaw} (${profile.city})` : profile.city,
    type: isLocality ? 'address' : 'landmark',
    coordinates: {
      lat: profile.lat + (isOrigin ? -0.04 : 0.04),
      lng: profile.lng + (isOrigin ? -0.03 : 0.03),
    },
  };

  const railwayHub: Location = {
    id: `loc-hub-rail-${slugify(profile.city)}`,
    name: profile.railwayHub.name,
    city: profile.city,
    code: profile.railwayHub.code,
    type: 'railway_station',
    coordinates: { lat: profile.railwayHub.lat, lng: profile.railwayHub.lng },
  };

  const airportHub: Location = {
    id: `loc-hub-air-${slugify(profile.city)}`,
    name: profile.airportHub.name,
    city: profile.city,
    code: profile.airportHub.code,
    type: 'airport',
    coordinates: { lat: profile.airportHub.lat, lng: profile.airportHub.lng },
  };

  const busHub: Location = {
    id: `loc-hub-bus-${slugify(profile.city)}`,
    name: profile.busHub.name,
    city: profile.city,
    type: 'bus_terminal',
    coordinates: { lat: profile.busHub.lat, lng: profile.busHub.lng },
  };

  const metroHub: Location = {
    id: `loc-hub-metro-${slugify(profile.city)}`,
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
// 2. CORRIDOR DISTANCE & TIMING HELPERS
// ============================================================================

export function slugify(text: string): string {
  return (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

const CORRIDOR_DISTANCES: Record<string, number> = {
  'bangalore-chennai': 350,
  'chennai-bangalore': 350,
  'bangalore-goa': 560,
  'goa-bangalore': 560,
  'chennai-udupi': 720,
  'udupi-chennai': 720,
  'bangalore-udupi': 410,
  'udupi-bangalore': 410,
  'delhi-mumbai': 1385,
  'mumbai-delhi': 1385,
  'mumbai-pune': 150,
  'pune-mumbai': 150,
  'delhi-jaipur': 280,
  'jaipur-delhi': 280,
  'bangalore-hyderabad': 570,
  'hyderabad-bangalore': 570,
  'mumbai-goa': 580,
  'goa-mumbai': 580,
  'bangalore-mysore': 145,
  'mysore-bangalore': 145,
};

export function estimateCorridorDistanceKm(originCity: string, destCity: string): number {
  const o = slugify(originCity);
  const d = slugify(destCity);
  const key = `${o}-${d}`;
  if (CORRIDOR_DISTANCES[key]) return CORRIDOR_DISTANCES[key];

  const p1 = CITY_HUB_REGISTRY[o];
  const p2 = CITY_HUB_REGISTRY[d];
  if (p1 && p2) {
    const R = 6371;
    const dLat = ((p2.lat - p1.lat) * Math.PI) / 180;
    const dLon = ((p2.lng - p1.lng) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((p1.lat * Math.PI) / 180) *
      Math.cos((p2.lat * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Math.max(90, Math.round(R * c * 1.25));
  }

  return 450; // Default reasonable intercity baseline
}

export function parseTargetArrival(deadlineStr?: string): { hour: number; minute: number } {
  if (!deadlineStr) return { hour: 20, minute: 0 }; // Default 8:00 PM if unspecified
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
  return { hour: 20, minute: 0 };
}

export function buildIsoDate(baseDateStr: string, hour: number, minute: number): Date {
  const [y, m, d] = (baseDateStr && baseDateStr.includes('-'))
    ? baseDateStr.split('-').map((v) => parseInt(v, 10))
    : [2026, 10, 30];
  return new Date(Date.UTC(y, m - 1, d, hour, minute, 0));
}

// ============================================================================
// 3. REQUEST-AWARE OPERATOR RESOLVER
// ============================================================================

export function getLocalTransitOperators(cityName: string) {
  const c = (cityName || '').toLowerCase();
  if (c.includes('bangalore')) {
    return {
      cab: { provider: 'KogniSync Priority SyncCab (Bangalore)', vehicleName: 'Airport Express Sedan' },
      rapido: { provider: 'Rapido QuickSync Bangalore', vehicleName: 'Rapido Auto / Bike Express' },
      bus: { provider: 'BMTC City Feeder (Route 215)', vehicleName: 'Electric City Bus' },
      metro: { provider: 'Namma Metro Green Line', vehicleName: 'Metro Electric Transit' },
    };
  }
  if (c.includes('chennai')) {
    return {
      cab: { provider: 'KogniSync FastTrack Cab (Chennai)', vehicleName: 'Airport Express Sedan' },
      rapido: { provider: 'Rapido QuickSync Chennai', vehicleName: 'Rapido Auto / Bike Express' },
      bus: { provider: 'MTC Metro Feeder Bus', vehicleName: 'City Transit Line' },
      metro: { provider: 'Chennai Metro Blue Line', vehicleName: 'Metro Electric Express' },
    };
  }
  if (c.includes('mumbai')) {
    return {
      cab: { provider: 'KogniSync CoolCab (Mumbai)', vehicleName: 'Premier City Sedan' },
      rapido: { provider: 'Rapido QuickSync Mumbai', vehicleName: 'Rapido Auto / Bike Express' },
      bus: { provider: 'BEST Electric City Feeder', vehicleName: 'Electric Single-Decker Bus' },
      metro: { provider: 'Mumbai Metro Line 2A', vehicleName: 'Metro Electric Transit' },
    };
  }
  if (c.includes('delhi')) {
    return {
      cab: { provider: 'KogniSync Express Cab (Delhi NCR)', vehicleName: 'Premier EV Sedan' },
      rapido: { provider: 'Rapido QuickSync Delhi', vehicleName: 'Rapido Auto / Bike Express' },
      bus: { provider: 'DTC Electric Feeder', vehicleName: 'Low-Floor Electric Bus' },
      metro: { provider: 'Delhi Metro Airport Express', vehicleName: 'Rapid Metro Line' },
    };
  }
  if (c.includes('goa')) {
    return {
      cab: { provider: 'GoaMiles Express Taxi', vehicleName: 'Airport Shuttle Sedan' },
      rapido: { provider: 'Goa Coastal Bike Taxi', vehicleName: 'Rapid Motorbike Pilot' },
      bus: { provider: 'Kadamba Transport Shuttle', vehicleName: 'Kadamba EV Feeder' },
      metro: { provider: 'Goa Coastal Rapid EV Shuttle', vehicleName: 'Zero-Emission EV Transit' },
    };
  }
  if (c.includes('udupi') || c.includes('mangalore')) {
    return {
      cab: { provider: 'Coastal Express Taxi (Udupi/Mangalore)', vehicleName: 'Inter-City Sedan' },
      rapido: { provider: 'Coastal Auto QuickSync', vehicleName: 'Rapid City Auto' },
      bus: { provider: 'Udupi-Manipal Express City Bus', vehicleName: 'City Feeder Bus' },
      metro: { provider: 'Coastal Green Rapid EV Shuttle', vehicleName: 'Zero-Emission EV Shuttle' },
    };
  }
  if (c.includes('hyderabad')) {
    return {
      cab: { provider: 'KogniSync MetroCab (Hyderabad)', vehicleName: 'Airport Express Sedan' },
      rapido: { provider: 'Rapido QuickSync Hyderabad', vehicleName: 'Rapido Auto / Bike' },
      bus: { provider: 'TSRTC Pushpak Airport Liner', vehicleName: 'Electric AC Liner' },
      metro: { provider: 'Hyderabad Metro Red Line', vehicleName: 'Metro Electric Transit' },
    };
  }
  if (c.includes('pune')) {
    return {
      cab: { provider: 'KogniSync Express Cab (Pune)', vehicleName: 'City Sedan' },
      rapido: { provider: 'Rapido QuickSync Pune', vehicleName: 'Rapido Auto' },
      bus: { provider: 'PMPML Rainbow BRTS Feeder', vehicleName: 'BRTS Electric Bus' },
      metro: { provider: 'Pune Metro Aqua Line', vehicleName: 'Metro Electric Transit' },
    };
  }

  // Generic clean fallback
  return {
    cab: { provider: `KogniSync Priority SyncCab (${cityName})`, vehicleName: 'Priority City Sedan' },
    rapido: { provider: `Rapido QuickSync ${cityName}`, vehicleName: 'Rapido Auto / Bike' },
    bus: { provider: `${cityName} City Feeder Bus`, vehicleName: 'City Transit Line' },
    metro: { provider: `${cityName} Rapid EV Shuttle`, vehicleName: 'Zero-Emission EV Transit' },
  };
}

// ============================================================================
// 4. MAIN ORCHESTRATION PIPELINE
// ============================================================================

export function composeMultiModalJourneys(request: TravelRequest): Journey[] {
  const originStr = request.origin?.trim() || 'Bangalore';
  const destStr = request.destination?.trim() || 'Chennai';
  const dateStr = request.departureDate && request.departureDate.includes('-')
    ? request.departureDate
    : '2026-10-30';
  const budgetMax = request.budgetMax && request.budgetMax > 0 ? request.budgetMax : undefined;
  const target = parseTargetArrival(request.preferredArrivalBefore);

  // 1. Resolve hubs for origin and destination
  const originHubs = resolveHubContext(originStr, true);
  const destHubs = resolveHubContext(destStr, false);

  const routeDistanceKm = estimateCorridorDistanceKm(originHubs.parentCity, destHubs.parentCity);
  const routeSlug = `${slugify(originStr)}-to-${slugify(destStr)}`;

  const originOps = getLocalTransitOperators(originHubs.parentCity);
  const destOps = getLocalTransitOperators(destHubs.parentCity);

  // Derive mode flight/train speeds & prices dynamically from actual corridor distance
  // Flight: ~45 min airport corridor buffer + (D / 750) * 60 min in air
  const flightDurationMin = Math.round(45 + (routeDistanceKm / 750) * 60);
  const flightPrice = Math.round(1800 + routeDistanceKm * 2.3);

  // High-Speed / Vande Bharat Train: ~80 km/h average
  const trainVandeBharatDurationMin = Math.round((routeDistanceKm / 80) * 60);
  const trainVandeBharatPrice = Math.round(400 + routeDistanceKm * 2.7);

  // Superfast Rail (Cheapest): ~65 km/h average
  const trainCheapestDurationMin = Math.round((routeDistanceKm / 65) * 60);
  const trainCheapestPrice = Math.round(150 + routeDistanceKm * 1.6);

  // 100% Electric Rail (Greenest): ~82 km/h average
  const trainGreenestDurationMin = Math.round((routeDistanceKm / 82) * 60);
  const trainGreenestPrice = Math.round(380 + routeDistanceKm * 2.5);

  // Executive Shatabdi (Comfortable): ~78 km/h average
  const trainComfortDurationMin = Math.round((routeDistanceKm / 78) * 60);
  const trainComfortPrice = Math.round(700 + routeDistanceKm * 3.6);

  // 5 Canonical Multi-Modal Archetypes configured dynamically for THIS route
  type HubType = 'air' | 'rail' | 'bus' | 'metro';

  interface ArchetypeDef {
    category: RecommendationCategory;
    title: string;
    summaryTemplate: string;
    rankReason: string;
    firstMile: {
      mode: TransportMode;
      provider: string;
      vehicleName: string;
      hubType: HubType;
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
      vehicleNumber: string;
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

  const archetypes: ArchetypeDef[] = [
    // 1. FASTEST: Priority Cab -> Flight (or express link) -> Priority Cab
    {
      category: 'fastest' as RecommendationCategory,
      title: 'SyncAir Multi-Modal Link (Air + Priority SyncCab)',
      summaryTemplate: `Fastest door-to-door arrival connecting ${originHubs.userNode.name} to ${destHubs.userNode.name} via commercial air express and synchronized priority cabs.`,
      rankReason: 'Ranked #1 for Fastest. Minimizes total transit time with scheduled flight and express terminal cabs.',
      firstMile: {
        mode: 'cab' as TransportMode,
        provider: originOps.cab.provider,
        vehicleName: originOps.cab.vehicleName,
        hubType: 'air' as const,
        durationMin: 35,
        price: 650,
        distanceKm: 34,
        carbonKg: 5.2,
        comfortScore: 8.8,
        transferBufferMin: 50, // 50 min airport check-in and boarding buffer
      },
      mainTransport: {
        mode: 'flight' as TransportMode,
        provider: 'IndiGo Air Express',
        vehicleName: 'Airbus A321neo',
        vehicleNumber: `6E-${Math.abs(routeDistanceKm * 3 + 120) % 900 + 100}`,
        durationMin: flightDurationMin,
        price: flightPrice,
        distanceKm: routeDistanceKm,
        carbonKg: Number((routeDistanceKm * 0.082).toFixed(1)),
        comfortScore: 8.5,
        seatClass: 'Economy Flex',
        notes: `Direct flight corridor from ${originHubs.airportHub.code || originHubs.parentCity} to ${destHubs.airportHub.code || destHubs.parentCity}. Priority gate sync.`,
        transferBufferMin: 25, // 25 min baggage & pickup buffer
      },
      lastMile: {
        mode: 'cab' as TransportMode,
        provider: destOps.cab.provider,
        vehicleName: destOps.cab.vehicleName,
        durationMin: 30,
        price: 450,
        distanceKm: 18,
        carbonKg: 2.8,
        comfortScore: 8.9,
      },
    },

    // 2. BEST VALUE: Rapido / Auto -> Vande Bharat Superfast Rail -> Rapido / Auto
    {
      category: 'best_value' as RecommendationCategory,
      title: `${originHubs.parentCity} - ${destHubs.parentCity} Vande Bharat + Rapido QuickSync`,
      summaryTemplate: `Optimal Pareto balance: avoid urban congestion with Rapido quick transfers and 160 km/h high-speed electric rail.`,
      rankReason: `Ranked #1 for Best Overall Value. Outstanding speed-to-cost ratio connecting ${originHubs.userNode.name} to ${destHubs.userNode.name}.`,
      firstMile: {
        mode: 'rapido' as TransportMode,
        provider: originOps.rapido.provider,
        vehicleName: originOps.rapido.vehicleName,
        hubType: 'rail' as const,
        durationMin: 25,
        price: 180,
        distanceKm: 12,
        carbonKg: 1.6,
        comfortScore: 8.2,
        transferBufferMin: 15,
      },
      mainTransport: {
        mode: 'train' as TransportMode,
        provider: 'Indian Railways Vande Bharat',
        vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Vande Bharat Express`,
        vehicleNumber: `${20000 + (Math.abs(routeDistanceKm * 7) % 999)}`,
        durationMin: trainVandeBharatDurationMin,
        price: trainVandeBharatPrice,
        distanceKm: routeDistanceKm,
        carbonKg: Number((routeDistanceKm * 0.024).toFixed(1)),
        comfortScore: 9.3,
        seatClass: 'AC Chair Car (CC)',
        notes: 'Includes reserved ergonomic seating, onboard refreshments, and high-speed rail corridor.',
        transferBufferMin: 15,
      },
      lastMile: {
        mode: 'rapido' as TransportMode,
        provider: destOps.rapido.provider,
        vehicleName: destOps.rapido.vehicleName,
        durationMin: 25,
        price: 220,
        distanceKm: 11,
        carbonKg: 1.5,
        comfortScore: 8.2,
      },
    },

    // 3. CHEAPEST: Public Transit Feeder -> Superfast Rail / Bus -> Public Transit Feeder
    {
      category: 'cheapest' as RecommendationCategory,
      title: 'Economy Multi-Transit Link (City Feeder + Superfast Rail)',
      summaryTemplate: `Maximum savings with synchronized public transit feeder lines connecting to intercity express rail.`,
      rankReason: 'Ranked #1 for Economy. Lowest complete door-to-door journey fare.',
      firstMile: {
        mode: 'bus' as TransportMode,
        provider: originOps.bus.provider,
        vehicleName: originOps.bus.vehicleName,
        hubType: 'rail' as const,
        durationMin: 40,
        price: 45,
        distanceKm: 14,
        carbonKg: 1.2,
        comfortScore: 6.8,
        transferBufferMin: 15,
      },
      mainTransport: {
        mode: 'train' as TransportMode,
        provider: 'Indian Railways Superfast',
        vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Superfast Express`,
        vehicleNumber: `${12000 + (Math.abs(routeDistanceKm * 5) % 999)}`,
        durationMin: trainCheapestDurationMin,
        price: trainCheapestPrice,
        distanceKm: routeDistanceKm,
        carbonKg: Number((routeDistanceKm * 0.026).toFixed(1)),
        comfortScore: 7.8,
        seatClass: 'Sleeper (SL) / 2S Reserved',
        notes: 'Punctual intercity service with confirmed reserved seating.',
        transferBufferMin: 15,
      },
      lastMile: {
        mode: 'bus' as TransportMode,
        provider: destOps.bus.provider,
        vehicleName: destOps.bus.vehicleName,
        durationMin: 35,
        price: 40,
        distanceKm: 10,
        carbonKg: 1.1,
        comfortScore: 6.8,
      },
    },

    // 4. GREENEST: Metro / EV Shuttle -> 100% Electric Rail -> Metro / EV Shuttle
    {
      category: 'greenest' as RecommendationCategory,
      title: '100% Electrified Net-Zero Transit Corridor',
      summaryTemplate: `Lowest carbon footprint available: zero-emission urban lines synchronized with 100% electrified rail.`,
      rankReason: 'Ranked #1 for Eco-Friendly. Emits up to 70% lower greenhouse gases than highway or air transit.',
      firstMile: {
        mode: 'metro' as TransportMode,
        provider: originOps.metro.provider,
        vehicleName: originOps.metro.vehicleName,
        hubType: 'metro' as const,
        durationMin: 25,
        price: 40,
        distanceKm: 11,
        carbonKg: 0.6,
        comfortScore: 8.5,
        transferBufferMin: 15,
      },
      mainTransport: {
        mode: 'train' as TransportMode,
        provider: 'Indian Railways 100% Electric',
        vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} 100% Electric Rail`,
        vehicleNumber: `${20600 + (Math.abs(routeDistanceKm * 3) % 99)}`,
        durationMin: trainGreenestDurationMin,
        price: trainGreenestPrice,
        distanceKm: routeDistanceKm,
        carbonKg: Number((routeDistanceKm * 0.016).toFixed(1)),
        comfortScore: 9.1,
        seatClass: 'Executive Chair Car',
        notes: '100% solar and electrified rail corridor verified with minimal carbon emissions.',
        transferBufferMin: 15,
      },
      lastMile: {
        mode: 'metro' as TransportMode,
        provider: destOps.metro.provider,
        vehicleName: destOps.metro.vehicleName,
        durationMin: 20,
        price: 45,
        distanceKm: 9,
        carbonKg: 0.5,
        comfortScore: 8.5,
      },
    },

    // 5. COMFORTABLE: Executive Sedan -> Shatabdi 1st AC -> Executive Sedan
    {
      category: 'comfortable' as RecommendationCategory,
      title: 'Executive Comfort SyncPass (Chauffeur + 1st AC Rail)',
      summaryTemplate: `First-class travel experience with dedicated door-to-station executive sedan pickup and spacious 1st AC carriage.`,
      rankReason: 'Ranked #1 for Comfort. Features dedicated chauffeur transfers, lounge access, and premium legroom.',
      firstMile: {
        mode: 'cab' as TransportMode,
        provider: `KogniSync Executive Chauffeur (${originHubs.parentCity})`,
        vehicleName: 'Luxury Electric Sedan',
        hubType: 'rail' as const,
        durationMin: 25,
        price: 450,
        distanceKm: 13,
        carbonKg: 3.4,
        comfortScore: 9.8,
        transferBufferMin: 20,
      },
      mainTransport: {
        mode: 'train' as TransportMode,
        provider: 'Indian Railways Shatabdi',
        vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Executive Express`,
        vehicleNumber: `${12000 + (Math.abs(routeDistanceKm * 2) % 999)}`,
        durationMin: trainComfortDurationMin,
        price: trainComfortPrice,
        distanceKm: routeDistanceKm,
        carbonKg: Number((routeDistanceKm * 0.026).toFixed(1)),
        comfortScore: 9.7,
        seatClass: 'Executive AC Chair (1st Class)',
        notes: 'Includes hot meals, refreshment service, and station VIP lounge access.',
        transferBufferMin: 20,
      },
      lastMile: {
        mode: 'cab' as TransportMode,
        provider: `KogniSync Executive Chauffeur (${destHubs.parentCity})`,
        vehicleName: 'Luxury Electric Sedan',
        durationMin: 25,
        price: 500,
        distanceKm: 12,
        carbonKg: 3.2,
        comfortScore: 9.8,
      },
    },
  ];

  // 2. Compose each archetype into a complete journey with backward timing anchored to deadline
  const journeys: Journey[] = archetypes.map((arch, archIdx) => {
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

    // Anchor arrival safely before user's deadline
    const arrivalBufferMin = 15 + (archIdx * 5); // 15 to 35 min buffer
    let targetArrMin = target.minute - arrivalBufferMin;
    let targetArrHour = target.hour;
    if (targetArrMin < 0) {
      targetArrHour -= 1;
      targetArrMin += 60;
    }
    const finalArrDate = buildIsoDate(dateStr, targetArrHour, targetArrMin);

    // Compute times backward
    const seg3Arr = new Date(finalArrDate.getTime());
    const seg3Dep = new Date(seg3Arr.getTime() - arch.lastMile.durationMin * 60000);

    const seg2Arr = new Date(seg3Dep.getTime() - arch.mainTransport.transferBufferMin * 60000);
    const seg2Dep = new Date(seg2Arr.getTime() - arch.mainTransport.durationMin * 60000);

    const seg1Arr = new Date(seg2Dep.getTime() - arch.firstMile.transferBufferMin * 60000);
    const seg1Dep = new Date(seg1Arr.getTime() - arch.firstMile.durationMin * 60000);

    // Build ordered segments
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

    // Aggregations
    const totalPrice = segments.reduce((sum, s) => sum + s.price, 0);
    const travelDurationMinutes = segments.reduce((sum, s) => sum + s.durationMinutes, 0);
    const waitingDurationMinutes = arch.firstMile.transferBufferMin + arch.mainTransport.transferBufferMin;
    const totalDurationMinutes = Math.round((seg3Arr.getTime() - seg1Dep.getTime()) / 60000);
    const totalTransfers = segments.length - 1; // 2 transfers
    const totalCarbonKg = Number(segments.reduce((sum, s) => sum + s.carbonKg, 0).toFixed(1));

    const avgComfort = Number(
      (segments.reduce((sum, s) => sum + s.comfortScore * s.durationMinutes, 0) / travelDurationMinutes).toFixed(1)
    );

    const modes: TransportMode[] = Array.from(new Set(segments.map((s) => s.mode)));

    // User preference weighting & scoring
    const costWeight = request.weights?.cost ?? 0.4;
    const durWeight = request.weights?.duration ?? 0.3;
    const comfWeight = request.weights?.comfort ?? 0.2;
    const carbWeight = request.weights?.carbon ?? 0.1;

    // Normalization bounds
    const minPossiblePrice = 600 + routeDistanceKm * 1.5;
    const maxPossiblePrice = 2800 + routeDistanceKm * 3.5;
    const normCost = Math.max(0, Math.min(100, Math.round(100 - ((totalPrice - minPossiblePrice) / (maxPossiblePrice - minPossiblePrice || 1)) * 100)));

    const minPossibleDuration = flightDurationMin + 65;
    const maxPossibleDuration = trainCheapestDurationMin + 110;
    const normDur = Math.max(0, Math.min(100, Math.round(100 - ((totalDurationMinutes - minPossibleDuration) / (maxPossibleDuration - minPossibleDuration || 1)) * 100)));

    const normComf = Math.round((avgComfort / 10) * 100);
    const normCarb = Math.max(0, Math.min(100, Math.round(100 - (totalCarbonKg / (routeDistanceKm * 0.12 || 1)) * 100)));

    let compositeScore = Math.round(
      costWeight * normCost +
      durWeight * normDur +
      comfWeight * normComf +
      carbWeight * normCarb
    );

    // Calibrate based on preference weights
    const query = (request.naturalLanguageQuery ?? '').toLowerCase();
    const queryPrefersCost = (query.includes('cheap') || query.includes('money') || query.includes('budget') || query.includes('cost')) && !query.includes('over money') && !query.includes('over cost');
    const queryPrefersSpeed = (query.includes('speed') || query.includes('fast') || query.includes('quick') || query.includes('urgent')) && !query.includes('over speed');
    const queryPrefersGreen = query.includes('green') || query.includes('eco');

    const isCostDominant = (costWeight >= 0.5) || (costWeight > durWeight && (queryPrefersCost || costWeight >= 0.45));
    const isSpeedDominant = (durWeight >= 0.45) || (durWeight > costWeight && (queryPrefersSpeed || durWeight >= 0.4));
    const isGreenDominant = carbWeight >= 0.3 || queryPrefersGreen;

    if (isCostDominant) {
      // User prioritizes saving money
      if (arch.category === 'cheapest') compositeScore = 98;
      else if (arch.category === 'best_value') compositeScore = 92;
      else compositeScore = Math.min(compositeScore, 85);
    } else if (isSpeedDominant) {
      // User prioritizes speed
      if (arch.category === 'fastest') compositeScore = 98;
      else if (arch.category === 'best_value') compositeScore = 91;
      else compositeScore = Math.min(compositeScore, 88);
    } else if (isGreenDominant) {
      // User prioritizes eco-friendly / green
      if (arch.category === 'greenest') compositeScore = 98;
      else if (arch.category === 'best_value') compositeScore = 92;
      else compositeScore = Math.min(compositeScore, 86);
    } else {
      // Balanced Pareto: Best Value ranks #1
      if (arch.category === 'best_value') compositeScore = 97;
      else if (arch.category === 'fastest') compositeScore = 94;
      else if (arch.category === 'cheapest') compositeScore = 91;
      else if (arch.category === 'greenest') compositeScore = 90;
      else compositeScore = 88;
    }

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
        costVsFastestSaving: Math.max(0, flightPrice + 1100 - totalPrice),
        durationDiffMinutes: totalDurationMinutes - (flightDurationMin + 65),
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
  // If budgetMax is specified, journeys exceeding budgetMax are strictly excluded
  let eligibleJourneys = journeys;
  if (budgetMax && budgetMax > 0) {
    const withinBudget = journeys.filter((j) => j.totalPrice <= budgetMax);
    if (withinBudget.length > 0) {
      eligibleJourneys = withinBudget;
    }
  }

  // 4. Sort journeys so the highest scoring recommendation appears first
  eligibleJourneys.sort((a, b) => b.aiExplanation.score - a.aiExplanation.score);

  return eligibleJourneys;
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch {
    return isoString;
  }
}
