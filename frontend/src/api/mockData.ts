import { Journey, TravelRequest } from '../types/journey';
import { Trip } from '../types/trip';
import { composeMultiModalJourneys } from './orchestrationEngine';

export const DEMO_PRESETS: { title: string; subtitle: string; query: string; request: Partial<TravelRequest> }[] = [
  {
    title: 'Bangalore → Chennai (Budget ₹3000)',
    subtitle: 'Cost-optimized before 2 PM tomorrow',
    query: 'I need to reach Chennai from Bangalore tomorrow before 2 PM. My budget is ₹3000 and I prefer saving money over speed.',
    request: {
      origin: 'Bangalore',
      destination: 'Chennai',
      budgetMax: 3000,
      departureDate: new Date(Date.now() + 86400000).toISOString().split('T')[0],
      preferredArrivalBefore: '14:00',
      weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
    },
  },
  {
    title: 'Mumbai → Pune (Express Work Trip)',
    subtitle: 'Fastest + high comfort trade-off',
    query: 'Heading from BKC Mumbai to Shivaji Nagar Pune this Friday for client meetings. Need comfortable work seating and fast arrival.',
    request: {
      origin: 'Mumbai',
      destination: 'Pune',
      budgetMax: 4500,
      departureDate: new Date(Date.now() + 172800000).toISOString().split('T')[0],
      preferredArrivalBefore: '11:00',
      weights: { cost: 0.15, duration: 0.45, comfort: 0.35, carbon: 0.05 },
    },
  },
  {
    title: 'Delhi → Jaipur (Greenest Heritage Trip)',
    subtitle: 'Zero-emission electric transit prioritization',
    query: 'Weekend trip from Delhi to Jaipur for 2 passengers. Prioritize lowest carbon footprint and electric transit options.',
    request: {
      origin: 'Delhi',
      destination: 'Jaipur',
      budgetMax: 5000,
      departureDate: new Date(Date.now() + 259200000).toISOString().split('T')[0],
      preferredArrivalBefore: '16:00',
      weights: { cost: 0.2, duration: 0.2, comfort: 0.2, carbon: 0.4 },
    },
  },
];

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

function parseArrivalTarget(deadline?: string): { hour: number; minute: number } {
  if (!deadline) return { hour: 18, minute: 0 };
  const d = deadline.trim().toLowerCase();
  const isPM = d.includes('pm');
  const isAM = d.includes('am');
  const cleaned = d.replace(/(am|pm|arrive|by|before|\s)/g, '');
  const parts = cleaned.split(':');
  if (parts.length >= 1) {
    let h = parseInt(parts[0], 10);
    const m = parts.length >= 2 ? parseInt(parts[1], 10) : 0;
    if (!isNaN(h)) {
      if (isPM && h < 12) h += 12;
      if (isAM && h === 12) h = 0;
      return { hour: Math.min(23, Math.max(0, h)), minute: Math.min(59, Math.max(0, m)) };
    }
  }
  return { hour: 18, minute: 0 };
}

function formatIso(dateStr: string, hour: number, minute: number): string {
  const [y, m, d] = dateStr.includes('-')
    ? dateStr.split('-').map((v) => parseInt(v, 10))
    : [2026, 10, 30];
  const dt = new Date(Date.UTC(y, m - 1, d, hour, minute, 0));
  return dt.toISOString();
}

function subtractMinutes(dateStr: string, hour: number, minute: number, minutesToSub: number): string {
  const [y, m, d] = dateStr.includes('-')
    ? dateStr.split('-').map((v) => parseInt(v, 10))
    : [2026, 10, 30];
  const dt = new Date(Date.UTC(y, m - 1, d, hour, minute, 0));
  const subDt = new Date(dt.getTime() - minutesToSub * 60000);
  return subDt.toISOString();
}

