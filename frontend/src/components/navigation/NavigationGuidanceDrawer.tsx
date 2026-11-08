import React from 'react';
import {
  Navigation,
  Crosshair,
  Compass,
  AlertCircle,
  X,
  ExternalLink,
} from 'lucide-react';
import type { UseJourneyGuidanceReturn } from '../../hooks/useJourneyGuidance';
import { ManeuverInstructionBanner } from './ManeuverInstructionBanner';
import { UpcomingManeuversList } from './UpcomingManeuversList';
import { MultimodalGuidanceCard } from './MultimodalGuidanceCard';
import { TransferReadinessCard } from './TransferReadinessCard';
import { JourneyProgressTracker } from './JourneyProgressTracker';
import type { JourneySegment } from '../../types/journey';

interface NavigationGuidanceDrawerProps {
  guidance: UseJourneyGuidanceReturn;
  segments: JourneySegment[];
  onClose?: () => void;
  className?: string;
}

export const NavigationGuidanceDrawer: React.FC<NavigationGuidanceDrawerProps> = ({
  guidance,
  segments,
  onClose,
  className = '',
}) => {
  const {
    activeSegmentIndex,
    activeSegment,
    activeGuidance,
    nextTransferReadiness,
    overallProgressPercent,
    progress,
    completeActiveSegment,
    undoSegment,
    advanceNextSegment,
    selectSegmentIndex,
    toggleManeuverCompletion,
    resetAllProgress,
    locationState,
    startLocationGuidance,
    stopLocationGuidance,
    triggerDemoPosition,
    isLocationTracking,
  } = guidance;

  const currentManeuvers = activeGuidance?.maneuvers || [];
  const nextManeuver = currentManeuvers[0];

  return (
    <div
      className={`flex flex-col gap-4 bg-slate-50/95 backdrop-blur-md p-4 sm:p-5 rounded-3xl border border-slate-200/90 shadow-lg ${className}`}
    >
      {/* Navigation Drawer Header */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-xl bg-blue-600 text-white shadow-sm shrink-0">
            <Navigation className="w-5 h-5 animate-pulse" />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-[10px] font-mono uppercase tracking-wider text-blue-600 font-bold">
              Navigation Guidance & Progress
            </span>
            <h3 className="text-sm sm:text-base font-bold text-slate-900 truncate">
              Leg {activeSegmentIndex + 1} of {segments.length}: {activeSegment?.origin.city} → {activeSegment?.destination.city}
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Foreground Location Assistance Toggle */}
          {isLocationTracking ? (
            <button
              type="button"
              onClick={stopLocationGuidance}
              aria-label="Stop foreground location tracking"
              className="px-2.5 py-1.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-mono font-bold flex items-center gap-1.5 hover:bg-rose-100 transition-colors cursor-pointer"
            >
              <Crosshair className="w-3.5 h-3.5 animate-spin-slow" />
              <span className="hidden sm:inline">Stop GPS</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={startLocationGuidance}
              aria-label="Start foreground location assistance"
              className="px-2.5 py-1.5 rounded-xl bg-white border border-slate-300 hover:border-blue-400 text-slate-700 text-xs font-mono font-bold flex items-center gap-1.5 hover:bg-blue-50/50 transition-colors cursor-pointer"
            >
              <Crosshair className="w-3.5 h-3.5 text-blue-600" />
              <span className="hidden sm:inline">Enable GPS</span>
            </button>
          )}

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close navigation guidance panel"
              className="p-1.5 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Location Guidance Status Banner (Foreground GPS) */}
      {locationState.status !== 'idle' && (
        <div className="p-3 rounded-2xl bg-white border border-slate-200 text-xs font-mono flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                locationState.status === 'live_position'
                  ? 'bg-emerald-500 animate-ping'
                  : locationState.status === 'demo_position'
                  ? 'bg-indigo-500'
                  : 'bg-amber-500'
              }`}
            />
            <span className="font-bold text-slate-800">
              {locationState.status === 'live_position' && 'Live Position Active'}
              {locationState.status === 'demo_position' && 'Demo Position (Simulated)'}
              {locationState.status === 'requesting' && 'Acquiring GPS Fix...'}
              {locationState.status === 'permission_denied' && 'GPS Blocked in Browser'}
              {locationState.status === 'unavailable' && 'GPS Unavailable'}
            </span>
            {locationState.accuracyMeters && (
              <span className="text-slate-400">±{locationState.accuracyMeters}m</span>
            )}
          </div>

          {locationState.errorMessage && (
            <span className="text-[11px] text-amber-700">{locationState.errorMessage}</span>
          )}

          {/* Quick Demo Location Trigger for Testing */}
          {locationState.status !== 'demo_position' && activeSegment && (
            <button
              type="button"
              onClick={() =>
                triggerDemoPosition({
                  latitude: activeSegment.origin.coordinates.lat,
                  longitude: activeSegment.origin.coordinates.lng,
                })
              }
              className="text-[10px] text-blue-600 hover:underline font-bold"
            >
              Simulate Origin GPS
            </button>
          )}
        </div>
      )}

      {/* 1. Turn-by-Turn Instruction Banner (Road modes with maneuvers) */}
      {activeGuidance?.isLiveManeuvers && nextManeuver ? (
        <ManeuverInstructionBanner
          maneuver={nextManeuver}
          onComplete={() => activeSegment && toggleManeuverCompletion(activeSegment.segmentId, 0)}
        />
      ) : null}

      {/* 2. Multimodal Guidance Card (Context, Origin->Dest, Independent Verification Notice) */}
      {activeGuidance && <MultimodalGuidanceCard guidance={activeGuidance} />}

      {/* 3. Upcoming Maneuvers List (Road legs with multiple steps) */}
      {activeGuidance?.isLiveManeuvers && currentManeuvers.length > 1 && (
        <UpcomingManeuversList
          maneuvers={currentManeuvers}
          onToggleManeuver={(idx) => activeSegment && toggleManeuverCompletion(activeSegment.segmentId, idx)}
        />
      )}

      {/* 4. Transfer Readiness Card (Upcoming connection window & buffer) */}
      {nextTransferReadiness && (
        <TransferReadinessCard readiness={nextTransferReadiness} />
      )}

      {/* 5. Journey Progress Tracker (Leg completion, undo, next, reset) */}
      <JourneyProgressTracker
        segments={segments}
        activeSegmentIndex={activeSegmentIndex}
        completedSegmentIds={progress.completedSegmentIds}
        overallProgressPercent={overallProgressPercent}
        onSelectSegment={selectSegmentIndex}
        onCompleteActiveSegment={completeActiveSegment}
        onUndoSegment={undoSegment}
        onAdvanceNext={advanceNextSegment}
        onResetProgress={resetAllProgress}
      />
    </div>
  );
};

