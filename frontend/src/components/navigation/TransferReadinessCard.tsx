import React from 'react';
import {
  Clock,
  AlertTriangle,
  CheckCircle,
  HelpCircle,
  Compass,
  ArrowRight,
} from 'lucide-react';
import type { TransferReadiness } from '../../types/navigation';

interface TransferReadinessCardProps {
  readiness: TransferReadiness;
  className?: string;
}

export const TransferReadinessCard: React.FC<TransferReadinessCardProps> = ({
  readiness,
  className = '',
}) => {
  const {
    state,
    hubName,
    incomingMode,
    outgoingMode,
    availableBufferMinutes,
    requiredBufferMinutes,
    minutesUntilTransfer,
    stateTitle,
    stateDescription,
    badgeColor,
    isTimeEstimated,
  } = readiness;

  const colorStyles = {
    emerald: {
      bg: 'bg-emerald-50/80 border-emerald-200 text-emerald-900',
      badge: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      icon: <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />,
    },
    amber: {
      bg: 'bg-amber-50/80 border-amber-200 text-amber-900',
      badge: 'bg-amber-100 text-amber-800 border-amber-300',
      icon: <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />,
    },
    blue: {
      bg: 'bg-blue-50/80 border-blue-200 text-blue-900',
      badge: 'bg-blue-100 text-blue-800 border-blue-300',
      icon: <Compass className="w-4 h-4 text-blue-600 shrink-0" />,
    },
    rose: {
      bg: 'bg-rose-50/80 border-rose-200 text-rose-900',
      badge: 'bg-rose-100 text-rose-800 border-rose-300',
      icon: <Clock className="w-4 h-4 text-rose-600 shrink-0" />,
    },
    slate: {
      bg: 'bg-slate-50 border-slate-200 text-slate-800',
      badge: 'bg-slate-100 text-slate-700 border-slate-300',
      icon: <HelpCircle className="w-4 h-4 text-slate-500 shrink-0" />,
    },
  }[badgeColor];

  return (
    <div
      className={`p-4 rounded-2xl border shadow-xs flex flex-col gap-3 transition-all ${colorStyles.bg} ${className}`}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          {colorStyles.icon}
          <h4 className="text-xs font-bold uppercase tracking-wider font-mono">
            Transfer Readiness
          </h4>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-[10px] font-bold font-mono uppercase tracking-wider ${colorStyles.badge}`}
          >
            {state.replace('_', ' ')}
          </span>
          {isTimeEstimated && (
            <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 text-[9px] font-mono">
              Estimated Timestamps
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-900">
          <span className="capitalize">{incomingMode}</span>
          <ArrowRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="capitalize">{outgoingMode}</span>
          <span className="text-slate-400 font-normal">at</span>
          <span className="truncate">{hubName}</span>
        </div>

        <h5 className="text-sm font-bold leading-snug">{stateTitle}</h5>
        <p className="text-xs leading-relaxed opacity-90">{stateDescription}</p>
      </div>

      <div className="pt-2 border-t border-slate-200/60 flex items-center justify-between text-[11px] font-mono">
        <div className="flex items-center gap-1 text-slate-700">
          <Clock className="w-3 h-3 text-slate-400 shrink-0" />
          <span>Buffer: <strong>{availableBufferMinutes}m</strong> (req: {requiredBufferMinutes}m)</span>
        </div>

        {minutesUntilTransfer > 0 && (
          <span className="text-slate-600 font-semibold">
            In ~{minutesUntilTransfer}m
          </span>
        )}
      </div>
    </div>
  );
};