export function validateJourneyAgainstRequest(
  journey: Journey,
  request: TravelRequest
): { valid: boolean; reason?: string } {
  if (!request.origin || !request.destination) {
    return { valid: true };
  }
  const reqOrigin = request.origin.trim().toLowerCase();
  const reqDest = request.destination.trim().toLowerCase();

  const jOrigName = (journey.origin?.name || '').toLowerCase();
  const jOrigCity = (journey.origin?.city || '').toLowerCase();
  const jDestName = (journey.destination?.name || '').toLowerCase();
  const jDestCity = (journey.destination?.city || '').toLowerCase();

  const firstSegOrigName = (journey.segments?.[0]?.origin?.name || '').toLowerCase();
  const firstSegOrigCity = (journey.segments?.[0]?.origin?.city || '').toLowerCase();
  const lastSegDestName = (journey.segments?.[journey.segments.length - 1]?.destination?.name || '').toLowerCase();
  const lastSegDestCity = (journey.segments?.[journey.segments.length - 1]?.destination?.city || '').toLowerCase();

  const originMatches =
    jOrigName.includes(reqOrigin) ||
    jOrigCity.includes(reqOrigin) ||
    firstSegOrigName.includes(reqOrigin) ||
    firstSegOrigCity.includes(reqOrigin) ||
    reqOrigin.includes(jOrigCity) ||
    reqOrigin.includes(jOrigName);

  const destMatches =
    jDestName.includes(reqDest) ||
    jDestCity.includes(reqDest) ||
    lastSegDestName.includes(reqDest) ||
    lastSegDestCity.includes(reqDest) ||
    reqDest.includes(jDestCity) ||
    reqDest.includes(jDestName);

  if (!originMatches) {
    return {
      valid: false,
      reason: `Origin mismatch: journey has '${journey.origin?.name}', expected '${request.origin}'`,
    };
  }
  if (!destMatches) {
    return {
      valid: false,
      reason: `Destination mismatch: journey has '${journey.destination?.name}', expected '${request.destination}'`,
    };
  }

  // Strict budget check
  if (request.budgetMax && request.budgetMax > 0 && journey.totalPrice > request.budgetMax) {
    return {
      valid: false,
      reason: `Total price ₹${journey.totalPrice} exceeds budget limit ₹${request.budgetMax}`,
    };
  }

  // Intermodal transfer feasibility validation
  for (let i = 0; i < journey.segments.length - 1; i++) {
    const curArr = new Date(journey.segments[i].arrivalTime).getTime();
    const nextDep = new Date(journey.segments[i + 1].departureTime).getTime();
    if (nextDep <= curArr) {
      return {
        valid: false,
        reason: `Infeasible transfer between leg ${i + 1} and ${i + 2}: arrives ${journey.segments[i].arrivalTime} but next departs ${journey.segments[i + 1].departureTime}`,
      };
    }
  }

  return { valid: true };
}

