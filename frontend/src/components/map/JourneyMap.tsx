import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Journey, JourneySegment } from '../../types/journey';
import { EnrichedJourneyRoute } from '../../types/route';
import { enrichJourneyRoute } from '../../api/routes';
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
  ExternalLink,
  Clock,
  Gauge,
  Eye,
} from 'lucide-react';

export interface JourneyMapProps {
  segments: JourneySegment[];
  journey?: Journey;
  selectedSegmentId?: string;
  onSegmentClick?: (segmentId: string) => void;
  className?: string;
  interactive?: boolean;
}

interface ProjectedPoint {
  x: number;
  y: number;
  lat: number;
  lng: number;
  title: string;
  city: string;
  type: string;
  isHub: boolean;
  hubType?: 'origin' | 'departure_hub' | 'transfer_hub' | 'arrival_hub' | 'destination';
  xrSceneId?: string | null;
  transferBufferMinutes?: number;
  segmentIndex?: number;
}

export const JourneyMap: React.FC<JourneyMapProps> = ({
  segments,
  journey,
  selectedSegmentId,
  onSegmentClick,
  className = '',
  interactive = true,
}) => {
  const navigate = useNavigate();
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number>(0);
  const [viewMode, setViewMode] = useState<'geographic' | 'schematic'>('geographic');
  const [hoveredNode, setHoveredNode] = useState<ProjectedPoint | null>(null);

  // Synthesize or use real Journey object for backend route enrichment
  const targetJourney: Journey = useMemo(() => {
    if (journey) return journey;
    const totalDist = segments.reduce((sum, s) => sum + (s.distanceKm || 0), 0);
    const totalDur = segments.reduce((sum, s) => sum + (s.durationMinutes || 0), 0);
    const totalP = segments.reduce((sum, s) => sum + (s.price || 0), 0);

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
      departureTime: segments[0]?.departureTime || new Date().toISOString(),
      arrivalTime: segments[segments.length - 1]?.arrivalTime || new Date().toISOString(),
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

  // Query enriched route geometry from backend Google Routes / Geo engine
  const { data: enrichedRoute } = useQuery<EnrichedJourneyRoute>({
    queryKey: ['route-enrichment', targetJourney.id, segments.map((s) => s.segmentId).join(':')],
    queryFn: () => enrichJourneyRoute(targetJourney),
    staleTime: 60000,
  });

  // Keep activeSegmentIndex in sync if external selectedSegmentId changes
  React.useEffect(() => {
    if (selectedSegmentId) {
      const idx = segments.findIndex((s) => s.segmentId === selectedSegmentId);
      if (idx !== -1) setActiveSegmentIndex(idx);
    }
  }, [selectedSegmentId, segments]);

  // SVG Projection parameters (SVG viewport: 800 x 420)
  const svgWidth = 800;
  const svgHeight = 420;
  const padding = 65;

  // Extract all coordinates to compute bounding box
  const allCoordinates = useMemo(() => {
    const coords: { lat: number; lng: number }[] = [];
    if (enrichedRoute?.segments?.length) {
      for (const seg of enrichedRoute.segments) {
        for (const c of seg.coordinates) {
          coords.push({ lat: c.latitude, lng: c.longitude });
        }
      }
    } else {
      for (const seg of segments) {
        coords.push(seg.origin.coordinates);
        coords.push(seg.destination.coordinates);
      }
    }
    return coords;
  }, [enrichedRoute, segments]);

  // Compute latitude/longitude bounds with margin
  const bounds = useMemo(() => {
    if (!allCoordinates.length) {
      return { minLat: 12.0, maxLat: 14.0, minLng: 74.0, maxLng: 81.0 };
    }
    let minLat = 90,
      maxLat = -90,
      minLng = 180,
      maxLng = -180;
    for (const c of allCoordinates) {
      if (c.lat < minLat) minLat = c.lat;
      if (c.lat > maxLat) maxLat = c.lat;
      if (c.lng < minLng) minLng = c.lng;
      if (c.lng > maxLng) maxLng = c.lng;
    }

    // Apply minimum delta to prevent zero-division
    const dLat = Math.max(0.15, maxLat - minLat);
    const dLng = Math.max(0.15, maxLng - minLng);

    return {
      minLat: minLat - dLat * 0.15,
      maxLat: maxLat + dLat * 0.15,
      minLng: minLng - dLng * 0.15,
      maxLng: maxLng + dLng * 0.15,
    };
  }, [allCoordinates]);

  // Project (lat, lng) -> SVG (x, y)
  const project = (lat: number, lng: number): { x: number; y: number } => {
    const latSpan = bounds.maxLat - bounds.minLat;
    const lngSpan = bounds.maxLng - bounds.minLng;

    const xRatio = (lng - bounds.minLng) / (lngSpan || 1);
    const yRatio = (lat - bounds.minLat) / (latSpan || 1);

    const x = padding + xRatio * (svgWidth - 2 * padding);
    // Invert Y because SVG (0,0) is top-left while latitude increases upwards (North)
    const y = svgHeight - (padding + yRatio * (svgHeight - 2 * padding));
    return { x: Math.round(x), y: Math.round(y) };
  };

  // Build projected waypoint nodes for hubs and endpoints
  const projectedWaypoints: ProjectedPoint[] = useMemo(() => {
    const points: ProjectedPoint[] = [];

    segments.forEach((seg, idx) => {
      // First waypoint (Journey Origin)
      if (idx === 0) {
        const { x, y } = project(seg.origin.coordinates.lat, seg.origin.coordinates.lng);
        points.push({
          x,
          y,
          lat: seg.origin.coordinates.lat,
          lng: seg.origin.coordinates.lng,
          title: seg.origin.name,
          city: seg.origin.city,
          type: seg.origin.type,
          isHub: false,
          hubType: 'origin',
          segmentIndex: 0,
        });
      }

      // Segment Destination / Transfer Hub
      const isFinal = idx === segments.length - 1;
      const { x, y } = project(seg.destination.coordinates.lat, seg.destination.coordinates.lng);
      const xrSceneId = matchXRSceneForHub(seg.destination.name) || matchXRSceneForHub(seg.destination.city);

      points.push({
        x,
        y,
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

    return points;
  }, [segments, bounds]);

  // Helper: Get mode stroke color
  const getModeColor = (mode: string) => {
    switch (mode) {
      case 'flight':
        return '#4f46e5'; // Indigo
      case 'train':
        return '#059669'; // Emerald
      case 'bus':
        return '#d97706'; // Amber
      case 'rapido':
      case 'auto':
        return '#7c3aed'; // Violet
      case 'cab':
      default:
        return '#2563eb'; // Blue
    }
  };

  // Active segment
  const activeSegment = segments[activeSegmentIndex] || segments[0];
  const activeEnrichedSeg = enrichedRoute?.segments?.[activeSegmentIndex];

  // Total summary telemetry
  const totalKm = enrichedRoute
    ? Math.round(enrichedRoute.total_distance_meters / 1000)
    : segments.reduce((sum, s) => sum + (s.distanceKm || 0), 0);

  const totalMin = enrichedRoute
    ? Math.round(enrichedRoute.total_duration_seconds / 60)
    : segments.reduce((sum, s) => sum + (s.durationMinutes || 0), 0);

  const providerSource = enrichedRoute?.source || 'deterministic_geo';
  const isGoogleSource = providerSource.includes('google');
  const isValhallaSource = providerSource.includes('valhalla');

  const providerBadgeLabel = isGoogleSource
    ? 'Google Routes API'
    : isValhallaSource
    ? 'Valhalla OSM Engine'
    : 'KogniSync Geo-Engine';

  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white overflow-hidden flex flex-col shadow-sm relative ${className}`}
    >
      {/* Top Map Toolbar */}
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50/90 flex flex-wrap items-center justify-between gap-3 z-10">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-blue-600 text-white shadow-xs">
            <Compass className="w-4 h-4 animate-spin-slow" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-900 font-display">
              Multimodal Journey Spatial Map
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              {segments[0]?.origin?.city} → {segments[segments.length - 1]?.destination?.city} · Door-to-Door Corridor
            </span>
          </div>
        </div>

        {/* View Mode Switch & Provider Badge */}
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

          <span
            className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-md border ${
              isGoogleSource || isValhallaSource
                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                : 'bg-blue-50 text-blue-800 border-blue-200'
            }`}
          >
            <Sparkles className="w-2.5 h-2.5" />
            {providerBadgeLabel}
          </span>
        </div>
      </div>

      {/* Map Canvas / Visualization Viewport */}
      <div className="relative h-80 sm:h-96 w-full bg-slate-950 flex flex-col items-center justify-center overflow-hidden">
        {/* Subtle grid pattern background */}
        <div className="absolute inset-0 opacity-15 bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:24px_24px] pointer-events-none" />

        {/* Coordinate HUD in top corner */}
        <div className="absolute top-3 left-4 flex items-center gap-2 text-[10px] font-mono text-slate-400 bg-slate-900/80 px-2.5 py-1 rounded-lg border border-slate-800 pointer-events-none z-10 backdrop-blur-xs">
          <span className="text-blue-400">LAT:</span> {bounds.minLat.toFixed(2)}° – {bounds.maxLat.toFixed(2)}° N
          <span className="text-slate-600">|</span>
          <span className="text-blue-400">LNG:</span> {bounds.minLng.toFixed(2)}° – {bounds.maxLng.toFixed(2)}° E
        </div>

        {viewMode === 'geographic' ? (
          /* =========================================================================
             MODE A: 2D Spatial SVG Vector Map Projection
             ========================================================================= */
          <svg
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            className="w-full h-full object-contain select-none"
          >
            <defs>
              {/* Radial glow for active pins */}
              <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.6" />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
              </radialGradient>
              {/* Gradient for flight corridors */}
              <linearGradient id="flightGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#a855f7" />
              </linearGradient>
            </defs>

            {/* Faint latitude/longitude guide lines */}
            <line x1={padding} y1={svgHeight / 2} x2={svgWidth - padding} y2={svgHeight / 2} stroke="#1e293b" strokeDasharray="4 4" strokeWidth="1" />
            <line x1={svgWidth / 2} y1={padding} x2={svgWidth / 2} y2={svgHeight - padding} stroke="#1e293b" strokeDasharray="4 4" strokeWidth="1" />

            {/* Segment Polylines */}
            {segments.map((seg, idx) => {
              const enrichedSeg = enrichedRoute?.segments?.[idx];
              const modeColor = getModeColor(seg.mode);
              const isActive = activeSegmentIndex === idx;

              // Generate SVG path string from coordinates
              let pathD = '';
              if (enrichedSeg?.coordinates?.length) {
                enrichedSeg.coordinates.forEach((c, cIdx) => {
                  const pt = project(c.latitude, c.longitude);
                  if (cIdx === 0) pathD += `M ${pt.x} ${pt.y}`;
                  else pathD += ` L ${pt.x} ${pt.y}`;
                });
              } else {
                const p1 = project(seg.origin.coordinates.lat, seg.origin.coordinates.lng);
                const p2 = project(seg.destination.coordinates.lat, seg.destination.coordinates.lng);
                if (seg.mode === 'flight') {
                  const midX = (p1.x + p2.x) / 2;
                  const midY = (p1.y + p2.y) / 2 - 40; // Arc elevation
                  pathD = `M ${p1.x} ${p1.y} Q ${midX} ${midY} ${p2.x} ${p2.y}`;
                } else {
                  pathD = `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
                }
              }

              return (
                <g key={`path-group-${seg.segmentId}`} className="cursor-pointer">
                  {/* Outer glow stroke when active */}
                  {isActive && (
                    <path
                      d={pathD}
                      fill="none"
                      stroke={modeColor}
                      strokeWidth="10"
                      strokeOpacity="0.25"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  )}

                  {/* Main Route Polyline */}
                  <path
                    d={pathD}
                    fill="none"
                    stroke={modeColor}
                    strokeWidth={isActive ? '4' : '3'}
                    strokeDasharray={
                      seg.mode === 'flight' ? '8 6' : seg.mode === 'train' ? '10 5' : undefined
                    }
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="transition-all hover:stroke-width-5"
                    onClick={() => {
                      setActiveSegmentIndex(idx);
                      if (onSegmentClick) onSegmentClick(seg.segmentId);
                    }}
                  />
                </g>
              );
            })}

            {/* Waypoint Pins & Nodes */}
            {projectedWaypoints.map((wp, idx) => {
              const isFirst = wp.hubType === 'origin';
              const isLast = wp.hubType === 'destination';
              const hasXR = !!wp.xrSceneId;

              return (
                <g
                  key={`wp-${wp.title}-${idx}`}
                  transform={`translate(${wp.x}, ${wp.y})`}
                  className="cursor-pointer group"
                  onClick={() => {
                    if (wp.segmentIndex !== undefined) setActiveSegmentIndex(wp.segmentIndex);
                  }}
                  onMouseEnter={() => setHoveredNode(wp)}
                  onMouseLeave={() => setHoveredNode(null)}
                >
                  {/* Pulse ring for XR-enabled hubs */}
                  {hasXR && (
                    <circle
                      r="16"
                      fill="url(#hubGlow)"
                      className="animate-ping opacity-60 pointer-events-none"
                    />
                  )}

                  {/* Outer circle */}
                  <circle
                    r={isFirst || isLast ? '9' : '7'}
                    fill={isFirst ? '#16a34a' : isLast ? '#e11d48' : '#0f172a'}
                    stroke={isFirst ? '#86efac' : isLast ? '#fda4af' : hasXR ? '#38bdf8' : '#94a3b8'}
                    strokeWidth={hasXR ? '3' : '2'}
                    className="transition-transform group-hover:scale-125"
                  />

                  {/* Inner dot */}
                  <circle
                    r={isFirst || isLast ? '3' : '2'}
                    fill="#ffffff"
                  />

                  {/* Label pill above node */}
                  <g
                    transform={`translate(0, ${isFirst || isLast ? -16 : -14})`}
                    className="pointer-events-none"
                  >
                    <rect
                      x="-50"
                      y="-12"
                      width="100"
                      height="16"
                      rx="4"
                      fill="#0f172a"
                      fillOpacity="0.9"
                      stroke="#334155"
                      strokeWidth="0.8"
                    />
                    <text
                      textAnchor="middle"
                      y="0"
                      fill="#f8fafc"
                      fontSize="9"
                      fontWeight="bold"
                      fontFamily="sans-serif"
                    >
                      {wp.city}
                    </text>
                  </g>
                </g>
              );
            })}
          </svg>
        ) : (
          /* =========================================================================
             MODE B: Corridor Topology Schematic Diagram
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
                        activeSegmentIndex === idx
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
              {projectedWaypoints.map((wp, idx) => {
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

        {/* Hover / Node inspector card */}
        {hoveredNode && (
          <div className="absolute top-12 left-4 bg-slate-900/95 border border-slate-700 p-3 rounded-xl shadow-xl z-30 max-w-xs text-xs text-slate-200 backdrop-blur-md animate-in fade-in">
            <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-1.5 mb-2">
              <span className="font-bold text-white text-sm">{hoveredNode.title}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-slate-800 font-mono text-slate-300">
                {hoveredNode.city}
              </span>
            </div>
            <div className="flex flex-col gap-1 text-[11px] text-slate-300">
              <div>
                <strong className="text-slate-400">Coords:</strong> {hoveredNode.lat.toFixed(4)}°N,{' '}
                {hoveredNode.lng.toFixed(4)}°E
              </div>
              {hoveredNode.transferBufferMinutes && (
                <div className="text-amber-400 font-medium">
                  Transfer Connection Buffer: +{hoveredNode.transferBufferMinutes} min
                </div>
              )}
            </div>
            {hoveredNode.xrSceneId && (
              <button
                onClick={() => navigate(`/xr/${hoveredNode.xrSceneId}`)}
                className="mt-2.5 w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs transition-colors shadow-xs"
              >
                <Eye className="w-3.5 h-3.5" />
                <span>Explore Station in 360°</span>
              </button>
            )}
          </div>
        )}

        {/* OpenStreetMap Attribution Label */}
        <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-slate-900/80 backdrop-blur-xs text-[10px] text-slate-400 border border-slate-800 shadow-2xs pointer-events-none select-none z-20">
          Map data © <span className="text-slate-300 font-medium">OpenStreetMap</span> contributors
        </div>
      </div>

      {/* Segment Selector & Detailed Telemetry Bar */}
      <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col gap-3">
        {/* Mode Selector Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 max-w-full">
          {segments.map((seg, idx) => {
            const isSelected = activeSegmentIndex === idx;
            const modeMeta = getModeMeta(seg.mode);
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
                style={{ backgroundColor: getModeColor(activeSegment.mode) }}
              >
                <ModeIcon mode={activeSegment.mode} size={20} />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-950 font-display">
                    {activeSegment.origin.city} → {activeSegment.destination.city}
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 uppercase">
                    {activeSegment.mode}
                  </span>
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
              {isGoogleSource
                ? 'Routing computed via Google Routes API v2'
                : isValhallaSource
                ? 'Road routing computed via Valhalla OSM Engine · Map data © OpenStreetMap contributors'
                : 'Routing computed via KogniSync spatial engine · Map data © OpenStreetMap contributors'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default JourneyMap;
