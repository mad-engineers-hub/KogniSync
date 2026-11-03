import React from 'react';
import { Sparkles, TrendingDown, Clock, CheckCircle2, Sliders, ShieldCheck } from 'lucide-react';
import { Journey } from '../../types/journey';
import { formatCurrency, formatDuration } from '../../lib/utils';

interface AIRecommendationExplanationProps {
  journey: Journey;
}

export const AIRecommendationExplanation: React.FC<AIRecommendationExplanationProps> = ({
  journey,
}) => {
  const { aiExplanation, optimization } = journey;

  return (
    <div className="rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50/60 via-white to-slate-50 p-5 shadow-sm flex flex-col gap-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-blue-100 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-blue-100 text-blue-700">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-900 font-display">
              Explainable Journey Optimization
            </h4>
            <span className="text-[11px] text-slate-500">
              Evaluated against multi-objective Pareto trade-off criteria
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {journey.isParetoOptimal && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs font-mono font-bold">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              Pareto Optimal
            </span>
          )}
          <div className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-100/80 border border-blue-200 text-xs font-mono font-bold text-blue-800">
            <span>Match Score: {aiExplanation.score}/100</span>
          </div>
        </div>
      </div>

      {/* Primary rank reasoning headline */}
      <div className="text-sm font-bold text-blue-900 leading-snug">
        {optimization?.explanation?.headline || aiExplanation.rankReason}
      </div>

      <p className="text-xs text-slate-700 leading-relaxed">
        {aiExplanation.summary}
      </p>

      {/* Objective Score Breakdown (Deterministic Mathematical Proof) */}
      {optimization?.scoreBreakdown && (
        <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-2xs flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs font-bold text-slate-800 border-b border-slate-100 pb-2">
            <span className="flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-blue-600" />
              Objective Score Contribution Matrix
            </span>
            <span className="text-[11px] font-mono text-slate-500 font-normal">
              Linear Convex Optimization: ∑(Norm × Weight)
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {/* Cost */}
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <span>Cost</span>
                <span className="font-bold text-slate-700">
                  {Math.round(optimization.scoreBreakdown.cost.weight * 100)}% wt
                </span>
              </div>
              <span className="text-xs font-bold text-slate-900 font-mono">
                {formatCurrency(optimization.metrics.totalCost, journey.currency)}
              </span>
              <div className="w-full bg-slate-200 h-1 rounded-full overflow-hidden">
                <div
                  className="bg-emerald-600 h-full rounded-full"
                  style={{ width: `${Math.round(optimization.scoreBreakdown.cost.normalized * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-emerald-700 font-mono font-semibold">
                +{Math.round(optimization.scoreBreakdown.cost.contribution * 100)} pts
              </span>
            </div>

            {/* Duration */}
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <span>Duration</span>
                <span className="font-bold text-slate-700">
                  {Math.round(optimization.scoreBreakdown.duration.weight * 100)}% wt
                </span>
              </div>
              <span className="text-xs font-bold text-slate-900 font-mono">
                {formatDuration(optimization.metrics.durationMinutes)}
              </span>
              <div className="w-full bg-slate-200 h-1 rounded-full overflow-hidden">
                <div
                  className="bg-blue-600 h-full rounded-full"
                  style={{ width: `${Math.round(optimization.scoreBreakdown.duration.normalized * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-blue-700 font-mono font-semibold">
                +{Math.round(optimization.scoreBreakdown.duration.contribution * 100)} pts
              </span>
            </div>

            {/* Comfort */}
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <span>Comfort</span>
                <span className="font-bold text-slate-700">
                  {Math.round(optimization.scoreBreakdown.comfort.weight * 100)}% wt
                </span>
              </div>
              <span className="text-xs font-bold text-slate-900 font-mono">
                {Math.round(optimization.metrics.comfortScore * 100)}% index
              </span>
              <div className="w-full bg-slate-200 h-1 rounded-full overflow-hidden">
                <div
                  className="bg-purple-600 h-full rounded-full"
                  style={{ width: `${Math.round(optimization.scoreBreakdown.comfort.normalized * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-purple-700 font-mono font-semibold">
                +{Math.round(optimization.scoreBreakdown.comfort.contribution * 100)} pts
              </span>
            </div>

            {/* Carbon */}
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex flex-col gap-1">
              <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <span>Carbon</span>
                <span className="font-bold text-slate-700">
                  {Math.round(optimization.scoreBreakdown.carbon.weight * 100)}% wt
                </span>
              </div>
              <span className="text-xs font-bold text-teal-800 font-mono">
                {optimization.metrics.carbonKg} kg CO₂
              </span>
              <div className="w-full bg-slate-200 h-1 rounded-full overflow-hidden">
                <div
                  className="bg-teal-600 h-full rounded-full"
                  style={{ width: `${Math.round(optimization.scoreBreakdown.carbon.normalized * 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-teal-700 font-mono font-semibold">
                +{Math.round(optimization.scoreBreakdown.carbon.contribution * 100)} pts
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Trade-off Callouts */}
      {aiExplanation.costVsFastestSaving !== undefined && aiExplanation.costVsFastestSaving > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 py-1">
          <div className="p-3 rounded-xl bg-white border border-emerald-200 flex items-center gap-3 shadow-2xs">
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-700">
              <TrendingDown className="w-4 h-4" />
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-slate-500 font-medium">Cost Savings</span>
              <span className="text-sm font-bold font-mono text-emerald-800">
                Saves {formatCurrency(aiExplanation.costVsFastestSaving, journey.currency)}
              </span>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-white border border-slate-200 flex items-center gap-3 shadow-2xs">
            <div className="p-2 rounded-lg bg-slate-100 text-slate-700">
              <Clock className="w-4 h-4" />
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-slate-500 font-medium">Time Difference vs Air Transit</span>
              <span className="text-sm font-bold font-mono text-slate-800">
                +{Math.round((aiExplanation.durationDiffMinutes || 0) / 60)}h{' '}
                {(aiExplanation.durationDiffMinutes || 0) % 60}m
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Deterministic Reasons & Trade-off Invariants */}
      <div className="flex flex-col gap-2 pt-2 border-t border-slate-100">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600 font-mono">
          Decision Factors & Trade-Offs:
        </span>
        <div className="flex flex-col gap-1.5">
          {optimization?.explanation?.reasons.map((reason, idx) => (
            <div key={`rec-${idx}`} className="flex items-start gap-2 text-xs text-slate-800 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
              <span>{reason}</span>
            </div>
          ))}
          {optimization?.explanation?.tradeoffs.map((tradeoff, idx) => (
            <div key={`to-${idx}`} className="flex items-start gap-2 text-xs text-amber-900 bg-amber-50/60 px-2.5 py-1 rounded-lg border border-amber-200/60">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
              <span>{tradeoff}</span>
            </div>
          ))}
          {!optimization &&
            aiExplanation.tradeOffs.map((tradeOff, idx) => (
              <div key={idx} className="flex items-start gap-2 text-xs text-slate-700">
                <CheckCircle2 className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
                <span>{tradeOff}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
};