export function generateMockJourneys(request: TravelRequest): Journey[] {
  const origin = request.origin?.trim() || 'Bangalore';
  const destination = request.destination?.trim() || 'Chennai';
  const dateStr = request.departureDate && request.departureDate.includes('-')
    ? request.departureDate
    : '2026-10-30';
  const budget = request.budgetMax && request.budgetMax > 0 ? request.budgetMax : 5000;
  const target = parseArrivalTarget(request.preferredArrivalBefore);

  const origSlug = slug(origin);
  const destSlug = slug(destination);
  const routeKey = `${origSlug}-${destSlug}`;

  // 1. FASTEST JOURNEY (Express Rail + Cab, e.g. 260 mins)
  const fastestDuration = 260; // 4h 20m
  const fastestArrMin = Math.max(0, target.minute - 40);
  const fastestArrHour = fastestArrMin < 0 ? target.hour - 1 : target.hour;
  const fastestArrIso = formatIso(dateStr, fastestArrHour, (fastestArrMin + 60) % 60);
  const fastestDepIso = subtractMinutes(dateStr, fastestArrHour, (fastestArrMin + 60) % 60, fastestDuration);
  const fastestPrice = Math.min(budget, Math.max(1200, Math.round(budget * 0.72)));

  const fastestJourney: Journey = {
    id: `jny-fastest-${routeKey}`,
    title: 'Express Superfast + SyncCab Link',
    recommendationCategory: 'fastest',
    modes: ['train', 'cab'],
    totalDurationMinutes: fastestDuration,
    totalPrice: fastestPrice,
    currency: 'INR',
    totalTransfers: 1,
    carbonKg: 14.8,
    comfortScore: 9.2,
    departureTime: fastestDepIso,
    arrivalTime: fastestArrIso,
    origin: {
      id: `loc-${origSlug}-central-rail`,
      name: `${origin} Central Railway Junction`,
      city: origin,
      type: 'railway_station',
      coordinates: { lat: 13.0827, lng: 80.2755 },
    },
    destination: {
      id: `loc-${destSlug}-center`,
      name: `${destination} City Center Hub`,
      city: destination,
      type: 'landmark',
      coordinates: { lat: 13.3409, lng: 74.7421 },
    },
    aiExplanation: {
      summary: `Fastest connection available for ${origin} → ${destination}. Direct high-speed connection arrives well before your deadline.`,
      rankReason: `Ranked #1 for Fastest. Saves over 2 hours compared to road transit with synchronous transfer guaranteed.`,
      tradeOffs: [
        `Fastest travel time from ${origin} to ${destination}`,
        'Includes priority synchronized station transfer',
      ],
      score: Math.min(99, Math.round(75 + (request.weights?.duration ?? 0.5) * 24)),
      costVsFastestSaving: 0,
      durationDiffMinutes: 0,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: `seg-${routeKey}-trn-01`,
        mode: 'train',
        provider: 'Indian Railways Superfast Express',
        vehicleName: 'Express Intercity',
        vehicleNumber: '12675',
        origin: {
          id: `loc-${origSlug}-central-rail`,
          name: `${origin} Central Station`,
          city: origin,
          type: 'railway_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        destination: {
          id: `loc-${destSlug}-junction`,
          name: `${destination} Railway Junction`,
          city: destination,
          type: 'railway_station',
          coordinates: { lat: 13.3409, lng: 74.7421 },
        },
        departureTime: fastestDepIso,
        arrivalTime: subtractMinutes(dateStr, fastestArrHour, (fastestArrMin + 60) % 60, 30),
        durationMinutes: 230,
        price: Math.round(fastestPrice * 0.85),
        currency: 'INR',
        availability: { status: 'available', remainingUnits: 14 },
        distanceKm: 380,
        carbonKg: 11.2,
        comfortScore: 9.3,
        seatClass: 'AC Chair Car / 2nd AC',
        notes: 'Complimentary high-speed WiFi and onboard refreshments.',
      },
      {
        segmentId: `seg-${routeKey}-cab-02`,
        mode: 'cab',
        provider: 'KogniSync Priority SyncCab',
        vehicleName: 'Sedan Premier Electric',
        origin: {
          id: `loc-${destSlug}-junction`,
          name: `${destination} Railway Junction`,
          city: destination,
          type: 'railway_station',
          coordinates: { lat: 13.3409, lng: 74.7421 },
        },
        destination: {
          id: `loc-${destSlug}-center`,
          name: `${destination} City Center Hub`,
          city: destination,
          type: 'landmark',
          coordinates: { lat: 13.3409, lng: 74.7421 },
        },
        departureTime: subtractMinutes(dateStr, fastestArrHour, (fastestArrMin + 60) % 60, 30),
        arrivalTime: fastestArrIso,
        durationMinutes: 30,
        price: Math.round(fastestPrice * 0.15),
        currency: 'INR',
        availability: { status: 'available', remainingUnits: 99 },
        distanceKm: 18,
        carbonKg: 3.6,
        comfortScore: 8.9,
        notes: 'Driver will meet at platform exit with name board.',
      },
    ],
  };

  // 2. BEST VALUE JOURNEY (Superfast Rail + Transit Sync, e.g. 310 mins)
  const bestValueDuration = 310;
  const bestValueArrMin = Math.max(0, target.minute - 60);
  const bestValueArrHour = bestValueArrMin < 0 ? target.hour - 1 : target.hour;
  const bestValueArrIso = formatIso(dateStr, bestValueArrHour, (bestValueArrMin + 60) % 60);
  const bestValueDepIso = subtractMinutes(dateStr, bestValueArrHour, (bestValueArrMin + 60) % 60, bestValueDuration);
  const bestValuePrice = Math.min(budget, Math.max(900, Math.round(budget * 0.42)));

  const bestValueJourney: Journey = {
    id: `jny-best-value-${routeKey}`,
    title: 'Superfast Intercity + Local Transit Link',
    recommendationCategory: 'best_value',
    modes: ['train', 'metro'],
    totalDurationMinutes: bestValueDuration,
    totalPrice: bestValuePrice,
    currency: 'INR',
    totalTransfers: 1,
    carbonKg: 9.4,
    comfortScore: 8.8,
    departureTime: bestValueDepIso,
    arrivalTime: bestValueArrIso,
    origin: {
      id: `loc-${origSlug}-main-station`,
      name: `${origin} Main Junction`,
      city: origin,
      type: 'railway_station',
      coordinates: { lat: 13.0827, lng: 80.2755 },
    },
    destination: {
      id: `loc-${destSlug}-central-terminus`,
      name: `${destination} Central Terminus`,
      city: destination,
      type: 'metro_station',
      coordinates: { lat: 13.3409, lng: 74.7421 },
    },
    aiExplanation: {
      summary: `Optimal balance of speed and affordability for ${origin} to ${destination}.`,
      rankReason: `Ranked #1 for Best Overall Value. Highly reliable schedule with smooth transfer integration.`,
      tradeOffs: [
        `Saves ₹${Math.max(500, fastestPrice - bestValuePrice)} compared to fastest option`,
        'Includes comfortable workspace seating with AC',
      ],
      score: 96,
      costVsFastestSaving: Math.max(500, fastestPrice - bestValuePrice),
      durationDiffMinutes: bestValueDuration - fastestDuration,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: `seg-${routeKey}-bv-trn-01`,
        mode: 'train',
        provider: 'Indian Railways Intercity',
        vehicleName: 'Superfast Express',
        origin: {
          id: `loc-${origSlug}-main-station`,
          name: `${origin} Main Junction`,
          city: origin,
          type: 'railway_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        destination: {
          id: `loc-${destSlug}-central-terminus`,
          name: `${destination} Central Terminus`,
          city: destination,
          type: 'metro_station',
          coordinates: { lat: 13.3409, lng: 74.7421 },
        },
        departureTime: bestValueDepIso,
        arrivalTime: bestValueArrIso,
        durationMinutes: bestValueDuration,
        price: bestValuePrice,
        currency: 'INR',
        availability: { status: 'available', remainingUnits: 22 },
        distanceKm: 375,
        carbonKg: 9.4,
        comfortScore: 8.8,
      },
    ],
  };

  // 3. CHEAPEST JOURNEY (Direct AC Sleeper Intercity Bus, e.g. 380 mins)
  const cheapestDuration = 380;
  const cheapestArrMin = Math.max(0, target.minute - 90);
  const cheapestArrHour = cheapestArrMin < 0 ? target.hour - 1 : target.hour;
  const cheapestArrIso = formatIso(dateStr, cheapestArrHour, (cheapestArrMin + 60) % 60);
  const cheapestDepIso = subtractMinutes(dateStr, cheapestArrHour, (cheapestArrMin + 60) % 60, cheapestDuration);
  const cheapestPrice = Math.min(budget, Math.max(650, Math.round(budget * 0.22)));

  const cheapestJourney: Journey = {
    id: `jny-cheapest-${routeKey}`,
    title: 'Direct AC Sleeper Intercity',
    recommendationCategory: 'cheapest',
    modes: ['bus'],
    totalDurationMinutes: cheapestDuration,
    totalPrice: cheapestPrice,
    currency: 'INR',
    totalTransfers: 0,
    carbonKg: 13.2,
    comfortScore: 7.4,
    departureTime: cheapestDepIso,
    arrivalTime: cheapestArrIso,
    origin: {
      id: `loc-${origSlug}-isbt`,
      name: `${origin} Central Bus Terminus`,
      city: origin,
      type: 'bus_terminal',
      coordinates: { lat: 13.0682, lng: 80.2052 },
    },
    destination: {
      id: `loc-${destSlug}-isbt`,
      name: `${destination} Main Bus Stand`,
      city: destination,
      type: 'bus_terminal',
      coordinates: { lat: 13.3409, lng: 74.7421 },
    },
    aiExplanation: {
      summary: `Maximum savings on ${origin} → ${destination}. Single direct vehicle with zero transfer overhead.`,
      rankReason: `Ranked #1 for Economy. Reaches ${destination} safely within budget.`,
      tradeOffs: [
        `Saves ₹${Math.max(600, bestValuePrice - cheapestPrice)} compared to rail`,
        'Zero transfer risk with direct sleeper service',
      ],
      score: Math.min(96, Math.round(75 + (request.weights?.cost ?? 0.5) * 23)),
      costVsFastestSaving: Math.max(1000, fastestPrice - cheapestPrice),
      durationDiffMinutes: cheapestDuration - fastestDuration,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: `seg-${routeKey}-chp-bus-01`,
        mode: 'bus',
        provider: 'Intercity Club Class Sleeper',
        vehicleName: 'Volvo Multi-Axle AC Sleeper',
        origin: {
          id: `loc-${origSlug}-isbt`,
          name: `${origin} Central Bus Terminus`,
          city: origin,
          type: 'bus_terminal',
          coordinates: { lat: 13.0682, lng: 80.2052 },
        },
        destination: {
          id: `loc-${destSlug}-isbt`,
          name: `${destination} Main Bus Stand`,
          city: destination,
          type: 'bus_terminal',
          coordinates: { lat: 13.3409, lng: 74.7421 },
        },
        departureTime: cheapestDepIso,
        arrivalTime: cheapestArrIso,
        durationMinutes: cheapestDuration,
        price: cheapestPrice,
        currency: 'INR',
        availability: { status: 'available', remainingUnits: 8 },
        distanceKm: 360,
        carbonKg: 13.2,
        comfortScore: 7.4,
      },
    ],
  };

  // 4. GREENEST JOURNEY (100% Electrified Express Rail, e.g. 300 mins)
  const greenestDuration = 300;
  const greenestArrMin = Math.max(0, target.minute - 60);
  const greenestArrHour = greenestArrMin < 0 ? target.hour - 1 : target.hour;
  const greenestArrIso = formatIso(dateStr, greenestArrHour, (greenestArrMin + 60) % 60);
  const greenestDepIso = subtractMinutes(dateStr, greenestArrHour, (greenestArrMin + 60) % 60, greenestDuration);
  const greenestPrice = Math.min(budget, Math.max(850, Math.round(budget * 0.32)));

  const greenestJourney: Journey = {
    id: `jny-greenest-${routeKey}`,
    title: '100% Electrified Express Rail Link',
    recommendationCategory: 'greenest',
    modes: ['train'],
    totalDurationMinutes: greenestDuration,
    totalPrice: greenestPrice,
    currency: 'INR',
    totalTransfers: 0,
    carbonKg: 5.4,
    comfortScore: 8.6,
    departureTime: greenestDepIso,
    arrivalTime: greenestArrIso,
    origin: {
      id: `loc-${origSlug}-eco-rail`,
      name: `${origin} Eco Rail Terminal`,
      city: origin,
      type: 'railway_station',
      coordinates: { lat: 13.0827, lng: 80.2755 },
    },
    destination: {
      id: `loc-${destSlug}-green-station`,
      name: `${destination} Green Station`,
      city: destination,
      type: 'railway_station',
      coordinates: { lat: 13.3409, lng: 74.7421 },
    },
    aiExplanation: {
      summary: `Lowest carbon footprint connecting ${origin} and ${destination} using 100% electrified rail.`,
      rankReason: `Produces just 5.4 kg CO2, saving 65% emissions compared to highway vehicles.`,
      tradeOffs: [
        'Lowest carbon impact of any option',
        'Direct train journey with no transfers required',
      ],
      score: Math.min(97, Math.round(75 + (request.weights?.carbon ?? 0.5) * 24)),
      costVsFastestSaving: Math.max(800, fastestPrice - greenestPrice),
      durationDiffMinutes: greenestDuration - fastestDuration,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: `seg-${routeKey}-grn-trn-01`,
        mode: 'train',
        provider: 'Vande Bharat Electric Rail',
        vehicleName: 'High-Speed Electric Train',
        origin: {
          id: `loc-${origSlug}-eco-rail`,
          name: `${origin} Eco Rail Terminal`,
          city: origin,
          type: 'railway_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        destination: {
          id: `loc-${destSlug}-green-station`,
          name: `${destination} Green Station`,
          city: destination,
          type: 'railway_station',
          coordinates: { lat: 13.3409, lng: 74.7421 },
        },
        departureTime: greenestDepIso,
        arrivalTime: greenestArrIso,
        durationMinutes: greenestDuration,
        price: greenestPrice,
        currency: 'INR',
        availability: { status: 'available', remainingUnits: 19 },
        distanceKm: 370,
        carbonKg: 5.4,
        comfortScore: 8.6,
      },
    ],
  };

  return composeMultiModalJourneys(request);
}

