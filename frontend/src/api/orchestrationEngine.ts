import {
  Journey,
  JourneyProvenance,
  JourneySegment,
  Location,
  RecommendationCategory,
  SegmentProvenance,
  TransportMode,
  TravelRequest,
} from '../types/journey';
import { optimizeCandidateJourneys } from '../utils/optimizer';

// ============================================================================
// 1. COMPREHENSIVE CITY & HUB REGISTRY
// ============================================================================

export interface CityHubProfile {
  city: string;
  lat: number;
  lng: number;
  railwayHub: { name: string; code?: string; lat: number; lng: number };
  airportHub?: { name: string; code?: string; lat: number; lng: number };
  busHub: { name: string; lat: number; lng: number };
  metroHub?: { name: string; lat: number; lng: number; hasMetro: boolean };
  hasMetro: boolean;
  hasAirport: boolean;
  hasLocalAirport?: boolean;
  isAirportGateway?: boolean;
  airportGatewayCity?: string;
  airportCity?: string;
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
    hasMetro: true,
    hasAirport: true,
  },
  chennai: {
    city: 'Chennai',
    lat: 13.0827,
    lng: 80.2707,
    railwayHub: { name: 'Chennai Central Railway Station', code: 'MAS', lat: 13.0827, lng: 80.2755 },
    airportHub: { name: 'Chennai International Airport (MAA)', code: 'MAA', lat: 12.9941, lng: 80.1709 },
    busHub: { name: 'Koyambedu Bus Terminal (CMBT)', lat: 13.0682, lng: 80.2052 },
    metroHub: { name: 'Central Metro Interchange Hub', lat: 13.0818, lng: 80.2735, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  mumbai: {
    city: 'Mumbai',
    lat: 19.0760,
    lng: 72.8777,
    railwayHub: { name: 'Chhatrapati Shivaji Maharaj Terminus (CSMT)', code: 'CSMT', lat: 18.9401, lng: 72.8354 },
    airportHub: { name: 'Chhatrapati Shivaji International Airport (BOM)', code: 'BOM', lat: 19.0896, lng: 72.8656 },
    busHub: { name: 'Dadar Intercity Bus Terminal', lat: 19.0178, lng: 72.8478 },
    metroHub: { name: 'Andheri Metro Interchange', lat: 19.1197, lng: 72.8464, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  delhi: {
    city: 'Delhi',
    lat: 28.6139,
    lng: 77.2090,
    railwayHub: { name: 'New Delhi Railway Station (NDLS)', code: 'NDLS', lat: 28.6429, lng: 77.2195 },
    airportHub: { name: 'Indira Gandhi International Airport (DEL)', code: 'DEL', lat: 28.5562, lng: 77.1000 },
    busHub: { name: 'ISBT Kashmere Gate Terminal', lat: 28.6675, lng: 77.2289 },
    metroHub: { name: 'Rajiv Chowk Metro Hub', lat: 28.6328, lng: 77.2197, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  goa: {
    city: 'Goa',
    lat: 15.2993,
    lng: 74.1240,
    railwayHub: { name: 'Madgaon Railway Junction', code: 'MAO', lat: 15.2736, lng: 73.9582 },
    airportHub: { name: 'Goa Dabolim Airport (GOI)', code: 'GOI', lat: 15.3808, lng: 73.8314 },
    busHub: { name: 'Panaji KADAMBA Bus Stand', lat: 15.4989, lng: 73.8278 },
    hasMetro: false,
    hasAirport: true,
  },
  udupi: {
    city: 'Udupi',
    lat: 13.3409,
    lng: 74.7421,
    railwayHub: { name: 'Udupi Railway Station', code: 'UD', lat: 13.3409, lng: 74.7421 },
    airportHub: { name: 'Mangalore International Airport (IXE)', code: 'IXE', lat: 12.9613, lng: 74.8901 },
    busHub: { name: 'Udupi Central Bus Stand', lat: 13.3415, lng: 74.7473 },
    hasMetro: false,
    hasAirport: true,
    hasLocalAirport: false,
    isAirportGateway: true,
    airportGatewayCity: 'Mangalore',
    airportCity: 'Mangalore',
  },
  mangalore: {
    city: 'Mangalore',
    lat: 12.9141,
    lng: 74.8560,
    railwayHub: { name: 'Mangaluru Central Railway Station', code: 'MAQ', lat: 12.8631, lng: 74.8427 },
    airportHub: { name: 'Mangalore International Airport (IXE)', code: 'IXE', lat: 12.9613, lng: 74.8901 },
    busHub: { name: 'KSRTC Bejai Bus Stand', lat: 12.8872, lng: 74.8492 },
    hasMetro: false,
    hasAirport: true,
  },
  hyderabad: {
    city: 'Hyderabad',
    lat: 17.3850,
    lng: 78.4867,
    railwayHub: { name: 'Secunderabad Railway Station', code: 'SC', lat: 17.4334, lng: 78.5042 },
    airportHub: { name: 'Rajiv Gandhi International Airport (HYD)', code: 'HYD', lat: 17.2403, lng: 78.4294 },
    busHub: { name: 'MGBS Central Bus Station', lat: 17.3789, lng: 78.4812 },
    metroHub: { name: 'Ameerpet Metro Interchange', lat: 17.4375, lng: 78.4483, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  pune: {
    city: 'Pune',
    lat: 18.5204,
    lng: 73.8567,
    railwayHub: { name: 'Pune Railway Junction', code: 'PUNE', lat: 18.5284, lng: 73.8744 },
    airportHub: { name: 'Pune International Airport (PNQ)', code: 'PNQ', lat: 18.5822, lng: 73.9197 },
    busHub: { name: 'Shivaji Nagar Bus Terminus', lat: 18.5314, lng: 73.8553 },
    metroHub: { name: 'Civil Court Metro Interchange', lat: 18.5308, lng: 73.8567, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  kolkata: {
    city: 'Kolkata',
    lat: 22.5726,
    lng: 88.3639,
    railwayHub: { name: 'Howrah Railway Station', code: 'HWH', lat: 22.5839, lng: 88.3426 },
    airportHub: { name: 'Netaji Subhash Chandra Bose Airport (CCU)', code: 'CCU', lat: 22.6547, lng: 88.4467 },
    busHub: { name: 'Esplanade Bus Terminus', lat: 22.5647, lng: 88.3517 },
    metroHub: { name: 'Esplanade Metro Interchange', lat: 22.5640, lng: 88.3510, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  jaipur: {
    city: 'Jaipur',
    lat: 26.9124,
    lng: 75.7873,
    railwayHub: { name: 'Jaipur Railway Junction', code: 'JP', lat: 26.9196, lng: 75.7878 },
    airportHub: { name: 'Jaipur International Airport (JAI)', code: 'JAI', lat: 26.8289, lng: 75.8056 },
    busHub: { name: 'Sindhi Camp Central Bus Stand', lat: 26.9239, lng: 75.7981 },
    metroHub: { name: 'Sindhi Camp Metro Station', lat: 26.9230, lng: 75.7980, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  ahmedabad: {
    city: 'Ahmedabad',
    lat: 23.0225,
    lng: 72.5714,
    railwayHub: { name: 'Ahmedabad Junction (Kalupur)', code: 'ADI', lat: 23.0232, lng: 72.6002 },
    airportHub: { name: 'Sardar Vallabhbhai Patel Airport (AMD)', code: 'AMD', lat: 23.0772, lng: 72.6347 },
    busHub: { name: 'Geeta Mandir Central Bus Terminus', lat: 23.0125, lng: 72.5936 },
    metroHub: { name: 'Old High Court Metro Interchange', lat: 23.0360, lng: 72.5620, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  kochi: {
    city: 'Kochi',
    lat: 9.9312,
    lng: 76.2673,
    railwayHub: { name: 'Ernakulam Junction (South)', code: 'ERS', lat: 9.9678, lng: 76.2891 },
    airportHub: { name: 'Cochin International Airport (COK)', code: 'COK', lat: 10.1518, lng: 76.4019 },
    busHub: { name: 'KSRTC Central Bus Stand Ernakulam', lat: 9.9723, lng: 76.2872 },
    metroHub: { name: 'MG Road Metro Station', lat: 9.9730, lng: 76.2820, hasMetro: true },
    hasMetro: true,
    hasAirport: true,
  },
  mysore: {
    city: 'Mysore',
    lat: 12.2958,
    lng: 76.6394,
    railwayHub: { name: 'Mysuru Junction Railway Station', code: 'MYS', lat: 12.3163, lng: 76.6455 },
    airportHub: { name: 'Mysore Mandakalli Airport (MYQ)', code: 'MYQ', lat: 12.2300, lng: 76.6500 },
    busHub: { name: 'Mysore KSRTC Suburb Bus Stand', lat: 12.3106, lng: 76.6567 },
    hasMetro: false,
    hasAirport: true,
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

function round4(val: number): number {
  return Math.round(val * 10000) / 10000;
}

export function computeDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c * 10) / 10;
}

export const REGIONAL_GAZETTEER: Record<string, { lat: number; lng: number; name: string }> = {
  tumkur: { lat: 13.3401, lng: 77.1006, name: 'Tumakuru' },
  tumakuru: { lat: 13.3401, lng: 77.1006, name: 'Tumakuru' },
  hubli: { lat: 15.3647, lng: 75.1240, name: 'Hubballi' },
  hubballi: { lat: 15.3647, lng: 75.1240, name: 'Hubballi' },
  dharwad: { lat: 15.4589, lng: 75.0078, name: 'Dharwad' },
  belgaum: { lat: 15.8497, lng: 74.4977, name: 'Belagavi' },
  belagavi: { lat: 15.8497, lng: 74.4977, name: 'Belagavi' },
  mangalore: { lat: 12.9141, lng: 74.8560, name: 'Mangaluru' },
  mangaluru: { lat: 12.9141, lng: 74.8560, name: 'Mangaluru' },
  mysore: { lat: 12.2958, lng: 76.6394, name: 'Mysuru' },
  mysuru: { lat: 12.2958, lng: 76.6394, name: 'Mysuru' },
  shivamogga: { lat: 13.9299, lng: 75.5681, name: 'Shivamogga' },
  shimoga: { lat: 13.9299, lng: 75.5681, name: 'Shivamogga' },
  davangere: { lat: 14.4644, lng: 75.9218, name: 'Davanagere' },
  ballari: { lat: 15.1394, lng: 76.9214, name: 'Ballari' },
  bellary: { lat: 15.1394, lng: 76.9214, name: 'Ballari' },
  hassan: { lat: 13.0033, lng: 76.1004, name: 'Hassan' },
  coimbatore: { lat: 11.0168, lng: 76.9558, name: 'Coimbatore' },
  madurai: { lat: 9.9252, lng: 78.1198, name: 'Madurai' },
  trichy: { lat: 10.7905, lng: 78.7047, name: 'Tiruchirappalli' },
  salem: { lat: 11.6643, lng: 78.1460, name: 'Salem' },
  vellore: { lat: 12.9165, lng: 79.1325, name: 'Vellore' },
  kochi: { lat: 9.9312, lng: 76.2673, name: 'Kochi' },
  thiruvananthapuram: { lat: 8.5241, lng: 76.9366, name: 'Thiruvananthapuram' },
  trivandrum: { lat: 8.5241, lng: 76.9366, name: 'Thiruvananthapuram' },
  kozhikode: { lat: 11.2588, lng: 75.7804, name: 'Kozhikode' },
  calicut: { lat: 11.2588, lng: 75.7804, name: 'Kozhikode' },
  vijayawada: { lat: 16.5062, lng: 80.6480, name: 'Vijayawada' },
  visakhapatnam: { lat: 17.6868, lng: 83.2185, name: 'Visakhapatnam' },
  vizag: { lat: 17.6868, lng: 83.2185, name: 'Visakhapatnam' },
  tirupati: { lat: 13.6288, lng: 79.4192, name: 'Tirupati' },
  warangal: { lat: 17.9689, lng: 79.5941, name: 'Warangal' },
  delhi: { lat: 28.6139, lng: 77.2090, name: 'New Delhi' },
  mumbai: { lat: 19.0760, lng: 72.8777, name: 'Mumbai' },
  pune: { lat: 18.5204, lng: 73.8567, name: 'Pune' },
  hyderabad: { lat: 17.3850, lng: 78.4867, name: 'Hyderabad' },
  chennai: { lat: 13.0827, lng: 80.2707, name: 'Chennai' },
  bangalore: { lat: 12.9716, lng: 77.5946, name: 'Bangalore' },
  bengaluru: { lat: 12.9716, lng: 77.5946, name: 'Bangalore' },
  kolkata: { lat: 22.5726, lng: 88.3639, name: 'Kolkata' },
  jaipur: { lat: 26.9124, lng: 75.7873, name: 'Jaipur' },
  ahmedabad: { lat: 23.0225, lng: 72.5714, name: 'Ahmedabad' },
  goa: { lat: 15.2993, lng: 74.1240, name: 'Goa' },
  panaji: { lat: 15.4909, lng: 73.8278, name: 'Panaji' },
};

export const CANONICAL_CITY_ALIASES: Record<string, string[]> = {
  tumkur: ['tumakuru'],
  tumakuru: ['tumkur'],
  bangalore: ['bengaluru'],
  bengaluru: ['bangalore'],
  mysore: ['mysuru'],
  mysuru: ['mysore'],
  hubli: ['hubballi'],
  hubballi: ['hubli'],
  belgaum: ['belagavi'],
  belagavi: ['belgaum'],
  shimoga: ['shivamogga'],
  shivamogga: ['shimoga'],
  bellary: ['ballari'],
  ballari: ['bellary'],
  davanagere: ['davangere'],
  davangere: ['davanagere'],
  calicut: ['kozhikode'],
  kozhikode: ['calicut'],
  trivandrum: ['thiruvananthapuram'],
  thiruvananthapuram: ['trivandrum'],
  cochin: ['kochi', 'ernakulam'],
  kochi: ['cochin', 'ernakulam'],
  ernakulam: ['kochi', 'cochin'],
  vizag: ['visakhapatnam'],
  visakhapatnam: ['vizag'],
  madras: ['chennai'],
  chennai: ['madras'],
  bombay: ['mumbai'],
  mumbai: ['bombay'],
  calcutta: ['kolkata'],
  kolkata: ['calcutta'],
  delhi: ['new delhi', 'gurgaon', 'gurugram', 'noida'],
  'new delhi': ['delhi'],
};

export interface CrossCityCollisionResult {
  isStaleCollision: boolean;
  conflictingCity?: string;
  distanceKm?: number;
}

/**
 * Cross-city collision detector:
 * Identifies if customCoordinates demonstrably belong to an entirely different registered city hub
 * (within 25 km of that city's hub) while the text query targets another city (e.g., Bengaluru
 * coordinates attached to a Tumkur search request).
 *
 * Preserves legitimate GPS / map-picker coordinates that do not conflict with a foreign registered city hub,
 * even if they are situated > 45 km from the requested city's centroid (e.g. Palolem in Goa, Sira in Tumkur,
 * Jewar in Delhi NCR).
 */
export function detectCrossCityCollision(
  coordsOrLocation: { lat: number; lng: number } | string | undefined,
  targetOrCoords?: string | { lat: number; lng: number },
  rawLocationStr?: string
): CrossCityCollisionResult {
  let customCoordinates: { lat: number; lng: number } | undefined;
  let targetCityKey: string | undefined;
  let rawStr = '';

  if (typeof coordsOrLocation === 'string') {
    // Flexible overload: detectCrossCityCollision(locationStr, customCoords)
    rawStr = coordsOrLocation;
    targetCityKey = coordsOrLocation;
    customCoordinates = (targetOrCoords && typeof targetOrCoords === 'object')
      ? (targetOrCoords as { lat: number; lng: number })
      : undefined;
  } else {
    // Standard signature: detectCrossCityCollision(customCoords, targetCityKey, rawLocationStr)
    customCoordinates = coordsOrLocation;
    targetCityKey = typeof targetOrCoords === 'string' ? targetOrCoords : undefined;
    rawStr = rawLocationStr || '';
  }

  if (!customCoordinates) {
    return { isStaleCollision: false };
  }

  const rawLower = (rawStr || '').toLowerCase().trim();
  const normalizedTarget = (targetCityKey || '').toLowerCase().trim();

  const isTargetMatch = (cityKey: string, cityName: string): boolean => {
    const keyLower = cityKey.toLowerCase();
    const nameLower = cityName.toLowerCase();
    if (!rawLower && !normalizedTarget) return false;
    if (keyLower === normalizedTarget || nameLower === normalizedTarget) return true;
    if (rawLower.includes(keyLower) || keyLower.includes(rawLower)) return true;
    if (rawLower.includes(nameLower) || nameLower.includes(rawLower)) return true;
    const aliases = CANONICAL_CITY_ALIASES[rawLower] || [];
    if (aliases.includes(keyLower) || aliases.includes(nameLower)) return true;
    const targetAliases = CANONICAL_CITY_ALIASES[normalizedTarget] || [];
    if (targetAliases.includes(keyLower) || targetAliases.includes(nameLower)) return true;
    const cityAliases = (CANONICAL_CITY_ALIASES[keyLower] || []).concat(CANONICAL_CITY_ALIASES[nameLower] || []);
    for (const a of cityAliases) {
      if (rawLower.includes(a) || normalizedTarget.includes(a)) return true;
    }
    return false;
  };

  // 1. Check against major city hub registry
  for (const [key, profile] of Object.entries(CITY_HUB_REGISTRY)) {
    const dist = computeDistanceKm(customCoordinates.lat, customCoordinates.lng, profile.lat, profile.lng);
    if (dist <= 25.0) {
      if (!isTargetMatch(key, profile.city)) {
        return {
          isStaleCollision: true,
          conflictingCity: profile.city,
          distanceKm: dist,
        };
      }
    }
  }

  // 2. Check against regional gazetteer hubs
  for (const [key, entry] of Object.entries(REGIONAL_GAZETTEER)) {
    const dist = computeDistanceKm(customCoordinates.lat, customCoordinates.lng, entry.lat, entry.lng);
    if (dist <= 25.0) {
      if (!isTargetMatch(key, entry.name)) {
        return {
          isStaleCollision: true,
          conflictingCity: entry.name,
          distanceKm: dist,
        };
      }
    }
  }

  return { isStaleCollision: false };
}

export interface ResolvedHubContext {
  rawLocation: string;
  isLocality: boolean;
  parentCity: string;
  userNode: Location;
  railwayHub: Location;
  airportHub?: Location;
  busHub: Location;
  metroHub?: Location;
  hasAirport: boolean;
  hasMetro: boolean;
  hasLocalAirport?: boolean;
  isAirportGateway?: boolean;
  airportGatewayCity?: string;
  airportCity?: string;
}

export function resolveHubContext(
  locationStr: string,
  isOrigin: boolean,
  customCoordinates?: { lat: number; lng: number }
): ResolvedHubContext {
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

  // Check for cross-city collision (stale coordinates from a different city)
  const collision = detectCrossCityCollision(customCoordinates, parentCityKey || lower, raw);

  // 3. Resolve profile via registry or regional gazetteer / custom coordinates
  let profile: CityHubProfile;
  let effectiveCoords: { lat: number; lng: number };

  if (parentCityKey && CITY_HUB_REGISTRY[parentCityKey]) {
    profile = CITY_HUB_REGISTRY[parentCityKey];
    if (customCoordinates && !collision.isStaleCollision) {
      // Rule 1 & 4: Preserve intentional GPS / map-picker coordinates
      effectiveCoords = customCoordinates;
    } else {
      // Rule 3: Stale collision cleared or missing custom coords -> use canonical centroid
      effectiveCoords = {
        lat: profile.lat,
        lng: profile.lng,
      };
    }
  } else {
    // Check gazetteer or custom coordinates for dynamic resolution
    const gz = REGIONAL_GAZETTEER[lower] || Object.entries(REGIONAL_GAZETTEER).find(([k]) => lower.includes(k) || k.includes(lower))?.[1];

    if (!gz && (!customCoordinates || collision.isStaleCollision)) {
      throw new Error(`Unable to resolve coordinates for location: "${raw}". Location is not recognized in regional gazetteer and no valid custom coordinates were provided.`);
    }

    let defLat: number;
    let defLng: number;

    if (gz) {
      defLat = gz.lat;
      defLng = gz.lng;
      if (customCoordinates && !collision.isStaleCollision) {
        // Rule 1 & 4: Preserve intentional coordinates even if distant from gazetteer center
        effectiveCoords = customCoordinates;
      } else {
        // Rule 3: Conflicting stale coordinates cleared -> use gazetteer coordinates
        effectiveCoords = {
          lat: round4(defLat + (isOrigin ? -0.015 : 0.015)),
          lng: round4(defLng + (isOrigin ? -0.015 : 0.015)),
        };
      }
    } else {
      // Rule 5: Unknown location text, but valid non-colliding customCoordinates provided (e.g. map picker pin)
      defLat = customCoordinates!.lat;
      defLng = customCoordinates!.lng;
      effectiveCoords = customCoordinates!;
    }

    const dynamicCity = capitalizedRaw;

    profile = {
      city: dynamicCity,
      lat: defLat,
      lng: defLng,
      railwayHub: { name: `${dynamicCity} Railway Station`, lat: round4(defLat + 0.005), lng: round4(defLng + 0.005) },
      busHub: { name: `${dynamicCity} Central Bus Stand`, lat: round4(defLat - 0.005), lng: round4(defLng - 0.002) },
      hasMetro: false,
      hasAirport: false,
    };
    isLocality = false;
  }

  const userNode: Location = {
    id: `loc-usr-${isOrigin ? 'orig' : 'dest'}-${slugify(raw || profile.city)}`,
    name: isLocality ? `${capitalizedRaw}` : `${capitalizedRaw} City Hub`,
    city: isLocality ? `${capitalizedRaw} (${profile.city})` : capitalizedRaw,
    type: isLocality ? 'address' : 'landmark',
    coordinates: effectiveCoords,
  };

  const railwayHub: Location = {
    id: `loc-hub-rail-${slugify(profile.city)}`,
    name: profile.railwayHub.name,
    city: profile.city,
    code: profile.railwayHub.code,
    type: 'railway_station',
    coordinates: { lat: profile.railwayHub.lat, lng: profile.railwayHub.lng },
  };

  const airportCity = profile.airportCity
    || (profile.airportHub as any)?.city
    || (profile.isAirportGateway ? profile.airportGatewayCity : undefined)
    || profile.city;

  const airportHub: Location | undefined = (profile.hasAirport && profile.airportHub)
    ? {
        id: `loc-hub-air-${slugify(airportCity)}`,
        name: profile.airportHub.name,
        city: airportCity,
        code: profile.airportHub.code,
        type: 'airport',
        coordinates: { lat: profile.airportHub.lat, lng: profile.airportHub.lng },
      }
    : undefined;

  const busHub: Location = {
    id: `loc-hub-bus-${slugify(profile.city)}`,
    name: profile.busHub.name,
    city: profile.city,
    type: 'bus_terminal',
    coordinates: { lat: profile.busHub.lat, lng: profile.busHub.lng },
  };

  const metroHub: Location | undefined = (profile.hasMetro && profile.metroHub)
    ? {
        id: `loc-hub-metro-${slugify(profile.city)}`,
        name: profile.metroHub.name,
        city: profile.city,
        type: 'metro_station',
        coordinates: { lat: profile.metroHub.lat, lng: profile.metroHub.lng },
      }
    : undefined;

  return {
    rawLocation: raw,
    isLocality,
    parentCity: profile.city,
    userNode,
    railwayHub,
    airportHub,
    busHub,
    metroHub,
    hasAirport: profile.hasAirport,
    hasMetro: profile.hasMetro,
    hasLocalAirport: profile.hasLocalAirport ?? profile.hasAirport,
    isAirportGateway: profile.isAirportGateway ?? false,
    airportGatewayCity: profile.airportGatewayCity,
    airportCity: profile.hasAirport ? airportCity : undefined,
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

export function estimateCorridorDistanceKm(
  originCity: string,
  destCity: string,
  originCoords?: { lat: number; lng: number },
  destCoords?: { lat: number; lng: number }
): number {
  const o = slugify(originCity);
  const d = slugify(destCity);
  const key = `${o}-${d}`;
  if (CORRIDOR_DISTANCES[key]) return CORRIDOR_DISTANCES[key];

  let c1 = originCoords || (CITY_HUB_REGISTRY[o] ? { lat: CITY_HUB_REGISTRY[o].lat, lng: CITY_HUB_REGISTRY[o].lng } : undefined);
  let c2 = destCoords || (CITY_HUB_REGISTRY[d] ? { lat: CITY_HUB_REGISTRY[d].lat, lng: CITY_HUB_REGISTRY[d].lng } : undefined);

  if (!c1) {
    const gz = REGIONAL_GAZETTEER[o] || Object.entries(REGIONAL_GAZETTEER).find(([k]) => o.includes(k))?.[1];
    if (gz) c1 = { lat: gz.lat, lng: gz.lng };
  }
  if (!c2) {
    const gz = REGIONAL_GAZETTEER[d] || Object.entries(REGIONAL_GAZETTEER).find(([k]) => d.includes(k))?.[1];
    if (gz) c2 = { lat: gz.lat, lng: gz.lng };
  }

  if (c1 && c2) {
    const R = 6371;
    const dLat = ((c2.lat - c1.lat) * Math.PI) / 180;
    const dLon = ((c2.lng - c1.lng) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((c1.lat * Math.PI) / 180) *
      Math.cos((c2.lat * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Math.max(50, Math.round(R * c * 1.25));
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
    };
  }
  if (c.includes('udupi') || c.includes('mangalore')) {
    return {
      cab: { provider: 'Coastal Express Taxi (Udupi/Mangalore)', vehicleName: 'Inter-City Sedan' },
      rapido: { provider: 'Coastal Auto QuickSync', vehicleName: 'Rapid City Auto' },
      bus: { provider: 'Udupi-Manipal Express City Bus', vehicleName: 'City Feeder Bus' },
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
  if (c.includes('kolkata')) {
    return {
      cab: { provider: 'KogniSync Priority SyncCab (Kolkata)', vehicleName: 'Yellow City Sedan' },
      rapido: { provider: 'Rapido QuickSync Kolkata', vehicleName: 'Rapido Auto / Bike' },
      bus: { provider: 'CSTC Electric City Feeder', vehicleName: 'City Transit Bus' },
      metro: { provider: 'Kolkata Metro Blue Line', vehicleName: 'Metro Electric Transit' },
    };
  }
  if (c.includes('jaipur')) {
    return {
      cab: { provider: 'KogniSync Priority SyncCab (Jaipur)', vehicleName: 'Pink City Sedan' },
      rapido: { provider: 'Rapido QuickSync Jaipur', vehicleName: 'Rapido Auto / Bike' },
      bus: { provider: 'JCTSL City Feeder', vehicleName: 'City Transit Bus' },
      metro: { provider: 'Jaipur Metro Pink Line', vehicleName: 'Metro Electric Transit' },
    };
  }
  if (c.includes('ahmedabad')) {
    return {
      cab: { provider: 'KogniSync Priority SyncCab (Ahmedabad)', vehicleName: 'City Express Sedan' },
      rapido: { provider: 'Rapido QuickSync Ahmedabad', vehicleName: 'Rapido Auto / Bike' },
      bus: { provider: 'AMTS Electric Feeder', vehicleName: 'City Transit Bus' },
      metro: { provider: 'Gujarat Metro Red Line', vehicleName: 'Metro Electric Transit' },
    };
  }
  if (c.includes('kochi')) {
    return {
      cab: { provider: 'KogniSync Priority SyncCab (Kochi)', vehicleName: 'Airport Taxi Sedan' },
      rapido: { provider: 'Rapido QuickSync Kochi', vehicleName: 'Rapido Auto / Bike' },
      bus: { provider: 'KSRTC Kochi City Circular', vehicleName: 'Low-Floor Electric Bus' },
      metro: { provider: 'Kochi Metro Rail Transit', vehicleName: 'Metro Electric Transit' },
    };
  }

  // Generic clean fallback for regional cities without verified metro
  return {
    cab: { provider: `KogniSync Priority SyncCab (${cityName})`, vehicleName: 'Priority City Sedan' },
    rapido: { provider: `Rapido QuickSync ${cityName}`, vehicleName: 'Rapido Auto / Bike' },
    bus: { provider: `${cityName} City Feeder Bus`, vehicleName: 'City Transit Line' },
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

  // 1. Resolve hubs for origin and destination (incorporating exact coordinates or gazetteer)
  const originHubs = resolveHubContext(originStr, true, request.originCoordinates);
  const destHubs = resolveHubContext(destStr, false, request.destinationCoordinates);

  const routeDistanceKm = estimateCorridorDistanceKm(
    originHubs.parentCity,
    destHubs.parentCity,
    originHubs.userNode.coordinates,
    destHubs.userNode.coordinates
  );
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

  // Infrastructure validity checks for multimodal archetypes
  const hasFlightInfrastructure = Boolean(
    originHubs.hasAirport &&
    destHubs.hasAirport &&
    originHubs.airportHub &&
    destHubs.airportHub
  );
  const hasOriginMetro = Boolean(
    originHubs.hasMetro &&
    originHubs.metroHub &&
    originOps.metro
  );
  const hasDestMetro = Boolean(
    destHubs.hasMetro &&
    destHubs.metroHub &&
    destOps.metro
  );

  const archetypes: ArchetypeDef[] = [];

  // 1. FASTEST: Priority Cab -> Flight -> Priority Cab (gated by verified airport infrastructure)
  if (hasFlightInfrastructure) {
    const origAirDistRaw = computeDistanceKm(
      originHubs.userNode.coordinates.lat,
      originHubs.userNode.coordinates.lng,
      originHubs.airportHub!.coordinates.lat,
      originHubs.airportHub!.coordinates.lng
    );
    const destAirDistRaw = computeDistanceKm(
      destHubs.airportHub!.coordinates.lat,
      destHubs.airportHub!.coordinates.lng,
      destHubs.userNode.coordinates.lat,
      destHubs.userNode.coordinates.lng
    );
    const firstMileAirDist = Math.max(10, Math.round(origAirDistRaw * 1.25 * 10) / 10);
    const firstMileAirDur = Math.max(20, Math.round((firstMileAirDist / 45) * 60));
    const firstMileAirPrice = Math.round(200 + firstMileAirDist * 18);

    const lastMileAirDist = Math.max(8, Math.round(destAirDistRaw * 1.25 * 10) / 10);
    const lastMileAirDur = Math.max(20, Math.round((lastMileAirDist / 45) * 60));
    const lastMileAirPrice = Math.round(150 + lastMileAirDist * 18);

    const airCorridorDist = Math.max(
      50,
      Math.round(
        computeDistanceKm(
          originHubs.airportHub!.coordinates.lat,
          originHubs.airportHub!.coordinates.lng,
          destHubs.airportHub!.coordinates.lat,
          destHubs.airportHub!.coordinates.lng
        )
      )
    );
    const calibratedFlightDur = Math.round(45 + (airCorridorDist / 750) * 60);
    const calibratedFlightPrice = Math.round(1800 + airCorridorDist * 2.3);

    archetypes.push({
      category: 'fastest' as RecommendationCategory,
      title: 'SyncAir Multi-Modal Link (Air + Priority SyncCab)',
      summaryTemplate: `Fastest door-to-door arrival connecting ${originHubs.userNode.name} to ${destHubs.userNode.name} via commercial air express and synchronized priority cabs.`,
      rankReason: 'Ranked #1 for Fastest. Minimizes total transit time with scheduled flight and express terminal cabs.',
      firstMile: {
        mode: 'cab' as TransportMode,
        provider: originOps.cab.provider,
        vehicleName: originOps.cab.vehicleName,
        hubType: 'air' as const,
        durationMin: firstMileAirDur,
        price: firstMileAirPrice,
        distanceKm: firstMileAirDist,
        carbonKg: Math.round(firstMileAirDist * 0.15 * 10) / 10,
        comfortScore: 8.8,
        transferBufferMin: 50, // 50 min airport check-in and boarding buffer
      },
      mainTransport: {
        mode: 'flight' as TransportMode,
        provider: 'IndiGo Air Express',
        vehicleName: 'Commercial Aircraft (Estimated Flight Corridor)',
        vehicleNumber: undefined,
        durationMin: calibratedFlightDur,
        price: calibratedFlightPrice,
        distanceKm: airCorridorDist,
        carbonKg: Number((airCorridorDist * 0.082).toFixed(1)),
        comfortScore: 8.5,
        seatClass: 'Economy (Estimated)',
        notes: `Estimated commercial flight corridor from ${originHubs.airportHub?.code || originHubs.parentCity} to ${destHubs.airportHub?.code || destHubs.parentCity}. Ungrounded in live carrier inventory; schedule, fare, and availability are non-bookable estimates.`,
        transferBufferMin: 25, // 25 min baggage & pickup buffer
      },
      lastMile: {
        mode: 'cab' as TransportMode,
        provider: destOps.cab.provider,
        vehicleName: destOps.cab.vehicleName,
        durationMin: lastMileAirDur,
        price: lastMileAirPrice,
        distanceKm: lastMileAirDist,
        carbonKg: Math.round(lastMileAirDist * 0.15 * 10) / 10,
        comfortScore: 8.9,
      },
    });
  }

  // 2. BEST VALUE: Rapido / Auto -> Vande Bharat Superfast Rail -> Rapido / Auto
  archetypes.push({
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
      vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Vande Bharat Express (Estimated Schedule)`,
      vehicleNumber: undefined,
      durationMin: trainVandeBharatDurationMin,
      price: trainVandeBharatPrice,
      distanceKm: routeDistanceKm,
      carbonKg: Number((routeDistanceKm * 0.024).toFixed(1)),
      comfortScore: 9.3,
      seatClass: 'AC Chair Car (CC)',
      notes: 'High-speed electric rail corridor estimate (160 km/h design speed). Ungrounded in live timetable; requires IRCTC verification.',
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
  });

  // 3. CHEAPEST: Public Transit Feeder -> Superfast Rail / Bus -> Public Transit Feeder
  archetypes.push({
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
      vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Superfast Express (Estimated Schedule)`,
      vehicleNumber: undefined,
      durationMin: trainCheapestDurationMin,
      price: trainCheapestPrice,
      distanceKm: routeDistanceKm,
      carbonKg: Number((routeDistanceKm * 0.026).toFixed(1)),
      comfortScore: 7.8,
      seatClass: 'Sleeper (SL) / 2S Reserved',
      notes: 'Estimated intercity rail transit. Schedule, fare, and seat availability require IRCTC timetable verification.',
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
  });

  // 4. GREENEST: Metro / EV Bus -> Low-Carbon Rail -> Metro / EV Bus
  archetypes.push({
    category: 'greenest' as RecommendationCategory,
    title: 'Eco-Transit Corridor (Low-Carbon Rail + Public Transit Feeder)',
    summaryTemplate: `Lowest carbon footprint available: low-emission urban transit synchronized with rail transit corridor (corridor timetable and electrification require verification).`,
    rankReason: 'Ranked #1 for Eco-Friendly. Emits up to 70% lower greenhouse gases than highway or air transit.',
    firstMile: {
      mode: hasOriginMetro ? ('metro' as TransportMode) : ('bus' as TransportMode),
      provider: hasOriginMetro ? originOps.metro!.provider : (originOps.bus?.provider || `${originHubs.parentCity} City Feeder Bus`),
      vehicleName: hasOriginMetro ? originOps.metro!.vehicleName : (originOps.bus?.vehicleName || 'Electric City Feeder Bus'),
      hubType: 'rail' as const,
      durationMin: hasOriginMetro ? 25 : 30,
      price: hasOriginMetro ? 40 : 35,
      distanceKm: hasOriginMetro ? 11 : 12,
      carbonKg: hasOriginMetro ? 0.6 : 0.8,
      comfortScore: hasOriginMetro ? 8.5 : 7.2,
      transferBufferMin: 15,
    },
    mainTransport: {
      mode: 'train' as TransportMode,
      provider: 'Indian Railways Low-Carbon Rail',
      vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Low-Carbon Rail Corridor (Estimated)`,
      vehicleNumber: undefined,
      durationMin: trainGreenestDurationMin,
      price: trainGreenestPrice,
      distanceKm: routeDistanceKm,
      carbonKg: Number((routeDistanceKm * 0.016).toFixed(1)),
      comfortScore: 9.1,
      seatClass: 'Executive Chair Car',
      notes: 'Low-carbon rail corridor estimate. Schedule, fare, and electrification status require IRCTC verification.',
      transferBufferMin: 15,
    },
    lastMile: {
      mode: hasDestMetro ? ('metro' as TransportMode) : ('bus' as TransportMode),
      provider: hasDestMetro ? destOps.metro!.provider : (destOps.bus?.provider || `${destHubs.parentCity} City Feeder Bus`),
      vehicleName: hasDestMetro ? destOps.metro!.vehicleName : (destOps.bus?.vehicleName || 'Electric City Feeder Bus'),
      durationMin: hasDestMetro ? 20 : 25,
      price: hasDestMetro ? 45 : 35,
      distanceKm: hasDestMetro ? 9 : 10,
      carbonKg: hasDestMetro ? 0.5 : 0.7,
      comfortScore: hasDestMetro ? 8.5 : 7.2,
    },
  });

  // 5. COMFORTABLE: Executive Sedan -> Shatabdi 1st AC -> Executive Sedan
  archetypes.push({
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
      vehicleName: `${originHubs.parentCity} - ${destHubs.parentCity} Executive Express (Estimated Schedule)`,
      vehicleNumber: undefined,
      durationMin: trainComfortDurationMin,
      price: trainComfortPrice,
      distanceKm: routeDistanceKm,
      carbonKg: Number((routeDistanceKm * 0.026).toFixed(1)),
      comfortScore: 9.7,
      seatClass: 'Executive AC Chair (1st Class)',
      notes: 'Premium day-express rail corridor estimate. Seat availability and schedule require IRCTC verification.',
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
  });

  // 2. Compose each archetype into a complete journey with backward timing anchored to deadline
  const journeys: Journey[] = archetypes.map((arch, archIdx) => {
    // Select the appropriate hubs based on archetype's main mode
    const depHub = arch.firstMile.hubType === 'air'
      ? originHubs.airportHub!
      : arch.firstMile.hubType === 'bus'
        ? originHubs.busHub
        : originHubs.railwayHub;

    const arrHub = arch.firstMile.hubType === 'air'
      ? destHubs.airportHub!
      : arch.firstMile.hubType === 'bus'
        ? destHubs.busHub
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

    const buildFallbackSegmentProvenance = (provider: string): SegmentProvenance => ({
      sourceType: 'deterministic_estimate',
      providerName: provider,
      isEstimate: true,
      hasLiveProvider: false,
      attributes: {
        fare: { sourceType: 'deterministic_estimate', providerName: provider, isEstimate: true, notes: 'Corridor distance-modeled estimate' },
        duration: { sourceType: 'deterministic_estimate', providerName: provider, isEstimate: true, notes: 'Corridor speed model' },
        distance: { sourceType: 'deterministic_estimate', providerName: 'KogniSync Geo-Engine', isEstimate: true, notes: 'Corridor geographic distance model' },
        departure: { sourceType: 'deterministic_estimate', providerName: provider, isEstimate: true, notes: 'Estimated schedule anchored to deadline' },
        arrival: { sourceType: 'deterministic_estimate', providerName: provider, isEstimate: true, notes: 'Estimated arrival' },
        departureTime: { sourceType: 'deterministic_estimate', providerName: provider, isEstimate: true, notes: 'Estimated schedule anchored to deadline' },
        arrivalTime: { sourceType: 'deterministic_estimate', providerName: provider, isEstimate: true, notes: 'Estimated arrival' },
        carbon: { sourceType: 'deterministic_estimate', providerName: 'KogniSync Multi-Modal Emission Factors', isEstimate: true },
        availability: { sourceType: 'simulated', providerName: 'KogniSync Demo Fleet Simulator', isEstimate: true, notes: 'Simulated capacity for demonstration' },
      },
    });

    const leg1Note =
      arch.firstMile.mode === 'cab' && depHub.type === 'airport'
        ? (originHubs.isAirportGateway
            ? `Ground transfer to external regional airport gateway: ${depHub.name} (${originHubs.airportGatewayCity || depHub.city}). Estimated road transit: ${arch.firstMile.durationMin}m with ${arch.firstMile.transferBufferMin}m terminal buffer.`
            : `Airport express transfer connecting ${originHubs.userNode.name} to ${depHub.name}. Estimated road transit: ${arch.firstMile.durationMin}m with ${arch.firstMile.transferBufferMin}m terminal buffer.`)
        : `Feeder pickup at ${originHubs.userNode.name}. Planning assumption: ${arch.firstMile.transferBufferMin}m transfer buffer at ${depHub.name}.`;

    const leg3Note =
      arch.lastMile.mode === 'cab' && arrHub.type === 'airport'
        ? (destHubs.isAirportGateway
            ? `Ground transfer from external regional airport gateway: ${arrHub.name} (${destHubs.airportGatewayCity || arrHub.city}). Estimated road transit: ${arch.lastMile.durationMin}m.`
            : `Airport arrival transfer connecting ${arrHub.name} to ${destHubs.userNode.name}. Estimated road transit: ${arch.lastMile.durationMin}m.`)
        : `Final transfer to ${destHubs.userNode.name}. Estimated connection from ${arrHub.name}.`;

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
      availability: { status: 'available', remainingUnits: undefined, isRealInventory: false },
      distanceKm: arch.firstMile.distanceKm,
      carbonKg: arch.firstMile.carbonKg,
      comfortScore: arch.firstMile.comfortScore,
      transferBufferMinutes: arch.firstMile.transferBufferMin,
      notes: leg1Note,
      provenance: buildFallbackSegmentProvenance(arch.firstMile.provider),
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
      availability: { status: 'available', remainingUnits: undefined, isRealInventory: false },
      distanceKm: arch.mainTransport.distanceKm,
      carbonKg: arch.mainTransport.carbonKg,
      comfortScore: arch.mainTransport.comfortScore,
      seatClass: arch.mainTransport.seatClass,
      transferBufferMinutes: arch.mainTransport.transferBufferMin,
      notes: `${arch.mainTransport.notes} Planning assumption: ${arch.mainTransport.transferBufferMin}m transfer buffer at ${arrHub.name}.`,
      provenance: buildFallbackSegmentProvenance(arch.mainTransport.provider),
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
      availability: { status: 'available', remainingUnits: undefined, isRealInventory: false },
      distanceKm: arch.lastMile.distanceKm,
      carbonKg: arch.lastMile.carbonKg,
      comfortScore: arch.lastMile.comfortScore,
      notes: leg3Note,
      provenance: buildFallbackSegmentProvenance(arch.lastMile.provider),
    };

    const segments: JourneySegment[] = [segment1, segment2, segment3];

    // Aggregations
    const totalPrice = segments.reduce((sum, s) => sum + s.price, 0);
    const travelDurationMinutes = segments.reduce((sum, s) => sum + s.durationMinutes, 0);
    const inVehicleDurationMinutes = segments.filter((s) => s.mode !== 'walk').reduce((sum, s) => sum + s.durationMinutes, 0);
    const walkingDurationMinutes = segments.filter((s) => s.mode === 'walk').reduce((sum, s) => sum + s.durationMinutes, 0);
    const waitingDurationMinutes = arch.firstMile.transferBufferMin + arch.mainTransport.transferBufferMin;
    const totalDurationMinutes = Math.round((seg3Arr.getTime() - seg1Dep.getTime()) / 60000);
    const totalTransfers = segments.length - 1; // 2 transfers
    const totalCarbonKg = Number(segments.reduce((sum, s) => sum + s.carbonKg, 0).toFixed(1));

    const avgComfort = Number(
      (segments.reduce((sum, s) => sum + s.comfortScore * s.durationMinutes, 0) / travelDurationMinutes).toFixed(1)
    );

    const modes: TransportMode[] = Array.from(new Set(segments.map((s) => s.mode)));

    const journeyProvenance: JourneyProvenance = {
      overallSourceType: 'deterministic_estimate',
      isFullyConfirmed: false,
      hasLiveAttributes: false,
      hasSimulatedAttributes: true,
      summary: 'Composed of deterministic estimates and simulated availability; real-world booking requires provider verification.',
    };

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
      inVehicleDurationMinutes,
      walkingDurationMinutes,
      isConnectionFeasible: true,
      connectionFeasibilityNotes: [
        `Transfer 1 (${depHub.name}): ${arch.firstMile.transferBufferMin} min buffer (Planning assumption: minimum boarding/check-in buffer met).`,
        `Transfer 2 (${arrHub.name}): ${arch.mainTransport.transferBufferMin} min buffer (Planning assumption: minimum deboarding/egress buffer met).`,
      ],
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
          'Corridor-modeled estimates: fare and transit duration are unverified until live booking lock',
        ],
        score: 90,
        costVsFastestSaving: Math.max(0, flightPrice + 1100 - totalPrice),
        durationDiffMinutes: totalDurationMinutes - (flightDurationMin + 65),
        dataCredibilityNotice: 'Fares, travel durations, and schedules are deterministic estimates. Availability is unverified synthetic data and requires live provider confirmation prior to booking.',
        isFareEstimated: true,
        isDurationEstimated: true,
        isAvailabilityVerified: false,
      },
      bookingFeasibility: {
        holdSupported: true,
        concurrencySafe: true,
        holdTtlSeconds: 600,
      },
      provenance: journeyProvenance,
    };

    return journey;
  });

  // 3. Multi-objective deterministic optimization & Pareto analysis:
  // Enforces hard constraints, determines Pareto-optimal non-dominated options,
  // computes objective contributions, and generates traceable explanations.
  return optimizeCandidateJourneys(journeys, request.weights, budgetMax, request.naturalLanguageQuery);
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch {
    return isoString;
  }
}
