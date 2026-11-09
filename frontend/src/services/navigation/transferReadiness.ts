import type { JourneySegment } from '../../types/journey';
import type { TransferReadiness } from '../../types/navigation';

/**
 * Deterministic transfer readiness calculator.
 * Evaluates the connection between an incoming and outgoing segment.
 *
 * All time calculations are pure functions that operate on epoch milliseconds,
 * guaranteeing correct handling of overnight journeys, date boundaries, and timezones.
 */
export function calculateTransferReadiness(
  incomingSegment: JourneySegment,
  outgoingSegment: JourneySegment,
  currentTime: Date | string | number = Date.now(),
  completedSegmentIds: Set<string> = new Set()
): TransferReadiness {
  const hubName = incomingSegment.destination?.name || outgoingSegment.origin?.name || 'Transfer Station';
  const incomingMode = incomingSegment.mode;
  const outgoingMode = outgoingSegment.mode;

  // 1. Missing or unparseable timestamps guard
  if (!incomingSegment.arrivalTime || !outgoingSegment.departureTime) {
    return createUnknownReadiness(
      incomingSegment.segmentId,
      outgoingSegment.segmentId,
      hubName,
      incomingMode,
      outgoingMode,
      'Missing scheduled arrival or departure timestamps'
    );
  }

  const incomingArrivalMs = new Date(incomingSegment.arrivalTime).getTime();
  const outgoingDepartureMs = new Date(outgoingSegment.departureTime).getTime();
  const nowMs = typeof currentTime === 'number'
    ? currentTime
    : new Date(currentTime).getTime();

  if (isNaN(incomingArrivalMs) || isNaN(outgoingDepartureMs) || isNaN(nowMs)) {
    return createUnknownReadiness(
      incomingSegment.segmentId,
      outgoingSegment.segmentId,
      hubName,
      incomingMode,
      outgoingMode,
      'Invalid ISO timestamp format'
    );
  }

  const isIncomingCompleted = completedSegmentIds.has(incomingSegment.segmentId);
  const isOutgoingCompleted = completedSegmentIds.has(outgoingSegment.segmentId);

  // 2. Both legs completed
  if (isIncomingCompleted && isOutgoingCompleted) {
    return {
      state: 'completed',
      hubName,
      incomingSegmentId: incomingSegment.segmentId,
      outgoingSegmentId: outgoingSegment.segmentId,
      incomingMode,
      outgoingMode,
      scheduledArrival: incomingSegment.arrivalTime,
      scheduledDeparture: outgoingSegment.departureTime,
      requiredBufferMinutes: incomingSegment.transferBufferMinutes || 15,
      availableBufferMinutes: Math.round((outgoingDepartureMs - incomingArrivalMs) / 60000),
      minutesUntilTransfer: 0,
      stateTitle: `Transfer Completed at ${hubName}`,
      stateDescription: `Connection to ${outgoingSegment.provider || outgoingMode} completed successfully.`,
      badgeColor: 'emerald',
      isTimeEstimated: Boolean(incomingSegment.provenance?.isEstimate || outgoingSegment.provenance?.isEstimate),
    };
  }

  const requiredBufferMinutes = incomingSegment.transferBufferMinutes && incomingSegment.transferBufferMinutes > 0
    ? incomingSegment.transferBufferMinutes
    : 15;
  const availableBufferMinutes = Math.round((outgoingDepartureMs - incomingArrivalMs) / 60000);
  const minutesUntilTransfer = Math.round((incomingArrivalMs - nowMs) / 60000);
  const minutesUntilDeparture = Math.round((outgoingDepartureMs - nowMs) / 60000);
  const isTimeEstimated = Boolean(incomingSegment.provenance?.isEstimate || outgoingSegment.provenance?.isEstimate);

  // 3. Estimated Missed Connection: departure timestamp has fully elapsed while outgoing leg is incomplete
  if (nowMs > outgoingDepartureMs) {
    const isAtStation = isIncomingCompleted && !isOutgoingCompleted;
    return {
      state: 'missed_estimated',
      hubName,
      incomingSegmentId: incomingSegment.segmentId,
      outgoingSegmentId: outgoingSegment.segmentId,
      incomingMode,
      outgoingMode,
      scheduledArrival: incomingSegment.arrivalTime,
      scheduledDeparture: outgoingSegment.departureTime,
      requiredBufferMinutes,
      availableBufferMinutes,
      minutesUntilTransfer,
      stateTitle: isAtStation ? `Departure Elapsed at ${hubName}` : `Estimated Departure Elapsed`,
      stateDescription: isAtStation
        ? `Scheduled connection time via ${outgoingSegment.provider || outgoingMode} has elapsed. Please check with station or carrier staff for re-accommodation.`
        : `Scheduled connection time via ${outgoingSegment.provider || outgoingMode} has passed. Verify current departure status with the operator.`,
      badgeColor: 'rose',
      isTimeEstimated,
    };
  }

  // 4. User already completed incoming segment and is at the station/hub waiting
  if (isIncomingCompleted && !isOutgoingCompleted) {
    return {
      state: 'in_progress',
      hubName,
      incomingSegmentId: incomingSegment.segmentId,
      outgoingSegmentId: outgoingSegment.segmentId,
      incomingMode,
      outgoingMode,
      scheduledArrival: incomingSegment.arrivalTime,
      scheduledDeparture: outgoingSegment.departureTime,
      requiredBufferMinutes,
      availableBufferMinutes,
      minutesUntilTransfer: 0,
      stateTitle: `At ${hubName} (Transfer In Progress)`,
      stateDescription: minutesUntilDeparture > 0
        ? `~${minutesUntilDeparture} min until departure of ${outgoingSegment.vehicleName || outgoingMode}. Follow station signage.`
        : `Connection departure scheduled now via ${outgoingSegment.provider || outgoingMode}.`,
      badgeColor: 'blue',
      isTimeEstimated,
    };
  }

  // 5. Tight Connection Warning: available buffer < 10 minutes or less than required buffer
  if (availableBufferMinutes < 10 || availableBufferMinutes < requiredBufferMinutes) {
    return {
      state: 'tight_connection',
      hubName,
      incomingSegmentId: incomingSegment.segmentId,
      outgoingSegmentId: outgoingSegment.segmentId,
      incomingMode,
      outgoingMode,
      scheduledArrival: incomingSegment.arrivalTime,
      scheduledDeparture: outgoingSegment.departureTime,
      requiredBufferMinutes,
      availableBufferMinutes,
      minutesUntilTransfer,
      stateTitle: `Tight Connection Window (${availableBufferMinutes} min buffer)`,
      stateDescription: `Limited transfer time between ${incomingMode} and ${outgoingMode} at ${hubName}. Prepare to disembark promptly upon arrival.`,
      badgeColor: 'amber',
      isTimeEstimated,
    };
  }

  // 6. Imminent arrival at transfer station (within 15 minutes)
  if (minutesUntilTransfer <= 15 && minutesUntilTransfer >= 0) {
    return {
      state: 'prepare',
      hubName,
      incomingSegmentId: incomingSegment.segmentId,
      outgoingSegmentId: outgoingSegment.segmentId,
      incomingMode,
      outgoingMode,
      scheduledArrival: incomingSegment.arrivalTime,
      scheduledDeparture: outgoingSegment.departureTime,
      requiredBufferMinutes,
      availableBufferMinutes,
      minutesUntilTransfer,
      stateTitle: `Prepare for Transfer at ${hubName}`,
      stateDescription: `Arriving in ~${minutesUntilTransfer} min. Gather your items and prepare to connect to ${outgoingSegment.provider || outgoingMode} (${availableBufferMinutes} min buffer).`,
      badgeColor: 'amber',
      isTimeEstimated,
    };
  }

  // 7. Incoming arrival has passed, but outgoing departure has not yet elapsed
  if (minutesUntilTransfer < 0 && minutesUntilDeparture >= 0) {
    return {
      state: 'prepare',
      hubName,
      incomingSegmentId: incomingSegment.segmentId,
      outgoingSegmentId: outgoingSegment.segmentId,
      incomingMode,
      outgoingMode,
      scheduledArrival: incomingSegment.arrivalTime,
      scheduledDeparture: outgoingSegment.departureTime,
      requiredBufferMinutes,
      availableBufferMinutes,
      minutesUntilTransfer: 0,
      stateTitle: `Transfer Window Active at ${hubName}`,
      stateDescription: `Arrived or arriving now. ~${minutesUntilDeparture} min until departure of ${outgoingSegment.provider || outgoingMode}.`,
      badgeColor: 'amber',
      isTimeEstimated,
    };
  }

  // 8. Upcoming Transfer
  return {
    state: 'upcoming',
    hubName,
    incomingSegmentId: incomingSegment.segmentId,
    outgoingSegmentId: outgoingSegment.segmentId,
    incomingMode,
    outgoingMode,
    scheduledArrival: incomingSegment.arrivalTime,
    scheduledDeparture: outgoingSegment.departureTime,
    requiredBufferMinutes,
    availableBufferMinutes,
    minutesUntilTransfer,
    stateTitle: `Upcoming Transfer at ${hubName}`,
    stateDescription: `Estimated arrival in ${minutesUntilTransfer} min. ${availableBufferMinutes} min scheduled connection buffer.`,
    badgeColor: 'emerald',
    isTimeEstimated,
  };
}