export const MOCK_JOURNEYS: Journey[] = [
  // 1. CHEAPEST: Intercity Express Bus
  {
    id: 'jny-cheapest-01',
    title: 'Direct AC Sleeper Intercity',
    origin: {
      id: 'loc-blr-majestic',
      name: 'Kempegowda Majestic Terminal',
      city: 'Bangalore',
      type: 'bus_terminal',
      coordinates: { lat: 12.9774, lng: 77.5713 },
    },
    destination: {
      id: 'loc-maa-koyambedu',
      name: 'Koyambedu Bus Terminus (CMBT)',
      city: 'Chennai',
      type: 'bus_terminal',
      coordinates: { lat: 13.0682, lng: 80.2052 },
    },
    departureTime: '2026-10-29T06:00:00Z',
    arrivalTime: '2026-10-29T12:20:00Z',
    totalDurationMinutes: 380, // 6h 20m
    totalPrice: 850,
    currency: 'INR',
    totalTransfers: 0,
    modes: ['bus'],
    carbonKg: 14.2,
    comfortScore: 7.2,
    recommendationCategory: 'cheapest',
    aiExplanation: {
      summary: 'Matches your ₹3000 budget with maximum savings. Direct route requires zero transfers and reaches Chennai at 12:20 PM, well before your 2:00 PM deadline.',
      rankReason: 'Ranked #1 for Economy. Saves ₹3,950 compared to the Fastest flight combo while reaching your destination comfortably with 100 minutes buffer.',
      tradeOffs: [
        'Saves ₹3,950 compared with air transit',
        'Takes 3h 10m longer than the fastest multi-modal air option',
        'Direct vehicle with no transfer risk or baggage re-checks',
      ],
      score: 94,
      costVsFastestSaving: 3950,
      durationDiffMinutes: 190,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: 'seg-bus-01',
        mode: 'bus',
        provider: 'KSRTC Airavat Club Class',
        vehicleName: 'Volvo Multi-Axle B11R',
        vehicleNumber: 'KA-01-F-8821',
        origin: {
          id: 'loc-blr-majestic',
          name: 'Kempegowda Bus Station (Majestic)',
          city: 'Bangalore',
          type: 'bus_terminal',
          coordinates: { lat: 12.9774, lng: 77.5713 },
        },
        destination: {
          id: 'loc-maa-koyambedu',
          name: 'CMBT Koyambedu',
          city: 'Chennai',
          type: 'bus_terminal',
          coordinates: { lat: 13.0682, lng: 80.2052 },
        },
        departureTime: '2026-10-29T06:00:00Z',
        arrivalTime: '2026-10-29T12:20:00Z',
        durationMinutes: 380,
        price: 850,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 12,
          inventoryId: 'inv-ksrtc-08821',
        },
        distanceKm: 346,
        carbonKg: 14.2,
        comfortScore: 7.2,
        seatClass: 'Airavat AC Semi-Sleeper',
        notes: 'Punctuality rate 96.4%. Live GPS telemetry linked to KogniSync.',
      },
    ],
  },

  // 2. BEST VALUE: Train + Metro
  {
    id: 'jny-best-value-02',
    title: 'Vande Bharat Express + Direct Metro Sync',
    origin: {
      id: 'loc-blr-sbc',
      name: 'KSR Bengaluru City Junction',
      city: 'Bangalore',
      code: 'SBC',
      type: 'railway_station',
      coordinates: { lat: 12.9781, lng: 77.5694 },
    },
    destination: {
      id: 'loc-maa-guindy',
      name: 'Guindy Central Tech Hub',
      city: 'Chennai',
      type: 'metro_station',
      coordinates: { lat: 13.0067, lng: 80.2023 },
    },
    departureTime: '2026-10-29T05:45:00Z',
    arrivalTime: '2026-10-29T10:55:00Z',
    totalDurationMinutes: 310, // 5h 10m
    totalPrice: 1450,
    currency: 'INR',
    totalTransfers: 1,
    modes: ['train', 'metro'],
    carbonKg: 9.8,
    comfortScore: 8.9,
    recommendationCategory: 'best_value',
    aiExplanation: {
      summary: 'Optimal Pareto balance between speed, cost, and high reliability. High-speed rail eliminates highway congestion risk with guaranteed onboard workspace.',
      rankReason: 'Ranked #1 for Best Overall Value. Only ₹600 more than bus, yet arrives 1 hour 25 minutes earlier with 99.1% on-time guarantee and lowest per-km carbon emissions.',
      tradeOffs: [
        'Saves 1h 10m compared to road transit',
        'Seamless 18-minute synchronized transfer at Chennai Central Metro',
        'Includes complimentary morning refreshments and ergonomic seating',
      ],
      score: 98,
      costVsFastestSaving: 3350,
      durationDiffMinutes: 120,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: 'seg-trn-01',
        mode: 'train',
        provider: 'Indian Railways High-Speed',
        vehicleName: 'Vande Bharat Express',
        vehicleNumber: '20608',
        origin: {
          id: 'loc-blr-sbc',
          name: 'KSR Bengaluru Station',
          city: 'Bangalore',
          code: 'SBC',
          type: 'railway_station',
          coordinates: { lat: 12.9781, lng: 77.5694 },
        },
        destination: {
          id: 'loc-maa-mas',
          name: 'Puratchi Thalaivar Dr. MGR Central',
          city: 'Chennai',
          code: 'MAS',
          type: 'railway_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        departureTime: '2026-10-29T05:45:00Z',
        arrivalTime: '2026-10-29T10:25:00Z',
        durationMinutes: 280,
        price: 1400,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 18,
          inventoryId: 'inv-vb-20608-cc',
        },
        distanceKm: 359,
        carbonKg: 8.9,
        comfortScore: 9.1,
        seatClass: 'AC Chair Car (CC)',
        transferBufferMinutes: 15,
        notes: 'Complimentary high-speed WiFi and onboard pantry included.',
      },
      {
        segmentId: 'seg-met-01',
        mode: 'metro',
        provider: 'Chennai Metro Rail (CMRL)',
        vehicleName: 'Blue Line Rapid Transit',
        origin: {
          id: 'loc-maa-central-metro',
          name: 'Central Metro Station',
          city: 'Chennai',
          type: 'metro_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        destination: {
          id: 'loc-maa-guindy',
          name: 'Guindy Metro Station',
          city: 'Chennai',
          type: 'metro_station',
          coordinates: { lat: 13.0067, lng: 80.2023 },
        },
        departureTime: '2026-10-29T10:40:00Z',
        arrivalTime: '2026-10-29T10:55:00Z',
        durationMinutes: 15,
        price: 50,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 999,
          inventoryId: 'inv-cmrl-qr-pass',
        },
        distanceKm: 11.4,
        carbonKg: 0.9,
        comfortScore: 8.5,
        notes: 'Automated QR gate pass generated instantly with booking.',
      },
    ],
  },

  // 3. FASTEST: Cab + Flight + Metro
  {
    id: 'jny-fastest-03',
    title: 'Pre-flight Cab + Express Air Shuttle + Metro',
    origin: {
      id: 'loc-blr-indiranagar',
      name: 'Indiranagar 100ft Road',
      city: 'Bangalore',
      type: 'address',
      coordinates: { lat: 12.9784, lng: 77.6408 },
    },
    destination: {
      id: 'loc-maa-mount-road',
      name: 'Mount Road Commercial District',
      city: 'Chennai',
      type: 'address',
      coordinates: { lat: 13.0604, lng: 80.2496 },
    },
    departureTime: '2026-10-29T07:15:00Z',
    arrivalTime: '2026-10-29T10:25:00Z',
    totalDurationMinutes: 190, // 3h 10m
    totalPrice: 4800,
    currency: 'INR',
    totalTransfers: 2,
    modes: ['cab', 'flight', 'metro'],
    carbonKg: 52.4,
    comfortScore: 8.4,
    recommendationCategory: 'fastest',
    aiExplanation: {
      summary: 'Fastest possible elapsed door-to-door transit time. Recommended when speed is top priority or emergency meetings require arrival before 11:00 AM.',
      rankReason: 'Ranked #1 for Speed. Exceeds your target budget of ₹3000 by ₹1800, but saves 2 hours over train and 3 hours over bus options.',
      tradeOffs: [
        'Total duration under 3.2 hours door-to-door',
        'Cost is ₹1,800 above specified budget threshold',
        'Requires 2 transfer handoffs (Airport Security + Metro Intermodal)',
      ],
      score: 87,
      costVsFastestSaving: 0,
      durationDiffMinutes: 0,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 450,
    },
    segments: [
      {
        segmentId: 'seg-cab-01',
        mode: 'cab',
        provider: 'Uber Airport Premier',
        vehicleName: 'Sedan AC',
        origin: {
          id: 'loc-blr-indiranagar',
          name: 'Indiranagar 100ft Rd',
          city: 'Bangalore',
          type: 'address',
          coordinates: { lat: 12.9784, lng: 77.6408 },
        },
        destination: {
          id: 'loc-blr-kia',
          name: 'Kempegowda International Airport (T1)',
          city: 'Bangalore',
          code: 'BLR',
          type: 'airport',
          coordinates: { lat: 13.1986, lng: 77.7066 },
        },
        departureTime: '2026-10-29T07:15:00Z',
        arrivalTime: '2026-10-29T08:05:00Z',
        durationMinutes: 50,
        price: 850,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 1,
          inventoryId: 'inv-uber-prebook-01',
        },
        distanceKm: 39.2,
        carbonKg: 8.1,
        comfortScore: 8.8,
        transferBufferMinutes: 45,
        notes: 'Pre-dispatched vehicle with guaranteed pickup SLA.',
      },
      {
        segmentId: 'seg-flt-01',
        mode: 'flight',
        provider: 'IndiGo Airlines',
        vehicleName: 'Airbus A321neo',
        vehicleNumber: '6E-543',
        origin: {
          id: 'loc-blr-kia',
          name: 'Bengaluru Airport T1',
          city: 'Bangalore',
          code: 'BLR',
          type: 'airport',
          coordinates: { lat: 13.1986, lng: 77.7066 },
        },
        destination: {
          id: 'loc-maa-airport',
          name: 'Chennai International Airport (MAA)',
          city: 'Chennai',
          code: 'MAA',
          type: 'airport',
          coordinates: { lat: 12.9941, lng: 80.1709 },
        },
        departureTime: '2026-10-29T08:50:00Z',
        arrivalTime: '2026-10-29T09:45:00Z',
        durationMinutes: 55,
        price: 3900,
        currency: 'INR',
        availability: {
          status: 'limited',
          remainingUnits: 4,
          inventoryId: 'inv-indigo-6e543-y',
        },
        distanceKm: 290,
        carbonKg: 43.5,
        comfortScore: 8.2,
        seatClass: 'Economy (Hand-baggage Saver)',
        transferBufferMinutes: 20,
      },
      {
        segmentId: 'seg-met-02',
        mode: 'metro',
        provider: 'Chennai Metro Rail',
        vehicleName: 'Airport Direct Express',
        origin: {
          id: 'loc-maa-airport',
          name: 'Airport Metro Station',
          city: 'Chennai',
          type: 'metro_station',
          coordinates: { lat: 12.9941, lng: 80.1709 },
        },
        destination: {
          id: 'loc-maa-mount-road',
          name: 'AG-DMS / Mount Road',
          city: 'Chennai',
          type: 'metro_station',
          coordinates: { lat: 13.0456, lng: 80.2483 },
        },
        departureTime: '2026-10-29T10:05:00Z',
        arrivalTime: '2026-10-29T10:25:00Z',
        durationMinutes: 20,
        price: 50,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 999,
          inventoryId: 'inv-cmrl-express-02',
        },
        distanceKm: 14.8,
        carbonKg: 0.8,
        comfortScore: 8.3,
      },
    ],
  },

  // 4. GREENEST / COMFORTABLE: Electric Shatabdi + EV Cab
  {
    id: 'jny-green-04',
    title: 'Zero-Emission EV Transit Chaining',
    origin: {
      id: 'loc-blr-koramangala',
      name: 'Koramangala 4th Block',
      city: 'Bangalore',
      type: 'address',
      coordinates: { lat: 12.9352, lng: 77.6245 },
    },
    destination: {
      id: 'loc-maa-tidel',
      name: 'Tidel Park OMR',
      city: 'Chennai',
      type: 'address',
      coordinates: { lat: 12.9897, lng: 80.2488 },
    },
    departureTime: '2026-10-29T06:15:00Z',
    arrivalTime: '2026-10-29T11:45:00Z',
    totalDurationMinutes: 330, // 5h 30m
    totalPrice: 1850,
    currency: 'INR',
    totalTransfers: 2,
    modes: ['cab', 'train', 'cab'],
    carbonKg: 6.2, // Lowest carbon!
    comfortScore: 9.3,
    recommendationCategory: 'greenest',
    aiExplanation: {
      summary: 'Eco-certified transit plan utilizing all-electric rides at both terminals connected by the fully electrified Shatabdi express link.',
      rankReason: 'Ranked #1 for Sustainability (88% carbon reduction vs flying). Balances strong executive comfort with strict ecological conservation.',
      tradeOffs: [
        'Emits only 6.2 kg CO₂ (lowest footprint across all options)',
        'Includes door-to-door luggage handling via certified EV partner',
        'Comfort rating of 9.3/10 with dedicated quiet coach seating',
      ],
      score: 96,
      costVsFastestSaving: 2950,
      durationDiffMinutes: 140,
    },
    bookingFeasibility: {
      holdSupported: true,
      concurrencySafe: true,
      holdTtlSeconds: 600,
    },
    segments: [
      {
        segmentId: 'seg-ev-01',
        mode: 'cab',
        provider: 'BluSmart EV Shuttle',
        vehicleName: 'BYD e6 All-Electric',
        origin: {
          id: 'loc-blr-koramangala',
          name: 'Koramangala 4th Block',
          city: 'Bangalore',
          type: 'address',
          coordinates: { lat: 12.9352, lng: 77.6245 },
        },
        destination: {
          id: 'loc-blr-cantt',
          name: 'Bengaluru Cantonment Station',
          city: 'Bangalore',
          code: 'BNC',
          type: 'railway_station',
          coordinates: { lat: 12.9937, lng: 77.5985 },
        },
        departureTime: '2026-10-29T06:15:00Z',
        arrivalTime: '2026-10-29T06:40:00Z',
        durationMinutes: 25,
        price: 250,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 3,
          inventoryId: 'inv-blusmart-ev-01',
        },
        distanceKm: 8.5,
        carbonKg: 0.4,
        comfortScore: 9.2,
      },
      {
        segmentId: 'seg-trn-02',
        mode: 'train',
        provider: 'Indian Railways Southern Zone',
        vehicleName: 'Shatabdi Express (Quiet Coach)',
        vehicleNumber: '12028',
        origin: {
          id: 'loc-blr-cantt',
          name: 'Bengaluru Cantt Station',
          city: 'Bangalore',
          code: 'BNC',
          type: 'railway_station',
          coordinates: { lat: 12.9937, lng: 77.5985 },
        },
        destination: {
          id: 'loc-maa-mas',
          name: 'Chennai Central (MAS)',
          city: 'Chennai',
          code: 'MAS',
          type: 'railway_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        departureTime: '2026-10-29T06:55:00Z',
        arrivalTime: '2026-10-29T11:10:00Z',
        durationMinutes: 255,
        price: 1350,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 14,
          inventoryId: 'inv-shatabdi-12028-ec',
        },
        distanceKm: 355,
        carbonKg: 5.2,
        comfortScore: 9.4,
        seatClass: 'Executive Chair Car (EC)',
      },
      {
        segmentId: 'seg-ev-02',
        mode: 'cab',
        provider: 'Shoffr Luxury EV',
        vehicleName: 'MG ZS EV',
        origin: {
          id: 'loc-maa-mas',
          name: 'Chennai Central Station Area',
          city: 'Chennai',
          type: 'railway_station',
          coordinates: { lat: 13.0827, lng: 80.2755 },
        },
        destination: {
          id: 'loc-maa-tidel',
          name: 'Tidel Park OMR',
          city: 'Chennai',
          type: 'address',
          coordinates: { lat: 12.9897, lng: 80.2488 },
        },
        departureTime: '2026-10-29T11:20:00Z',
        arrivalTime: '2026-10-29T11:45:00Z',
        durationMinutes: 25,
        price: 250,
        currency: 'INR',
        availability: {
          status: 'available',
          remainingUnits: 2,
          inventoryId: 'inv-shoffr-ev-02',
        },
        distanceKm: 13.2,
        carbonKg: 0.6,
        comfortScore: 9.3,
      },
    ],
  },
];

