import { Journey } from '../types/journey';

export interface JourneyXRReference {
  sceneId: string;
  title: string;
  context: 'first_mile' | 'transfer' | 'last_mile' | 'destination';
  hubName: string;
}

/**
 * Normalizes hub names and finds relevant canonical XR scenes for a segment or transfer.
 */
export function matchXRSceneForHub(hubName: string): string | null {
  if (!hubName) return null;
  const norm = hubName.toLowerCase().replace(/[^a-z0-9]/g, '');

  if (norm.includes('chennai') || norm.includes('central') || norm.includes('mas')) {
    return 'xrs_chennai_central_concourse';
  }
  if (
    norm.includes('ksr') ||
    norm.includes('bengaluru') ||
    norm.includes('bangalore') ||
    norm.includes('majestic') ||
    norm.includes('udayapalya')
  ) {
    return 'xrs_ksr_bengaluru_interchange';
  }
  if (norm.includes('udupi') || norm.includes('mangalore') || norm.includes('ixe') || norm.includes('manipal')) {
    return 'xrs_mangalore_udupi_transit';
  }
  if (norm.includes('goa') || norm.includes('madgaon') || norm.includes('margao') || norm.includes('mao')) {
    return 'xrs_goa_madgaon_hub';
  }
  return null;
}

/**
 * Returns all matched XR references along a complete multimodal journey.
 */
export function getJourneyXRReferences(journey: Journey): JourneyXRReference[] {
  const refs: JourneyXRReference[] = [];
  const seenScenes = new Set<string>();

  const add = (sceneId: string, title: string, context: JourneyXRReference['context'], hubName: string) => {
    if (!seenScenes.has(sceneId)) {
      seenScenes.add(sceneId);
      refs.push({ sceneId, title, context, hubName });
    }
  };

  // 1. Check segments and intermediate transfer hubs
  journey.segments.forEach((seg, idx) => {
    // Departure hub for first segment
    if (idx === 0) {
      const sceneId = matchXRSceneForHub(seg.origin.name);
      if (sceneId) {
        add(sceneId, 'Departure Interchange', 'first_mile', seg.origin.name);
      }
    }

    // Transfer node at destination of intermediate segment
    if (idx < journey.segments.length - 1) {
      const sceneId = matchXRSceneForHub(seg.destination.name);
      if (sceneId) {
        add(sceneId, 'Intermodal Station Guide & AR Wayfinding', 'transfer', seg.destination.name);
      }
    }

    // Final destination arrival
    if (idx === journey.segments.length - 1) {
      const sceneId = matchXRSceneForHub(seg.destination.name);
      if (sceneId) {
        add(sceneId, 'Destination Arrival Hub', 'last_mile', seg.destination.name);
      }
    }
  });

  // 2. Check destination city for canonical hotel XR scene
  const destNorm = (journey.destination?.name || '').toLowerCase();
  if (destNorm.includes('chennai')) {
    add('xrs_htl_8179b205', 'Grand Courtyard Chennai (Hotel Preview)', 'destination', 'Chennai');
  } else if (destNorm.includes('bengaluru') || destNorm.includes('bangalore')) {
    add('xrs_htl_aceeb75d', 'Hotel Residency Bengaluru (Hotel Preview)', 'destination', 'Bengaluru');
  }

  return refs;
}
