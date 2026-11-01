import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { OptimizationWeights, TransportMode } from '../types/journey';
import { TravelIntent } from '../api/journey';
import {
  TravelRequestState,
  formatDisplayDate,
  formatTime12h,
  buildUnderstoodSummary,
  normalizeTravelIntent,
} from '../utils/travelUtils';

// Re-export utilities so existing consumers do not break
export {
  type TravelRequestState,
  formatDisplayDate,
  formatTime12h,
  buildUnderstoodSummary,
  normalizeTravelIntent,
};

interface TravelRequestContextValue {
  state: TravelRequestState;
  setOrigin: (origin: string) => void;
  setDestination: (destination: string) => void;
  setDate: (dateStr: string) => void;
  setTimeDeadlineText: (text: string) => void;
  setPassengers: (passengers: number) => void;
  setBudget: (budget: number) => void;
  setWeights: React.Dispatch<React.SetStateAction<OptimizationWeights>>;
  toggleMode: (mode: TransportMode) => void;
  setSelectedModes: React.Dispatch<React.SetStateAction<Record<TransportMode, boolean>>>;
  setNaturalLanguageQuery: (query: string) => void;
  setUnderstoodMessage: (message: string | null) => void;
  swapLocations: () => void;
  applyIntent: (intent: TravelIntent) => void;
  buildSearchUrl: () => string;
  buildSearchUrlFromIntent: (intent: TravelIntent) => string;
}

const DEFAULT_MODES: Record<TransportMode, boolean> = {
  flight: true,
  train: true,
  bus: true,
  cab: true,
  metro: true,
  rapido: true,
  auto: true,
  walk: false,
};

const TravelRequestContext = createContext<TravelRequestContextValue | null>(null);