export const MOCK_CONFIRMED_TRIP: Trip = {
  tripId: 'trp-kogni-89214',
  bookingId: 'bkg-99412',
  pnr: 'KOGNI-BLRMAA-7749',
  qrCodeUrl: 'https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=KOGNI-BLRMAA-7749-VALIDATED',
  createdAt: new Date().toISOString(),
  journey: MOCK_JOURNEYS[1], // Vande Bharat + Metro
  passengers: [
    {
      id: 'pax-1',
      fullName: 'Rahul Sharma',
      email: 'rahul.sharma@example.com',
      phone: '+91 98765 43210',
      gender: 'male',
      age: 29,
    },
  ],
  tickets: [
    {
      segmentId: 'seg-trn-01',
      mode: 'train',
      provider: 'Indian Railways (Vande Bharat 20608)',
      ticketNumber: 'IR-20608-C4-32W',
      seatOrBerth: 'Coach C4 · Seat 32 (Window)',
      gateOrPlatform: 'Platform 1 · KSR Bengaluru',
      originName: 'KSR Bengaluru Station (SBC)',
      destinationName: 'Chennai Central (MAS)',
      departureTime: '2026-10-29T05:45:00Z',
      arrivalTime: '2026-10-29T10:25:00Z',
      qrPayload: 'IR-20608-C4-32W',
      status: 'confirmed',
    },
    {
      segmentId: 'seg-met-01',
      mode: 'metro',
      provider: 'Chennai Metro Rail (CMRL)',
      ticketNumber: 'CMRL-QR-98214',
      gateOrPlatform: 'Concourse Gate B · Central Station',
      originName: 'Central Metro',
      destinationName: 'Guindy Metro',
      departureTime: '2026-10-29T10:40:00Z',
      arrivalTime: '2026-10-29T10:55:00Z',
      qrPayload: 'CMRL-QR-98214',
      status: 'confirmed',
    },
  ],
  payment: {
    paymentId: 'pay_998124_upi',
    method: 'upi',
    amount: 1450,
    currency: 'INR',
    status: 'success',
    transactionRef: 'UPI-REF-20261028-9941',
    timestamp: new Date().toISOString(),
  },
  status: 'confirmed',
  supportHotline: '+91 1800-KOGNI-SYNC',
};
