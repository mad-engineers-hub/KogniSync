import { OptimizationWeights, TransportMode } from '../types/journey';
import { TravelIntent } from '../api/journey';

export interface TravelRequestState {
  origin: string;
  destination: string;
  date: string; // ISO: YYYY-MM-DD
  displayDate: string; // e.g., "Oct 30, 2026"
  departureTime: string | null; // e.g. "08:00"
  arrivalDeadline: string | null; // e.g. "20:00"
  timeDeadlineText: string; // e.g., "Arrive by 8:00 PM"
  passengers: number;
  budget: number;
  currency: string;
  weights: OptimizationWeights;
  selectedModes: Record<TransportMode, boolean>;
  naturalLanguageQuery: string;
  understoodMessage: string | null;
  originCoordinates?: { lat: number; lng: number } | null;
  destinationCoordinates?: { lat: number; lng: number } | null;
}

export function formatDisplayDate(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const y = parseInt(parts[0], 10);
      const m = parseInt(parts[1], 10);
      const d = parseInt(parts[2], 10);
      const dateObj = new Date(y, m - 1, d);
      if (!isNaN(dateObj.getTime())) {
        return dateObj.toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        });
      }
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

export function formatTime12h(time24: string): string {
  if (!time24) return '';
  try {
    const cleaned = time24.trim();
    if (cleaned.toLowerCase().includes('am') || cleaned.toLowerCase().includes('pm')) {
      return cleaned;
    }
    const [hStr, mStr] = cleaned.split(':');
    let h = parseInt(hStr, 10);
    const m = mStr || '00';
    if (isNaN(h)) return time24;
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return `${h}:${m} ${ampm}`;
  } catch {
    return time24;
  }
}

export function buildUnderstoodSummary(state: {
  origin?: string | null;
  destination?: string | null;
  displayDate?: string | null;
  arrivalDeadline?: string | null;
  departureTime?: string | null;
  budget?: number | null;
  timePriority?: number | null;
}): string {
  if (!state.origin && !state.destination) return '';
  const orig = state.origin || 'Origin';
  const dest = state.destination || 'Destination';

  let timePart = '';
  if (state.arrivalDeadline && state.departureTime) {
    timePart = `Depart ${formatTime12h(state.departureTime)} · Arrive by ${formatTime12h(state.arrivalDeadline)}`;
  } else if (state.arrivalDeadline) {
    timePart = `Arrive by ${formatTime12h(state.arrivalDeadline)}`;
  } else if (state.departureTime) {
    timePart = `Depart at ${formatTime12h(state.departureTime)}`;
  }

  const budgetPart = state.budget ? `₹${state.budget.toLocaleString()} budget` : '';
  const timePri = state.timePriority ?? 0.5;
  const priPart = timePri <= 0.3 ? 'Cost-focused' : (timePri >= 0.7 ? 'Speed-focused' : 'Balanced');

  const parts = [
    `${orig} → ${dest}`,
    state.displayDate || 'Tomorrow',
    timePart,
    budgetPart,
    priPart
  ].filter(Boolean);

  return `✨ Understood: ${parts.join(' · ')}`;
}

export function normalizeTravelIntent(
  intent: TravelIntent,
  current: TravelRequestState
): TravelRequestState {
  const nextOrigin = intent.origin && intent.origin.trim() ? intent.origin.trim() : current.origin;
  const nextDest = intent.destination && intent.destination.trim() ? intent.destination.trim() : current.destination;
  const nextDate = intent.date && intent.date.trim() ? intent.date.trim() : current.date;
  const nextDisplayDate = nextDate ? formatDisplayDate(nextDate) : current.displayDate;
  const nextDeparture = intent.departure_time !== undefined && intent.departure_time !== null ? intent.departure_time : current.departureTime;
  const nextArrival = intent.arrival_deadline !== undefined && intent.arrival_deadline !== null ? intent.arrival_deadline : current.arrivalDeadline;
  const nextBudget = intent.budget !== undefined && intent.budget !== null && intent.budget > 0 ? intent.budget : current.budget;
  const nextPassengers = intent.passengers && intent.passengers >= 1 ? intent.passengers : current.passengers;

  let nextTimeText = current.timeDeadlineText;
  if (nextArrival && nextDeparture) {
    nextTimeText = `Depart ${formatTime12h(nextDeparture)} · Arrive by ${formatTime12h(nextArrival)}`;
  } else if (nextArrival) {
    nextTimeText = `Arrive by ${formatTime12h(nextArrival)}`;
  } else if (nextDeparture) {
    nextTimeText = `Depart at ${formatTime12h(nextDeparture)}`;
  }

  const durWeight = intent.time_priority !== undefined && intent.time_priority !== null ? intent.time_priority : current.weights.duration;
  const nextWeights: OptimizationWeights = {
    duration: durWeight,
    cost: durWeight !== undefined ? (1 - durWeight) : current.weights.cost,
    comfort: intent.comfort !== undefined && intent.comfort !== null ? intent.comfort : current.weights.comfort,
    carbon: intent.sustainability !== undefined && intent.sustainability !== null ? intent.sustainability : current.weights.carbon,
  };

  const nextModes = { ...current.selectedModes };
  if (intent.preferred_modes && intent.preferred_modes.length > 0) {
    (Object.keys(nextModes) as TransportMode[]).forEach((m) => {
      nextModes[m] = false;
    });
    for (const m of intent.preferred_modes) {
      if (m in nextModes) {
        nextModes[m as TransportMode] = true;
      }
    }
  }

  const summary = intent.intent_summary
    ? `✨ Understood: ${intent.intent_summary}`
    : buildUnderstoodSummary({
        origin: nextOrigin,
        destination: nextDest,
        displayDate: nextDisplayDate,
        arrivalDeadline: nextArrival,
        departureTime: nextDeparture,
        budget: nextBudget,
        timePriority: nextWeights.duration,
      });

  return {
    ...current,
    origin: nextOrigin,
    destination: nextDest,
    date: nextDate,
    displayDate: nextDisplayDate,
    departureTime: nextDeparture,
    arrivalDeadline: nextArrival,
    timeDeadlineText: nextTimeText,
    budget: nextBudget,
    passengers: nextPassengers,
    weights: nextWeights,
    selectedModes: nextModes,
    understoodMessage: summary,
  };
}

