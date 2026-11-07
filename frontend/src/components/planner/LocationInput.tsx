import React, { useState, useRef } from 'react';
import { MapPin, ArrowRightLeft, LocateFixed, Loader2, Check, X } from 'lucide-react';
import { Coordinates, LocationError } from '../../types/location';
import { locationService } from '../../services/location/locationService';
import { useNotification } from '../../context/NotificationContext';
import { GPS_NOTIFICATION_MESSAGES } from '../../services/location/gpsNotificationMessages';

export interface LocationInputProps {
  origin: string;
  destination: string;
  onOriginChange: (val: string, coords?: Coordinates | null) => void;
  onDestinationChange: (val: string, coords?: Coordinates | null) => void;
  onSwap?: () => void;
  originCoordinates?: Coordinates | null;
  onOriginCoordinatesChange?: (coords: Coordinates | null) => void;
  autoLocateOnMount?: boolean; // Strictly false by default for user privacy
}

const COMMON_CITIES = [
  'Bangalore',
  'Chennai',
  'Mumbai',
  'Pune',
  'Delhi',
  'Jaipur',
  'Hyderabad',
  'Kochi',
];

export const LocationInput: React.FC<LocationInputProps> = ({
  origin,
  destination,
  onOriginChange,
  onDestinationChange,
  onSwap,
  originCoordinates,
  onOriginCoordinatesChange,
}) => {
  const { showSuccess, showError, showWarning, dismissCategory } = useNotification();
  const [isLocating, setIsLocating] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const locationRequestIdRef = useRef<number>(0);

  const handleUseCurrentLocation = async () => {
    const currentRequestId = ++locationRequestIdRef.current;
    setIsLocating(true);
    setIsSuccess(false);

    try {
      const result = await locationService.getCurrentLocation();
      if (currentRequestId !== locationRequestIdRef.current) return;
      onOriginChange(result.formattedAddress, result.coordinates);
      onOriginCoordinatesChange?.(result.coordinates);
      setIsSuccess(true);
      setTimeout(() => setIsSuccess(false), 3000);

      if (result.accuracyMeters > 2500) {
        showWarning(GPS_NOTIFICATION_MESSAGES.POOR_ACCURACY, { category: 'gps' });
      } else {
        showSuccess(GPS_NOTIFICATION_MESSAGES.SUCCESS, {
          category: 'gps',
          duration: 4500,
        });
      }
    } catch (err) {
      if (currentRequestId !== locationRequestIdRef.current) return;
      if (err instanceof LocationError) {
        if (err.code === 'POOR_ACCURACY') {
          showWarning(err.userFriendlyMessage, { category: 'gps' });
        } else {
          showError(err.userFriendlyMessage, { category: 'gps' });
        }
      } else {
        showError('Your device could not provide a location. Check your location settings and retry.', {
          category: 'gps',
        });
      }
    } finally {
      if (currentRequestId === locationRequestIdRef.current) {
        setIsLocating(false);
      }
    }
  };

  const handleOriginInputChange = (val: string) => {
    locationRequestIdRef.current++;
    // If user edits text manually, clear previous coordinates to avoid coordinate/text mismatch
    onOriginChange(val, null);
    onOriginCoordinatesChange?.(null);
    dismissCategory('gps');
  };

  return (
    <div className="flex flex-col gap-1 w-full relative">
      <div className="flex flex-col sm:flex-row items-center gap-2 w-full relative">
        {/* Origin */}
        <div className="w-full flex-1 relative">
          <label className="block text-[11px] font-semibold text-slate-700 mb-1">
            Origin
          </label>
          <div className="relative flex items-center">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-blue-600">
              <MapPin className="w-4 h-4" />
            </div>
            <input
              type="text"
              list="cities-origin"
              value={origin}
              onChange={(e) => handleOriginInputChange(e.target.value)}
              placeholder="e.g. Bangalore"
              className="w-full pl-9 pr-16 py-2 bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 text-sm focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-600/10 transition-colors shadow-2xs"
            />
            <datalist id="cities-origin">
              {COMMON_CITIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>

            {/* GPS Autofill & Action Controls */}
            <div className="absolute right-2 flex items-center gap-1">
              {origin && (
                <button
                  type="button"
                  onClick={() => handleOriginInputChange('')}
                  className="text-slate-300 hover:text-slate-500 p-1 cursor-pointer"
                  title="Clear origin"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                type="button"
                onClick={handleUseCurrentLocation}
                disabled={isLocating}
                className={`p-1.5 rounded-lg border transition-all cursor-pointer flex items-center justify-center ${
                  isLocating
                    ? 'bg-blue-50 border-blue-200 text-blue-600'
                    : isSuccess
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-600'
                    : 'bg-slate-50 hover:bg-blue-50 border-slate-200 hover:border-blue-300 text-slate-500 hover:text-blue-600'
                }`}
                title="Use my current location"
                aria-label="Use my current location"
              >
                {isLocating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : isSuccess ? (
                  <Check className="w-3.5 h-3.5" />
                ) : (
                  <LocateFixed className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Swap Button */}
        {onSwap && (
          <button
            type="button"
            onClick={onSwap}
            className="mt-5 p-2 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-600 hover:text-slate-900 transition-all active:scale-95 flex items-center justify-center shrink-0 shadow-2xs cursor-pointer"
            title="Swap origin and destination"
          >
            <ArrowRightLeft className="w-4 h-4" />
          </button>
        )}

        {/* Destination */}
        <div className="w-full flex-1 relative">
          <label className="block text-[11px] font-semibold text-slate-700 mb-1">
            Destination
          </label>
          <div className="relative flex items-center">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-teal-600">
              <MapPin className="w-4 h-4" />
            </div>
            <input
              type="text"
              list="cities-dest"
              value={destination}
              onChange={(e) => onDestinationChange(e.target.value)}
              placeholder="e.g. Chennai"
              className="w-full pl-9 pr-8 py-2 bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 text-sm focus:outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-600/10 transition-colors shadow-2xs"
            />
            <datalist id="cities-dest">
              {COMMON_CITIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            {destination && (
              <button
                type="button"
                onClick={() => onDestinationChange('')}
                className="absolute right-2 text-slate-300 hover:text-slate-500 p-1 cursor-pointer"
                title="Clear destination"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
