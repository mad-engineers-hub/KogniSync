import React from 'react';
import {
  ArrowUp,
  ArrowRight,
  ArrowLeft,
  ArrowUpRight,
  ArrowUpLeft,
  CornerUpRight,
  CornerUpLeft,
  RotateCcw,
  Compass,
  MapPin,
  GitMerge,
  Navigation,
  Train,
  Plane,
  Bus,
  Car,
  Footprints,
} from 'lucide-react';
import type { NormalizedManeuver } from '../../types/navigation';
import type { TransportMode } from '../../types/journey';

export function getManeuverIcon(action: NormalizedManeuver['action']): React.ReactElement {
  switch (action) {
    case 'depart':
      return <Compass className="w-6 h-6 text-emerald-400 shrink-0" />;
    case 'arrive':
      return <MapPin className="w-6 h-6 text-rose-400 shrink-0" />;
    case 'continue':
      return <ArrowUp className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'slight_right':
      return <ArrowUpRight className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'right':
      return <ArrowRight className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'sharp_right':
      return <CornerUpRight className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'u_turn':
      return <RotateCcw className="w-6 h-6 text-amber-400 shrink-0" />;
    case 'sharp_left':
      return <CornerUpLeft className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'left':
      return <ArrowLeft className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'slight_left':
      return <ArrowUpLeft className="w-6 h-6 text-blue-400 shrink-0" />;
    case 'merge':
      return <GitMerge className="w-6 h-6 text-indigo-400 shrink-0" />;
    case 'roundabout':
      return <RotateCcw className="w-6 h-6 text-purple-400 shrink-0" />;
    default:
      return <Navigation className="w-6 h-6 text-slate-400 shrink-0" />;
  }
}

export function getModeIcon(mode: TransportMode): React.ReactElement {
  switch (mode) {
    case 'train':
      return <Train className="w-5 h-5 text-purple-600" />;
    case 'flight':
      return <Plane className="w-5 h-5 text-indigo-600" />;
    case 'bus':
      return <Bus className="w-5 h-5 text-amber-600" />;
    case 'cab':
    case 'auto':
    case 'rapido':
      return <Car className="w-5 h-5 text-emerald-600" />;
    case 'walk':
      return <Footprints className="w-5 h-5 text-blue-600" />;
    default:
      return <Navigation className="w-5 h-5 text-slate-600" />;
  }
}
