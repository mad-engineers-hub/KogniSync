import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Clock, ArrowRight, ShieldCheck, Sparkles, Leaf, ArrowDown } from 'lucide-react';
import { Journey } from '../../types/journey';
import { ModeIcon } from '../common/ModeIcon';
import { OptimizationBadge } from '../common/OptimizationBadge';
import { formatCurrency, formatDuration, formatTime } from '../../lib/utils';

interface JourneyCardProps {
  journey: Journey;
  isFeatured?: boolean;
}

export const JourneyCard: React.FC<JourneyCardProps> = ({ journey, isFeatured = false }) => {
  const navigate = useNavigate();

  return (
    <div
      className={`rounded-2xl border transition-all duration-200 overflow-hidden ${
        isFeatured
          ? 'bg-white border-blue-500 shadow-md ring-1 ring-blue-500/20'
          : 'bg-white hover:bg-slate-50/50 border-slate-200 hover:border-slate-300 shadow-sm'
      }`}
    >
      {/* 1. Top Banner: Recommendation category badge, title & AI match score */}
      <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/80 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <OptimizationBadge category={journey.recommendationCategory} size="sm" />
          <span className="text-xs font-bold text-slate-800 truncate font-display">
            {journey.title}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1 text-[11px] font-mono text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200 font-semibold shadow-2xs">
            <Sparkles className="w-3 h-3 text-blue-600" />
            <span>Score: {journey.aiExplanation.score}/100</span>
          </div>
        </div>
      </div>

      <div className="p-5 flex flex-col gap-4">
        {/* 2. Overall Journey Origin & Destination Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
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
            <span>{journey.segments.length} Legs · {journey.totalTransfers} Transfers</span>
          </div>

          <div className="flex flex-col gap-1.5">
            {journey.segments.map((seg, idx) => (
              <React.Fragment key={seg.segmentId}>
                {/* Individual Segment Card */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 p-3 rounded-xl bg-white border border-slate-200/80 shadow-2xs hover:border-blue-300 transition-colors">
                  <div className="flex items-start sm:items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-blue-50/80 border border-blue-200/60 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0 text-blue-700">
                      <ModeIcon mode={seg.mode} size={16} />
                    </div>

                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900 truncate">
                          {seg.provider}
                        </span>
                        {seg.vehicleNumber && (
                          <span className="text-[10px] font-mono text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded border border-slate-200">
                            {seg.vehicleNumber}
                          </span>
                        )}
                        {seg.seatClass && (
                          <span className="text-[10px] text-blue-700 font-medium">
                            {seg.seatClass}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 text-xs text-slate-600 truncate mt-0.5">
                        <span className="font-semibold text-slate-800">{seg.origin.name}</span>
                        <span className="text-slate-400">→</span>
                        <span className="font-semibold text-slate-800">{seg.destination.name}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-center border-t sm:border-t-0 pt-2 sm:pt-0 border-slate-100 shrink-0">
                    <span className="text-xs sm:text-sm font-bold font-mono text-slate-900">
                      {formatCurrency(seg.price, seg.currency)}
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
                        <strong className="font-bold">{seg.transferBufferMinutes || 15} min transfer</strong>
                        <span className="text-amber-500 mx-1.5">·</span>
                        Change at <span className="font-semibold text-slate-800">{seg.destination.name}</span>
                      </span>
                    </div>
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* 4. AI Recommendation Explanation Banner */}
        <div className="p-3 rounded-xl bg-blue-50/70 border border-blue-100 text-xs text-slate-700 leading-relaxed flex items-start gap-2.5">
          <Sparkles className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <span className="font-bold text-slate-900">
              {journey.aiExplanation.rankReason}
            </span>
            <span className="text-slate-600">{journey.aiExplanation.summary}</span>
          </div>
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