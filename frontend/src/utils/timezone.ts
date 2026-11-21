/**
 * Timezone and Timestamp Integrity Utility for KogniSync
 *
 * Implements strict UTC instant persistence with local interpretation for India Standard Time (IST / Asia/Kolkata).
 * IST is UTC+05:30 (fixed +330 minutes offset, no DST).
 */

export const IST_TIMEZONE = 'Asia/Kolkata';
export const IST_OFFSET_MINUTES = 330; // +05:30

export interface IstDateTimeComponents {
  dateStr: string;      // 'YYYY-MM-DD'
  timeStr: string;      // 'HH:mm'
  hour: number;         // 0-23
  minute: number;       // 0-59
  isoWithOffset: string;// 'YYYY-MM-DDTHH:mm:00+05:30'
  displayTime: string;  // e.g. '7:20 PM'
  displayDateTime: string; // e.g. '15-Nov 7:20 PM'
}

/**
 * Converts local date ('YYYY-MM-DD') and local time ('HH:mm') in IST into a UTC Date instant.
 * Example: '2026-11-15' and '20:00' -> 2026-11-15T14:30:00.000Z
 */
export function istToUtcInstant(dateStr: string, timeStr: string): Date {
  const [year, month, day] = (dateStr && dateStr.includes('-'))
    ? dateStr.split('-').map((v) => parseInt(v, 10))
    : [2026, 11, 15];

  let hour = 20;
  let minute = 0;
  if (timeStr && timeStr.includes(':')) {
    const parts = timeStr.split(':').map((v) => parseInt(v, 10));
    if (!isNaN(parts[0])) hour = Math.min(23, Math.max(0, parts[0]));
    if (!isNaN(parts[1])) minute = Math.min(59, Math.max(0, parts[1]));
  }

  // Construct UTC timestamp representing the wall-clock components, then shift backward by IST offset (+330 min)
  const utcMillis = Date.UTC(year, month - 1, day, hour, minute, 0, 0) - (IST_OFFSET_MINUTES * 60 * 1000);
  return new Date(utcMillis);
}

/**
 * Converts a UTC instant (Date or ISO string) into its local IST wall-clock representation.
 */
export function utcToIstComponents(instant: Date | string): IstDateTimeComponents {
  const d = typeof instant === 'string' ? new Date(instant) : instant;
  if (isNaN(d.getTime())) {
    throw new Error(`Invalid timestamp passed to utcToIstComponents: ${instant}`);
  }

  // Shift UTC millis by +330 minutes so UTC getter methods yield local IST values
  const istMillis = d.getTime() + (IST_OFFSET_MINUTES * 60 * 1000);
  const istDate = new Date(istMillis);

  const y = istDate.getUTCFullYear();
  const m = String(istDate.getUTCMonth() + 1).padStart(2, '0');
  const day = String(istDate.getUTCDate()).padStart(2, '0');
  const h = String(istDate.getUTCHours()).padStart(2, '0');
  const min = String(istDate.getUTCMinutes()).padStart(2, '0');

  const dateStr = `${y}-${m}-${day}`;
  const timeStr = `${h}:${min}`;
  const isoWithOffset = `${dateStr}T${timeStr}:00+05:30`;

  const hourNum = istDate.getUTCHours();
  const period = hourNum >= 12 ? 'PM' : 'AM';
  const displayHour = hourNum % 12 === 0 ? 12 : hourNum % 12;
  const displayTime = `${displayHour}:${min} ${period}`;

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthAbbr = monthNames[istDate.getUTCMonth()];
  const displayDateTime = `${day}-${monthAbbr} ${displayTime}`;

  return {
    dateStr,
    timeStr,
    hour: hourNum,
    minute: istDate.getUTCMinutes(),
    isoWithOffset,
    displayTime,
    displayDateTime,
  };
}

/**
 * Formats a UTC instant into a clean local IST time string for UI display.
 */
export function formatIstTime(instant: Date | string): string {
  try {
    return utcToIstComponents(instant).displayTime;
  } catch {
    return String(instant);
  }
}

/**
 * Formats a UTC instant into a clean local IST date and time string for UI display.
 */
export function formatIstDateTime(instant: Date | string): string {
  try {
    return utcToIstComponents(instant).displayDateTime;
  } catch {
    return String(instant);
  }
}

/**
 * Checks whether an instant is in the past relative to referenceNow (or Date.now()).
 */
