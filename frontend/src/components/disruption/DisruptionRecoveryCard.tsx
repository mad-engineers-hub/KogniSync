/**
 * frontend/src/components/disruption/DisruptionRecoveryCard.tsx
 *
 * Multimodal Journey Recovery & Alternative Recommendation Card (Milestone M3.7).
 * Displays Pareto-ranked alternative routes, delta metrics (time, fare, carbon),
 * trade-off explanations, and explicit manual rebooking requirement badges.
 */
import React from 'react';
import {
  CheckCircle,
  Clock,
  ArrowRight,
  Leaf,
  Info,
  AlertTriangle,
} from 'lucide-react';
import { RecoveryRecommendation } from '../../types/disruption';
import { formatCurrency, formatDuration } from '../../lib/utils';
import { ProvenanceBadge } from '../common/ProvenanceBadge';

interface DisruptionRecoveryCardProps {
  recommendation: RecoveryRecommendation;
  onSelectRecovery?: (recoveredJourney: any) => void;
  isSelected?: boolean;
}

export const DisruptionRecoveryCard: React.FC<DisruptionRecoveryCardProps> = ({
  recommendation,
  onSelectRecovery,
  isSelected = false,
}) => {
  const {
    strategy,
    title,
    summary,
    tradeOffs,
    recoveredJourney,
    durationDeltaMinutes,
    priceDelta,
    carbonDeltaKg,
    isFeasible,
    feasibilityNotes,
    provenance,
  } = recommendation;

  if (!isFeasible || strategy === 'no_feasible_alternative' || !recoveredJourney) {
    return (
      <div className="p-5 rounded-2xl border border-rose-200 bg-rose-50/50 shadow-xs flex flex-col gap-3">
        <div className="flex items-center gap-2 text-rose-700">
          <AlertTriangle className="w-5 h-5 text-rose-600" />
          <h4 className="text-sm font-bold font-display">{title}</h4>
        </div>
        <p className="text-xs text-slate-700 leading-relaxed font-medium">{summary}</p>
        {feasibilityNotes && feasibilityNotes.length > 0 && (
          <ul className="text-xs text-rose-800 list-disc list-inside space-y-1 font-mono">
            {feasibilityNotes.map((note, idx) => (
              <li key={idx}>{note}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return (
    <div
      className={`p-5 sm:p-6 rounded-2xl border transition-all flex flex-col gap-5 ${
        isSelected
          ? 'border-blue-600 bg-blue-50/40 shadow-md ring-2 ring-blue-600/20'
          : 'border-slate-200 bg-white hover:border-blue-300 shadow-xs'
      }`}
    >
      {/* Top Banner: Strategy Badge, Title, and Provenance */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-col gap-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2.5 py-0.5 rounded-full bg-blue-600 text-white text-[10px] font-bold font-mono uppercase tracking-wider">
              {strategy.replace(/_/g, ' ')}
            </span>
            <ProvenanceBadge sourceType={provenance} />
            <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-mono font-bold">
              PARETO OPTIMIZED RECOVERY
            </span>
          </div>

          <h3 className="text-base sm:text-lg font-black text-slate-950 font-display mt-0.5">
            {title}
          </h3>
        </div>

        {onSelectRecovery && (
          <button
            onClick={() => onSelectRecovery(recoveredJourney)}
            className={`px-4 py-2.5 rounded-xl font-bold text-xs flex items-center gap-2 shadow-xs transition-all cursor-pointer self-end sm:self-auto shrink-0 ${
              isSelected
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-white border border-slate-300 text-slate-800 hover:bg-slate-100 hover:border-slate-400'
            }`}
          >
            <span>{isSelected ? 'Active Preview' : 'Inspect Alternative'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Summary Narrative */}
      <p className="text-xs sm:text-sm text-slate-700 leading-relaxed font-medium">
        {summary}
      </p>

      {/* Side-by-Side Comparison Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
        {/* Duration Delta */}
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase font-mono tracking-wider font-bold text-slate-500">
            Total Duration
          </span>
          <div className="flex items-center gap-1.5">
            <Clock className="w-4 h-4 text-slate-600" />
            <span className="text-sm font-bold text-slate-900 font-mono">
              {formatDuration(recoveredJourney.totalDurationMinutes)}
            </span>
            <span
              className={`text-[11px] font-bold font-mono ${
                durationDeltaMinutes <= 0 ? 'text-emerald-600' : 'text-amber-600'
              }`}
            >
              ({durationDeltaMinutes > 0 ? `+${durationDeltaMinutes}` : `${durationDeltaMinutes}`}m)
            </span>
          </div>
        </div>

        {/* Fare Delta */}
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase font-mono tracking-wider font-bold text-slate-500">
            Total Fare
          </span>
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-bold text-slate-900 font-mono">
              {formatCurrency(recoveredJourney.totalPrice, recoveredJourney.currency)}
            </span>
            <span
              className={`text-[11px] font-bold font-mono ${
                priceDelta <= 0 ? 'text-emerald-600' : 'text-amber-600'
              }`}
            >
              ({priceDelta > 0 ? `+₹${priceDelta}` : `₹${priceDelta}`})
            </span>
          </div>
        </div>

        {/* Carbon Delta */}
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase font-mono tracking-wider font-bold text-slate-500">
            Carbon Footprint
          </span>
          <div className="flex items-center gap-1.5">
            <Leaf className="w-4 h-4 text-emerald-600" />
            <span className="text-sm font-bold text-slate-900 font-mono">
              {recoveredJourney.carbonKg} kg CO₂
            </span>
            <span
              className={`text-[11px] font-bold font-mono ${
                carbonDeltaKg <= 0 ? 'text-emerald-600' : 'text-amber-600'
              }`}
            >
              ({carbonDeltaKg > 0 ? `+${carbonDeltaKg}` : `${carbonDeltaKg}`} kg)
            </span>
          </div>
        </div>
      </div>

      {/* Trade-offs & Strategic Explanations */}
      {tradeOffs && tradeOffs.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-slate-600">
            Trade-Off Analysis & Recovery Details:
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {tradeOffs.map((to, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2 p-2.5 rounded-lg bg-slate-50/80 border border-slate-200/60 text-xs text-slate-700 font-medium"
              >
                <CheckCircle className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
                <span>{to}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mandatory Safety Invariant Notice */}
      <div className="p-3 rounded-xl border border-amber-200 bg-amber-50/70 flex items-start gap-2.5 text-xs text-amber-900">
        <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <div className="flex flex-col gap-0.5">
          <span className="font-bold">Manual Rebooking Required (Safety Guarantee)</span>
          <span className="text-[11px] text-amber-800 leading-relaxed font-medium">
            Selecting this recovery itinerary will update your interactive map and guidance preview.
            In accordance with KogniSync safety policies, existing carrier bookings will NEVER be automatically released, cancelled, or charged without your explicit rebooking consent.
          </span>
        </div>
      </div>
    </div>
  );
};

