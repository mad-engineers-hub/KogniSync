import { apiClient, USE_MOCK_FALLBACK } from './client';
import { Journey, TravelRequest } from '../types/journey';
import { MOCK_JOURNEYS, generateMockJourneys, validateJourneyAgainstRequest } from './mockData';
import { composeMultiModalJourneys } from './orchestrationEngine';

// Cache to store dynamically generated journeys so details and booking flows succeed seamlessly
export const journeySessionCache = new Map<string, Journey>();

export async function searchJourneys(request: TravelRequest): Promise<Journey[]> {
  try {
    if (!USE_MOCK_FALLBACK) {
      const liveResults = await apiClient<Journey[]>('/api/v1/journeys/search', {
        method: 'POST',
        body: JSON.stringify(request),
      });
      if (liveResults && liveResults.length > 0) {
        liveResults.forEach((j) => {
          journeySessionCache.set(j.id, j);
          try {
            if (typeof window !== 'undefined' && window.sessionStorage) {
              sessionStorage.setItem(`kogni_jny_${j.id}`, JSON.stringify(j));
            }
          } catch {}
        });
        return liveResults;
      }
    }
  } catch (err) {
    console.warn('Backend journey search unavailable, utilizing mock orchestration engine.', err);
  }

  // Realistic mock latency
  await new Promise((resolve) => setTimeout(resolve, 200));

  // Generate parametric journeys tailored strictly to request.origin and request.destination
  const generated = generateMockJourneys(request);

  // Strictly validate each journey against the user request to guarantee no impossible routes
  const validJourneys = generated.filter((j) => {
    const val = validateJourneyAgainstRequest(j, request);
    if (!val.valid) {
      console.warn(`[searchJourneys] Filtering out invalid journey ${j.id}: ${val.reason}`);
      return false;
    }
    return true;
  });

  // If budget specified, categorize any edge cases
  const scoredJourneys = validJourneys.map((j) => {
    if (request.budgetMax && request.budgetMax > 0 && j.totalPrice > request.budgetMax) {
      return {
        ...j,
        aiExplanation: {
          ...j.aiExplanation,
          summary: `${j.aiExplanation.summary} Note: Exceeds specified budget of ₹${request.budgetMax} by ₹${j.totalPrice - request.budgetMax}.`,
        },
      };
    }
    return j;
  });

  scoredJourneys.forEach((j) => {
    journeySessionCache.set(j.id, j);
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        sessionStorage.setItem(`kogni_jny_${j.id}`, JSON.stringify(j));
      }
    } catch {}
  });

  return scoredJourneys;
}

export async function getJourneyById(id: string): Promise<Journey | null> {
  // 1. Check in-memory session cache
  if (journeySessionCache.has(id)) {
    return journeySessionCache.get(id)!;
  }

  // 2. Check browser sessionStorage
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      const stored = sessionStorage.getItem(`kogni_jny_${id}`);
      if (stored) {
        const parsed: Journey = JSON.parse(stored);
        journeySessionCache.set(id, parsed);
        return parsed;
      }
    }
  } catch {}

  // 3. Dynamic reconstruction from journey ID slug:
  // e.g. jny-udayapalya-to-chennai-fastest or jny-chennai-to-udupi-best_value
  const match = id.match(/^jny-([a-z0-9-]+)-to-([a-z0-9-]+)-(fastest|best_value|cheapest|greenest|comfortable)$/);
  if (match) {
    const rawOrigin = match[1].replace(/-/g, ' ');
    const rawDest = match[2].replace(/-/g, ' ');
    const journeys = composeMultiModalJourneys({
      origin: rawOrigin,
      destination: rawDest,
      departureDate: new Date().toISOString().split('T')[0],
      passengersCount: 1,
      weights: { cost: 0.4, duration: 0.3, comfort: 0.2, carbon: 0.1 },
    });
    const found = journeys.find((j) => j.id === id);
    if (found) {
      journeySessionCache.set(found.id, found);
      return found;
    }
  }

  try {
    if (!USE_MOCK_FALLBACK) {
      const live = await apiClient<Journey>(`/api/v1/journeys/${id}`);
      if (live) {
        journeySessionCache.set(live.id, live);
        return live;
      }
    }
  } catch (err) {
    console.warn('Backend journey detail unavailable, reading from local cache/mock.', err);
  }

  await new Promise((resolve) => setTimeout(resolve, 100));
  const found = MOCK_JOURNEYS.find((j) => j.id === id);
  if (found) {
    journeySessionCache.set(found.id, found);
    return found;
  }
  return null;
}

