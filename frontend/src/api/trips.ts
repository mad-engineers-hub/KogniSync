import { apiClient, USE_MOCK_FALLBACK } from './client';
import { Trip, TripSegmentTicket } from '../types/trip';
import { Booking, PaymentDetails } from '../types/booking';
import { MOCK_CONFIRMED_TRIP } from './mockData';

export const tripSessionCache = new Map<string, Trip>();

export function generateSvgQrDataUri(pnr: string): string {
  // Generates a self-contained SVG QR code representation that renders 100% offline
  const size = 140;
  const moduleCount = 21; // standard version 1 QR grid 21x21
  const cellSize = size / moduleCount;

  let hash = 0;
  for (let i = 0; i < pnr.length; i++) {
    hash = (hash << 5) - hash + pnr.charCodeAt(i);
    hash |= 0;
  }

  let rects = '';
  const isCorner = (r: number, c: number) => {
    if (r < 7 && c < 7) return true;
    if (r < 7 && c >= moduleCount - 7) return true;
    if (r >= moduleCount - 7 && c < 7) return true;
    return false;
  };

  const drawFinder = (startX: number, startY: number) => {
    rects += `<rect x="${startX * cellSize}" y="${startY * cellSize}" width="${7 * cellSize}" height="${7 * cellSize}" fill="#071b49" rx="${cellSize}"/>`;
    rects += `<rect x="${(startX + 1) * cellSize}" y="${(startY + 1) * cellSize}" width="${5 * cellSize}" height="${5 * cellSize}" fill="#ffffff" rx="${cellSize / 2}"/>`;
    rects += `<rect x="${(startX + 2) * cellSize}" y="${(startY + 2) * cellSize}" width="${3 * cellSize}" height="${3 * cellSize}" fill="#071b49" rx="${cellSize / 2}"/>`;
  };

  drawFinder(0, 0);
  drawFinder(moduleCount - 7, 0);
  drawFinder(0, moduleCount - 7);

  for (let r = 0; r < moduleCount; r++) {
    for (let c = 0; c < moduleCount; c++) {
      if (isCorner(r, c)) continue;
      const val = Math.abs(Math.sin(hash + r * 31 + c * 17) * 10000) % 1;
      if (val > 0.44) {
        rects += `<rect x="${c * cellSize}" y="${r * cellSize}" width="${cellSize - 0.5}" height="${cellSize - 0.5}" fill="#071b49" rx="1"/>`;
      }
    }
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" fill="#ffffff"><rect width="${size}" height="${size}" fill="#ffffff" rx="10"/>${rects}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export async function getTripById(tripId: string): Promise<Trip | null> {
  if (tripSessionCache.has(tripId)) {
    return tripSessionCache.get(tripId)!;
  }

  try {
    if (!USE_MOCK_FALLBACK) {
      return await apiClient<Trip>(`/api/v1/trips/${tripId}`);
    }
  } catch (err) {
    console.warn('Backend trip fetch fallback:', err);
  }

  await new Promise((resolve) => setTimeout(resolve, 300));

  if (tripSessionCache.has(tripId)) {
    return tripSessionCache.get(tripId)!;
  }

  if (tripId === MOCK_CONFIRMED_TRIP.tripId || tripId.startsWith('trp-')) {
    return {
      ...MOCK_CONFIRMED_TRIP,
      tripId,
    };
  }

  return MOCK_CONFIRMED_TRIP;
}

export function buildTripFromBooking(booking: Booking, payment: PaymentDetails): Trip {
  const origCity = booking.journey?.origin?.city || booking.journey?.origin?.name || 'ORG';
  const destCity = booking.journey?.destination?.city || booking.journey?.destination?.name || 'DST';
  const origCode = (origCity.replace(/[^a-zA-Z]/g, '').slice(0, 3) || 'ORG').toUpperCase().padEnd(3, 'X');
  const destCode = (destCity.replace(/[^a-zA-Z]/g, '').slice(0, 3) || 'DST').toUpperCase().padEnd(3, 'X');
  const pnr = `KOGNI-${origCode}${destCode}-${Math.floor(1000 + Math.random() * 9000)}`;

  const tickets: TripSegmentTicket[] = booking.journey.segments.map((seg, idx) => ({
    segmentId: seg.segmentId,
    mode: seg.mode,
    provider: seg.provider,
    ticketNumber: `TKT-${seg.mode.toUpperCase()}-${Math.floor(10000 + Math.random() * 90000)}`,
    seatOrBerth: seg.seatClass ? `${seg.seatClass} · Seat ${12 + idx * 4}` : undefined,
    gateOrPlatform: seg.mode === 'flight' ? 'Gate 4B · Terminal 1' : seg.mode === 'train' ? 'Platform 1' : 'Bay 3',
    originName: seg.origin.name,
    destinationName: seg.destination.name,
    departureTime: seg.departureTime,
    arrivalTime: seg.arrivalTime,
    qrPayload: `${pnr}-SEG-${idx + 1}`,
    status: 'confirmed',
  }));

  const trip: Trip = {
    tripId: `trp-${Math.random().toString(36).substring(2, 9)}`,
    bookingId: booking.bookingId,
    pnr,
    qrCodeUrl: generateSvgQrDataUri(pnr),
    createdAt: new Date().toISOString(),
    journey: booking.journey,
    passengers: booking.passengers,
    tickets,
    payment,
    status: 'confirmed',
    supportHotline: '+91 1800-KOGNI-SYNC',
    calendarSyncUrl: '#calendar-sync',
  };

  tripSessionCache.set(trip.tripId, trip);
  return trip;
}
