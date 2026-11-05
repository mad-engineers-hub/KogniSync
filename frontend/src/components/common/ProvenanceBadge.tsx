import React from 'react';
import { Activity, Layers, Calculator, FlaskConical, HelpCircle, CheckCircle2, AlertTriangle } from 'lucide-react';
import { ProvenanceSourceType } from '../../types/journey';
import { cn } from '../../lib/utils';

export type OverallProvenanceType =
  | ProvenanceSourceType
  | 'mixed';

interface ProvenanceBadgeProps {
  sourceType?: OverallProvenanceType;
  isFullyConfirmed?: boolean;
  className?: string;
  size?: 'xs' | 'sm' | 'md';
  showDetails?: boolean;
}

export const ProvenanceBadge: React.FC<ProvenanceBadgeProps> = ({
  sourceType = 'deterministic_estimate',
  isFullyConfirmed = false,
  className,
  size = 'sm',
  showDetails = false,
}) => {
  const getConfig = () => {
    switch (sourceType) {
      case 'provider_live':
        return {
          label: isFullyConfirmed ? 'Live Confirmed' : 'Live Partner Feed',
          icon: isFullyConfirmed ? (
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
          ) : (
            <Activity className="w-3 h-3 text-emerald-600" />
          ),
          classes: 'bg-emerald-50 text-emerald-800 border-emerald-300',
          title: 'Directly verified from live partner API / real-time carrier feed.',
        };
      case 'mixed':
        return {
          label: 'Mixed Data (Live + Est.)',
          icon: <Layers className="w-3 h-3 text-indigo-600" />,
          classes: 'bg-indigo-50 text-indigo-800 border-indigo-200',
          title: 'Contains both real-time provider data and deterministic corridor estimates.',
        };
      case 'simulated':
        return {
          label: 'Simulated Demo Data',
          icon: <FlaskConical className="w-3 h-3 text-amber-600" />,
          classes: 'bg-amber-50 text-amber-800 border-amber-200',
          title: 'Simulated demonstration data; unverified live inventory.',
        };
      case 'unknown':
        return {
          label: 'Unverified Data',
          icon: <HelpCircle className="w-3 h-3 text-slate-500" />,
          classes: 'bg-slate-100 text-slate-700 border-slate-300',
          title: 'Unverified attributes with unknown provenance.',
        };
      case 'deterministic_estimate':
      default:
        return {
          label: 'Modeled Estimate',
          icon: <Calculator className="w-3 h-3 text-sky-600" />,
          classes: 'bg-sky-50 text-sky-800 border-sky-200',
          title: 'Mathematically estimated via corridor models, distance curves, and scheduled timetables.',
        };
    }
  };

  const config = getConfig();

  const sizeClasses = {
    xs: 'text-[9px] px-1.5 py-0.5 gap-1 font-semibold',
    sm: 'text-[10px] px-2 py-0.5 gap-1.5 font-bold font-mono',
    md: 'text-xs px-2.5 py-1 gap-1.5 font-semibold font-mono',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border transition-colors shadow-2xs',
        config.classes,
        sizeClasses[size],
        className
      )}
      title={config.title}
      aria-label={`Data provenance: ${config.label}`}
    >
      {config.icon}
      <span>{config.label}</span>
      {showDetails && (
        <span className="text-[9px] font-normal opacity-80 border-l border-current pl-1 ml-0.5">
          {isFullyConfirmed ? 'Locked' : 'Unconfirmed'}
        </span>
      )}
    </span>
  );
};

interface AttributeProvenanceTagProps {
  attributeName: string;
  sourceType?: ProvenanceSourceType;
  isEstimate?: boolean;
  providerName?: string;
  className?: string;
}

export const AttributeProvenanceTag: React.FC<AttributeProvenanceTagProps> = ({
  attributeName,
  sourceType = 'deterministic_estimate',
  isEstimate = true,
  providerName,
  className,
}) => {
  const isLive = sourceType === 'provider_live' && !isEstimate;
  const isSimulated = sourceType === 'simulated';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded-md border',
        isLive
          ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
          : isSimulated
          ? 'bg-amber-50 text-amber-800 border-amber-200'
          : 'bg-slate-50 text-slate-700 border-slate-200',
        className
      )}
      title={
        isLive
          ? `${attributeName} is live provider data${providerName ? ` from ${providerName}` : ''}.`
          : isSimulated
          ? `${attributeName} is simulated demo data.`
          : `${attributeName} is a deterministic corridor estimate.`
      }
    >
      <span className="font-semibold capitalize">{attributeName}:</span>
      <span>{isLive ? 'Live' : isSimulated ? 'Simulated' : 'Est.'}</span>
    </span>
  );
};

export const SimulatedInventoryWarning: React.FC<{ className?: string }> = ({ className }) => (
  <div
    className={cn(
      'flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-50 border border-amber-200/90 text-amber-900 text-[11px] font-mono',
      className
    )}
    title="Simulated inventory: seats/units are demonstration capacity and not a real-world carrier lock."
  >
    <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
    <span>Demo Capacity · Unverified Live Inventory</span>
  </div>
);