export interface TravelContext {
  origin?: string | null;
  destination?: string | null;
  date?: string | null;
  departure_time?: string | null;
  arrival_deadline?: string | null;
  passengers?: number;
  budget?: number | null;
  currency?: string;
  time_priority?: number;
  comfort?: number;
  sustainability?: number;
  preferred_modes?: string[];
}

export interface TravelIntent {
  origin?: string | null;
  destination?: string | null;
  date?: string | null;
  departure_time?: string | null;
  arrival_deadline?: string | null;
  passengers?: number;
  budget?: number | null;
  currency?: string;
  time_priority?: number;
  comfort?: number;
  sustainability?: number;
  preferred_modes?: string[];
  intent_summary?: string | null;
  confidence?: number;
}

export async function parseTravelIntent(
  text: string,
  currentContext?: TravelContext
): Promise<TravelIntent> {
  try {
    const res = await apiClient<{ intent: TravelIntent }>('/api/ai/parse-travel-intent', {
      method: 'POST',
      body: JSON.stringify({
        text,
        current_context: currentContext,
      }),
    });
    if (res?.intent) {
      return res.intent;
    }
  } catch (err) {
    console.warn('Backend AI intent extraction failed/timed out, applying client fallback heuristic:', err);
  }

  // Client-side heuristic fallback so users are never blocked by network latency
  return extractClientIntent(text, currentContext);
}

