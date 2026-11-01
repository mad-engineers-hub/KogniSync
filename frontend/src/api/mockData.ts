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
  return composeMultiModalJourneys(request);
}

// Canonical multi-modal journeys generated deterministically for default route
export const MOCK_JOURNEYS: Journey[] = composeMultiModalJourneys({
  origin: 'Bangalore',
  destination: 'Chennai',
  departureDate: '2026-10-30',
  preferredArrivalBefore: '14:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.4, duration: 0.3, comfort: 0.2, carbon: 0.1 },
});


export const MOCK_CONFIRMED_TRIP: Trip = {
  tripId: 'trp-demo-blr-maa-01',
  bookingId: 'bk-demo-blr-maa-01',
  pnr: 'KOGNI-BLRMAA-8842',
  qrCodeUrl: 'https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=KOGNISYNC-TRIP-BLRMAA-8842',
  createdAt: '2026-10-30T08:30:00Z',
  journey: MOCK_JOURNEYS[0],
  passengers: [
    {
      id: 'pax-01',
      fullName: 'Gagan Sharma',
      email: 'gagan@kognisync.travel',
      phone: '+91 98450 12345',
      idNumber: 'XXXX-XXXX-4321',
    },
  ],
  tickets: MOCK_JOURNEYS[0].segments.map((seg, idx) => ({
    segmentId: seg.segmentId,
    mode: seg.mode,
    provider: seg.provider,
    ticketNumber: `TKT-${seg.mode.toUpperCase()}-${80000 + idx * 111}`,
    seatOrBerth: seg.seatClass ? `${seg.seatClass} · Seat ${14 + idx * 2}` : undefined,
    gateOrPlatform: seg.mode === 'flight' ? 'Gate 4B · Terminal 1' : seg.mode === 'train' ? 'Platform 1' : 'Bay 3',
    originName: seg.origin.name,
    destinationName: seg.destination.name,
    departureTime: seg.departureTime,
    arrivalTime: seg.arrivalTime,
    qrPayload: `SEG-${idx + 1}-${seg.segmentId}`,
    status: 'confirmed',
  })),
  payment: {
    paymentId: 'pay-demo-01',
    transactionRef: 'txn-demo-verified-9921',
    amount: MOCK_JOURNEYS[0].totalPrice,
    currency: 'INR',
    method: 'upi',
    timestamp: '2026-10-30T08:32:00Z',
    status: 'success',
  },
  status: 'confirmed',
  calendarSyncUrl: 'https://calendar.google.com/calendar/render?action=TEMPLATE&text=KogniSync+Trip',
  supportHotline: '+91 80 4455 6677 (24x7 Multi-Modal Dispatch Desk)',
};
