/**
 * frontend/src/components/disruption/DemoDisruptionController.tsx
 *
 * Interactive Disruption Demo Controller (Milestone M3.7).
 * Enables one-click testing of repeatable disruption scenarios with explicit simulation labels.
 */
import React from 'react';
import { Sparkles, XCircle, AlertOctagon, Car } from 'lucide-react';

interface DemoDisruptionControllerProps {
  activeScenario: string | null;
  onSelectScenario: (scenario: string | null) => void;
  isLoading?: boolean;
}

export const DemoDisruptionController: React.FC<DemoDisruptionControllerProps> = ({
  activeScenario,
  onSelectScenario,
  isLoading = false,
}) => {
  return (
    <div className="p-4 sm:p-5 rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50/70 via-white to-slate-50 shadow-xs flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-indigo-950">
          <div className="p-1.5 rounded-lg bg-indigo-600 text-white shadow-2xs">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold font-mono tracking-wider uppercase">
            Disruption Simulator (M3.7 Demo Mode)
          </span>
        </div>

        <span className="px-2 py-0.5 rounded-full bg-slate-900 text-amber-300 text-[10px] font-bold font-mono">
          SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA
        </span>
      </div>

      <p className="text-xs text-slate-600 leading-relaxed font-medium">
        Inject deterministic road or traffic incidents along journey corridors to evaluate KogniSync's real-time impact assessment, connection risk calculation, and Pareto recovery recommendations.
      </p>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          onClick={() => onSelectScenario(activeScenario === 'shiradi_ghat' ? null : 'shiradi_ghat')}
          disabled={isLoading}
          className={`px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all cursor-pointer shadow-2xs ${
            activeScenario === 'shiradi_ghat'
              ? 'bg-rose-600 text-white ring-2 ring-rose-400'
              : 'bg-white border border-rose-200 text-rose-800 hover:bg-rose-50'
          }`}
        >
          <AlertOctagon className="w-3.5 h-3.5" />
          <span>NH-75 Shiradi Ghat Landslide</span>
        </button>

        <button
          onClick={() => onSelectScenario(activeScenario === 'silk_board' ? null : 'silk_board')}
          disabled={isLoading}
          className={`px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all cursor-pointer shadow-2xs ${
            activeScenario === 'silk_board'
              ? 'bg-amber-600 text-white ring-2 ring-amber-400'
              : 'bg-white border border-amber-200 text-amber-800 hover:bg-amber-50'
          }`}
        >
          <Car className="w-3.5 h-3.5" />
          <span>Silk Board ORR Congestion</span>
        </button>

        {activeScenario && (
          <button
            onClick={() => onSelectScenario(null)}
            disabled={isLoading}
            className="px-3 py-2 rounded-xl text-xs font-bold bg-white border border-slate-300 text-slate-700 hover:bg-slate-100 flex items-center gap-1.5 transition-colors cursor-pointer shadow-2xs"
          >
            <XCircle className="w-3.5 h-3.5 text-slate-500" />
            <span>Clear Scenario (Normal Route)</span>
          </button>
        )}
      </div>
    </div>
  );
};

