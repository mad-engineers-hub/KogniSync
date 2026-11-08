import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Check, ListOrdered } from 'lucide-react';
import type { NormalizedManeuver } from '../../types/navigation';
import { getManeuverIcon } from './ManeuverInstructionBanner';

interface UpcomingManeuversListProps {
  maneuvers: NormalizedManeuver[];
  onToggleManeuver?: (index: number) => void;
  className?: string;
}

export const UpcomingManeuversList: React.FC<UpcomingManeuversListProps> = ({
  maneuvers,
  onToggleManeuver,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  if (!maneuvers || maneuvers.length === 0) {
    return null;
  }

  // Skip the first maneuver if it's already shown in the banner
  const subsequentManeuvers = maneuvers.slice(1);

  if (subsequentManeuvers.length === 0) {
    return (
      <div className={`p-3.5 rounded-xl border border-slate-200 bg-slate-50 text-xs text-slate-500 font-mono text-center ${className}`}>
        Final road maneuver for this leg.
      </div>
    );
  }

  return (
    <div className={`rounded-2xl border border-slate-200 bg-white shadow-xs overflow-hidden flex flex-col ${className}`}>
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        className="w-full px-4 py-3 bg-slate-50 hover:bg-slate-100/80 transition-colors flex items-center justify-between text-left border-b border-slate-200/80 cursor-pointer"
      >
        <div className="flex items-center gap-2 text-slate-800">
          <ListOrdered className="w-4 h-4 text-blue-600 shrink-0" />
          <span className="text-xs font-bold uppercase tracking-wider font-mono">
            Upcoming Maneuvers ({subsequentManeuvers.length})
          </span>
        </div>
        <div className="flex items-center gap-1 text-slate-400">
          <span className="text-[10px] font-mono">{isExpanded ? 'Hide' : 'Show'}</span>
          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {isExpanded && (
        <div className="divide-y divide-slate-100 max-h-64 overflow-y-auto">
          {subsequentManeuvers.map((m, relativeIdx) => {
            const actualIndex = relativeIdx + 1;
            const icon = getManeuverIcon(m.action);

            return (
              <div
                key={m.id || actualIndex}
                className={`p-3 sm:p-3.5 flex items-center justify-between gap-3 transition-colors ${
                  m.isCompleted ? 'bg-slate-50/80 opacity-60' : 'hover:bg-slate-50/50'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-1.5 rounded-lg bg-slate-100 border border-slate-200 shrink-0 text-slate-600">
                    {icon}
                  </div>
                  <div className="flex flex-col min-w-0">
                    <p className={`text-xs font-medium text-slate-900 leading-snug line-clamp-2 ${
                      m.isCompleted ? 'line-through text-slate-500' : ''
                    }`}>
                      {m.instruction}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-slate-500">
                      <span>{m.formattedDistance}</span>
                      <span>•</span>
                      <span>~{m.formattedDuration}</span>
                      {m.streetNames && m.streetNames.length > 0 && (
                        <>
                          <span>•</span>
                          <span className="truncate max-w-[120px]">{m.streetNames[0]}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {onToggleManeuver && (
                  <button
                    type="button"
                    onClick={() => onToggleManeuver(actualIndex)}
                    aria-label={`Mark maneuver ${actualIndex} ${m.isCompleted ? 'incomplete' : 'complete'}`}
                    className={`w-6 h-6 rounded-lg border flex items-center justify-center shrink-0 transition-all ${
                      m.isCompleted
                        ? 'bg-emerald-600 border-emerald-600 text-white shadow-xs'
                        : 'border-slate-300 hover:border-slate-400 text-transparent hover:text-slate-300'
                    }`}
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