export function isPastInstant(instant: Date | string, referenceNow?: Date | string): boolean {
  const targetTime = typeof instant === 'string' ? new Date(instant).getTime() : instant.getTime();
  const refTime = referenceNow
    ? (typeof referenceNow === 'string' ? new Date(referenceNow).getTime() : referenceNow.getTime())
    : Date.now();
  return targetTime < refTime;
}

export interface DepartureTimingClassification {
  isPast: boolean;
  isToday: boolean;
  isTomorrow: boolean;
  isFuture: boolean;
  minutesFromNow: number;
  localDepartureDateIST: string;
  referenceDateIST: string;
}

/**
 * Classifies departure timing in Asia/Kolkata (past, later today, tomorrow, future).
 */
export function evaluateDepartureTiming(
  departureInstant: Date | string,
  referenceNow?: Date | string
): DepartureTimingClassification {
  const depDate = typeof departureInstant === 'string' ? new Date(departureInstant) : departureInstant;
  const refDate = referenceNow
    ? (typeof referenceNow === 'string' ? new Date(referenceNow) : referenceNow)
    : new Date();

  const depTime = depDate.getTime();
  const refTime = refDate.getTime();
  const diffMinutes = Math.round((depTime - refTime) / 60000);

  const depIst = utcToIstComponents(depDate);
  const refIst = utcToIstComponents(refDate);

  const isPast = depTime < refTime;
  const isToday = depIst.dateStr === refIst.dateStr && !isPast;

  // Compute tomorrow date string in IST
  const tomorrowRef = new Date(refTime + 24 * 3600 * 1000);
  const tomorrowIst = utcToIstComponents(tomorrowRef);
  const isTomorrow = depIst.dateStr === tomorrowIst.dateStr && !isPast;

  return {
    isPast,
    isToday,
    isTomorrow,
    isFuture: !isPast,
    minutesFromNow: diffMinutes,
    localDepartureDateIST: depIst.dateStr,
    referenceDateIST: refIst.dateStr,
  };
}

export interface PropagatedDownstreamWindow {
  passengerReadinessWindow: {
    earliestIST: string;
    latestIST: string;
    earliestInstantUTC: string;
    latestInstantUTC: string;
    dateStr: string;
  };
  departureWindow: {
    earliestIST: string;
    latestIST: string;
    earliestInstantUTC: string;
    latestInstantUTC: string;
    dateStr: string;
  };
  arrivalWindow: {
    earliestIST: string;
    latestIST: string;
    earliestInstantUTC: string;
    latestInstantUTC: string;
    dateStr: string;
  };
  transferBufferMinutes: number;
  waitingMinutesRange: { min: number; max: number };
  onwardTravelDurationMinutes: number;
}

/**
 * Propagates arrival uncertainty through a transfer buffer, frequency-based platform wait,
 * and downstream transit segment.
 *
 * Example:
 * Incoming railway arrival: 09:00 – 10:30 IST on 2026-11-17
 * Transfer buffer: 15 min -> Passenger readiness: 09:15 – 10:45 IST
 * Frequency-based wait: 0 – 5 min -> Onward departure: 09:15 – 10:50 IST
 * Onward metro trip: 6 min -> Destination arrival: 09:21 – 10:56 IST
 */
