import React, { useState } from 'react';
import { Journey, RecommendationCategory } from '../../types/journey';
import { JourneyCard } from './JourneyCard';
import { JourneyComparison } from './JourneyComparison';
import { JourneyMap } from '../map/JourneyMap';
import { Sparkles, SlidersHorizontal, ArrowUpDown, AlertCircle, Map } from 'lucide-react';

interface JourneyResultsProps {
  journeys: Journey[];
  isLoading?: boolean;
  onModifySearch?: () => void;
}

export const JourneyResults: React.FC<JourneyResultsProps> = ({
  journeys,
  isLoading = false,
  onModifySearch,
}) => {
  const [activeTab, setActiveTab] = useState<RecommendationCategory | 'all'>('all');
  const [sortBy, setSortBy] = useState<'score' | 'price' | 'duration' | 'carbon'>('score');
  const [showComparison, setShowComparison] = useState(false);
  const [showMap, setShowMap] = useState(true);
  const [selectedJourneyId, setSelectedJourneyId] = useState<string | null>(null);

  // Filter journeys by tab
  const filteredJourneys = journeys.filter((j) => {
    if (activeTab === 'all') return true;
    return j.recommendationCategory === activeTab;
  });

  // Sort journeys (deterministic tie-breaking aligned with backend optimizer)
  const sortedJourneys = [...filteredJourneys].sort((a, b) => {
    if (sortBy === 'score') {
      const diff = b.aiExplanation.score - a.aiExplanation.score;
      if (Math.abs(diff) > 0.001) return diff;
      if (a.totalPrice !== b.totalPrice) return a.totalPrice - b.totalPrice;
      return a.totalDurationMinutes - b.totalDurationMinutes;
    }
    if (sortBy === 'price') return a.totalPrice - b.totalPrice;
    if (sortBy === 'duration') return a.totalDurationMinutes - b.totalDurationMinutes;
    if (sortBy === 'carbon') return a.carbonKg - b.carbonKg;
    return 0;
  });

  // Active journey displayed on the map
  const activeJourney =
    journeys.find((j) => j.id === selectedJourneyId) || sortedJourneys[0] || journeys[0];

  const categories: { key: RecommendationCategory | 'all'; label: string; count: number }[] = [
    { key: 'all', label: 'All Journeys', count: journeys.length },
    {
      key: 'cheapest',
      label: 'Cheapest',
      count: journeys.filter((j) => j.recommendationCategory === 'cheapest').length,
    },
    {
      key: 'fastest',
      label: 'Fastest',
      count: journeys.filter((j) => j.recommendationCategory === 'fastest').length,
    },
    {
      key: 'best_value',
      label: 'Best Value',
      count: journeys.filter((j) => j.recommendationCategory === 'best_value').length,
    },
    {
      key: 'greenest',
      label: 'Greenest',
      count: journeys.filter((j) => j.recommendationCategory === 'greenest').length,
    },
  ];

  if (isLoading) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center gap-4 text-center">
        <div className="relative">
          <div className="w-12 h-12 rounded-full border-3 border-blue-600/20 border-t-blue-600 animate-spin" />
          <Sparkles className="w-5 h-5 text-blue-600 absolute inset-0 m-auto" />
        </div>
        <p className="font-bold text-slate-800 text-base">
          Synchronizing multi-modal transit graph...
        </p>
        <p className="text-xs text-slate-500 max-w-sm">
          Searching across carriers, calculating transfer buffers, and optimizing cost vs duration trade-offs.
        </p>
      </div>
    );
  }

  if (journeys.length === 0) {
    return (
      <div className="w-full py-16 px-4 rounded-2xl border border-slate-200 bg-white text-center flex flex-col items-center gap-3 shadow-xs">
        <AlertCircle className="w-10 h-10 text-amber-500" />
        <h3 className="text-lg font-bold text-slate-900">No synchronized journeys found</h3>
        <p className="text-xs text-slate-500 max-w-md">
          Could not find complete multi-modal routes satisfying all constraints. Try adjusting your travel date or expanding your budget ceiling.
        </p>
        {onModifySearch && (
          <button
            onClick={onModifySearch}
            className="mt-2 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition-colors shadow-xs"
          >
            Modify Search Criteria
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col gap-6 min-w-0 max-w-full">
      {/* Category Tabs & Sorting Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4 min-w-0">
        {/* Category tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 max-w-full min-w-0">
          {categories.map((cat) => (
            <button
              key={cat.key}
              onClick={() => setActiveTab(cat.key)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
                activeTab === cat.key
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <span>{cat.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                  activeTab === cat.key ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-500'
                }`}
              >
                {cat.count}
              </span>
            </button>
          ))}
        </div>

        {/* Controls: Map toggle, Matrix toggle & Sort By */}
        <div className="flex items-center gap-2.5 self-end sm:self-auto flex-wrap">
          <button
            onClick={() => setShowMap(!showMap)}
            className={`text-xs font-semibold flex items-center gap-1.5 px-3 py-1.5 rounded-xl transition-all shadow-2xs ${
              showMap
                ? 'bg-blue-600 text-white shadow-xs'
                : 'text-blue-700 hover:text-blue-800 bg-blue-50 border border-blue-200'
            }`}
          >
            <Map className="w-3.5 h-3.5" />
            <span>{showMap ? 'Hide Route Map' : 'Show Route Map'}</span>
          </button>

          <button
            onClick={() => setShowComparison(!showComparison)}
            className="text-xs font-semibold text-blue-700 hover:text-blue-800 flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-50 border border-blue-200 transition-colors shadow-2xs"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>{showComparison ? 'Hide Trade-Offs' : 'Compare Trade-Offs'}</span>
          </button>

          <div className="flex items-center gap-1.5 text-xs text-slate-600">
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-white border border-slate-300 rounded-lg px-2.5 py-1 text-slate-800 font-medium focus:outline-none focus:border-blue-600 shadow-2xs"
            >
              <option value="score">Recommended</option>
              <option value="price">Lowest Price</option>
              <option value="duration">Fastest Time</option>
              <option value="carbon">Lowest Carbon</option>
            </select>
          </div>
        </div>
      </div>

      {/* Multi-Objective Pareto Frontier Telemetry Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700">
        <div className="flex items-center gap-2">
          <span className="font-bold text-slate-900 font-display">Deterministic Multi-Objective Optimizer:</span>
          <span className="text-slate-600">
            Evaluated across 5 normalized dimensions (Cost, Duration, Comfort, Carbon, Transfers).
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-bold font-mono border border-emerald-300">
            {journeys.filter((j) => j.isParetoOptimal).length} of {journeys.length} on Pareto Frontier
          </span>
        </div>
      </div>

      {/* Interactive Google Routes & Geo Map Visualization */}
      {showMap && activeJourney && (
        <div className="animate-in fade-in duration-200">
          <JourneyMap
            journey={activeJourney}
            segments={activeJourney.segments}
            alternativeJourneys={journeys.filter((j) => j.id !== activeJourney.id)}
            onSelectJourney={(id) => setSelectedJourneyId(id)}
          />
        </div>
      )}

      {/* Trade-off Matrix Comparison Drawer */}
      {showComparison && (
        <div className="animate-in fade-in duration-200">
          <JourneyComparison journeys={journeys} />
        </div>
      )}

      {/* Journey Cards list */}
      <div className="flex flex-col gap-4">
        {sortedJourneys.length === 0 ? (
          <div className="p-8 rounded-2xl bg-white border border-slate-200 text-center flex flex-col items-center gap-2 shadow-2xs">
            <p className="text-sm font-semibold text-slate-700">No journeys in this category matching current constraints.</p>
            <button
              onClick={() => setActiveTab('all')}
              className="text-xs text-blue-600 font-semibold hover:underline cursor-pointer"
            >
              View all {journeys.length} synchronized journeys
            </button>
          </div>
        ) : (
          sortedJourneys.map((journey, index) => (
            <JourneyCard
              key={journey.id}
              journey={journey}
              isFeatured={index === 0 && activeTab === 'all'}
              isSelectedForMap={activeJourney?.id === journey.id}
              onSelectForMap={() => setSelectedJourneyId(journey.id)}
            />
          ))
        )}
      </div>
    </div>
  );
};
