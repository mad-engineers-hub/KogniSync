import { useState, useEffect, useMemo, useCallback } from 'react';
import type { Journey, JourneySegment } from '../types/journey';
import type { EnrichedJourneyRoute } from '../types/route';
import type {
  JourneyProgressState,
  SegmentGuidance,
  TransferReadiness,
  LocationGuidanceState,
} from '../types/navigation';
import { getSegmentGuidance } from '../services/navigation/maneuverEngine';
import { calculateTransferReadiness } from '../services/navigation/transferReadiness';
import {
  createInitialProgress,
  loadStoredProgress,
  saveProgressToStorage,
  clearStoredProgress,
  markSegmentCompleted,
  undoSegmentCompleted,
  markManeuverCompleted,
  advanceToNextSegment,
  setActiveSegment,
  calculateOverallProgressPercent,
} from '../services/navigation/journeyProgressStore';
import {
  startForegroundLocationTracking,
  stopForegroundLocationTracking,
  createDemoPosition,
} from '../services/navigation/foregroundGps';

export interface UseJourneyGuidanceReturn {
  progress: JourneyProgressState;
  activeSegmentIndex: number;
  activeSegment: JourneySegment | undefined;
  activeGuidance: SegmentGuidance | undefined;
  allGuidance: SegmentGuidance[];
  nextTransferReadiness: TransferReadiness | null;
  overallProgressPercent: number;
  isSegmentCompleted: (segmentId: string) => boolean;
  completeActiveSegment: () => void;
  undoSegment: (segmentId: string) => void;
  advanceNextSegment: () => void;
  selectSegmentIndex: (index: number) => void;
  toggleManeuverCompletion: (segmentId: string, maneuverIndex: number) => void;
  resetAllProgress: () => void;
  locationState: LocationGuidanceState;
  startLocationGuidance: () => void;
  stopLocationGuidance: () => void;
  triggerDemoPosition: (coords: { latitude: number; longitude: number }) => void;
  isLocationTracking: boolean;
}

export function useJourneyGuidance(
  journey: Journey,
  enrichedRoute?: EnrichedJourneyRoute
): UseJourneyGuidanceReturn {
  const journeyId = journey.id;
  const segments = journey.segments || [];
  const totalSegments = segments.length;

  // 1. Journey Progress State (restored from localStorage if available)
  const [progress, setProgress] = useState<JourneyProgressState>(() => {
    const stored = loadStoredProgress(journeyId);
    return stored || createInitialProgress(journeyId);
  });

  // Re-sync if journeyId changes
  useEffect(() => {
    const stored = loadStoredProgress(journeyId);
    setProgress(stored || createInitialProgress(journeyId));
  }, [journeyId]);

  // Persist progress changes to localStorage
  useEffect(() => {
    saveProgressToStorage(progress);
  }, [progress]);

  // 2. Foreground Location Guidance State
  const [locationState, setLocationState] = useState<LocationGuidanceState>({
    status: 'idle',
  });

  // Ensure foreground tracking stops on unmount
  useEffect(() => {
    return () => {
      stopForegroundLocationTracking();
    };
  }, []);

  const startLocationGuidance = useCallback(() => {
    startForegroundLocationTracking((state) => {
      setLocationState(state);
    });
  }, []);

  const stopLocationGuidance = useCallback(() => {
    stopForegroundLocationTracking();
    setLocationState({ status: 'idle' });
  }, []);

  const triggerDemoPosition = useCallback(
    (coords: { latitude: number; longitude: number }) => {
      setLocationState(createDemoPosition(coords));
    },
    []
  );

  // 3. Compute Segment Guidance for all segments
  const allGuidance: SegmentGuidance[] = useMemo(() => {
    return segments.map((seg, idx) => {
      const geom = enrichedRoute?.segments?.find((g) => g.segment_id === seg.segmentId);
      const completedManeuvers = progress.completedManeuverIndices[seg.segmentId] || [];
      return getSegmentGuidance(seg, idx + 1, geom, completedManeuvers);
    });
  }, [segments, enrichedRoute, progress.completedManeuverIndices]);

  const activeSegmentIndex = Math.min(progress.activeSegmentIndex, Math.max(0, totalSegments - 1));
  const activeSegment = segments[activeSegmentIndex];
  const activeGuidance = allGuidance[activeSegmentIndex];

  // 4. Compute Transfer Readiness for the next upcoming transfer connection
  const nextTransferReadiness: TransferReadiness | null = useMemo(() => {
    if (totalSegments < 2) return null;
    const completedSet = new Set(progress.completedSegmentIds);

    // Look for the transfer relevant to the active segment or next pending transfer
    const currentIdx = activeSegmentIndex;
    if (currentIdx < totalSegments - 1) {
      const incoming = segments[currentIdx];
      const outgoing = segments[currentIdx + 1];
      return calculateTransferReadiness(incoming, outgoing, Date.now(), completedSet);
    }

    return null;
  }, [segments, activeSegmentIndex, progress.completedSegmentIds, totalSegments]);

  // 5. Actions
  const isSegmentCompleted = useCallback(
    (segmentId: string) => progress.completedSegmentIds.includes(segmentId),
    [progress.completedSegmentIds]
  );

  const completeActiveSegment = useCallback(() => {
    if (!activeSegment) return;
    setProgress((prev) => markSegmentCompleted(prev, activeSegment.segmentId, totalSegments));
  }, [activeSegment, totalSegments]);

  const undoSegment = useCallback((segmentId: string) => {
    setProgress((prev) => undoSegmentCompleted(prev, segmentId));
  }, []);

  const advanceNextSegment = useCallback(() => {
    setProgress((prev) => advanceToNextSegment(prev, totalSegments));
  }, [totalSegments]);

  const selectSegmentIndex = useCallback(
    (index: number) => {
      setProgress((prev) => setActiveSegment(prev, index, totalSegments));
    },
    [totalSegments]
  );

  const toggleManeuverCompletion = useCallback(
    (segmentId: string, maneuverIndex: number) => {
      setProgress((prev) => markManeuverCompleted(prev, segmentId, maneuverIndex));
    },
    []
  );

  const resetAllProgress = useCallback(() => {
    clearStoredProgress(journeyId);
    setProgress(createInitialProgress(journeyId));
  }, [journeyId]);

  const overallProgressPercent = useMemo(() => {
    return calculateOverallProgressPercent(progress, totalSegments);
  }, [progress, totalSegments]);

  const isLocationTracking =
    locationState.status === 'live_position' ||
    locationState.status === 'requesting' ||
    locationState.status === 'demo_position';

  return {
    progress,
    activeSegmentIndex,
    activeSegment,
    activeGuidance,
    allGuidance,
    nextTransferReadiness,
    overallProgressPercent,
    isSegmentCompleted,
    completeActiveSegment,
    undoSegment,
    advanceNextSegment,
    selectSegmentIndex,
    toggleManeuverCompletion,
    resetAllProgress,
    locationState,
    startLocationGuidance,
    stopLocationGuidance,
    triggerDemoPosition,
    isLocationTracking,
  };
}