export function propagateDownstreamWindow(
  incomingArrivalWindow: { earliestInstantUTC: string | Date; latestInstantUTC: string | Date },
  transferBufferMinutes: number,
  onwardTravelDurationMinutes: number,
  waitingMinutesRange: { min: number; max: number } = { min: 0, max: 0 }
): PropagatedDownstreamWindow {
  const incEarliest = typeof incomingArrivalWindow.earliestInstantUTC === 'string'
    ? new Date(incomingArrivalWindow.earliestInstantUTC)
    : incomingArrivalWindow.earliestInstantUTC;
  const incLatest = typeof incomingArrivalWindow.latestInstantUTC === 'string'
    ? new Date(incomingArrivalWindow.latestInstantUTC)
    : incomingArrivalWindow.latestInstantUTC;

  // 1. Passenger readiness window after applying transfer buffer exactly once
  const readyEarliest = new Date(incEarliest.getTime() + transferBufferMinutes * 60000);
  const readyLatest = new Date(incLatest.getTime() + transferBufferMinutes * 60000);

  // 2. Onward departure window including frequency-based waiting time range (e.g. 0–5 min)
  const waitMin = waitingMinutesRange.min || 0;
  const waitMax = waitingMinutesRange.max || 0;
  const depEarliest = new Date(readyEarliest.getTime() + waitMin * 60000);
  const depLatest = new Date(readyLatest.getTime() + waitMax * 60000);

  // 3. Onward arrival window after applying pure transit ride duration exactly once
  const arrEarliest = new Date(depEarliest.getTime() + onwardTravelDurationMinutes * 60000);
  const arrLatest = new Date(depLatest.getTime() + onwardTravelDurationMinutes * 60000);

  const readyEarliestIst = utcToIstComponents(readyEarliest);
  const readyLatestIst = utcToIstComponents(readyLatest);
  const depEarliestIst = utcToIstComponents(depEarliest);
  const depLatestIst = utcToIstComponents(depLatest);
  const arrEarliestIst = utcToIstComponents(arrEarliest);
  const arrLatestIst = utcToIstComponents(arrLatest);

  return {
    passengerReadinessWindow: {
      earliestIST: readyEarliestIst.timeStr,
      latestIST: readyLatestIst.timeStr,
      earliestInstantUTC: readyEarliest.toISOString(),
      latestInstantUTC: readyLatest.toISOString(),
      dateStr: readyEarliestIst.dateStr,
    },
    departureWindow: {
      earliestIST: depEarliestIst.timeStr,
      latestIST: depLatestIst.timeStr,
      earliestInstantUTC: depEarliest.toISOString(),
      latestInstantUTC: depLatest.toISOString(),
      dateStr: depEarliestIst.dateStr,
    },
    arrivalWindow: {
      earliestIST: arrEarliestIst.timeStr,
      latestIST: arrLatestIst.timeStr,
      earliestInstantUTC: arrEarliest.toISOString(),
      latestInstantUTC: arrLatest.toISOString(),
      dateStr: arrEarliestIst.dateStr,
    },
    transferBufferMinutes,
    waitingMinutesRange: { min: waitMin, max: waitMax },
    onwardTravelDurationMinutes,
  };
}

export interface IntersegmentConnectionEvaluation {
  isFeasible: boolean;
  connectionType: 'scheduled' | 'frequency_based_estimate' | 'feeder_shuttle';
  status: 'feasible' | 'infeasible' | 'uncertain';
  passengerReadinessEarliestIST: string;
  passengerReadinessLatestIST: string;
  passengerReadinessEarliestUTC: string;
  passengerReadinessLatestUTC: string;
  onwardDepartureEarliestIST: string;
  onwardDepartureLatestIST: string;
  bufferDeficitMinutes?: number;
  reason: string;
}

/**
 * Authoritative connection feasibility evaluator between two adjacent multimodal segments.
 *
 * Checks whether the onward connection is compatible with the arrival bounds of the preceding leg.
 * - For a fixed scheduled departure: compares scheduled departure against passenger's latest readiness time.
 *   If scheduled departure < latest readiness time, connection is marked infeasible (passenger cannot catch it if preceding leg arrives at latest bound).
 * - For frequency-based urban transit (e.g. metro / local bus): tracks passenger readiness plus optional headway wait without asserting an unverified fixed departure.
 * - For unverified schedules: marks uncertainty.
 */
