import React, { useState } from 'react';
import {
  Navigation,
  ArrowUp,
  ArrowLeft,
  ArrowRight,
  ArrowUpLeft,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Footprints,
  Compass,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import { ARWayfindingCase, ARWayfindingStep } from '../../types/xr';

interface ARWayfindingPanelProps {
  wayfindingCases: ARWayfindingCase[];
  selectedCaseId?: string;
  onSelectCase?: (caseId: string) => void;
  onClose?: () => void;
}

export const ARWayfindingPanel: React.FC<ARWayfindingPanelProps> = ({
  wayfindingCases,
  selectedCaseId,
  onSelectCase,
  onClose,
}) => {
  const [activeStepIndex, setActiveStepIndex] = useState(0);

  if (!wayfindingCases || wayfindingCases.length === 0) {
    return null;
  }

  const activeCase =
    wayfindingCases.find((c) => c.wayfinding_id === selectedCaseId) || wayfindingCases[0];

  const getDirectionIcon = (direction: ARWayfindingStep['turn_direction']) => {
    switch (direction) {
      case 'left':
        return <ArrowLeft className="w-4 h-4 text-blue-400" />;
      case 'right':
        return <ArrowRight className="w-4 h-4 text-blue-400" />;
      case 'slight_left':
        return <ArrowUpLeft className="w-4 h-4 text-cyan-400" />;
      case 'slight_right':
        return <ArrowUpRight className="w-4 h-4 text-cyan-400" />;
      case 'arrival':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
      default:
        return <ArrowUp className="w-4 h-4 text-blue-400" />;
    }
  };

  const totalDistance = activeCase.steps.reduce((acc, step) => acc + step.distance_meters, 0);

  return (
    <div className="w-full rounded-2xl bg-slate-900/95 text-white backdrop-blur-xl border border-slate-700/80 p-4 sm:p-5 flex flex-col gap-4 shadow-xl">
      {/* Route Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30">
            <Compass className="w-5 h-5 animate-spin-slow" />
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-blue-400">
              Intermodal AR Wayfinding
            </div>
            <h3 className="text-sm sm:text-base font-bold text-white">
              {activeCase.origin_title} → {activeCase.destination_title}
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs text-slate-300 font-mono">
          <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <strong>{activeCase.estimated_walking_minutes} min</strong> walk
          </span>
          <span className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700">
            <Footprints className="w-3.5 h-3.5 text-emerald-400" />
            <strong>{totalDistance} m</strong>
          </span>
        </div>
      </div>

      {/* Alternative routes selector if multiple */}
      {wayfindingCases.length > 1 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {wayfindingCases.map((c) => (
            <button
              key={c.wayfinding_id}
              type="button"
              onClick={() => {
                onSelectCase?.(c.wayfinding_id);
                setActiveStepIndex(0);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors border ${
                c.wayfinding_id === activeCase.wayfinding_id
                  ? 'bg-blue-600 border-blue-500 text-white shadow-sm'
                  : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-700'
              }`}
            >
              To {c.destination_title}
            </button>
          ))}
        </div>
      )}

      {/* Active Step Hero View */}
      {activeCase.steps[activeStepIndex] && (
        <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/70 to-slate-800/80 border border-blue-500/40 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="p-3 rounded-2xl bg-blue-600 text-white shadow-lg">
              {getDirectionIcon(activeCase.steps[activeStepIndex].turn_direction)}
            </div>
            <div>
              <div className="text-[11px] font-mono text-blue-300 uppercase font-semibold">
                Step {activeStepIndex + 1} of {activeCase.steps.length} · {activeCase.steps[activeStepIndex].distance_meters}m
              </div>
              <div className="text-sm sm:text-base font-bold text-white mt-0.5">
                {activeCase.steps[activeStepIndex].instruction}
              </div>
              <div className="text-xs text-slate-300 mt-1 flex items-center gap-1.5">
                <span className="text-slate-400">Landmark:</span>
                <span className="font-semibold text-amber-300">
                  {activeCase.steps[activeStepIndex].target_landmark}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              disabled={activeStepIndex === 0}
              onClick={() => setActiveStepIndex((prev) => Math.max(0, prev - 1))}
              className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold border border-slate-700"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={activeStepIndex === activeCase.steps.length - 1}
              onClick={() =>
                setActiveStepIndex((prev) => Math.min(activeCase.steps.length - 1, prev + 1))
              }
              className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold text-white shadow-sm"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Step List Timeline */}
      <div className="flex flex-col gap-2 max-h-56 overflow-y-auto pr-1">
        {activeCase.steps.map((step, idx) => {
          const isCurrent = idx === activeStepIndex;
          const isDone = idx < activeStepIndex;
          return (
            <div
              key={step.step_number}
              onClick={() => setActiveStepIndex(idx)}
              className={`flex items-start gap-3 p-2.5 rounded-xl transition-all cursor-pointer border ${
                isCurrent
                  ? 'bg-blue-900/40 border-blue-500/60 shadow-sm'
                  : 'bg-slate-800/40 border-slate-800/80 hover:bg-slate-800/70 text-slate-300'
              }`}
            >
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 font-bold text-xs mt-0.5 ${
                  isDone
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                    : isCurrent
                    ? 'bg-blue-600 text-white font-mono'
                    : 'bg-slate-700 text-slate-400'
                }`}
              >
                {isDone ? '✓' : step.step_number}
              </div>

              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold leading-snug text-white">
                  {step.instruction}
                </div>
                <div className="text-[11px] text-slate-400 flex items-center gap-2 mt-0.5">
                  <span>{step.distance_meters} meters</span>
                  <span>·</span>
                  <span className="truncate text-slate-300">Target: {step.target_landmark}</span>
                </div>
              </div>

              <div className="shrink-0 pt-1">{getDirectionIcon(step.turn_direction)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
