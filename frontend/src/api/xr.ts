import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import {
  XRScene,
  ARWayfindingCase,
  XRDeviceProfile,
  XRExperienceMatchRequest,
  XRExperienceMatchResponse,
} from '../types/xr';
import { STATIC_XR_SCENES, STATIC_DEVICE_PROFILES } from './xrData';

export async function fetchXRScenes(entityType?: string, city?: string): Promise<XRScene[]> {
  try {
    const params = new URLSearchParams();
    if (entityType) params.set('entity_type', entityType);
    if (city) params.set('city', city);
    const query = params.toString() ? `?${params.toString()}` : '';
    const scenes = await apiClient<XRScene[]>(`/api/v1/xr/scenes${query}`);
    if (scenes && scenes.length > 0) return scenes;
  } catch (err) {
    console.warn('[XR API] Falling back to static XR scenes:', err);
  }

  let list = Object.values(STATIC_XR_SCENES);
  if (entityType) {
    list = list.filter((s) => s.entity_type === entityType);
  }
  if (city) {
    const cNorm = city.toLowerCase().replace(/[^a-z0-9]/g, '');
    list = list.filter(
      (s) =>
        s.city_name.toLowerCase().includes(cNorm) ||
        s.location_name.toLowerCase().includes(cNorm)
    );
  }
  return list;
}

export async function fetchXRScene(sceneId: string): Promise<XRScene> {
  try {
    const scene = await apiClient<XRScene>(`/api/v1/xr/scenes/${sceneId}`);
    if (scene) return scene;
  } catch (err) {
    console.warn(`[XR API] Falling back to static scene for ${sceneId}:`, err);
  }

  const local = STATIC_XR_SCENES[sceneId];
  if (local) return local;
  throw new Error(`XR Scene '${sceneId}' not found.`);
}

export async function matchJourneyXR(
  req: XRExperienceMatchRequest
): Promise<XRExperienceMatchResponse> {
  try {
    const res = await apiClient<XRExperienceMatchResponse>('/api/v1/xr/match', {
      method: 'POST',
      body: JSON.stringify(req),
    });
    if (res && res.scenes) return res;
  } catch (err) {
    console.warn('[XR API] Falling back to client-side journey matcher:', err);
  }

  // Client-side fallback matching
  const matched: XRScene[] = [];
  const seen = new Set<string>();

  const add = (s: XRScene) => {
    if (!seen.has(s.scene_id)) {
      seen.add(s.scene_id);
      matched.push(s);
    }
  };

  const norm = (str?: string) => (str || '').toLowerCase().replace(/[^a-z0-9]/g, '');

  if (req.hotel_id) {
    for (const s of Object.values(STATIC_XR_SCENES)) {
      if (s.entity_id === req.hotel_id || s.scene_id === `xrs_${req.hotel_id}`) {
        add(s);
      }
    }
  }

  if (req.transfer_hubs) {
    for (const hub of req.transfer_hubs) {
      const hNorm = norm(hub);
      for (const s of Object.values(STATIC_XR_SCENES)) {
        if (norm(s.title).includes(hNorm) || norm(s.location_name).includes(hNorm) || s.tags.some(t => norm(t).includes(hNorm))) {
          add(s);
        }
      }
    }
  }

  if (req.destination) {
    const dNorm = norm(req.destination);
    for (const s of Object.values(STATIC_XR_SCENES)) {
      if (
        norm(s.city_name).includes(dNorm) ||
        norm(s.location_name).includes(dNorm) ||
        s.tags.some((t) => norm(t).includes(dNorm)) ||
        (dNorm.includes('udupi') && norm(s.scene_id).includes('udupi')) ||
        (dNorm.includes('goa') && norm(s.scene_id).includes('goa')) ||
        (dNorm.includes('chennai') && norm(s.scene_id).includes('chennai'))
      ) {
        add(s);
      }
    }
  }

  if (req.origin) {
    const oNorm = norm(req.origin);
    for (const s of Object.values(STATIC_XR_SCENES)) {
      if (
        s.entity_type === 'transfer' &&
        (norm(s.city_name).includes(oNorm) ||
          norm(s.location_name).includes(oNorm) ||
          s.tags.some((t) => norm(t).includes(oNorm)) ||
          (oNorm.includes('udayapalya') && norm(s.city_name).includes('bengaluru')))
      ) {
        add(s);
      }
    }
  }

  return {
    total_matches: matched.length,
    primary_scene: matched[0],
    scenes: matched,
  };
}

export async function fetchSceneWayfinding(
  sceneId: string,
  wayfindingId?: string
): Promise<ARWayfindingCase[]> {
  try {
    const query = wayfindingId ? `?wayfinding_id=${wayfindingId}` : '';
    const res = await apiClient<ARWayfindingCase[]>(`/api/v1/xr/wayfinding/${sceneId}${query}`);
    if (res) return res;
  } catch (err) {
    console.warn(`[XR API] Falling back to static wayfinding for ${sceneId}:`, err);
  }

  const scene = STATIC_XR_SCENES[sceneId];
  if (!scene) return [];
  if (wayfindingId) {
    return scene.wayfinding_cases.filter((w) => w.wayfinding_id === wayfindingId);
  }
  return scene.wayfinding_cases;
}

export async function fetchDeviceProfiles(): Promise<XRDeviceProfile[]> {
  try {
    const res = await apiClient<XRDeviceProfile[]>('/api/v1/xr/device-profiles');
    if (res) return res;
  } catch {}
  return STATIC_DEVICE_PROFILES;
}

// React Query hooks
export function useXRScene(sceneId: string) {
  return useQuery({
    queryKey: ['xr-scene', sceneId],
    queryFn: () => fetchXRScene(sceneId),
    enabled: Boolean(sceneId),
  });
}

export function useJourneyXRMatch(
  origin?: string,
  destination?: string,
  transferHubs?: string[],
  hotelId?: string
) {
  return useQuery({
    queryKey: ['xr-match', origin, destination, transferHubs?.join(','), hotelId],
    queryFn: () =>
      matchJourneyXR({
        origin,
        destination,
        transfer_hubs: transferHubs,
        hotel_id: hotelId,
      }),
    enabled: Boolean(origin || destination || transferHubs?.length || hotelId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useARWayfinding(sceneId: string, wayfindingId?: string) {
  return useQuery({
    queryKey: ['xr-wayfinding', sceneId, wayfindingId],
    queryFn: () => fetchSceneWayfinding(sceneId, wayfindingId),
    enabled: Boolean(sceneId),
  });
}

export function useDeviceProfiles() {
  return useQuery({
    queryKey: ['xr-device-profiles'],
    queryFn: fetchDeviceProfiles,
    staleTime: 60 * 60 * 1000,
  });
}