export function evaluateIntersegmentConnection(
  incomingArrivalWindow: { earliestInstantUTC: string | Date; latestInstantUTC: string | Date },
  outgoingService: {
    connectionType: 'scheduled' | 'frequency_based_estimate' | 'feeder_shuttle';
    scheduledDepartureInstantUTC?: string | Date;
    scheduledDepartureIST?: string;
    isScheduleVerified?: boolean;
    waitingMinutesRange?: { min: number; max: number };
  },
  transferBufferMinutes: number
): IntersegmentConnectionEvaluation {
  const incEarliest = typeof incomingArrivalWindow.earliestInstantUTC === 'string'
    ? new Date(incomingArrivalWindow.earliestInstantUTC)
    : incomingArrivalWindow.earliestInstantUTC;
  const incLatest = typeof incomingArrivalWindow.latestInstantUTC === 'string'
    ? new Date(incomingArrivalWindow.latestInstantUTC)
    : incomingArrivalWindow.latestInstantUTC;

  const readyEarliest = new Date(incEarliest.getTime() + transferBufferMinutes * 60000);
  const readyLatest = new Date(incLatest.getTime() + transferBufferMinutes * 60000);

  const readyEarliestIst = utcToIstComponents(readyEarliest);
  const readyLatestIst = utcToIstComponents(readyLatest);

  if (outgoingService.connectionType === 'scheduled') {
    if (!outgoingService.scheduledDepartureInstantUTC) {
      return {
        isFeasible: false,
        connectionType: 'scheduled',
        status: 'uncertain',
        passengerReadinessEarliestIST: readyEarliestIst.timeStr,
        passengerReadinessLatestIST: readyLatestIst.timeStr,
        passengerReadinessEarliestUTC: readyEarliest.toISOString(),
        passengerReadinessLatestUTC: readyLatest.toISOString(),
        onwardDepartureEarliestIST: 'Unknown',
        onwardDepartureLatestIST: 'Unknown',
        reason: 'Onward scheduled departure timestamp is missing or unverified.',
      };
    }

    const schedDep = typeof outgoingService.scheduledDepartureInstantUTC === 'string'
      ? new Date(outgoingService.scheduledDepartureInstantUTC)
      : outgoingService.scheduledDepartureInstantUTC;
    const schedDepIst = utcToIstComponents(schedDep);

    // If scheduled departure is earlier than latest passenger readiness, connection cannot be guaranteed
    if (schedDep.getTime() < readyLatest.getTime()) {
      const deficitMinutes = Math.round((readyLatest.getTime() - schedDep.getTime()) / 60000);
      return {
        isFeasible: false,
        connectionType: 'scheduled',
        status: 'infeasible',
        passengerReadinessEarliestIST: readyEarliestIst.timeStr,
        passengerReadinessLatestIST: readyLatestIst.timeStr,
        passengerReadinessEarliestUTC: readyEarliest.toISOString(),
        passengerReadinessLatestUTC: readyLatest.toISOString(),
        onwardDepartureEarliestIST: schedDepIst.timeStr,
        onwardDepartureLatestIST: schedDepIst.timeStr,
        bufferDeficitMinutes: deficitMinutes,
        reason: `Fixed scheduled departure (${schedDepIst.timeStr} IST) cannot be accepted for a preceding arrival that may occur up to ${utcToIstComponents(incLatest).timeStr} IST (readiness: ${readyLatestIst.timeStr} IST; deficit: ${deficitMinutes}m).`,
      };
    }

    return {
      isFeasible: true,
      connectionType: 'scheduled',
      status: 'feasible',
      passengerReadinessEarliestIST: readyEarliestIst.timeStr,
      passengerReadinessLatestIST: readyLatestIst.timeStr,
      passengerReadinessEarliestUTC: readyEarliest.toISOString(),
      passengerReadinessLatestUTC: readyLatest.toISOString(),
      onwardDepartureEarliestIST: schedDepIst.timeStr,
      onwardDepartureLatestIST: schedDepIst.timeStr,
      reason: `Fixed scheduled departure (${schedDepIst.timeStr} IST) is reachable after required ${transferBufferMinutes}m transfer buffer.`,
    };
  }

  // Frequency-based urban transit (e.g. metro / local bus)
  const waitMin = outgoingService.waitingMinutesRange?.min || 0;
  const waitMax = outgoingService.waitingMinutesRange?.max || 0;
  const depEarliest = new Date(readyEarliest.getTime() + waitMin * 60000);
  const depLatest = new Date(readyLatest.getTime() + waitMax * 60000);
  const depEarliestIst = utcToIstComponents(depEarliest);
  const depLatestIst = utcToIstComponents(depLatest);

  return {
    isFeasible: true,
    connectionType: outgoingService.connectionType,
    status: 'feasible',
    passengerReadinessEarliestIST: readyEarliestIst.timeStr,
    passengerReadinessLatestIST: readyLatestIst.timeStr,
    passengerReadinessEarliestUTC: readyEarliest.toISOString(),
    passengerReadinessLatestUTC: readyLatest.toISOString(),
    onwardDepartureEarliestIST: depEarliestIst.timeStr,
    onwardDepartureLatestIST: depLatestIst.timeStr,
    reason: waitMax > 0
      ? `Estimated onward connection: Frequency-based transit operates on regular headways (~3–5m). Passenger readiness (${readyEarliestIst.timeStr} – ${readyLatestIst.timeStr} IST) plus 0–${waitMax}m estimated wait yields onward departure window (${depEarliestIst.timeStr} – ${depLatestIst.timeStr} IST).`
      : `Estimated onward connection: Frequency-based transit operates on regular headways. Onward departure window (${readyEarliestIst.timeStr} – ${readyLatestIst.timeStr} IST) tracks passenger readiness after ${transferBufferMinutes}m transfer buffer.`,
  };
}