function createUnknownReadiness(
  incomingSegmentId: string,
  outgoingSegmentId: string,
  hubName: string,
  incomingMode: JourneySegment['mode'],
  outgoingMode: JourneySegment['mode'],
  reason: string
): TransferReadiness {
  return {
    state: 'unknown',
    hubName,
    incomingSegmentId,
    outgoingSegmentId,
    incomingMode,
    outgoingMode,
    scheduledArrival: '',
    scheduledDeparture: '',
    requiredBufferMinutes: 15,
    availableBufferMinutes: 0,
    minutesUntilTransfer: 0,
    stateTitle: `Transfer Readiness Unknown`,
    stateDescription: `Timing information for transfer at ${hubName} is incomplete (${reason}).`,
    badgeColor: 'slate',
    isTimeEstimated: true,
  };
}

/**
 * Disruption-aware transfer readiness calculator (Milestone M3.7).
 * Combines existing scheduled transfer readiness with external disruption delay estimates.
 * Preserves completed user progress (completed progress is immutable).
 */
export function calculateDisruptedTransferReadiness(
  incomingSegment: JourneySegment,
  outgoingSegment: JourneySegment,
  disruptionDelayMinutes: number = 0,
  currentTime: Date | string | number = Date.now(),
  completedSegmentIds: Set<string> = new Set()
): TransferReadiness {
  const base = calculateTransferReadiness(
    incomingSegment,
    outgoingSegment,
    currentTime,
    completedSegmentIds
  );

  // If completed or unknown, disruption does not alter completed status
  if (base.state === 'completed' || base.state === 'unknown' || disruptionDelayMinutes <= 0) {
    return {
      ...base,
      disruptionRisk: 'safe',
      disruptionDelayMinutes: 0,
    };
  }

  // Calculate adjusted buffer: scheduled buffer - disruption delay
  const adjustedBuffer = base.availableBufferMinutes - disruptionDelayMinutes;

  let disruptionRisk: 'safe' | 'at_risk' | 'critical' | 'missed_estimated' = 'safe';
  let state = base.state;
  let badgeColor = base.badgeColor;
  let stateTitle = base.stateTitle;
  let stateDescription = base.stateDescription;

  if (adjustedBuffer < 0) {
    disruptionRisk = 'critical';
    state = 'missed_estimated';
    badgeColor = 'rose';
    stateTitle = `Critical Disruption: Transfer at Risk at ${base.hubName}`;
    stateDescription = `Estimated +${disruptionDelayMinutes}m delay on incoming ${incomingSegment.mode} eliminates connection buffer (shortfall: ${Math.abs(
      adjustedBuffer
    )}m). Recovery rerouting recommended.`;
  } else if (adjustedBuffer < base.requiredBufferMinutes) {
    disruptionRisk = 'at_risk';
    state = 'tight_connection';
    badgeColor = 'amber';
    stateTitle = `Tight Connection (+${disruptionDelayMinutes}m Disruption Delay)`;
    stateDescription = `Incoming disruption reduces buffer to ${adjustedBuffer}m (required: ${base.requiredBufferMinutes}m) at ${base.hubName}. Prepare for expedited transfer.`;
  }

  return {
    ...base,
    state,
    badgeColor,
    stateTitle,
    stateDescription,
    availableBufferMinutes: adjustedBuffer,
    disruptionRisk,
    disruptionDelayMinutes,
    disruptionNotice: `+${disruptionDelayMinutes}m Disruption Delay`,
  };
}


