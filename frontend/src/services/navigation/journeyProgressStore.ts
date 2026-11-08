import type { JourneyProgressState } from '../../types/navigation';

const STORAGE_PREFIX = 'kognisync_guidance_progress_';

/**
 * Creates the initial default progress state for a journey.
 */
export function createInitialProgress(journeyId: string): JourneyProgressState {
  return {
    journeyId,
    activeSegmentIndex: 0,
    completedSegmentIds: [],
    completedManeuverIndices: {},
    lastUpdatedISO: new Date().toISOString(),
    isDeviceLocal: true,
  };
}

/**
 * Loads journey progress from localStorage with graceful fallback.
 */
export function loadStoredProgress(journeyId: string): JourneyProgressState | null {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${journeyId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as JourneyProgressState;
    if (parsed && parsed.journeyId === journeyId && Array.isArray(parsed.completedSegmentIds)) {
      return {
        ...parsed,
        isDeviceLocal: true,
      };
    }
  } catch (err) {
    console.warn(`Could not restore local journey progress for ${journeyId}:`, err);
  }
  return null;
}

/**
 * Persists journey progress to localStorage.
 */
export function saveProgressToStorage(state: JourneyProgressState): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    const toStore: JourneyProgressState = {
      ...state,
      lastUpdatedISO: new Date().toISOString(),
      isDeviceLocal: true,
    };
    window.localStorage.setItem(`${STORAGE_PREFIX}${state.journeyId}`, JSON.stringify(toStore));
  } catch (err) {
    console.warn(`Could not persist local journey progress for ${state.journeyId}:`, err);
  }
}

/**
 * Clears stored progress for a journey.
 */
export function clearStoredProgress(journeyId: string): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    window.localStorage.removeItem(`${STORAGE_PREFIX}${journeyId}`);
  } catch (err) {
    console.warn(`Could not clear local journey progress for ${journeyId}:`, err);
  }
}

/**
 * Pure transition: Mark a segment as completed.
 * Automatically advances activeSegmentIndex to the next incomplete segment if available.
 */
export function markSegmentCompleted(
  state: JourneyProgressState,
  segmentId: string,
  totalSegments: number
): JourneyProgressState {
  const existingSet = new Set(state.completedSegmentIds);
  existingSet.add(segmentId);

  const completed = Array.from(existingSet);
  let nextActiveIndex = state.activeSegmentIndex;

  // If completing current segment, advance to next segment if not at the end
  if (nextActiveIndex < totalSegments - 1) {
    nextActiveIndex += 1;
  }

  return {
    ...state,
    completedSegmentIds: completed,
    activeSegmentIndex: Math.min(nextActiveIndex, totalSegments - 1),
    lastUpdatedISO: new Date().toISOString(),
  };
}

/**
 * Pure transition: Undo completion of a segment.
 */
export function undoSegmentCompleted(
  state: JourneyProgressState,
  segmentId: string
): JourneyProgressState {
  return {
    ...state,
    completedSegmentIds: state.completedSegmentIds.filter((id) => id !== segmentId),
    lastUpdatedISO: new Date().toISOString(),
  };
}

/**
 * Pure transition: Mark an individual maneuver completed.
 */
export function markManeuverCompleted(
  state: JourneyProgressState,
  segmentId: string,
  maneuverIndex: number
): JourneyProgressState {
  const currentIndices = state.completedManeuverIndices[segmentId] || [];
  const set = new Set(currentIndices);
  set.add(maneuverIndex);

  return {
    ...state,
    completedManeuverIndices: {
      ...state.completedManeuverIndices,
      [segmentId]: Array.from(set).sort((a, b) => a - b),
    },
    lastUpdatedISO: new Date().toISOString(),
  };
}

/**
 * Pure transition: Advance to the next segment.
 */
export function advanceToNextSegment(
  state: JourneyProgressState,
  totalSegments: number
): JourneyProgressState {
  const nextIndex = Math.min(state.activeSegmentIndex + 1, totalSegments - 1);
  return {
    ...state,
    activeSegmentIndex: nextIndex,
    lastUpdatedISO: new Date().toISOString(),
  };
}

/**
 * Pure transition: Move to a specific segment index.
 */
export function setActiveSegment(
  state: JourneyProgressState,
  index: number,
  totalSegments: number
): JourneyProgressState {
  const safeIndex = Math.max(0, Math.min(index, totalSegments - 1));
  return {
    ...state,
    activeSegmentIndex: safeIndex,
    lastUpdatedISO: new Date().toISOString(),
  };
}

/**
 * Computes overall completion percentage (0 - 100).
 */
export function calculateOverallProgressPercent(
  state: JourneyProgressState,
  totalSegments: number
): number {
  if (totalSegments <= 0) return 0;
  const count = state.completedSegmentIds.length;
  return Math.min(100, Math.round((count / totalSegments) * 100));
}

