/**
 * frontend/src/components/disruption/ProviderIntelligencePanel.tsx
 *
 * Operational Provider Intelligence & Freshness Monitoring Panel (Milestone M3.8).
 * Displays real-time operational status, supported modes, observation timestamps,
 * attribute provenance, and failure diagnostics for external data feeds
 * (TomTom Orbis Traffic v2, GTFS Realtime, Simulation Engine).
 */
import React, { useState, useEffect } from 'react';
import { getDisruptionProviders } from '../../api/disruptions';
import { DisruptionProviderCapability } from '../../types/disruption';

interface ProviderIntelligencePanelProps {
  onRefresh?: () => void;
  className?: string;
}

export const ProviderIntelligencePanel: React.FC<ProviderIntelligencePanelProps> = ({
  onRefresh,
  className = '',
}) => {
  const [providers, setProviders] = useState<DisruptionProviderCapability[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date>(new Date());
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const fetchCapabilities = async () => {
    try {
      setError(null);
      const caps = await getDisruptionProviders();
      setProviders(caps);
      setLastRefreshedAt(new Date());
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch provider health data.');
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchCapabilities();
  }, []);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await fetchCapabilities();
    if (onRefresh) onRefresh();
  };

  const getStatusBadge = (provider: DisruptionProviderCapability) => {
    const status = provider.connectivityStatus || (provider.isAvailable ? 'available' : 'unconfigured');

    switch (status) {
      case 'available':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
            ● AVAILABLE
          </span>
        );
      case 'rate_limited':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            ⚠ RATE LIMITED
          </span>
        );
      case 'degraded':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-orange-100 text-orange-800 border border-orange-300">
            ▲ DEGRADED
          </span>
        );
      case 'blocked':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-rose-100 text-rose-800 border border-rose-300">
            ✕ BLOCKED
          </span>
        );
      case 'unconfigured':
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-100 text-slate-700 border border-slate-300">
            ○ UNCONFIGURED
          </span>
        );
    }
  };

  const getProvenanceBadge = (prov: string) => {
    switch (prov) {
      case 'provider_live':
        return (
          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-blue-900 text-blue-200">
            LIVE PROVIDER DATA
          </span>
        );
      case 'simulated':
        return (
          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-amber-900 text-amber-200">
            SIMULATED FEED
          </span>
        );
      default:
        return (
          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
            ESTIMATED / NOT LIVE
          </span>
        );
    }
  };

  return (
    <div
      className={`bg-white border border-slate-200 rounded-lg shadow-sm text-slate-800 overflow-hidden ${className}`}
      data-testid="provider-intelligence-panel"
      role="region"
      aria-label="Provider Intelligence and Health Status"
    >
      {/* Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 rounded-full bg-blue-600 animate-pulse"></div>
          <span className="text-xs font-bold uppercase tracking-wider text-slate-700 font-mono">
            Provider Intelligence & Feeds
          </span>
          <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
            ({providers.length} registered)
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="inline-flex items-center px-2 py-1 text-[11px] font-medium text-slate-700 bg-white border border-slate-300 rounded hover:bg-slate-100 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-colors"
            aria-label="Refresh provider status"
          >
            {isRefreshing ? (
              <span className="inline-block animate-spin mr-1">⟳</span>
            ) : (
              <span className="mr-1">⟳</span>
            )}
            Refresh
          </button>

          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs font-medium text-blue-600 hover:text-blue-800 p-1 rounded focus:outline-none"
            aria-expanded={isExpanded}
            aria-label={isExpanded ? 'Collapse provider details' : 'Expand provider details'}
          >
            {isExpanded ? 'Hide Details ▲' : 'Details ▼'}
          </button>
        </div>
      </div>

      {/* Quick Summary Pill Bar */}
      <div className="px-3.5 py-2 bg-white flex flex-wrap gap-2 items-center text-xs border-b border-slate-100">
        {loading ? (
          <span className="text-slate-400 text-xs italic">Discovering registered adapters...</span>
        ) : error ? (
          <span className="text-rose-600 text-xs font-mono">{error}</span>
        ) : (
          providers.map((p) => (
            <div
              key={p.name}
              className="inline-flex items-center space-x-1.5 px-2 py-1 rounded bg-slate-50 border border-slate-200 text-[11px]"
            >
              <span className="font-semibold text-slate-800">{p.displayName}</span>
              {getStatusBadge(p)}
            </div>
          ))
        )}
      </div>

      {/* Expanded Diagnostics Drawer */}
      {isExpanded && (
        <div className="p-3.5 space-y-3 bg-slate-50 text-xs">
          <div className="text-[11px] text-slate-500 flex justify-between items-center">
            <span>Last checked: {lastRefreshedAt.toLocaleTimeString()}</span>
            <span className="font-mono text-[10px]">Zero Fabrication Invariant Enforced</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {providers.map((p) => (
              <div
                key={p.name}
                className="bg-white p-3 rounded border border-slate-200 shadow-2xs space-y-2"
                data-testid={`provider-card-${p.name}`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-bold text-slate-900 text-sm">{p.displayName}</div>
                    <div className="text-[10px] font-mono text-slate-500 uppercase">
                      ID: {p.name} | Type: {p.providerType || 'unknown'}
                    </div>
                  </div>
                  {getStatusBadge(p)}
                </div>

                <div className="flex items-center space-x-2">
                  <span className="text-[10px] text-slate-500 font-medium">Source:</span>
                  {getProvenanceBadge(p.provenanceSource)}
                </div>

                <div className="text-[11px] text-slate-700 bg-slate-50 p-2 rounded border border-slate-200">
                  <div className="font-medium text-slate-900 mb-0.5">Operational Status:</div>
                  <div className="font-mono text-[10px] text-slate-600">{p.statusNotice}</div>
                  {p.statusReason && (
                    <div className="text-[10px] text-slate-500 mt-1 italic">
                      Diagnostics: {p.statusReason}
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-1 text-[10px] font-mono text-slate-500">
                  <div>
                    Modes: <span className="text-slate-800">{p.supportedModes?.join(', ') || 'none'}</span>
                  </div>
                  <div>
                    Coverage: <span className="text-slate-800">{p.supportedGeographicCoverage || 'global'}</span>
                  </div>
                  {p.lastObservationTime && (
                    <div className="col-span-2">
                      Last Obs:{' '}
                      <span className="text-slate-800">
                        {new Date(p.lastObservationTime).toLocaleTimeString()}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* User-facing Truth Notice Box */}
          <div className="p-2.5 rounded bg-blue-50 border border-blue-200 text-blue-900 text-[11px] leading-relaxed">
            <span className="font-bold">Operational Note:</span> TomTom Orbis v2 and GTFS Realtime
            adapters require commercial/agency API configuration. In absence of valid environment
            credentials, the system reports status honestly as <code className="bg-blue-100 px-1 py-0.5 rounded font-mono text-[10px]">BLOCKED</code> and activates deterministic simulation scenarios with visible badges. No live telemetry is fabricated.
          </div>
        </div>
      )}
    </div>
  );
};
