import React from 'react';
import { Journey } from '../../types/journey';
import { Passenger } from '../../types/booking';
import { formatCurrency, formatDuration, formatTime } from '../../lib/utils';
import { ModeIcon } from '../common/ModeIcon';
import { ShieldCheck, AlertTriangle } from 'lucide-react';
import { ProvenanceBadge } from '../common/ProvenanceBadge';

interface BookingSummaryProps {
  journey: Journey;
  passengers: Passenger[];
}

export const BookingSummary: React.FC<BookingSummaryProps> = ({ journey, passengers }) => {
  const paxCount = Math.max(passengers.length, 1);
  const basePrice = journey.totalPrice * paxCount;
  const taxesAndFees = Math.round(basePrice * 0.05); // 5% GST
  const finalTotal = basePrice + taxesAndFees;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-col gap-4 shadow-sm">
      <div className="border-b border-slate-100 pb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900 font-display">
            Synchronized Journey Summary
          </h3>
          <span className="text-xs text-slate-500 font-mono">
            {journey.origin.name} → {journey.destination.name} ({formatDuration(journey.totalDurationMinutes)} · {journey.segments.length} Legs)
          </span>
        </div>
        <ProvenanceBadge
          sourceType={journey.provenance?.overallSourceType || 'deterministic_estimate'}
          isFullyConfirmed={journey.provenance?.isFullyConfirmed}
          size="xs"
        />
      </div>

      {/* Sandbox Simulation Notice if inventory is not real/confirmed */}
      {(!journey.provenance?.isFullyConfirmed || journey.segments.some((s) => s.availability.isRealInventory === false)) && (
        <div className="p-3 rounded-xl bg-amber-50/90 border border-amber-200 text-xs text-amber-950 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <span className="font-bold">Sandbox Reservation Simulation</span>
            <span className="leading-relaxed text-slate-700">
              This journey uses simulated carrier inventory and deterministic fare estimates.
              Holds created in this demo reserve simulated seats in the demonstration database and cannot be used for real-world travel.
            </span>
          </div>
        </div>
      )}

      {/* Segments mini-list */}
      <div className="flex flex-col gap-2.5">
        {journey.segments.map((seg) => (
          <div
            key={seg.segmentId}
            className="flex items-center justify-between text-xs p-2.5 rounded-xl bg-slate-50 border border-slate-200/80"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <ModeIcon mode={seg.mode} size={15} />
              <div className="flex flex-col min-w-0">
                <span className="font-bold text-slate-800 truncate">
                  {seg.provider}
                </span>
                <span className="text-[11px] text-slate-600 truncate">
                  {seg.origin.name} → {seg.destination.name}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {formatTime(seg.departureTime)} - {formatTime(seg.arrivalTime)} · {formatDuration(seg.durationMinutes)}
                </span>
              </div>
            </div>

            <span className="font-mono text-slate-900 font-bold shrink-0 ml-2">
              {formatCurrency(seg.price * paxCount, seg.currency)}
            </span>
          </div>
        ))}
      </div>

      {/* Price breakdown */}
      <div className="pt-3 border-t border-slate-100 flex flex-col gap-1.5 text-xs">
        <div className="flex items-center justify-between text-slate-600">
          <span>
            Base Transit Fare ({paxCount} traveler{paxCount > 1 ? 's' : ''}){' '}
            <span className="text-[11px] font-mono text-slate-400">
              {journey.provenance?.overallSourceType === 'provider_live' ? '(Live Quote)' : '(Corridor Est.)'}
            </span>
          </span>
          <span className="font-mono font-medium text-slate-800">
            {formatCurrency(basePrice, journey.currency)}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-600">
          <span>Statutory GST & Intermodal Surcharge (5%)</span>
          <span className="font-mono font-medium text-slate-800">
            {formatCurrency(taxesAndFees, journey.currency)}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-600">
          <span>Hold Locking & Compensation Guarantee</span>
          <span className="font-mono text-emerald-700 font-bold">FREE (₹0)</span>
        </div>

        <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-base font-bold text-slate-900">
          <div className="flex flex-col">
            <span>Total Payable</span>
            <span className="text-[11px] font-mono font-normal text-slate-500">
              {journey.provenance?.overallSourceType === 'provider_live' ? 'Confirmed carrier total' : 'Estimated total fare'}
            </span>
          </div>
          <span className="font-display font-extrabold text-2xl text-blue-700">
            {formatCurrency(finalTotal, journey.currency)}
          </span>
        </div>
      </div>

      {/* Invariant guarantee callout */}
      <div className="p-3 rounded-xl bg-blue-50/80 border border-blue-200/80 flex items-start gap-2.5 text-xs text-blue-900">
        <ShieldCheck className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <p className="leading-relaxed">
          KogniSync orchestrates sagas with automatic line-item compensation. If any segment fails confirmation, all held seats are immediately released without penalty.
        </p>
      </div>
    </div>
  );
};