function extractClientIntent(text: string, currentContext?: TravelContext): TravelIntent {
  const t = text.trim();
  const lower = t.toLowerCase();

  let origin: string | null = currentContext?.origin || null;
  let destination: string | null = currentContext?.destination || null;
  let budget: number | null = currentContext?.budget || null;
  let arrivalDeadline: string | null = currentContext?.arrival_deadline || null;
  let date: string | null = currentContext?.date || null;
  let timePriority: number = currentContext?.time_priority ?? 0.5;

  // 1. 'reach <Dest> from <Origin>'
  const mReach = lower.match(/\breach\s+([a-z]+(?:\s+[a-z]+)?)\s+from\s+([a-z]+(?:\s+[a-z]+)?)\b/);
  if (mReach) {
    destination = capitalize(cleanEndpoint(mReach[1]));
    origin = capitalize(cleanEndpoint(mReach[2]));
  }

  // 2. 'from <Origin> to <Dest>'
  if (!origin || !destination) {
    const mFromTo = lower.match(/\bfrom\s+([a-z]+(?:\s+[a-z]+)?)\s+to\s+([a-z]+(?:\s+[a-z]+)?)\b/);
    if (mFromTo) {
      origin = capitalize(cleanEndpoint(mFromTo[1]));
      destination = capitalize(cleanEndpoint(mFromTo[2]));
    }
  }

  // 3. direct '<Origin> to <Dest>' (e.g. 'Bangalore to Goa this weekend')
  if (!origin || !destination) {
    const mSimple = lower.match(/\b([a-z]+(?:\s+[a-z]+)?)\s+to\s+([a-z]+(?:\s+[a-z]+)?)\b/);
    if (mSimple) {
      const candO = cleanEndpoint(mSimple[1]);
      const candD = cleanEndpoint(mSimple[2]);
      if (!['need', 'want', 'heading', 'welcome', 'travel', 'trip', 'plan', 'go'].includes(candO)) {
        origin = capitalize(candO);
        destination = capitalize(candD);
      }
    }
  }

  // Budget
  const mBudget = lower.match(/(?:under|budget\s*(?:is|of)?|₹|rs\.?|inr)\s*(\d{3,6})/);
  if (mBudget) {
    budget = parseInt(mBudget[1], 10);
  }

  // Arrival deadline
  const mArr = lower.match(/\b(?:before|by|arrive\s+by|arrive\s+before)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b/);
  if (mArr) {
    let h = parseInt(mArr[1], 10);
    const m = mArr[2] || '00';
    const ampm = mArr[3] || '';
    if (ampm === 'pm' && h < 12) h += 12;
    if (ampm === 'am' && h === 12) h = 0;
    arrivalDeadline = `${h.toString().padStart(2, '0')}:${m}`;
  }

  // Date
  const now = new Date();
  if (lower.includes('tomorrow')) {
    const d = new Date(now.getTime() + 86400000);
    date = d.toISOString().split('T')[0];
  } else if (lower.includes('weekend') || lower.includes('saturday')) {
    const daysAhead = (6 - now.getDay() + 7) % 7 || 7;
    const d = new Date(now.getTime() + daysAhead * 86400000);
    date = d.toISOString().split('T')[0];
  } else if (!date) {
    const d = new Date(now.getTime() + 86400000);
    date = d.toISOString().split('T')[0];
  }

  // Speed vs Economy
  if (lower.includes('speed') || lower.includes('fastest') || lower.includes('quickest')) {
    timePriority = 0.85;
  } else if (lower.includes('money') || lower.includes('cheapest') || lower.includes('cheap')) {
    timePriority = 0.25;
  }

  return {
    origin: origin || currentContext?.origin || 'Bangalore',
    destination: destination || currentContext?.destination || 'Chennai',
    date: date || '2026-10-30',
    departure_time: currentContext?.departure_time || null,
    arrival_deadline: arrivalDeadline || currentContext?.arrival_deadline || '20:00',
    passengers: currentContext?.passengers || 1,
    budget: budget !== null ? budget : (currentContext?.budget || 5000),
    time_priority: timePriority,
    comfort: currentContext?.comfort || 0.7,
    sustainability: lower.includes('green') || lower.includes('eco') ? 1.0 : (currentContext?.sustainability || 0.4),
    confidence: 0.95,
  };
}

function cleanEndpoint(raw: string): string {
  return raw.replace(/\b(?:this|tomorrow|today|next|before|by|on|at|under|with|for)\b.*$/g, '').trim();
}

function capitalize(s: string): string {
  if (!s) return '';
  return s.split(' ').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}


export interface ExtractedIntent {
  origin?: string;
  destination?: string;
  budget?: number;
  timePriority?: 'speed' | 'economy' | 'balance' | 'eco';
  arrivalBefore?: string;
  inferredDate?: string;
  weights: {
    cost: number;
    duration: number;
    comfort: number;
    carbon: number;
  };
}

export async function extractTravelIntent(prompt: string): Promise<ExtractedIntent> {
  const intent = await parseTravelIntent(prompt);
  return {
    origin: intent.origin || undefined,
    destination: intent.destination || undefined,
    budget: intent.budget || undefined,
    arrivalBefore: intent.arrival_deadline || undefined,
    inferredDate: intent.date || undefined,
    timePriority: (intent.time_priority && intent.time_priority >= 0.7) ? 'speed' : (intent.time_priority && intent.time_priority <= 0.3) ? 'economy' : 'balance',
    weights: {
      cost: intent.time_priority ? 1 - intent.time_priority : 0.4,
      duration: intent.time_priority || 0.3,
      comfort: intent.comfort || 0.2,
      carbon: intent.sustainability || 0.1,
    },
  };
}