export const TravelRequestProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [searchParams] = useSearchParams();

  // Check if URL has existing search params (e.g. from ResultsPage "Modify Search")
  const hasQueryParams = Boolean(
    searchParams.get('origin') || searchParams.get('destination') || searchParams.get('q')
  );

  // Initialize from searchParams if present, else standard defaults
  const initialOrigin = searchParams.get('origin') || 'Bangalore';
  const initialDestination = searchParams.get('destination') || 'Chennai';
  const rawDate = searchParams.get('date') || '2026-10-30';
  const initialDisplayDate = formatDisplayDate(rawDate);
  const initialArrival = searchParams.get('arrivalBefore') || '14:00';
  const initialDeparture = searchParams.get('departureAfter') || null;
  const initialBudget = searchParams.get('budgetMax') ? parseInt(searchParams.get('budgetMax')!, 10) : 3000;
  const initialPassengers = searchParams.get('passengers') ? parseInt(searchParams.get('passengers')!, 10) : 1;
  const initialQuery = searchParams.get('q') || '';

  const initialCostWeight = searchParams.get('costWeight') ? parseFloat(searchParams.get('costWeight')!) : 0.5;
  const initialDurationWeight = searchParams.get('durationWeight') ? parseFloat(searchParams.get('durationWeight')!) : 0.2;
  const initialComfortWeight = searchParams.get('comfortWeight') ? parseFloat(searchParams.get('comfortWeight')!) : 0.15;
  const initialCarbonWeight = searchParams.get('carbonWeight') ? parseFloat(searchParams.get('carbonWeight')!) : 0.1;

  const [state, setState] = useState<TravelRequestState>(() => {
    let timeText = initialArrival ? `Arrive by ${formatTime12h(initialArrival)}` : 'Anytime';
    if (initialArrival && initialDeparture) {
      timeText = `Depart ${formatTime12h(initialDeparture)} · Arrive by ${formatTime12h(initialArrival)}`;
    } else if (initialDeparture) {
      timeText = `Depart at ${formatTime12h(initialDeparture)}`;
    }

    const summary = hasQueryParams
      ? buildUnderstoodSummary({
          origin: initialOrigin,
          destination: initialDestination,
          displayDate: initialDisplayDate || 'Tomorrow',
          arrivalDeadline: initialArrival,
          departureTime: initialDeparture,
          budget: initialBudget,
          timePriority: initialDurationWeight,
        })
      : null;

    return {
      origin: initialOrigin,
      destination: initialDestination,
      date: rawDate,
      displayDate: initialDisplayDate,
      departureTime: initialDeparture,
      arrivalDeadline: initialArrival,
      timeDeadlineText: timeText,
      passengers: initialPassengers,
      budget: initialBudget,
      currency: 'INR',
      weights: {
        cost: initialCostWeight,
        duration: initialDurationWeight,
        comfort: initialComfortWeight,
        carbon: initialCarbonWeight,
      },
      selectedModes: { ...DEFAULT_MODES },
      naturalLanguageQuery: initialQuery,
      understoodMessage: summary,
    };
  });

  // Re-sync if URL parameters change (e.g. Back / Edit Search navigation)
  useEffect(() => {
    const urlOrigin = searchParams.get('origin');
    const urlDest = searchParams.get('destination');
    const urlDate = searchParams.get('date');
    const urlBudget = searchParams.get('budgetMax');
    const urlArrival = searchParams.get('arrivalBefore');
    const urlDeparture = searchParams.get('departureAfter');
    const urlQuery = searchParams.get('q');
    const urlPassengers = searchParams.get('passengers');
    const urlCost = searchParams.get('costWeight');
    const urlDuration = searchParams.get('durationWeight');
    const urlComfort = searchParams.get('comfortWeight');
    const urlCarbon = searchParams.get('carbonWeight');

    if (urlOrigin || urlDest || urlBudget || urlArrival || urlDate) {
      setState((prev) => {
        const nextOrigin = urlOrigin || prev.origin;
        const nextDest = urlDest || prev.destination;
        const nextDate = urlDate || prev.date;
        const nextDisplayDate = formatDisplayDate(nextDate);
        const nextBudget = urlBudget ? parseInt(urlBudget, 10) : prev.budget;
        const nextArrival = urlArrival || prev.arrivalDeadline;
        const nextDeparture = urlDeparture || prev.departureTime;
        const nextPassengers = urlPassengers ? parseInt(urlPassengers, 10) : prev.passengers;
        const nextQuery = urlQuery !== null ? urlQuery : prev.naturalLanguageQuery;

        const durW = urlDuration ? parseFloat(urlDuration) : prev.weights.duration;
        const costW = urlCost ? parseFloat(urlCost) : prev.weights.cost;
        const comfW = urlComfort ? parseFloat(urlComfort) : prev.weights.comfort;
        const carbW = urlCarbon ? parseFloat(urlCarbon) : prev.weights.carbon;

        let timeText = prev.timeDeadlineText;
        if (nextArrival && nextDeparture) {
          timeText = `Depart ${formatTime12h(nextDeparture)} · Arrive by ${formatTime12h(nextArrival)}`;
        } else if (nextArrival) {
          timeText = `Arrive by ${formatTime12h(nextArrival)}`;
        } else if (nextDeparture) {
          timeText = `Depart at ${formatTime12h(nextDeparture)}`;
        }

        const summary = buildUnderstoodSummary({
          origin: nextOrigin,
          destination: nextDest,
          displayDate: nextDisplayDate,
          arrivalDeadline: nextArrival,
          departureTime: nextDeparture,
          budget: nextBudget,
          timePriority: durW,
        });

        return {
          ...prev,
          origin: nextOrigin,
          destination: nextDest,
          date: nextDate,
          displayDate: nextDisplayDate,
          arrivalDeadline: nextArrival,
          departureTime: nextDeparture,
          timeDeadlineText: timeText,
          budget: nextBudget,
          passengers: nextPassengers,
          naturalLanguageQuery: nextQuery,
          weights: {
            cost: costW,
            duration: durW,
            comfort: comfW,
            carbon: carbW,
          },
          understoodMessage: summary,
        };
      });
    }
  }, [searchParams]);

  const setOrigin = (origin: string) => {
    setState((prev) => {
      const next = { ...prev, origin };
      return {
        ...next,
        understoodMessage: buildUnderstoodSummary({
          origin,
          destination: prev.destination,
          displayDate: prev.displayDate,
          arrivalDeadline: prev.arrivalDeadline,
          departureTime: prev.departureTime,
          budget: prev.budget,
          timePriority: prev.weights.duration,
        }),
      };
    });
  };

  const setDestination = (destination: string) => {
    setState((prev) => {
      const next = { ...prev, destination };
      return {
        ...next,
        understoodMessage: buildUnderstoodSummary({
          origin: prev.origin,
          destination,
          displayDate: prev.displayDate,
          arrivalDeadline: prev.arrivalDeadline,
          departureTime: prev.departureTime,
          budget: prev.budget,
          timePriority: prev.weights.duration,
        }),
      };
    });
  };

  const setDate = (dateStr: string) => {
    setState((prev) => {
      const disp = formatDisplayDate(dateStr);
      return {
        ...prev,
        date: dateStr,
        displayDate: disp,
        understoodMessage: buildUnderstoodSummary({
          origin: prev.origin,
          destination: prev.destination,
          displayDate: disp,
          arrivalDeadline: prev.arrivalDeadline,
          departureTime: prev.departureTime,
          budget: prev.budget,
          timePriority: prev.weights.duration,
        }),
      };
    });
  };

  const setTimeDeadlineText = (text: string) => {
    setState((prev) => ({ ...prev, timeDeadlineText: text }));
  };

  const setPassengers = (passengers: number) => {
    setState((prev) => ({ ...prev, passengers }));
  };

  const setBudget = (budget: number) => {
    setState((prev) => {
      const next = { ...prev, budget };
      return {
        ...next,
        understoodMessage: buildUnderstoodSummary({
          origin: prev.origin,
          destination: prev.destination,
          displayDate: prev.displayDate,
          arrivalDeadline: prev.arrivalDeadline,
          departureTime: prev.departureTime,
          budget,
          timePriority: prev.weights.duration,
        }),
      };
    });
  };

  const setWeights: React.Dispatch<React.SetStateAction<OptimizationWeights>> = (value) => {
    setState((prev) => {
      const nextWeights = typeof value === 'function' ? value(prev.weights) : value;
      return {
        ...prev,
        weights: nextWeights,
        understoodMessage: buildUnderstoodSummary({
          origin: prev.origin,
          destination: prev.destination,
          displayDate: prev.displayDate,
          arrivalDeadline: prev.arrivalDeadline,
          departureTime: prev.departureTime,
          budget: prev.budget,
          timePriority: nextWeights.duration,
        }),
      };
    });
  };

  const toggleMode = (mode: TransportMode) => {
    setState((prev) => ({
      ...prev,
      selectedModes: {
        ...prev.selectedModes,
        [mode]: !prev.selectedModes[mode],
      },
    }));
  };

  const setSelectedModes: React.Dispatch<React.SetStateAction<Record<TransportMode, boolean>>> = (value) => {
    setState((prev) => ({
      ...prev,
      selectedModes: typeof value === 'function' ? value(prev.selectedModes) : value,
    }));
  };

  const setNaturalLanguageQuery = (naturalLanguageQuery: string) => {
    setState((prev) => ({ ...prev, naturalLanguageQuery }));
  };

  const setUnderstoodMessage = (understoodMessage: string | null) => {
    setState((prev) => ({ ...prev, understoodMessage }));
  };

  const swapLocations = () => {
    setState((prev) => {
      const newOrigin = prev.destination;
      const newDest = prev.origin;
      return {
        ...prev,
        origin: newOrigin,
        destination: newDest,
        understoodMessage: buildUnderstoodSummary({
          origin: newOrigin,
          destination: newDest,
          displayDate: prev.displayDate,
          arrivalDeadline: prev.arrivalDeadline,
          departureTime: prev.departureTime,
          budget: prev.budget,
          timePriority: prev.weights.duration,
        }),
      };
    });
  };

  const applyIntent = (intent: TravelIntent) => {
    setState((prev) => normalizeTravelIntent(intent, prev));
  };

  const buildSearchUrl = () => {
    const params = new URLSearchParams({
      origin: state.origin || 'Bangalore',
      destination: state.destination || 'Chennai',
      date: state.date || '2026-10-30',
      passengers: (state.passengers || 1).toString(),
      costWeight: state.weights.cost.toString(),
      durationWeight: state.weights.duration.toString(),
      comfortWeight: state.weights.comfort.toString(),
      carbonWeight: state.weights.carbon.toString(),
    });

    if (state.naturalLanguageQuery?.trim()) {
      params.set('q', state.naturalLanguageQuery.trim());
    }
    if (state.budget && state.budget > 0) {
      params.set('budgetMax', state.budget.toString());
    }
    if (state.arrivalDeadline) {
      params.set('arrivalBefore', state.arrivalDeadline);
    }
    if (state.departureTime) {
      params.set('departureAfter', state.departureTime);
    }

    return `/plan?${params.toString()}`;
  };

  const buildSearchUrlFromIntent = (intent: TravelIntent) => {
    const normalized = normalizeTravelIntent(intent, state);
    const params = new URLSearchParams({
      origin: normalized.origin || 'Bangalore',
      destination: normalized.destination || 'Chennai',
      date: normalized.date || '2026-10-30',
      passengers: (normalized.passengers || 1).toString(),
      costWeight: normalized.weights.cost.toString(),
      durationWeight: normalized.weights.duration.toString(),
      comfortWeight: normalized.weights.comfort.toString(),
      carbonWeight: normalized.weights.carbon.toString(),
    });

    if (normalized.naturalLanguageQuery?.trim()) {
      params.set('q', normalized.naturalLanguageQuery.trim());
    }
    if (normalized.budget && normalized.budget > 0) {
      params.set('budgetMax', normalized.budget.toString());
    }
    if (normalized.arrivalDeadline) {
      params.set('arrivalBefore', normalized.arrivalDeadline);
    }
    if (normalized.departureTime) {
      params.set('departureAfter', normalized.departureTime);
    }

    return `/plan?${params.toString()}`;
  };

  return (
    <TravelRequestContext.Provider
      value={{
        state,
        setOrigin,
        setDestination,
        setDate,
        setTimeDeadlineText,
        setPassengers,
        setBudget,
        setWeights,
        toggleMode,
        setSelectedModes,
        setNaturalLanguageQuery,
        setUnderstoodMessage,
        swapLocations,
        applyIntent,
        buildSearchUrl,
        buildSearchUrlFromIntent,
      }}
    >
      {children}
    </TravelRequestContext.Provider>
  );
};

export function useTravelRequest(): TravelRequestContextValue {
  const context = useContext(TravelRequestContext);
  if (!context) {
    throw new Error('useTravelRequest must be used within a TravelRequestProvider');
  }
  return context;
}
