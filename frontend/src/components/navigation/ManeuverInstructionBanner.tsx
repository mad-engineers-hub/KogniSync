import React from 'react';
import {
  Compass,
  CheckCircle2,
} from 'lucide-react';
import type { NormalizedManeuver } from '../../types/navigation';
import { getManeuverIcon } from './navigationIcons';

interface ManeuverInstructionBannerProps {
  maneuver?: NormalizedManeuver;
  onComplete?: () => void;
  className?: string;
}

export const ManeuverInstructionBanner: React.FC<ManeuverInstructionBannerProps> = ({
  maneuver,
  onComplete,
  className = '',
}) => {
  if (!maneuver) {
    return (
      <div className={`p-4 rounded-2xl bg-slate-900 text-white shadow-lg border border-slate-800 ${className}`}>
        <div className="flex items-center gap-3">
          <Compass className="w-5 h-5 text-slate-400 shrink-0" />
          <p className="text-sm text-slate-300 font-medium">Follow the designated corridor to your next waypoint.</p>
        </div>
      </div>
    );
  }

  const icon = getManeuverIcon(maneuver.action);

  return (
    <div
      aria-live="polite"
      className={`p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 text-white shadow-xl border border-slate-800/80 backdrop-blur-md flex flex-col gap-3 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3.5 min-w-0">
          <div className="p-2.5 rounded-xl bg-slate-800/90 border border-slate-700/60 shadow-inner shrink-0">
            {icon}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-[10px] font-mono uppercase tracking-wider text-blue-400 font-bold">
              Next Turn Instruction
            </span>
            <h3 className="text-base sm:text-lg font-bold text-white leading-snug line-clamp-2">
              {maneuver.instruction}
            </h3>
            {maneuver.streetNames && maneuver.streetNames.length > 0 && (
              <span className="text-xs text-slate-400 truncate mt-0.5">
                onto <span className="text-slate-200 font-semibold">{maneuver.streetNames.join(', ')}</span>
              </span>
            )}
          </div>
        </div>

        {onComplete && (
          <button
            type="button"
            onClick={onComplete}
            aria-label="Mark maneuver completed"
            className={`p-2 rounded-xl border transition-all shrink-0 ${
              maneuver.isCompleted
                ? 'bg-emerald-600/20 border-emerald-500/50 text-emerald-400'
                : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            <CheckCircle2 className="w-5 h-5" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-3 pt-1 border-t border-slate-800/60 text-xs font-mono">
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-950/60 border border-blue-800/40 text-blue-300 font-semibold">
          <span>In {maneuver.formattedDistance}</span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/60 border border-slate-700/40 text-slate-300">
          <span>~{maneuver.formattedDuration}</span>
        </div>
      </div>
    </div>
  );
};

