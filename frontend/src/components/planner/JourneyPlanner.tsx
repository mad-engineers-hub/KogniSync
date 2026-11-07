import React, { useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Sparkles,
  SlidersHorizontal,
  Mic,
  ArrowRight,
  MapPin,
  Calendar,
  User,
  ArrowLeftRight,
  ChevronDown,
  X,
  Clock,
  Leaf,
  Plane,
  Train,
  Bus,
  Car,
  TrainFront,
  Footprints,
  Check,
  Loader2,
  LocateFixed,
  AlertCircle,
} from 'lucide-react';
import { TransportMode } from '../../types/journey';
import { parseTravelIntent, TravelContext } from '../../api/journey';
import { useTravelRequest } from '../../context/TravelRequestContext';
import { useNotification } from '../../context/NotificationContext';
import { locationService } from '../../services/location/locationService';
import { LocationError } from '../../types/location';
import { GPS_NOTIFICATION_MESSAGES } from '../../services/location/gpsNotificationMessages';

interface JourneyPlannerProps {
  onSearchExecuted?: () => void;
}

export const JourneyPlanner: React.FC<JourneyPlannerProps> = ({ onSearchExecuted }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const {
    state,
    setOrigin,
    setDestination,
    setDate,
    setTimeDeadlineText,
    setPassengers,
    setBudget,
    setWeights,
    toggleMode,
    setNaturalLanguageQuery,
    swapLocations,
    applyIntent,
    buildSearchUrl,
  } = useTravelRequest();

  // Tab State: 'natural' | 'structured'
  const [activeTab, setActiveTab] = useState<'natural' | 'structured'>('natural');
  const [isPassengersOpen, setIsPassengersOpen] = useState(false);

  // Expansion display state: 'collapsed' | 'expanding' | 'expanded'
  // If the user arrived with pre-existing search params (e.g. from Results page "Modify Search"), start expanded.
  const hasInitialParams = Boolean(
    searchParams.get('origin') || searchParams.get('destination') || searchParams.get('q')
  );
  const [displayState, setDisplayState] = useState<'collapsed' | 'expanding' | 'expanded'>(
    hasInitialParams ? 'expanded' : 'collapsed'
  );

  // Budget Display State
  const budgetMin = 500;

  // AI Loading & Confirmation Feedback State
  const [isUnderstanding, setIsUnderstanding] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Global Notification System (M3.4.1)
  const { showSuccess, showError, showWarning, dismissCategory } = useNotification();

  // GPS Location Autofill State (M3.4)
  const [isLocatingOrigin, setIsLocatingOrigin] = useState(false);
  const [gpsSuccess, setGpsSuccess] = useState(false);
  const locationRequestIdRef = useRef<number>(0);

  const handleUseCurrentLocation = async () => {
    const currentRequestId = ++locationRequestIdRef.current;
    setIsLocatingOrigin(true);
    setGpsSuccess(false);

    try {
      const result = await locationService.getCurrentLocation();
      // Guard against race conditions: ignore if user manually edited while GPS was resolving
      if (currentRequestId !== locationRequestIdRef.current) {
        if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
          console.log('[GPS-DIAGNOSTIC] Stale location result discarded due to newer user edit.');
        }
        return;
      }

      setOrigin(result.formattedAddress, result.coordinates);
      setGpsSuccess(true);
      setTimeout(() => setGpsSuccess(false), 3000);

      // Replaces any obsolete GPS errors with global notification
      if (result.accuracyMeters > 2500) {
        showWarning(GPS_NOTIFICATION_MESSAGES.POOR_ACCURACY, { category: 'gps' });
      } else {
        showSuccess(GPS_NOTIFICATION_MESSAGES.SUCCESS, {
          category: 'gps',
          duration: 4500,
        });
      }

      if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
        console.log(`[GPS-DIAGNOSTIC] JourneyPlanner: From field set to "${result.formattedAddress}" with coordinates:`, result.coordinates);
      }
    } catch (err) {
      if (currentRequestId !== locationRequestIdRef.current) return;

      if (err instanceof LocationError) {
        if (err.code === 'POOR_ACCURACY') {
          showWarning(err.userFriendlyMessage, { category: 'gps' });
        } else {
          showError(err.userFriendlyMessage, { category: 'gps' });
        }
        if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
          console.warn(`[GPS-DIAGNOSTIC] LocationError caught: code=${err.code}, message="${err.message}", userMessage="${err.userFriendlyMessage}"`);
        }
      } else {
        showError('Your device could not provide a location. Check your location settings and retry.', {
          category: 'gps',
        });
      }
    } finally {
      if (currentRequestId === locationRequestIdRef.current) {
        setIsLocatingOrigin(false);
      }
    }
  };

  // Determine whether the expanded form should be visible
  const isExpanded = displayState === 'expanded' || activeTab === 'structured';

  // Handle Tab Switch
  const handleTabChange = (tab: 'natural' | 'structured') => {
    setActiveTab(tab);
    if (tab === 'structured') {
      setDisplayState('expanded');
    }
  };

  // Swap Origin and Destination
  const handleSwap = () => {
    swapLocations();
  };

  // Handle Live Natural Language Interpretation with Gemini (Collaped -> Expanded Transition)
  const handleParseAndPlan = async (customQuery?: string) => {
    const textToParse = (customQuery !== undefined ? customQuery : state.naturalLanguageQuery).trim();
    if (!textToParse) {
      setErrorMessage("Please enter where you'd like to travel.");
      return;
    }

    setIsUnderstanding(true);
    setDisplayState('expanding');
    setErrorMessage(null);

    const currentContext: TravelContext = {
      origin: state.origin || null,
      destination: state.destination || null,
      date: state.date || null,
      departure_time: state.departureTime,
      arrival_deadline: state.arrivalDeadline,
      passengers: state.passengers,
      budget: state.budget,
      time_priority: state.weights.duration,
      comfort: state.weights.comfort,
      sustainability: state.weights.carbon,
      preferred_modes: (Object.keys(state.selectedModes) as TransportMode[]).filter(
        (m) => state.selectedModes[m]
      ),
    };

    try {
      const intent = await parseTravelIntent(textToParse, currentContext);
      applyIntent(intent);
      // Transition smoothly into expanded form for fine-tuning
      setDisplayState('expanded');
    } catch (err: any) {
      console.error('Failed to parse travel intent:', err);
      setErrorMessage(
        err?.message || "Couldn't understand the journey request. Please try again."
      );
      // On failure, stay collapsed and show the inline error
      setDisplayState('collapsed');
    } finally {
      setIsUnderstanding(false);
    }
  };

  // Example pills handler
  const handleApplyExample = (queryText: string) => {
    setNaturalLanguageQuery(queryText);
    handleParseAndPlan(queryText);
  };

  // Search execution handler
  const handleExecuteSearch = () => {
    const targetUrl = buildSearchUrl();
    navigate(targetUrl);
    onSearchExecuted?.();
  };

  return (
    <div className="w-full max-w-[840px] bg-white/96 backdrop-blur-md rounded-2xl lg:rounded-[24px] border border-[#DCE5F2] shadow-[0_12px_40px_rgba(7,27,73,0.08)] p-5 sm:p-6 lg:p-7 flex flex-col gap-3.5 sm:gap-4 text-slate-800 transition-all">
      {/* 1. Header Tabs: Natural Language vs Structured Search */}
      <div className="flex items-center gap-6 border-b border-[#E2E8F0] pb-2 -mt-1">
        <button
          type="button"
          onClick={() => handleTabChange('natural')}
          className={`flex items-center gap-2 pb-2 text-xs sm:text-sm font-semibold transition-all relative cursor-pointer ${
            activeTab === 'natural'
              ? 'text-[#1769FF] border-b-2 border-[#1769FF] -mb-[9px]'
              : 'text-[#52627A] hover:text-[#071B49]'
          }`}
        >
          <Sparkles className="w-4 h-4 text-[#1769FF]" />
          <span>Natural Language</span>
        </button>

        <button
          type="button"
          onClick={() => handleTabChange('structured')}
          className={`flex items-center gap-2 pb-2 text-xs sm:text-sm font-medium transition-all relative cursor-pointer ${
            activeTab === 'structured'
              ? 'text-[#1769FF] border-b-2 border-[#1769FF] -mb-[9px]'
              : 'text-[#52627A] hover:text-[#071B49]'
          }`}
        >
          <SlidersHorizontal className="w-4 h-4 text-slate-400" />
          <span>Structured Search</span>
        </button>
      </div>

      {/* 2. Natural Language Travel Intent Input Bar */}
      {activeTab === 'natural' && (
        <div className="flex flex-col gap-2.5">
          {/* Pill Container matching reference design */}
          <div className="relative border border-[#DCE5F2] hover:border-[#1769FF]/50 rounded-xl sm:rounded-2xl p-2 sm:p-2.5 pl-3.5 bg-white shadow-2xs transition-colors flex items-center gap-2.5 sm:gap-3">
            <Sparkles className="w-4 h-4 text-[#1769FF] shrink-0" />
            <div className="flex-1 min-w-0">
              <input
                type="text"
                value={state.naturalLanguageQuery}
                onChange={(e) => setNaturalLanguageQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleParseAndPlan();
                  }
                }}
                placeholder="Where do you want to go?"
                className="w-full bg-transparent text-[#071B49] placeholder:text-slate-400 text-xs sm:text-[14px] leading-relaxed font-medium focus:outline-none"
              />
            </div>

            {/* Right side: Mic + Action button */}
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                className="p-1.5 text-slate-400 hover:text-slate-600 transition-colors rounded-lg hover:bg-slate-50 cursor-pointer"
                title="Voice input"
              >
                <Mic className="w-4 h-4" />
              </button>

              <button
                type="button"
                onClick={() => handleParseAndPlan()}
                disabled={isUnderstanding || !state.naturalLanguageQuery.trim()}
                className={`px-4 sm:px-5 py-2.5 rounded-xl font-semibold text-xs sm:text-sm flex items-center gap-1.5 shadow-sm active:scale-95 transition-all whitespace-nowrap cursor-pointer disabled:opacity-60 ${
                  displayState === 'expanded'
                    ? 'bg-slate-100 hover:bg-slate-200 text-[#071B49] border border-slate-200'
                    : 'bg-[#1769FF] hover:bg-[#0F56D9] text-white shadow-[#1769FF]/20'
                }`}
              >
                {isUnderstanding ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Planning...</span>
                  </>
                ) : displayState === 'expanded' ? (
                  <>
                    <span>Re-parse</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                ) : (
                  <>
                    <span>Plan Journey</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Error Feedback */}
          {errorMessage && (
            <div className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 animate-in fade-in duration-200">
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Example Search Pills (shown in initial collapsed view) */}
          {!isExpanded && (
            <div className="flex items-center gap-2 flex-wrap text-xs text-[#52627A] pt-0.5">
              <span className="font-medium text-[11px] text-[#64748B] shrink-0">Try examples:</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  type="button"
                  onClick={() =>
                    handleApplyExample(
                      'I need to reach Chennai from Bangalore tomorrow before 2 PM. My budget is ₹3000 and I prefer saving money over speed.'
                    )
                  }
                  className="px-2.5 py-0.5 rounded-full bg-white hover:bg-[#F5F8FC] border border-[#DCE5F2] hover:border-[#1769FF]/40 text-[11px] text-[#071B49] font-medium transition-colors cursor-pointer shadow-2xs"
                >
                  Bangalore to Chennai
                </button>

                <button
                  type="button"
                  onClick={() =>
                    handleApplyExample(
                      "Fastest way from Bangalore to Goa this Saturday. Money isn't a problem."
                    )
                  }
                  className="px-2.5 py-0.5 rounded-full bg-white hover:bg-[#F5F8FC] border border-[#DCE5F2] hover:border-[#1769FF]/40 text-[11px] text-[#071B49] font-medium transition-colors cursor-pointer shadow-2xs"
                >
                  Bangalore to Goa
                </button>

                <button
                  type="button"
                  onClick={() =>
                    handleApplyExample(
                      'I prefer trains and want to keep it under ₹2000.'
                    )
                  }
                  className="px-2.5 py-0.5 rounded-full bg-white hover:bg-[#F5F8FC] border border-[#DCE5F2] hover:border-[#1769FF]/40 text-[11px] text-[#071B49] font-medium transition-colors cursor-pointer shadow-2xs"
                >
                  Trains under ₹2,000
                </button>

                <button
                  type="button"
                  onClick={() =>
                    handleApplyExample(
                      'I want an eco-friendly trip.'
                    )
                  }
                  className="px-2.5 py-0.5 rounded-full bg-white hover:bg-[#F5F8FC] border border-[#DCE5F2] hover:border-[#1769FF]/40 text-[11px] text-[#071B49] font-medium transition-colors cursor-pointer shadow-2xs"
                >
                  Eco-friendly trip
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3. Smoothly Expanding Section: Understood pill, Structured Fields, Preferences, Transport Modes & CTA */}
      <div
        className={`grid transition-[grid-template-rows,opacity] duration-400 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none motion-reduce:duration-0 ${
          isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0 pointer-events-none'
        }`}
      >
        <div className="overflow-hidden flex flex-col gap-3.5 sm:gap-4">
          {/* AI Understood Feedback / Confirmation Pill */}
          {activeTab === 'natural' && state.understoodMessage && (
            <div className="flex items-center justify-between gap-3 px-3.5 py-2 rounded-xl bg-[#EBF2FF] border border-[#BFDBFE] text-xs text-[#071B49] animate-in fade-in duration-200">
              <div className="flex items-center gap-2 min-w-0">
                <Sparkles className="w-3.5 h-3.5 text-[#1769FF] shrink-0" />
                <span className="font-semibold truncate">{state.understoodMessage}</span>
              </div>
              <button
                type="button"
                onClick={() => setDisplayState('collapsed')}
                className="text-[11px] font-medium text-[#1769FF] hover:text-[#0D2E77] hover:underline cursor-pointer shrink-0 ml-2"
              >
                Collapse
              </button>
            </div>
          )}

          {/* Subtle Divider */}
          <div className="w-full h-px bg-slate-100 my-0.5" />

          {/* 4. Structured Fields: From, Swap, To, Date, Time/Deadline, Passengers */}
          <div className="flex flex-col sm:grid sm:grid-cols-2 lg:flex lg:flex-row lg:items-end gap-2.5">
            {/* From Field */}
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <span className="text-[11px] font-medium text-[#52627A]">From</span>
              <div className="flex items-center gap-1.5 border border-[#DCE5F2] rounded-xl px-3 py-2 bg-white shadow-2xs hover:border-[#1769FF]/50 transition-colors h-10">
                <MapPin className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                <input
                  type="text"
                  value={state.origin}
                  onChange={(e) => {
                    locationRequestIdRef.current++;
                    setOrigin(e.target.value, null);
                    dismissCategory('gps');
                  }}
                  placeholder="Origin city"
                  className="w-full bg-transparent text-xs font-semibold text-[#071B49] focus:outline-none"
                />
                {state.origin && (
                  <button
                    type="button"
                    onClick={() => {
                      locationRequestIdRef.current++;
                      setOrigin('', null);
                      dismissCategory('gps');
                    }}
                    className="text-slate-300 hover:text-slate-500 cursor-pointer p-0.5"
                    title="Clear origin"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
                {/* GPS Autofill Button */}
                <button
                  type="button"
                  onClick={handleUseCurrentLocation}
                  disabled={isLocatingOrigin}
                  className={`p-1 rounded-md border transition-all cursor-pointer flex items-center justify-center shrink-0 ${
                    isLocatingOrigin
                      ? 'bg-blue-50 border-blue-200 text-blue-600'
                      : gpsSuccess
                      ? 'bg-emerald-50 border-emerald-300 text-emerald-600'
                      : 'bg-slate-50 hover:bg-blue-50 border-slate-200 hover:border-blue-300 text-slate-400 hover:text-blue-600'
                  }`}
                  title={
                    isLocatingOrigin
                      ? 'Detecting your location...'
                      : gpsSuccess
                      ? `Location detected: ${state.origin}`
                      : 'Use my current location'
                  }
                  aria-label="Use my current location"
                >
                  {isLocatingOrigin ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : gpsSuccess ? (
                    <Check className="w-3 h-3" />
                  ) : (
                    <LocateFixed className="w-3 h-3" />
                  )}
                </button>
              </div>
            </div>

            {/* Swap Button Centered between From & To */}
            <div className="hidden lg:flex items-center justify-center pb-1 px-0.5">
              <button
                type="button"
                onClick={handleSwap}
                title="Swap From and To"
                className="w-7 h-7 rounded-full bg-white border border-[#DCE5F2] hover:border-[#1769FF] text-[#1769FF] hover:bg-blue-50 flex items-center justify-center shrink-0 shadow-2xs cursor-pointer transition-colors"
              >
                <ArrowLeftRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* To Field */}
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <span className="text-[11px] font-medium text-[#52627A]">To</span>
              <div className="flex items-center gap-2 border border-[#DCE5F2] rounded-xl px-3 py-2 bg-white shadow-2xs hover:border-[#1769FF]/50 transition-colors h-10">
                <MapPin className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                <input
                  type="text"
                  value={state.destination}
                  onChange={(e) => setDestination(e.target.value)}
                  placeholder="Destination city"
                  className="w-full bg-transparent text-xs font-semibold text-[#071B49] focus:outline-none"
                />
                {state.destination && (
                  <button
                    type="button"
                    onClick={() => setDestination('')}
                    className="text-slate-300 hover:text-slate-500 cursor-pointer"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Date Field */}
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <span className="text-[11px] font-medium text-[#52627A]">Date</span>
              <div className="flex items-center gap-2 border border-[#DCE5F2] rounded-xl px-3 py-2 bg-white shadow-2xs hover:border-[#1769FF]/50 transition-colors h-10">
                <Calendar className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                <input
                  type="text"
                  value={state.displayDate || state.date}
                  onChange={(e) => setDate(e.target.value)}
                  placeholder="Departure date"
                  className="w-full bg-transparent text-xs font-semibold text-[#071B49] focus:outline-none"
                />
                {(state.displayDate || state.date) && (
                  <button
                    type="button"
                    onClick={() => setDate('')}
                    className="text-slate-300 hover:text-slate-500 cursor-pointer"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Time / Deadline Field */}
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <span className="text-[11px] font-medium text-[#52627A]">Time / Deadline</span>
              <div className="flex items-center gap-2 border border-[#DCE5F2] rounded-xl px-3 py-2 bg-white shadow-2xs hover:border-[#1769FF]/50 transition-colors h-10">
                <Clock className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                <input
                  type="text"
                  value={state.timeDeadlineText}
                  onChange={(e) => setTimeDeadlineText(e.target.value)}
                  placeholder="Anytime"
                  className="w-full bg-transparent text-xs font-semibold text-[#071B49] focus:outline-none"
                />
                {state.timeDeadlineText && (
                  <button
                    type="button"
                    onClick={() => setTimeDeadlineText('')}
                    className="text-slate-300 hover:text-slate-500 cursor-pointer"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Passengers Field */}
            <div className="w-full sm:w-auto lg:w-28 flex flex-col gap-1 relative shrink-0">
              <span className="text-[11px] font-medium text-[#52627A]">Passengers</span>
              <button
                type="button"
                onClick={() => setIsPassengersOpen(!isPassengersOpen)}
                className="flex items-center justify-between border border-[#DCE5F2] rounded-xl px-3 py-2 bg-white shadow-2xs hover:border-[#1769FF]/50 transition-colors text-left cursor-pointer h-10"
              >
                <div className="flex items-center gap-2">
                  <User className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                  <span className="text-xs font-semibold text-[#071B49]">{state.passengers}</span>
                </div>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              {isPassengersOpen && (
                <div className="absolute top-full right-0 mt-1 w-36 bg-white border border-[#DCE5F2] rounded-lg shadow-lg z-30 p-1.5 flex flex-col gap-0.5 animate-in fade-in">
                  {[1, 2, 3, 4, 5, 6].map((num) => (
                    <button
                      key={num}
                      type="button"
                      onClick={() => {
                        setPassengers(num);
                        setIsPassengersOpen(false);
                      }}
                      className={`text-left px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                        state.passengers === num
                          ? 'bg-blue-50 font-bold text-[#1769FF]'
                          : 'hover:bg-slate-50 text-slate-700'
                      }`}
                    >
                      {num} {num === 1 ? 'Passenger' : 'Passengers'}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 5. Journey Preferences (Optional) */}
          <div className="flex flex-col gap-2 pt-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-[#071B49]">Journey Preferences</span>
              <span className="text-[11px] text-[#64748B] font-normal">(Optional)</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {/* Card 1: Budget */}
              <div className="border border-[#DCE5F2] rounded-xl p-3 bg-[#F8FAFC] shadow-2xs flex flex-col gap-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-[#FEF3C7] text-[#D97706] flex items-center justify-center font-bold text-sm shrink-0">
                    ₹
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-xs font-bold text-[#071B49]">Budget</span>
                    <span className="text-[11px] text-[#52627A] truncate font-mono">
                      ₹{budgetMin} - ₹{state.budget >= 10000 ? '10,000' : state.budget.toLocaleString()}
                    </span>
                  </div>
                </div>
                <input
                  type="range"
                  min={500}
                  max={10000}
                  step={500}
                  value={state.budget}
                  onChange={(e) => setBudget(parseInt(e.target.value, 10))}
                  className="w-full h-1 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#1769FF]"
                />
              </div>

              {/* Card 2: Time Priority */}
              <div className="border border-[#DCE5F2] rounded-xl p-3 bg-[#F8FAFC] shadow-2xs flex flex-col gap-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-[#EBF2FF] text-[#1769FF] flex items-center justify-center shrink-0">
                    <Clock className="w-4 h-4" />
                  </div>
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="text-xs font-bold text-[#071B49]">Time Priority</span>
                    <div className="flex items-center justify-between text-[11px] text-[#52627A]">
                      <span className={state.weights.duration <= 0.3 ? 'font-bold text-[#1769FF]' : ''}>
                        Flexible
                      </span>
                      <span className={state.weights.duration >= 0.7 ? 'font-bold text-[#1769FF]' : ''}>
                        Fastest
                      </span>
                    </div>
                  </div>
                </div>
                <input
                  type="range"
                  min={10}
                  max={100}
                  value={Math.round(state.weights.duration * 100)}
                  onChange={(e) =>
                    setWeights((prev) => ({ ...prev, duration: parseInt(e.target.value, 10) / 100 }))
                  }
                  className="w-full h-1 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#1769FF]"
                />
              </div>

              {/* Card 3: Comfort */}
              <div className="border border-[#DCE5F2] rounded-xl p-3 bg-[#F8FAFC] shadow-2xs flex flex-col gap-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-[#EBF2FF] text-[#1769FF] flex items-center justify-center shrink-0">
                    <User className="w-4 h-4" />
                  </div>
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="text-xs font-bold text-[#071B49]">Comfort</span>
                    <div className="flex items-center justify-between text-[11px] text-[#52627A]">
                      <span className={state.weights.comfort <= 0.3 ? 'font-bold text-[#1769FF]' : ''}>
                        Basic
                      </span>
                      <span className={state.weights.comfort >= 0.7 ? 'font-bold text-[#1769FF]' : ''}>
                        Premium
                      </span>
                    </div>
                  </div>
                </div>
                <input
                  type="range"
                  min={10}
                  max={100}
                  value={Math.round(state.weights.comfort * 100)}
                  onChange={(e) =>
                    setWeights((prev) => ({ ...prev, comfort: parseInt(e.target.value, 10) / 100 }))
                  }
                  className="w-full h-1 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#1769FF]"
                />
              </div>

              {/* Card 4: Sustainability */}
              <div className="border border-[#DCE5F2] rounded-xl p-3 bg-[#F8FAFC] shadow-2xs flex flex-col gap-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-[#ECFDF5] text-[#10A77A] flex items-center justify-center shrink-0">
                    <Leaf className="w-4 h-4" />
                  </div>
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="text-xs font-bold text-[#071B49]">Sustainability</span>
                    <div className="flex items-center justify-between text-[11px] text-[#52627A]">
                      <span className={state.weights.carbon <= 0.3 ? 'font-bold text-[#10A77A]' : ''}>
                        Any
                      </span>
                      <span className={state.weights.carbon >= 0.7 ? 'font-bold text-[#10A77A]' : ''}>
                        Eco-friendly
                      </span>
                    </div>
                  </div>
                </div>
                <input
                  type="range"
                  min={10}
                  max={100}
                  value={Math.round(state.weights.carbon * 100)}
                  onChange={(e) =>
                    setWeights((prev) => ({ ...prev, carbon: parseInt(e.target.value, 10) / 100 }))
                  }
                  className="w-full h-1 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#10A77A]"
                />
              </div>
            </div>
          </div>

          {/* 6. Transport Modes Selectors */}
          <div className="flex flex-col gap-2 pt-1">
            <span className="text-xs font-bold text-[#071B49]">Transport Modes</span>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {/* Flight */}
              <button
                type="button"
                onClick={() => toggleMode('flight')}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer h-10 ${
                  state.selectedModes.flight
                    ? 'bg-[#F0F6FF] border-[#1769FF] text-[#1769FF]'
                    : 'bg-white border-[#DCE5F2] text-[#52627A]'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <Plane className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Flights</span>
                </div>
                <div
                  className={`w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 ml-1 ${
                    state.selectedModes.flight ? 'bg-[#1769FF] text-white' : 'border border-slate-300 bg-white'
                  }`}
                >
                  {state.selectedModes.flight && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                </div>
              </button>

              {/* Train */}
              <button
                type="button"
                onClick={() => toggleMode('train')}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer h-10 ${
                  state.selectedModes.train
                    ? 'bg-[#F0F6FF] border-[#1769FF] text-[#1769FF]'
                    : 'bg-white border-[#DCE5F2] text-[#52627A]'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <Train className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Trains</span>
                </div>
                <div
                  className={`w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 ml-1 ${
                    state.selectedModes.train ? 'bg-[#1769FF] text-white' : 'border border-slate-300 bg-white'
                  }`}
                >
                  {state.selectedModes.train && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                </div>
              </button>

              {/* Bus */}
              <button
                type="button"
                onClick={() => toggleMode('bus')}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer h-10 ${
                  state.selectedModes.bus
                    ? 'bg-[#F0F6FF] border-[#1769FF] text-[#1769FF]'
                    : 'bg-white border-[#DCE5F2] text-[#52627A]'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <Bus className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Buses</span>
                </div>
                <div
                  className={`w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 ml-1 ${
                    state.selectedModes.bus ? 'bg-[#1769FF] text-white' : 'border border-slate-300 bg-white'
                  }`}
                >
                  {state.selectedModes.bus && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                </div>
              </button>

              {/* Cab */}
              <button
                type="button"
                onClick={() => toggleMode('cab')}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer h-10 ${
                  state.selectedModes.cab
                    ? 'bg-[#F0F6FF] border-[#1769FF] text-[#1769FF]'
                    : 'bg-white border-[#DCE5F2] text-[#52627A]'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <Car className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Cabs</span>
                </div>
                <div
                  className={`w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 ml-1 ${
                    state.selectedModes.cab ? 'bg-[#1769FF] text-white' : 'border border-slate-300 bg-white'
                  }`}
                >
                  {state.selectedModes.cab && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                </div>
              </button>

              {/* Metro */}
              <button
                type="button"
                onClick={() => toggleMode('metro')}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer h-10 ${
                  state.selectedModes.metro
                    ? 'bg-[#F0F6FF] border-[#1769FF] text-[#1769FF]'
                    : 'bg-white border-[#DCE5F2] text-[#52627A]'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <TrainFront className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Metro</span>
                </div>
                <div
                  className={`w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 ml-1 ${
                    state.selectedModes.metro ? 'bg-[#1769FF] text-white' : 'border border-slate-300 bg-white'
                  }`}
                >
                  {state.selectedModes.metro && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                </div>
              </button>

              {/* Walk */}
              <button
                type="button"
                onClick={() => toggleMode('walk')}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-xs font-semibold transition-all cursor-pointer h-10 ${
                  state.selectedModes.walk
                    ? 'bg-[#F0F6FF] border-[#1769FF] text-[#1769FF]'
                    : 'bg-white border-[#DCE5F2] text-[#52627A]'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <Footprints className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">Walk</span>
                </div>
                <div
                  className={`w-3.5 h-3.5 rounded flex items-center justify-center shrink-0 ml-1 ${
                    state.selectedModes.walk ? 'bg-[#1769FF] text-white' : 'border border-slate-300 bg-white'
                  }`}
                >
                  {state.selectedModes.walk && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                </div>
              </button>
            </div>
          </div>

          {/* 7. Action Bar (Search Journeys primary CTA & Collapse shortcut) */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-100">
            {activeTab === 'natural' ? (
              <button
                type="button"
                onClick={() => setDisplayState('collapsed')}
                className="text-xs text-[#52627A] hover:text-[#071B49] font-medium transition-colors cursor-pointer flex items-center gap-1"
              >
                <span>← Collapse view</span>
              </button>
            ) : (
              <div />
            )}

            <button
              type="button"
              onClick={handleExecuteSearch}
              className="bg-[#071B49] hover:bg-[#0D2E77] text-white px-6 py-2.5 rounded-xl font-semibold text-xs sm:text-sm flex items-center gap-2 shadow-sm active:scale-95 transition-all cursor-pointer"
            >
              <span>Search Journeys</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default JourneyPlanner;