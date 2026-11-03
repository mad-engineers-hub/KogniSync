import React from 'react';
import {
  Navigation,
  Info,
  Car,
  Bus,
  Train,
  DoorOpen,
  Building,
  ArrowRight,
  X,
} from 'lucide-react';
import { XRSceneHotspot } from '../../types/xr';

interface XRHotspotOverlayProps {
  hotspot: XRSceneHotspot;
  onClose: () => void;
  onTriggerAction?: (hotspot: XRSceneHotspot) => void;
}

export const XRHotspotOverlay: React.FC<XRHotspotOverlayProps> = ({
  hotspot,
  onClose,
  onTriggerAction,
}) => {
  const getCategoryIcon = (category: XRSceneHotspot['category']) => {
    switch (category) {
      case 'bus_bay':
        return <Bus className="w-4 h-4 text-amber-400" />;
      case 'cab_pickup':
        return <Car className="w-4 h-4 text-emerald-400" />;
      case 'platform':
        return <Train className="w-4 h-4 text-blue-400" />;
      case 'exit':
        return <DoorOpen className="w-4 h-4 text-rose-400" />;
      case 'hotel_amenity':
        return <Building className="w-4 h-4 text-purple-400" />;
      default:
        return <Info className="w-4 h-4 text-sky-400" />;
    }
  };

  const getCategoryLabel = (category: XRSceneHotspot['category']) => {
    switch (category) {
      case 'bus_bay':
        return 'Bus Feeder';
      case 'cab_pickup':
        return 'Cab Pickup';
      case 'platform':
        return 'Train Platform';
      case 'exit':
        return 'Concourse Exit';
      case 'hotel_amenity':
        return 'Hotel Amenity';
      default:
        return 'Station Info';
    }
  };

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 w-[90%] max-w-md p-4 rounded-2xl bg-slate-900/95 text-white backdrop-blur-xl border border-slate-700/80 shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-200">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-slate-800 border border-slate-700">
            {getCategoryIcon(hotspot.category)}
          </div>
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400">
              {getCategoryLabel(hotspot.category)}
            </span>
            <h4 className="text-sm font-bold text-white">{hotspot.title}</h4>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          title="Close Hotspot"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {hotspot.description && (
        <p className="mt-2 text-xs text-slate-300 leading-relaxed">{hotspot.description}</p>
      )}

      {hotspot.action === 'wayfinding' && (
        <button
          type="button"
          onClick={() => onTriggerAction?.(hotspot)}
          className="mt-3.5 w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shadow-md transition-all active:scale-[0.98]"
        >
          <Navigation className="w-3.5 h-3.5" />
          <span>Launch AR Wayfinding Route</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
};
