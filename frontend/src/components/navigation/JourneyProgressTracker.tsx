import React, { useState } from 'react';
import {
  CheckCircle2,
  RotateCcw,
  ChevronRight,
  Smartphone,
  AlertTriangle,
} from 'lucide-react';
import type { JourneySegment } from '../../types/journey';

interface JourneyProgressTrackerProps {
  segments: JourneySegment[];
  activeSegmentIndex: number;
  completedSegmentIds: string[];
  overallProgressPercent: number;
  onSelectSegment: (index: number) => void;
  onCompleteActiveSegment: () => void;
  onUndoSegment: (segmentId: string) => void;
  onAdvanceNext: () => void;
  onResetProgress: () => void;
  className?: string;
}

export const JourneyProgressTracker: React.FC<JourneyProgressTrackerProps> = ({
  segments,
  activeSegmentIndex,
  completedSegmentIds,
  overallProgressPercent,
  onSelectSegment,
  onCompleteActiveSegment,
  onUndoSegment,
  onAdvanceNext,
  onResetProgress,
  className = '',
}) => {
  const [showResetConfirm, setShowResetConfirm] = useState<boolean>(false);
  const total = segments.length;
  const activeSegment = segments[activeSegmentIndex];
  const isCurrentCompleted = activeSegment && completedSegmentIds.includes(activeSegment.segmentId);

  return (
    <div className={`p-4 sm:p-5 rounded-2xl border border-slate-200 bg-white shadow-xs flex flex-col gap-4 ${className}`}>
      {/* Top Header & Percentage */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <h4 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-800">
            Journey Progress
          </h4>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-bold font-mono text-slate-900">
            {overallProgressPercent}% Complete
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[9px] font-mono border border-slate-200">
            <Smartphone className="w-2.5 h-2.5 text-slate-500" />
            Device-Local
          </span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden border border-slate-200/60">
        <div
          className="bg-emerald-600 h-full rounded-full transition-all duration-300"
          style={{ width: `${overallProgressPercent}%` }}
        />
      </div>

      {/* Segment Pills Trail */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        {segments.map((seg, idx) => {
          const isCompleted = completedSegmentIds.includes(seg.segmentId);
          const isActive = idx === activeSegmentIndex;

          return (
            <button
              key={seg.segmentId}
              type="button"
              onClick={() => onSelectSegment(idx)}
              aria-label={`Select leg ${idx + 1}: ${seg.mode} to ${seg.destination.name}`}
              className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition-all shrink-0 flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? 'bg-blue-600 text-white shadow-sm ring-2 ring-blue-400/40'
                  : isCompleted
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-300'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200/80'
              }`}
            >
              {isCompleted ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <span className="w-3.5 h-3.5 rounded-full bg-slate-300 text-slate-700 text-[9px] flex items-center justify-center">
                  {idx + 1}
                </span>
              )}
              <span className="capitalize">{seg.mode}</span>
            </button>
          );
        })}
      </div>

      {/* Interactive Controls */}
      <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          {isCurrentCompleted ? (
            <button
              type="button"
              onClick={() => activeSegment && onUndoSegment(activeSegment.segmentId)}
              className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-mono font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span>Undo Leg {activeSegmentIndex + 1}</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onCompleteActiveSegment}
              className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-mono font-bold flex items-center gap-1.5 shadow-xs transition-all active:scale-98 cursor-pointer"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Mark Leg Complete</span>
            </button>
          )}

          {activeSegmentIndex < total - 1 && (
            <button
              type="button"
              onClick={onAdvanceNext}
              className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-mono font-medium flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span>Next Leg</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            </button>
          )}
        </div>

        {/* Reset Confirmation State */}
        {showResetConfirm ? (
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-rose-50 border border-rose-200">
            <AlertTriangle className="w-3.5 h-3.5 text-rose-600 ml-1.5" />
            <span className="text-[10px] text-rose-800 font-mono font-bold">Reset all?</span>
            <button
              type="button"
              onClick={() => {
                onResetProgress();
                setShowResetConfirm(false);
              }}
              className="px-2 py-0.5 rounded-lg bg-rose-600 text-white text-[10px] font-mono font-bold cursor-pointer"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={() => setShowResetConfirm(false)}
              className="px-2 py-0.5 rounded-lg bg-slate-200 text-slate-700 text-[10px] font-mono cursor-pointer"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowResetConfirm(true)}
            aria-label="Reset journey progress"
            className="text-[11px] font-mono text-slate-400 hover:text-slate-600 transition-colors cursor-pointer underline"
          >
            Reset Progress
          </button>
        )}
      </div>
    </div>
  );
};

