import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Clock,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  Leaf,
  Eye,
  Compass,
  CheckCircle,
} from 'lucide-react';
import { Journey } from '../../types/journey';
import { ModeIcon } from '../common/ModeIcon';
import { OptimizationBadge } from '../common/OptimizationBadge';
import { formatCurrency, formatDuration, formatTime } from '../../lib/utils';
import { matchXRSceneForHub, getJourneyXRReferences } from '../../utils/xrMatching';

interface JourneyCardProps {
  journey: Journey;
  isFeatured?: boolean;
  isSelectedForMap?: boolean;
  onSelectForMap?: () => void;
}

export const JourneyCard: React.FC<JourneyCardProps> = ({
  journey,
  isFeatured = false,
  isSelectedForMap = false,
  onSelectForMap,
}) => {
  const navigate = useNavigate();
  const xrRefs = getJourneyXRReferences(journey);

  return (
    <div
      onClick={onSelectForMap}
      className={`rounded-2xl border transition-all duration-200 overflow-hidden cursor-pointer ${
        isSelectedForMap
          ? 'bg-white border-blue-600 shadow-md ring-2 ring-blue-500/20'
          : isFeatured
          ? 'bg-white border-blue-500 shadow-md ring-1 ring-blue-500/20'
          : 'bg-white hover:bg-slate-50/50 border-slate-200 hover:border-slate-300 shadow-sm'
      }`}
    >
      {/* 1. Top Banner: Recommendation category badge, title & AI match score */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 bg-slate-50 border-b border-slate-100">
        <div className="flex items-center gap-2 flex-wrap">
          <OptimizationBadge category={journey.recommendationCategory} />
          {journey.isParetoOptimal && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold font-mono border border-emerald-300"
              title="Pareto Optimal: Non-dominated choice across all 5 objectives"
            >
              <CheckCircle className="w-3 h-3 text-emerald-600" />
              Pareto Frontier
            </span>
          )}
          <span className="font-semibold text-slate-800 text-sm">{journey.title}</span>
        </div>
        <div className="flex items-center gap-2">
          {xrRefs.length > 0 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-blue-100/90 text-blue-700 text-[10px] font-bold font-mono border border-blue-200">
              <Eye className="w-3 h-3 text-blue-600" />
              XR Ready
            </span>
          )}
          <span className="text-xs font-mono font-medium text-slate-500">
            Score: <strong className="text-slate-900">{journey.aiExplanation.score}</strong>
          </span>
        </div>
      </div>

      <div className="p-4 sm:p-5 flex flex-col gap-4">
        {/* 2. Primary Route & Timing Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-base sm:text-lg font-bold text-slate-950 font-display">
                {journey.origin.name}
              </span>
              <span className="text-slate-400 font-light">→</span>
              <span className="text-base sm:text-lg font-bold text-slate-950 font-display">
                {journey.destination.name}
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              Complete Synchronized Door-to-Door Itinerary
            </span>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs sm:text-sm font-bold text-slate-900 bg-slate-100/80 px-3 py-1.5 rounded-xl border border-slate-200 self-start sm:self-auto">
            <span>{formatTime(journey.departureTime)}</span>
            <span className="text-slate-400 font-normal">to</span>
            <span>{formatTime(journey.arrivalTime)}</span>
            <span className="text-slate-300">|</span>
            <span className="text-blue-700">{formatDuration(journey.totalDurationMinutes)}</span>
          </div>
        </div>

        {/* 3. True Multi-Modal Synchronized Timeline */}
        <div className="flex flex-col gap-2 p-3 sm:p-4 rounded-xl bg-slate-50/80 border border-slate-200/80">
          <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-slate-500 font-mono pb-1">
            <span>Synchronized Journey Legs</span>
            <span>
              {journey.segments.length} Legs · {journey.totalTransfers} Transfers
            </span>
          </div>

          {/* Sequential Ordered Segments */}
          <div className="flex flex-col gap-1.5">
            {journey.segments.map((seg, idx) => {
              const transferSceneId =
                idx < journey.segments.length - 1
                  ? matchXRSceneForHub(seg.destination.name)
                  : null;

              return (
                <React.Fragment key={seg.segmentId || idx}>
                  {/* Segment Row */}
                  <div className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-white border border-slate-200/90 shadow-2xs">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 rounded-lg bg-slate-100 text-slate-700 shrink-0">
                        <ModeIcon mode={seg.mode} className="w-4 h-4" />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900 truncate">
                          <span>{seg.provider}</span>
                          {seg.vehicleNumber && (
                            <span className="text-[10px] font-mono text-slate-500">
                              ({seg.vehicleNumber})
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-600 truncate">
                          <span>{seg.origin.name}</span>
                          <span className="text-slate-400 mx-1">→</span>
                          <span className="font-medium text-slate-900">
                            {seg.destination.name}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col items-end shrink-0">
                      <span className="text-xs font-extrabold text-slate-900 font-mono">
                        {formatCurrency(seg.price, journey.currency)}
                      </span>
                      <span className="text-[11px] text-slate-500 font-mono">
                        {formatDuration(seg.durationMinutes)} · {formatTime(seg.departureTime)} - {formatTime(seg.arrivalTime)}
                      </span>
                    </div>
                  </div>

                  {/* Explicit Transfer Node between segments */}
                  {idx < journey.segments.length - 1 && (
                    <div className="flex items-center gap-2 pl-2 sm:pl-4 py-0.5 text-xs text-amber-900 min-w-0 max-w-full">
                      <div className="w-0.5 h-6 bg-amber-300 ml-2 sm:ml-3 shrink-0" />
                      <div className="inline-flex items-center flex-wrap gap-1.5 px-3 py-1 rounded-xl sm:rounded-full bg-amber-50 border border-amber-200/80 text-[11px] font-mono font-medium shadow-2xs max-w-full min-w-0">
                        <Clock className="w-3 h-3 text-amber-600 shrink-0" />
                        <span className="truncate">
                          <strong className="font-bold">
                            {seg.transferBufferMinutes || 15} min transfer
                          </strong>
                          <span className="text-amber-500 mx-1.5">·</span>
                          Change at <span className="font-semibold text-slate-800">{seg.destination.name}</span>
                        </span>
                        {transferSceneId && (
                          <Link
                            to={`/xr/${transferSceneId}`}
                            className="inline-flex items-center gap-1 ml-auto text-[10px] font-bold text-blue-700 bg-blue-100 hover:bg-blue-200 px-2 py-0.5 rounded-full transition-colors"
                            title="Explore Intermodal Station Concourse in 360°"
                          >
                            <Compass className="w-2.5 h-2.5 text-blue-600" />
                            <span>360° AR Guide</span>
                          </Link>
                        )}
                      </div>
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* 4. AI Recommendation Explanation Banner with Traceable Deterministic Decision Factors */}
        <div className="p-3.5 rounded-xl bg-blue-50/70 border border-blue-100 text-xs text-slate-700 leading-relaxed flex flex-col gap-2">
          <div className="flex items-start gap-2.5">
            <Sparkles className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
            <div className="flex flex-col gap-0.5">
              <span className="font-bold text-slate-900">
                {journey.optimization?.explanation?.headline || journey.aiExplanation.rankReason}
              </span>
              <span className="text-slate-600">{journey.aiExplanation.summary}</span>
            </div>
          </div>

          {/* Traceable Deterministic Decision Factors */}
          {journey.optimization?.explanation && (journey.optimization.explanation.reasons.length > 0 || journey.optimization.explanation.tradeoffs.length > 0) && (
            <div className="pl-6 pt-1.5 flex flex-wrap gap-1.5 border-t border-blue-100/80">
              {journey.optimization.explanation.reasons.map((reason, rIdx) => (
                <span
                  key={`r-${rIdx}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-blue-200/80 text-[11px] font-mono text-slate-700 font-medium"
                >
                  <span className="text-blue-600 font-bold">✓</span> {reason}
                </span>
              ))}
              {journey.optimization.explanation.tradeoffs.map((tradeoff, tIdx) => (
                <span
                  key={`t-${tIdx}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 border border-amber-200 text-[11px] font-mono text-amber-900 font-medium"
                >
                  <span className="text-amber-600 font-bold">⚖</span> {tradeoff}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 5. Bottom bar: Complete Journey Pricing, Carbon, Feasibility & Actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-3 border-t border-slate-100">
          <div className="flex items-center gap-4">
            <div className="flex flex-col">
              <span className="text-2xl font-extrabold font-display text-slate-900">
                {formatCurrency(journey.totalPrice, journey.currency)}
              </span>
              <span className="text-[11px] text-slate-500 font-medium">
                Total fare · All {journey.segments.length} segments combined
              </span>
            </div>

            <div className="h-8 w-px bg-slate-200 hidden sm:block" />

            {/* Environmental & hold telemetry */}
            <div className="flex flex-col gap-0.5 text-xs text-slate-600 font-mono">
              <div className="flex items-center gap-1.5 text-teal-700 font-semibold">
                <Leaf className="w-3.5 h-3.5 text-teal-600" />
                <span>{journey.carbonKg} kg CO₂</span>
                <span className="text-slate-300">·</span>
                <span className="text-slate-500">{journey.totalTransfers} Transfers</span>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-slate-500">
                <ShieldCheck className="w-3 h-3 text-emerald-600" />
                <span>Holdable (10m atomic reservation)</span>
              </div>
            </div>
          </div>

          {/* Action buttons: View Journey and Select Journey */}
          <div className="flex items-center gap-2.5 self-end sm:self-auto">
            <Link
              to={`/plan/${journey.id}`}
              className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-slate-900 font-semibold text-xs border border-slate-200 transition-colors shadow-2xs"
            >
              View Journey
            </Link>

            <button
              onClick={() => navigate(`/booking/${journey.id}`)}
              className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-md shadow-blue-600/20 transition-all flex items-center gap-1.5 active:scale-95 cursor-pointer"
            >
              <span>Select Journey</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default JourneyCard;
