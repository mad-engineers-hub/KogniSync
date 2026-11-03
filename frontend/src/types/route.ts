export interface RouteCoordinate {
  latitude: number;
  longitude: number;
}

export interface SegmentRouteGeometry {
  segment_id: string;
  mode: string;
  origin_title: string;
  origin_city: string;
  destination_title: string;
  destination_city: string;
  origin_coords: RouteCoordinate;
  destination_coords: RouteCoordinate;
  coordinates: RouteCoordinate[];
  distance_meters: number;
  duration_seconds: number;
  encoded_polyline?: string;
  source: string;
  warnings?: string[];
}

export interface EnrichedJourneyRoute {
  journey_id: string;
  total_distance_meters: number;
  total_duration_seconds: number;
  segments: SegmentRouteGeometry[];
  source: string;
  provider_status: string;
}

export interface MapsHealthResponse {
  enabled: boolean;
  active_provider: string;
  api_key_configured: boolean;
  service: string;
}
