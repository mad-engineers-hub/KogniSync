/**
 * Canonical XR Type Definitions for KogniSync.
 * Conforms strictly to organizer enums in BookingInventory/data/enums.json.
 */

export type XRSceneType = 'panorama_360' | 'model_3d' | 'photogrammetry' | 'video_360';
export type XRAssetFormat = 'jpg_equirect' | 'gltf' | 'glb' | 'usdz' | 'ktx2' | 'mp4';
export type XRPlatform = 'webxr' | 'arcore' | 'arkit' | 'desktop_fallback';
export type DeviceClass = 'phone_ar' | 'tablet_ar' | 'headset_vr' | 'desktop';
export type XREntityType = 'transfer' | 'hotel' | 'poi' | 'flight' | 'xr_scene';

export interface XRSceneHotspot {
  hotspot_id: string;
  scene_id: string;
  title: string;
  description?: string;
  category: 'transfer' | 'platform' | 'bus_bay' | 'cab_pickup' | 'hotel_amenity' | 'exit' | 'info';
  yaw: number; // 0..360 degrees
  pitch: number; // -90..+90 degrees
  action: 'navigate' | 'info' | 'wayfinding' | 'booking';
  target_id?: string;
}

export interface XRSceneAsset {
  asset_id: string;
  format: XRAssetFormat;
  uri: string;
  mime_type: string;
  file_size_bytes: number;
  description?: string;
}

export interface XRDeviceProfile {
  profile_id: string;
  device_class: DeviceClass;
  platform: XRPlatform;
  supported: boolean;
  notes?: string;
}

export interface ARWayfindingStep {
  step_number: number;
  instruction: string;
  distance_meters: number;
  turn_direction:
    | 'straight'
    | 'left'
    | 'right'
    | 'slight_left'
    | 'slight_right'
    | 'stairs_up'
    | 'stairs_down'
    | 'elevator'
    | 'arrival';
  target_landmark: string;
}

export interface ARWayfindingCase {
  wayfinding_id: string;
  scene_id: string;
  origin_title: string;
  destination_title: string;
  estimated_walking_minutes: number;
  steps: ARWayfindingStep[];
}

export interface XRScene {
  scene_id: string;
  title: string;
  subtitle: string;
  entity_type: XREntityType;
  entity_id?: string;
  city_id?: string;
  city_name: string;
  location_name: string;
  scene_type: XRSceneType;
  description: string;
  assets: XRSceneAsset[];
  hotspots: XRSceneHotspot[];
  wayfinding_cases: ARWayfindingCase[];
  supported_platforms: XRPlatform[];
  tags: string[];
}

export interface XRExperienceMatchRequest {
  origin?: string;
  destination?: string;
  transfer_hubs?: string[];
  hotel_id?: string;
}

export interface XRExperienceMatchResponse {
  total_matches: number;
  primary_scene?: XRScene;
  scenes: XRScene[];
}
