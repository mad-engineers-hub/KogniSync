import { Journey } from '../types/journey';
import { STATIC_XR_SCENES } from '../api/xrData';

export interface JourneyXRReference {
  sceneId: string;
  title: string;
  context: 'first_mile' | 'transfer' | 'last_mile' | 'destination';
  hubName: string;
}

const GENERIC_TRANSPORT_TAGS = new Set([
  'transfer',
  'railway',
  'bus',
  'train',
  'flight',
  'cab',
  'intermodal',
  'transit',
  'station',
  'airport',
  'feeder',
]);

/**
 * Data-driven matcher: finds canonical XR transfer scenes matching hub metadata.
 */
export function matchXRSceneForHub(hubName: string): string | null {
  if (!hubName) return null;
  const qNorm = hubName.toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!qNorm) return null;

  for (const scene of Object.values(STATIC_XR_SCENES)) {
    if (scene.entity_type !== 'transfer') continue;

    // Direct location or city match
    const locNorm = scene.location_name.toLowerCase().replace(/[^a-z0-9]/g, '');
    const cityNorm = scene.city_name.toLowerCase().replace(/[^a-z0-9]/g, '');

    if (
      (cityNorm && (qNorm.includes(cityNorm) || cityNorm.includes(qNorm))) ||
      (locNorm && (qNorm.includes(locNorm) || locNorm.includes(qNorm)))
    ) {
      return scene.scene_id;
    }

    // Specific non-generic tag match (e.g. 'blr', 'mas', 'ixe', 'mao', 'ksr', 'madgaon')
    const specificTags = (scene.tags || []).filter((t) => !GENERIC_TRANSPORT_TAGS.has(t.toLowerCase()));
    for (const tag of specificTags) {
      const tagNorm = tag.toLowerCase().replace(/[^a-z0-9]/g, '');
      if (tagNorm.length >= 3 && qNorm.includes(tagNorm)) {
        return scene.scene_id;
      }
    }
  }
  return null;
}

/**
 * Returns all matched XR references along a complete multimodal journey
 * by inspecting segments and destination data against canonical scenes.
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

  // 1. Check segments and intermediate transfer hubs against canonical scene registry
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

  // 2. Data-driven hotel preview: resolve canonical hotel XR scenes matching destination city
  const destNorm = (journey.destination?.name || journey.destination?.city || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');

  if (destNorm) {
    for (const scene of Object.values(STATIC_XR_SCENES)) {
      if (scene.entity_type === 'hotel') {
        const hotelCityNorm = scene.city_name.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (destNorm.includes(hotelCityNorm) || hotelCityNorm.includes(destNorm)) {
          add(scene.scene_id, `${scene.title} (Hotel Preview)`, 'destination', scene.city_name);
        }
      }
    }
  }

  return refs;
}
