import React from 'react';
import {
  Compass,
  AlertCircle,
  Clock,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';
import type { SegmentGuidance } from '../../types/navigation';
import { getModeIcon } from './navigationIcons';

interface MultimodalGuidanceCardProps {
  guidance: SegmentGuidance;
  className?: string;
}

export const MultimodalGuidanceCard: React.FC<MultimodalGuidanceCardProps> = ({
  guidance,
  className = '',
}) => {
  const icon = getModeIcon(guidance.mode);

  return (
    <div className={`p-4 sm:p-5 rounded-2xl border border-slate-200 bg-white shadow-xs flex flex-col gap-3.5 ${className}`}>
      {/* Top Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-slate-100 border border-slate-200 shrink-0">
            {icon}
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
              Leg {guidance.sequence} • {guidance.mode}
            </span>
            <h4 className="text-sm font-bold text-slate-900 truncate">
              {guidance.provider}
              {guidance.vehicleNumber && ` (${guidance.vehicleNumber})`}
            </h4>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-[10px] font-bold font-mono ${
              guidance.isLiveManeuvers
                ? 'bg-blue-50 text-blue-700 border-blue-200'
                : 'bg-slate-100 text-slate-600 border-slate-200'
            }`}
          >
            {guidance.isLiveManeuvers ? (
              <>
                <ShieldCheck className="w-3 h-3 text-blue-600" />
                Live OSM Maneuvers
              </>
            ) : (
              guidance.provenanceBadge
            )}
          </span>
        </div>
      </div>

      {/* Origin -> Destination Route */}
      <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs">
        <div className="flex flex-col min-w-0">
          <span className="text-[10px] text-slate-400 font-mono">FROM</span>
          <span className="font-bold text-slate-900 truncate">{guidance.originTitle}</span>
          <span className="text-[10px] text-slate-500 truncate">{guidance.originCity}</span>
        </div>

        <ArrowRight className="w-4 h-4 text-slate-300 shrink-0" />

        <div className="flex flex-col min-w-0 text-right">
          <span className="text-[10px] text-slate-400 font-mono">TO</span>
          <span className="font-bold text-slate-900 truncate">{guidance.destinationTitle}</span>
          <span className="text-[10px] text-slate-500 truncate">{guidance.destinationCity}</span>
        </div>
      </div>

      {/* Primary Action Guidance */}
      <div className="flex flex-col gap-1">
        <h5 className="text-xs sm:text-sm font-bold text-slate-900">{guidance.actionTitle}</h5>
        <p className="text-xs text-slate-600 leading-relaxed">{guidance.actionDetail}</p>
      </div>

      {/* Independent Verification Advisory for non-road/intercity legs */}
      {guidance.independentVerificationRequired && guidance.independentVerificationNotice && (
        <div className="p-3 rounded-xl bg-amber-50/90 border border-amber-200 text-amber-900 text-xs flex items-start gap-2.5 leading-relaxed font-mono">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <span className="font-bold text-[10px] uppercase tracking-wider text-amber-800">
              Station / Terminal Advisory
            </span>
            <span>{guidance.independentVerificationNotice}</span>
          </div>
        </div>
      )}

      {/* Timetable / Duration Metadata */}
      <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span>Scheduled: {guidance.durationMinutes} min</span>
        </div>

        {guidance.transferNotice && (
          <span className="text-blue-600 font-semibold truncate max-w-[200px]">
            {guidance.transferNotice}
          </span>
        )}
      </div>
    </div>
  );
};

