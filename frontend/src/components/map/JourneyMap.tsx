import React, { useState, useMemo, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useLocation } from 'react-router-dom';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Journey, JourneySegment } from '../../types/journey';
import { EnrichedJourneyRoute } from '../../types/route';
import { enrichJourneyRoute, buildClientFallbackRoute } from '../../api/routes';
import { ModeIcon } from '../common/ModeIcon';
import { getModeMeta, formatDuration } from '../../lib/utils';
import { matchXRSceneForHub } from '../../utils/xrMatching';
import {
  MapPin,
  Compass,
  Navigation,
  Sparkles,
  Layers,
  Info,
  Clock,
  Gauge,
  Eye,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Route as RouteIcon,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';

import { useJourneyGuidance } from '../../hooks/useJourneyGuidance';
import { NavigationGuidanceDrawer } from '../navigation/NavigationGuidanceDrawer';
import { DisruptionEvent, JourneyDisruptionAssessment } from '../../types/disruption';

export interface JourneyMapProps {
  segments: JourneySegment[];
  journey?: Journey;
  alternativeJourneys?: Journey[];
  selectedJourneyId?: string;
  onSelectJourney?: (journeyId: string) => void;
  selectedSegmentId?: string;
  onSegmentClick?: (segmentId: string) => void;
  className?: string;
  interactive?: boolean;
  initialViewMode?: 'geographic' | 'schematic';
  showGuidance?: boolean;
  initialGuidanceOpen?: boolean;
  disruptions?: DisruptionEvent[];
  disruptionAssessment?: JourneyDisruptionAssessment | null;
}

interface ProjectedWaypoint {
  lat: number;
  lng: number;
  title: string;
  city: string;
  type: string;
  isHub: boolean;
  hubType: 'origin' | 'departure_hub' | 'transfer_hub' | 'arrival_hub' | 'destination';
  xrSceneId?: string | null;
  transferBufferMinutes?: number;
  segmentIndex?: number;
}

// Mode color palette
const MODE_COLORS: Record<string, { stroke: string; glow: string; weight: number; dashArray?: string }> = {
  walk: { stroke: '#059669', glow: '#34d399', weight: 4, dashArray: '4, 8' },
  cab: { stroke: '#2563eb', glow: '#60a5fa', weight: 5 },
  auto: { stroke: '#2563eb', glow: '#60a5fa', weight: 5 },
  rapido: { stroke: '#7c3aed', glow: '#a78bfa', weight: 5 },
  bus: { stroke: '#d97706', glow: '#fbbf24', weight: 5 },
  train: { stroke: '#9333ea', glow: '#c084fc', weight: 6 },
  flight: { stroke: '#4f46e5', glow: '#818cf8', weight: 4, dashArray: '8, 8' },
  metro: { stroke: '#0d9488', glow: '#2dd4bf', weight: 5 },
};

function getModeStyle(mode: string) {
  return MODE_COLORS[mode] || { stroke: '#2563eb', glow: '#60a5fa', weight: 5 };
}

export const JourneyMap: React.FC<JourneyMapProps> = ({
  segments,
  journey,
  alternativeJourneys = [],
  selectedJourneyId,
  onSelectJourney,
  selectedSegmentId,
  onSegmentClick,
  className = '',
  interactive = true,
  initialViewMode = 'geographic',
  showGuidance = true,
  initialGuidanceOpen = false,
  disruptions = [],
  disruptionAssessment = null,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number>(0);
  const [viewMode, setViewMode] = useState<'geographic' | 'schematic'>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('view') === 'schematic') return 'schematic';
      if (params.get('view') === 'geographic') return 'geographic';
    }
    return initialViewMode;
  });
  const [guidanceOpen, setGuidanceOpen] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('guidance') === 'true') return true;
    }
    return initialGuidanceOpen;
  });

  // Re-sync with URL query parameter changes or parent prop
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('guidance') === 'true' || initialGuidanceOpen) {
      setGuidanceOpen(true);
    }
  }, [location.search, initialGuidanceOpen]);
  const [leafletError, setLeafletError] = useState<boolean>(false);
  const [tileError, setTileError] = useState<boolean>(false);

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const layersGroupRef = useRef<L.FeatureGroup | null>(null);

  // Synthesize or use real Journey object for backend route enrichment
  const targetJourney: Journey = useMemo(() => {
    if (journey) return journey;
    const totalDist = segments.reduce((sum, s) => sum + (s.distanceKm || 0), 0);
    const totalDur = segments.reduce((sum, s) => sum + (s.durationMinutes || 0), 0);
    const totalP = segments.reduce((sum, s) => sum + (s.price || 0), 0);
    const defaultTime = '2026-11-04T08:00:00Z';

    return {
      id: `jny-map-${segments[0]?.origin?.id || 'orig'}-${segments[segments.length - 1]?.destination?.id || 'dest'}`,
      title: `${segments[0]?.origin?.city || 'Origin'} to ${segments[segments.length - 1]?.destination?.city || 'Destination'} Route`,
      origin: segments[0]?.origin || {
        id: 'orig',
        name: 'Origin',
        city: 'Origin',
        type: 'address',
        coordinates: { lat: 12.97, lng: 77.59 },
      },
      destination: segments[segments.length - 1]?.destination || {
        id: 'dest',
        name: 'Destination',
        city: 'Destination',
        type: 'address',
        coordinates: { lat: 13.08, lng: 80.27 },
      },
      departureTime: segments[0]?.departureTime || defaultTime,
      arrivalTime: segments[segments.length - 1]?.arrivalTime || defaultTime,
      totalDurationMinutes: totalDur,
      totalPrice: totalP,
      currency: 'INR',
      totalTransfers: Math.max(0, segments.length - 1),
      modes: Array.from(new Set(segments.map((s) => s.mode))),
      segments,
      carbonKg: 20,
      comfortScore: 8,
      recommendationCategory: 'best_value',
      aiExplanation: {
        summary: 'Synchronized door-to-door transit route',
        tradeOffs: [],
        rankReason: 'Optimized routing corridor',
        score: 90,
      },
      bookingFeasibility: {
        holdSupported: true,
        concurrencySafe: true,
        holdTtlSeconds: 900,
      },
    };
  }, [journey, segments]);

  // Query enriched route geometry from backend Valhalla / Geo engine
  const { data: enrichedRoute } = useQuery<EnrichedJourneyRoute>({
    queryKey: ['route-enrichment', targetJourney.id, segments.map((s) => s.segmentId).join(':')],
    queryFn: () => enrichJourneyRoute(targetJourney),
    staleTime: 60000,
    retry: 1,
  });

  // Effective route geometry (server enriched with client fallback)
  const effectiveRoute = useMemo<EnrichedJourneyRoute>(() => {
    if (enrichedRoute) return enrichedRoute;
    return buildClientFallbackRoute(targetJourney);
  }, [enrichedRoute, targetJourney]);

  // Unified navigation guidance and device-local progress hook
  const guidance = useJourneyGuidance(targetJourney, effectiveRoute);

  // Effective active segment index derived from props, guidance, or local state
  const effectiveActiveSegmentIndex = useMemo(() => {
    if (selectedSegmentId) {
      const idx = segments.findIndex((s) => s.segmentId === selectedSegmentId);
      if (idx !== -1) return idx;
    }
    if (guidanceOpen) {
      return guidance.activeSegmentIndex;
    }
    return activeSegmentIndex;
  }, [selectedSegmentId, segments, activeSegmentIndex, guidanceOpen, guidance.activeSegmentIndex]);

  // Waypoints for both Leaflet markers and schematic representation
  const waypoints: ProjectedWaypoint[] = useMemo(() => {
    const pts: ProjectedWaypoint[] = [];
    if (!segments.length) return pts;

    // Origin
    pts.push({
      lat: segments[0].origin.coordinates.lat,
      lng: segments[0].origin.coordinates.lng,
      title: segments[0].origin.name,
      city: segments[0].origin.city,
      type: segments[0].origin.type,
      isHub: false,
      hubType: 'origin',
      segmentIndex: 0,
      xrSceneId: matchXRSceneForHub(segments[0].origin.name) || matchXRSceneForHub(segments[0].origin.city),
    });

    // Segment destinations
    segments.forEach((seg, idx) => {
      const isFinal = idx === segments.length - 1;
      const xrSceneId = matchXRSceneForHub(seg.destination.name) || matchXRSceneForHub(seg.destination.city);
      pts.push({
        lat: seg.destination.coordinates.lat,
        lng: seg.destination.coordinates.lng,
        title: seg.destination.name,
        city: seg.destination.city,
        type: seg.destination.type,
        isHub: !isFinal,
        hubType: isFinal ? 'destination' : idx === 0 ? 'departure_hub' : 'transfer_hub',
        xrSceneId,
        transferBufferMinutes: seg.transferBufferMinutes,
        segmentIndex: idx,
      });
    });

    return pts;
  }, [segments]);

  // -------------------------------------------------------------------------
  // LEAFLET MAP INITIALIZATION & LIFECYCLE
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (viewMode !== 'geographic' || !mapContainerRef.current) return;

    try {
      if (!mapInstanceRef.current) {
        // Initialize Leaflet map
        const map = L.map(mapContainerRef.current, {
          zoomControl: false,
          attributionControl: false,
          minZoom: 3,
          maxZoom: 19,
        });

        // Configurable Basemap Tile Layer (defaulting to CARTO Positron with OSM attribution)
        const tileUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_MAP_TILE_URL) ||
          'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
        const tileSubdomains = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_MAP_TILE_SUBDOMAINS) || 'abcd';

        const tileLayer = L.tileLayer(tileUrl, {
          subdomains: tileSubdomains,
          maxZoom: 19,
        }).addTo(map);

        tileLayer.on('tileerror', () => {
          setTileError(true);
        });

        const featureGroup = L.featureGroup().addTo(map);
        layersGroupRef.current = featureGroup;
        mapInstanceRef.current = map;
      }

      // Invalidate size to ensure proper tile loading
      setTimeout(() => {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
        }
      }, 150);
    } catch (err) {
      console.error('Leaflet initialization failed; falling back to SVG:', err);
      setLeafletError(true);
      setViewMode('schematic');
    }

    return () => {
      // Map instance is preserved across tabs unless unmounted
    };
  }, [viewMode]);

  // Clean cleanup on component unmount
  useEffect(() => {
    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
        layersGroupRef.current = null;
      }
    };
  }, []);

  // -------------------------------------------------------------------------
  // LEAFLET LAYERS UPDATE (POLYLINES & MARKERS)
  // -------------------------------------------------------------------------
  useEffect(() => {
    const map = mapInstanceRef.current;
    const featureGroup = layersGroupRef.current;
    if (!map || !featureGroup || viewMode !== 'geographic') return;

    featureGroup.clearLayers();

    const allLatLangs: L.LatLngExpression[] = [];

    // 1. Draw Alternative Journeys (Muted lines)
    if (alternativeJourneys && alternativeJourneys.length > 0) {
      alternativeJourneys.forEach((alt) => {
        if (alt.id === targetJourney.id) return;
        const altPoints: [number, number][] = [];
        alt.segments.forEach((s) => {
          altPoints.push([s.origin.coordinates.lat, s.origin.coordinates.lng]);
          altPoints.push([s.destination.coordinates.lat, s.destination.coordinates.lng]);
        });

        if (altPoints.length >= 2) {
          const altLine = L.polyline(altPoints, {
            color: '#94a3b8',
            weight: 3,
            dashArray: '6, 6',
            opacity: 0.55,
          }).addTo(featureGroup);

          altLine.bindTooltip(
            `<strong>${alt.title}</strong><br/>₹${alt.totalPrice} · ${formatDuration(alt.totalDurationMinutes)}<br/><span style="font-size:10px;color:#2563eb;">Click to switch route</span>`,
            { sticky: true }
          );

          altLine.on('click', () => {
            if (onSelectJourney) onSelectJourney(alt.id);
          });
        }
      });
    }

    // 2. Draw Active Journey Segments (Real Valhalla / Geo Geometry)
    const disruptedSegmentMap = new Map(
      (disruptionAssessment?.segmentImpacts || [])
        .filter((imp) => imp.impactLevel !== 'none')
        .map((imp) => [imp.segmentId, imp])
    );

    segments.forEach((seg, idx) => {
      const enrichedSeg = effectiveRoute.segments?.[idx];
      const style = getModeStyle(seg.mode);
      const isActive = effectiveActiveSegmentIndex === idx;

      let latlngs: [number, number][] = [];

      // Prefer GeoJSON geometry LineString coordinates [lng, lat]
      if (enrichedSeg?.geojson_geometry?.coordinates?.length) {
        latlngs = enrichedSeg.geojson_geometry.coordinates.map((c) => [c[1], c[0]]);
      } else if (seg.geojsonGeometry?.coordinates?.length) {
        latlngs = seg.geojsonGeometry.coordinates.map((c) => [c[1], c[0]]);
      } else if (enrichedSeg?.coordinates?.length) {
        latlngs = enrichedSeg.coordinates.map((c) => [c.latitude, c.longitude]);
      } else {
        latlngs = [
          [seg.origin.coordinates.lat, seg.origin.coordinates.lng],
          [seg.destination.coordinates.lat, seg.destination.coordinates.lng],
        ];
      }

      latlngs.forEach((pt) => allLatLangs.push(pt));

      // Active casing / halo glow
      if (isActive) {
        L.polyline(latlngs, {
          color: style.glow,
          weight: style.weight + 8,
          opacity: 0.45,
          lineCap: 'round',
          lineJoin: 'round',
        }).addTo(featureGroup);
      }

      // Disrupted segment hazard casing
      if (disruptedSegmentMap.has(seg.segmentId)) {
        const imp = disruptedSegmentMap.get(seg.segmentId)!;
        L.polyline(latlngs, {
          color: imp.impactLevel === 'critical' ? '#e11d48' : '#d97706',
          weight: style.weight + 4,
          dashArray: '8, 8',
          opacity: 0.95,
          lineCap: 'round',
        }).addTo(featureGroup);
      }

      // Main route polyline
      const isCompleted = guidance.isSegmentCompleted(seg.segmentId);
      const line = L.polyline(latlngs, {
        color: isCompleted ? '#10b981' : style.stroke,
        weight: isActive ? style.weight + 2 : style.weight,
        dashArray: isCompleted ? '6, 6' : style.dashArray,
        opacity: isActive ? 1.0 : isCompleted ? 0.65 : 0.85,
        lineCap: 'round',
        lineJoin: 'round',
      }).addTo(featureGroup);

      const isLive = enrichedSeg?.is_live_geometry ?? seg.isLiveGeometry ?? false;
      const dist = Math.round((enrichedSeg?.distance_meters ?? (seg.distanceKm * 1000)) / 1000);
      const dur = Math.round((enrichedSeg?.duration_seconds ?? (seg.durationMinutes * 60)) / 60);

      const popupContent = `
        <div style="font-family: sans-serif; min-width: 180px; padding: 2px;">
          <div style="font-weight: 700; font-size: 13px; color: #0f172a; margin-bottom: 2px;">
            ${seg.provider} <span style="font-size: 11px; text-transform: uppercase; color: #64748b;">(${seg.mode})</span>
          </div>
          <div style="font-size: 11px; color: #475569; margin-bottom: 4px;">
            ${seg.origin.city} → ${seg.destination.city}
          </div>
          <div style="font-size: 11px; font-family: monospace; color: #0f172a; display: flex; gap: 8px; margin-bottom: 6px;">
            <span><strong>${dist}</strong> km</span>
            <span>·</span>
            <span><strong>${dur}</strong> min</span>
          </div>
          <div style="display: inline-block; font-size: 10px; font-family: monospace; padding: 2px 6px; border-radius: 4px; ${
            isLive
              ? 'background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0;'
              : 'background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe;'
          }">
            ${isLive ? '✓ Verified Valhalla OSM Route' : 'Corridor Transit Estimate'}
          </div>
        </div>
      `;

      line.bindPopup(popupContent);
      line.on('click', () => {
        setActiveSegmentIndex(idx);
        if (onSegmentClick) onSegmentClick(seg.segmentId);
      });
    });

    // 3. Draw Grounded Markers (Origin, Destination, Transfer Hubs)
    waypoints.forEach((wp) => {
      const isOrigin = wp.hubType === 'origin';
      const isDest = wp.hubType === 'destination';
      const hasXR = !!wp.xrSceneId;

      let iconHtml = '';
      if (isOrigin) {
        iconHtml = `
          <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px;">
            <div style="position: absolute; width: 28px; height: 28px; border-radius: 9999px; background: #10b981; opacity: 0.35; animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
            <div style="position: relative; width: 20px; height: 20px; border-radius: 9999px; background: #059669; border: 2.5px solid #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center;">
              <div style="width: 6px; height: 6px; border-radius: 9999px; background: #ffffff;"></div>
            </div>
          </div>
        `;
      } else if (isDest) {
        iconHtml = `
          <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px;">
            <div style="position: relative; width: 22px; height: 22px; border-radius: 9999px; background: #e11d48; border: 2.5px solid #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center;">
              <div style="width: 7px; height: 7px; border-radius: 9999px; background: #ffffff;"></div>
            </div>
          </div>
        `;
      } else {
        // Transfer Hub
        iconHtml = `
          <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 26px; height: 26px;">
            ${
              hasXR
                ? '<div style="position: absolute; width: 28px; height: 28px; border-radius: 9999px; background: #38bdf8; opacity: 0.45; animation: ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>'
                : ''
            }
            <div style="position: relative; width: 18px; height: 18px; border-radius: 9999px; background: #d97706; border: 2px solid #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.25); display: flex; align-items: center; justify-content: center;">
              <div style="width: 5px; height: 5px; border-radius: 9999px; background: #ffffff;"></div>
            </div>
          </div>
        `;
      }

      const customIcon = L.divIcon({
        className: 'custom-leaflet-marker',
        html: iconHtml,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
      });

      const marker = L.marker([wp.lat, wp.lng], { icon: customIcon }).addTo(featureGroup);

      const xrButtonHtml = hasXR
        ? `<button id="xr-btn-${wp.xrSceneId}" style="margin-top: 8px; width: 100%; display: flex; align-items: center; justify-content: center; gap: 4px; padding: 6px 10px; background: #2563eb; color: #ffffff; font-weight: 700; font-size: 11px; border: none; border-radius: 8px; cursor: pointer;">
             <span>Explore 360° Concourse</span>
           </button>`
        : '';

      const markerPopup = `
        <div style="font-family: sans-serif; min-width: 170px; padding: 2px;">
          <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: ${
            isOrigin ? '#059669' : isDest ? '#e11d48' : '#d97706'
          }; margin-bottom: 2px;">
            ${isOrigin ? 'Journey Origin' : isDest ? 'Final Destination' : 'Transfer Hub'}
          </div>
          <div style="font-weight: 700; font-size: 13px; color: #0f172a;">${wp.title}</div>
          <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">${wp.city} · ${wp.type}</div>
          <div style="font-size: 10px; font-family: monospace; color: #64748b;">
            ${wp.lat.toFixed(4)}°N, ${wp.lng.toFixed(4)}°E
          </div>
          ${
            wp.transferBufferMinutes
              ? `<div style="margin-top: 4px; font-size: 11px; font-weight: 600; color: #d97706;">Transfer Buffer: +${wp.transferBufferMinutes} min</div>`
              : ''
          }
          ${xrButtonHtml}
        </div>
      `;

      marker.bindPopup(markerPopup);

      // Attach XR click listener on popup open
      if (hasXR) {
        marker.on('popupopen', () => {
          const btn = document.getElementById(`xr-btn-${wp.xrSceneId}`);
          if (btn) {
            btn.onclick = () => {
              navigate(`/xr/${wp.xrSceneId}`);
            };
          }
        });
      }

      marker.on('click', () => {
        if (wp.segmentIndex !== undefined) {
          setActiveSegmentIndex(wp.segmentIndex);
        }
      });
    });

    // 3B. Draw Active Disruption Incident Markers
    const activeEvents: DisruptionEvent[] = [
      ...(disruptions || []),
      ...(disruptionAssessment?.activeDisruptions || []),
    ];
    const uniqueEvents = Array.from(new Map(activeEvents.map((e) => [e.id, e])).values());

    uniqueEvents.forEach((ev) => {
      const pt = ev.point || ev.affectedLocations?.[0]?.coordinates;
      if (!pt) return;

      const isCrit = ev.severity === 'critical';
      const isSim = ev.provenance === 'simulated';
      const markerColor = isCrit ? '#e11d48' : '#d97706';
      const pingColor = isCrit ? '#f43f5e' : '#f59e0b';

      const incidentIconHtml = `
        <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 34px; height: 34px;" title="${ev.title}">
          <div style="position: absolute; width: 34px; height: 34px; border-radius: 9999px; background: ${pingColor}; opacity: 0.45; animation: ping 1.2s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
          <div style="position: relative; width: 24px; height: 24px; border-radius: 9999px; background: ${markerColor}; border: 2.5px solid #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; color: #ffffff; font-size: 12px; font-weight: bold;">
            ⚠️
          </div>
        </div>
      `;

      const incidentIcon = L.divIcon({
        className: 'disruption-marker-icon',
        html: incidentIconHtml,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      });

      const popupHtml = `
        <div style="font-family: sans-serif; min-width: 200px; max-width: 260px; padding: 2px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; gap: 4px;">
            <span style="font-size: 10px; font-family: monospace; font-weight: bold; text-transform: uppercase; padding: 1px 5px; border-radius: 4px; background: ${
              isCrit ? '#ffe4e6' : '#fef3c7'
            }; color: ${isCrit ? '#9f1239' : '#92400e'};">
              ${ev.severity} disruption
            </span>
            <span style="font-size: 9px; font-family: monospace; font-weight: bold; background: #0f172a; color: ${
              isSim ? '#fcd34d' : '#93c5fd'
            }; padding: 1px 5px; border-radius: 4px;">
              ${isSim ? 'SIMULATED' : 'LIVE'}
            </span>
          </div>
          <div style="font-weight: 700; font-size: 12px; color: #0f172a; margin-bottom: 3px;">
            ${ev.title}
          </div>
          <div style="font-size: 11px; color: #475569; line-height: 1.4; margin-bottom: 6px;">
            ${ev.description}
          </div>
          ${
            ev.estimatedDelayMinutes
              ? `<div style="font-size: 11px; font-family: monospace; color: #b91c1c; font-weight: bold;">Estimated Delay: +${ev.estimatedDelayMinutes} min</div>`
              : ''
          }
        </div>
      `;

      const marker = L.marker([pt.lat, pt.lng], { icon: incidentIcon }).addTo(featureGroup);
      marker.bindPopup(popupHtml);
      allLatLangs.push([pt.lat, pt.lng]);
    });

    // 4. Draw Foreground User Location (GPS / Demo Position) if active
    if (guidance.locationState.coords) {
      const { latitude, longitude } = guidance.locationState.coords;
      const isLive = guidance.locationState.status === 'live_position';
      const userMarkerHtml = `
        <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 24px; height: 24px;">
          <div style="position: absolute; width: 24px; height: 24px; border-radius: 9999px; background: ${isLive ? '#2563eb' : '#6366f1'}; opacity: 0.45; animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
          <div style="position: relative; width: 16px; height: 16px; border-radius: 9999px; background: ${isLive ? '#2563eb' : '#6366f1'}; border: 2.5px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.35);"></div>
        </div>
      `;
      const userIcon = L.divIcon({
        className: 'user-gps-location-marker',
        html: userMarkerHtml,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });
      L.marker([latitude, longitude], { icon: userIcon, zIndexOffset: 3000 })
        .bindTooltip(isLive ? 'Current GPS Location' : 'Demo Guidance Location', { direction: 'top', offset: [0, -8] })
        .addTo(featureGroup);

      if (guidance.locationState.accuracyMeters && isLive) {
        L.circle([latitude, longitude], {
          radius: guidance.locationState.accuracyMeters,
          color: '#2563eb',
          fillColor: '#60a5fa',
          fillOpacity: 0.15,
          weight: 1,
        }).addTo(featureGroup);
      }
    }

    // 5. Fit Bounds with comfortable padding
    if (allLatLangs.length > 0) {
      const boundsObj = L.latLngBounds(allLatLangs as L.LatLngTuple[]);
      map.fitBounds(boundsObj, {
        padding: [45, 45],
        maxZoom: 14,
        animate: true,
      });
    }
  }, [
    effectiveRoute,
    segments,
    alternativeJourneys,
    effectiveActiveSegmentIndex,
    viewMode,
    waypoints,
    targetJourney.id,
    onSelectJourney,
    onSegmentClick,
    navigate,
    guidance.locationState.coords,
    guidance.locationState.status,
    guidance.progress.completedSegmentIds,
    disruptions,
    disruptionAssessment,
  ]);

  // Map control callbacks
  const handleZoomIn = () => {
    mapInstanceRef.current?.zoomIn();
  };

  const handleZoomOut = () => {
    mapInstanceRef.current?.zoomOut();
  };

  const handleFitRoute = () => {
    if (layersGroupRef.current && mapInstanceRef.current) {
      const b = layersGroupRef.current.getBounds();
      if (b.isValid()) {
        mapInstanceRef.current.fitBounds(b, { padding: [45, 45], maxZoom: 14, animate: true });
      }
    }
  };

  const handleRecenterOrigin = () => {
    if (mapInstanceRef.current && segments[0]) {
      const { lat, lng } = segments[0].origin.coordinates;
      mapInstanceRef.current.setView([lat, lng], 13, { animate: true });
    }
  };

  const handleRecenterDestination = () => {
    if (mapInstanceRef.current && segments[segments.length - 1]) {
      const { lat, lng } = segments[segments.length - 1].destination.coordinates;
      mapInstanceRef.current.setView([lat, lng], 13, { animate: true });
    }
  };

  // Active segment inspection
  const activeSegment = segments[effectiveActiveSegmentIndex] || segments[0];
  const activeEnrichedSeg = effectiveRoute?.segments?.[effectiveActiveSegmentIndex];

  // Total summary telemetry
  const totalKm = effectiveRoute
    ? Math.round(effectiveRoute.total_distance_meters / 1000)
    : segments.reduce((sum, s) => sum + (s.distanceKm || 0), 0);

  const totalMin = effectiveRoute
    ? Math.round(effectiveRoute.total_duration_seconds / 60)
    : segments.reduce((sum, s) => sum + (s.durationMinutes || 0), 0);

  const providerSource = effectiveRoute?.source || 'deterministic_geo';
  const hasLiveGeometry = effectiveRoute?.has_live_geometry || effectiveRoute.segments?.some((s) => s.is_live_geometry);
  const isValhallaSource = providerSource.includes('valhalla');
  const isGoogleSource = providerSource.includes('google');

  const providerBadgeLabel = hasLiveGeometry
    ? isValhallaSource
      ? 'Valhalla OSM Live'
      : isGoogleSource
      ? 'Google Routes Live'
      : 'Live Route Geometry'
    : 'Deterministic Corridor';

  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white overflow-hidden flex flex-col shadow-sm relative ${className}`}
    >
      {/* Top Map Toolbar */}
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50/95 flex flex-wrap items-center justify-between gap-3 z-10">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-blue-600 text-white shadow-xs">
            <Compass className="w-4 h-4 animate-spin-slow" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-900 font-display">
              Multimodal Journey Navigation Map
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              {segments[0]?.origin?.city} → {segments[segments.length - 1]?.destination?.city} · Door-to-Door Corridor
            </span>
          </div>
        </div>

        {/* View Mode Switch & Live Geometry Provenance Badge */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-white p-0.5 rounded-lg border border-slate-200 text-[11px] font-mono shadow-2xs">
            <button
              onClick={() => setViewMode('geographic')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-colors ${
                viewMode === 'geographic'
                  ? 'bg-blue-50 text-blue-800 font-bold border border-blue-200'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Navigation className="w-3 h-3 text-blue-600" />
              <span>Spatial Map</span>
            </button>
            <button
              onClick={() => setViewMode('schematic')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-colors ${
                viewMode === 'schematic'
                  ? 'bg-blue-50 text-blue-800 font-bold border border-blue-200'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Layers className="w-3 h-3 text-slate-600" />
              <span>Waypoints</span>
            </button>
          </div>

          {interactive && showGuidance && (
            <button
              type="button"
              onClick={() => setGuidanceOpen(!guidanceOpen)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-bold transition-all cursor-pointer ${
                guidanceOpen
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-white hover:bg-slate-50 border border-slate-200 text-slate-700'
              }`}
            >
              <Compass className={`w-3.5 h-3.5 ${guidanceOpen ? 'animate-spin-slow' : 'text-blue-600'}`} />
              <span>{guidanceOpen ? 'Guidance Active' : 'Guide Me'}</span>
            </button>
          )}

          <span
            className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-md border font-semibold ${
              hasLiveGeometry
                ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                : 'bg-blue-50 text-blue-800 border-blue-200'
            }`}
          >
            {hasLiveGeometry ? (
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            ) : (
              <Sparkles className="w-3 h-3 text-blue-600" />
            )}
            {providerBadgeLabel}
          </span>
        </div>
      </div>

      {/* Alternative Journey Routes Bar (if available) */}
      {alternativeJourneys.length > 0 && (
        <div className="px-4 py-2 bg-slate-100/80 border-b border-slate-200 flex items-center gap-2 overflow-x-auto text-[11px] font-mono">
          <span className="text-slate-500 font-semibold uppercase tracking-wider text-[10px] shrink-0">
            Pareto Routes:
          </span>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => onSelectJourney?.(targetJourney.id)}
              className="px-2.5 py-1 rounded-md bg-white border border-blue-600 text-blue-700 font-bold shadow-2xs flex items-center gap-1"
            >
              <div className="w-2 h-2 rounded-full bg-blue-600" />
              <span>{targetJourney.title || 'Selected Route'} (₹{targetJourney.totalPrice})</span>
            </button>
            {alternativeJourneys.map((alt) => (
              <button
                key={alt.id}
                onClick={() => onSelectJourney?.(alt.id)}
                className="px-2.5 py-1 rounded-md bg-white/70 hover:bg-white border border-slate-200 text-slate-600 hover:text-slate-900 transition-colors flex items-center gap-1"
              >
                <div className="w-2 h-2 rounded-full bg-slate-400" />
                <span>{alt.title} (₹{alt.totalPrice})</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Map Canvas / Visualization Viewport */}
      <div className="relative h-80 sm:h-96 w-full bg-slate-900 flex flex-col items-center justify-center overflow-hidden">
        {viewMode === 'geographic' && !leafletError ? (
          /* =========================================================================
             MODE A: Leaflet Interactive OpenStreetMap / Valhalla Map
             ========================================================================= */
          <div className="relative w-full h-full">
            <div
              ref={mapContainerRef}
              className="w-full h-full z-0 bg-slate-100"
              style={{ minHeight: '100%' }}
            />

            {/* Floating Navigation Controls */}
            {interactive && (
              <div className="absolute top-3 right-3 flex flex-col gap-1.5 z-[1000] bg-white/95 rounded-xl border border-slate-200 p-1 shadow-md backdrop-blur-xs">
                <button
                  type="button"
                  onClick={handleZoomIn}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-700 hover:text-slate-900 transition-colors cursor-pointer"
                  title="Zoom In"
                >
                  <ZoomIn className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleZoomOut}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-700 hover:text-slate-900 transition-colors cursor-pointer"
                  title="Zoom Out"
                >
                  <ZoomOut className="w-4 h-4" />
                </button>
                <div className="h-px bg-slate-200 my-0.5" />
                <button
                  type="button"
                  onClick={handleFitRoute}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-700 hover:text-slate-900 transition-colors cursor-pointer"
                  title="Fit Whole Route"
                >
                  <Maximize2 className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={handleRecenterOrigin}
                  className="p-1.5 rounded-lg hover:bg-emerald-50 text-emerald-700 transition-colors cursor-pointer"
                  title="Focus Origin"
                >
                  <MapPin className="w-4 h-4 text-emerald-600" />
                </button>
                <button
                  type="button"
                  onClick={handleRecenterDestination}
                  className="p-1.5 rounded-lg hover:bg-rose-50 text-rose-700 transition-colors cursor-pointer"
                  title="Focus Destination"
                >
                  <Navigation className="w-4 h-4 text-rose-600" />
                </button>
              </div>
            )}

            {/* Tile Error Resilience Banner */}
            {tileError && (
              <div className="absolute top-3 left-3 z-[1000] flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-amber-50/95 border border-amber-200 text-[10px] text-amber-800 shadow-sm backdrop-blur-xs font-mono">
                <AlertCircle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span>Basemap tiles temporarily unavailable.</span>
                <button
                  type="button"
                  onClick={() => setViewMode('schematic')}
                  className="font-bold underline ml-1 text-amber-900 hover:text-amber-950 cursor-pointer"
                >
                  Switch to Waypoints View
                </button>
              </div>
            )}

            {/* Route Legend Indicator */}
            <div className="absolute bottom-2 left-2 z-[1000] bg-white/95 px-3 py-1.5 rounded-lg border border-slate-200 shadow-xs backdrop-blur-xs flex items-center gap-3 text-[10px] font-mono text-slate-600">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-600" />
                <span>Origin</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                <span>Transfer</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-rose-600" />
                <span>Destination</span>
              </div>
            </div>

            {/* Basemap Tile Attribution */}
            <div className="absolute bottom-1 right-2 z-[1000] px-2 py-0.5 rounded bg-white/90 backdrop-blur-xs text-[9px] text-slate-500 border border-slate-200 shadow-2xs pointer-events-auto select-none">
              &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer" className="hover:underline text-slate-700 font-medium">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener noreferrer" className="hover:underline text-slate-700 font-medium">CARTO</a>
            </div>
          </div>
        ) : (
          /* =========================================================================
             MODE B: Corridor Topology Schematic Diagram (Accessible SVG Fallback)
             ========================================================================= */
          <div className="w-full max-w-2xl flex flex-col justify-center h-full relative z-10 px-6">
            <div className="relative flex items-center justify-between w-full">
              {/* Connecting multi-mode colored segment line */}
              <div className="absolute top-1/2 left-0 right-0 -translate-y-1/2 h-2.5 rounded-full overflow-hidden flex shadow-lg bg-slate-800">
                {segments.map((seg, idx) => {
                  const meta = getModeMeta(seg.mode);
                  return (
                    <div
                      key={seg.segmentId}
                      style={{
                        flex: seg.durationMinutes || 30,
                        backgroundColor: meta.accentColor,
                      }}
                      className={`h-full transition-opacity cursor-pointer ${
                        effectiveActiveSegmentIndex === idx
                          ? 'opacity-100 ring-2 ring-white'
                          : 'opacity-75 hover:opacity-100'
                      }`}
                      onClick={() => {
                        setActiveSegmentIndex(idx);
                        if (onSegmentClick) onSegmentClick(seg.segmentId);
                      }}
                      title={`${seg.provider} (${seg.mode}): ${seg.distanceKm} km`}
                    />
                  );
                })}
              </div>

              {/* Waypoint Nodes along the route */}
              {waypoints.map((wp, idx) => {
                const isFirst = wp.hubType === 'origin';
                const isLast = wp.hubType === 'destination';

                return (
                  <div
                    key={`${wp.title}-${idx}`}
                    className="flex flex-col items-center z-20 group relative cursor-pointer"
                    onClick={() => {
                      if (wp.segmentIndex !== undefined) setActiveSegmentIndex(wp.segmentIndex);
                    }}
                  >
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center transition-transform group-hover:scale-125 shadow-md ${
                        isFirst
                          ? 'bg-green-600 ring-4 ring-green-900/60 text-white'
                          : isLast
                          ? 'bg-rose-600 ring-4 ring-rose-900/60 text-white'
                          : 'bg-slate-900 ring-2 ring-slate-600 text-slate-200'
                      }`}
                    >
                      <MapPin className="w-3.5 h-3.5" />
                    </div>

                    <div className="absolute top-9 flex flex-col items-center text-center w-28 -translate-x-1/2 left-1/2 pointer-events-none">
                      <span className="text-[11px] font-bold text-white tracking-tight truncate w-full">
                        {wp.city}
                      </span>
                      <span className="text-[9px] text-slate-400 font-mono truncate w-full">
                        {wp.title}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Segment Selector & Detailed Telemetry Bar */}
      <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col gap-3">
        {/* Mode Selector Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 max-w-full">
          {segments.map((seg, idx) => {
            const isSelected = effectiveActiveSegmentIndex === idx;
            const dist = seg.distanceKm || (activeEnrichedSeg ? Math.round(activeEnrichedSeg.distance_meters / 1000) : 0);

            return (
              <button
                key={seg.segmentId}
                onClick={() => {
                  setActiveSegmentIndex(idx);
                  if (onSegmentClick) onSegmentClick(seg.segmentId);
                }}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-semibold whitespace-nowrap transition-all shadow-2xs ${
                  isSelected
                    ? 'bg-white border-blue-600 ring-2 ring-blue-100 text-slate-900 shadow-xs'
                    : 'bg-white/80 hover:bg-white border-slate-200 text-slate-600'
                }`}
              >
                <ModeIcon mode={seg.mode} size={15} />
                <div className="flex flex-col text-left">
                  <span className="font-bold leading-tight">{seg.provider}</span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {dist} km · {formatDuration(seg.durationMinutes)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Selected Segment Inspection Card */}
        {activeSegment && (
          <div className="p-3.5 rounded-xl border border-slate-200 bg-white shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center text-white shrink-0 shadow-xs"
                style={{ backgroundColor: getModeStyle(activeSegment.mode).stroke }}
              >
                <ModeIcon mode={activeSegment.mode} size={20} />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-950 font-display">
                    {activeSegment.origin.city} → {activeSegment.destination.city}
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 uppercase font-semibold">
                    {activeSegment.mode}
                  </span>
                  {activeEnrichedSeg?.is_live_geometry && (
                    <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold">
                      LIVE ROAD
                    </span>
                  )}
                </div>
                <span className="text-xs text-slate-500 mt-0.5">
                  {activeSegment.origin.name} to {activeSegment.destination.name} via{' '}
                  <strong className="text-slate-800">{activeSegment.provider}</strong>
                </span>
              </div>
            </div>

            {/* Metrics & XR Station Button */}
            <div className="flex items-center gap-4 self-end sm:self-auto shrink-0">
              <div className="flex items-center gap-3 text-xs font-mono text-slate-600">
                <div className="flex items-center gap-1">
                  <Gauge className="w-3.5 h-3.5 text-slate-400" />
                  <span>
                    {activeEnrichedSeg
                      ? `${Math.round(activeEnrichedSeg.distance_meters / 1000)} km`
                      : `${activeSegment.distanceKm} km`}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  <span>
                    {activeEnrichedSeg
                      ? formatDuration(Math.round(activeEnrichedSeg.duration_seconds / 60))
                      : formatDuration(activeSegment.durationMinutes)}
                  </span>
                </div>
              </div>

              {/* XR Station Link if available */}
              {(() => {
                const xrId =
                  matchXRSceneForHub(activeSegment.destination.name) ||
                  matchXRSceneForHub(activeSegment.destination.city) ||
                  matchXRSceneForHub(activeSegment.origin.name);
                if (!xrId) return null;
                return (
                  <button
                    onClick={() => navigate(`/xr/${xrId}`)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-bold border border-blue-200 transition-colors shadow-2xs"
                  >
                    <Eye className="w-3.5 h-3.5 text-blue-600" />
                    <span>360° Concourse</span>
                  </button>
                );
              })()}
            </div>
          </div>
        )}

        {/* Global Journey Telemetry Footer */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] text-slate-500 font-mono">
          <div className="flex items-center gap-3">
            <span>
              Total Corridor: <strong className="text-slate-800">{totalKm} km</strong>
            </span>
            <span>·</span>
            <span>
              Door-to-Door Duration:{' '}
              <strong className="text-slate-800">{formatDuration(totalMin)}</strong>
            </span>
            <span>·</span>
            <span>
              Legs: <strong className="text-slate-800">{segments.length}</strong>
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-slate-400">
            <Info className="w-3.5 h-3.5" />
            <span>
              {hasLiveGeometry
                ? 'Road geometry powered by Valhalla OpenStreetMap routing'
                : 'Corridor estimated using spatial transit topologies'}
            </span>
          </div>
        </div>
      </div>

      {/* Navigation Guidance & Journey Progress Drawer */}
      {interactive && showGuidance && guidanceOpen && (
        <NavigationGuidanceDrawer
          guidance={guidance}
          segments={segments}
          onClose={() => setGuidanceOpen(false)}
        />
      )}
    </div>
  );
};
