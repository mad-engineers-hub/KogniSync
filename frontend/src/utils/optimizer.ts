import type {
  JourneyOptimizationMetrics,
  JourneyScoreBreakdown,
  JourneyRecommendationExplanation,
  OptimizedJourneyOutput,
  OptimizationWeights,
  OptimizationResponse,
} from '../types/optimizer';
import type { Journey } from '../types/journey';

// Centralized emissions factors (kg CO2 per passenger-km)
export const CARBON_FACTORS_KG_PER_KM: Record<string, number> = {
  flight: 0.150,
  cab: 0.120,
  car: 0.120,
  taxi: 0.120,
  auto: 0.075,
  rapido: 0.045,
  bus: 0.040,
  train: 0.025,
  rail: 0.025,
  metro: 0.020,
  walk: 0.000,
};

// Base comfort ratings per transport mode [0, 1]
export const BASE_MODE_COMFORT: Record<string, number> = {
  flight: 0.85,
  cab: 0.80,
  car: 0.80,
  taxi: 0.80,
  train: 0.75,
  rail: 0.75,
  metro: 0.70,
  bus: 0.60,
  auto: 0.55,
  rapido: 0.50,
  walk: 0.40,
};

export function computeSegmentCarbonKg(mode: string, distanceKm: number): number {
  const factor = CARBON_FACTORS_KG_PER_KM[mode.toLowerCase()] ?? 0.060;
  return Number((distanceKm * factor).toFixed(2));
}

export function deriveJourneyComfortScore(
  modes: string[],
  totalTransfers: number,
  durationMinutes: number,
  baseComfortInput?: number
): number {
  let rawBase: number;
  if (baseComfortInput !== undefined && baseComfortInput > 0) {
    rawBase = baseComfortInput > 1.0 ? baseComfortInput / 10.0 : baseComfortInput;
  } else if (modes.length > 0) {
    rawBase =
      modes.reduce((sum, m) => sum + (BASE_MODE_COMFORT[m.toLowerCase()] ?? 0.65), 0) /
      modes.length;
  } else {
    rawBase = 0.70;
  }

  const transferPenalty = Math.max(0, totalTransfers) * 0.04;
  const excessHours = Math.max(0, (durationMinutes - 360) / 120);
  const durationPenalty = Math.min(0.15, excessHours * 0.03);

  const finalComfort = rawBase - transferPenalty - durationPenalty;
  return Number(Math.max(0.10, Math.min(1.00, finalComfort)).toFixed(3));
}

export function normalizeMinimization(val: number, minVal: number, maxVal: number): number {
  if (maxVal - minVal <= 1e-9) return 1.0;
  const norm = (maxVal - val) / (maxVal - minVal);
  return Number(Math.max(0.0, Math.min(1.0, norm)).toFixed(4));
}

export function normalizeMaximization(val: number, minVal: number, maxVal: number): number {
  if (maxVal - minVal <= 1e-9) return 1.0;
  const norm = (val - minVal) / (maxVal - minVal);
  return Number(Math.max(0.0, Math.min(1.0, norm)).toFixed(4));
}

export interface CandidateNormalizationBounds {
  minCost: number;
  maxCost: number;
  minDur: number;
  maxDur: number;
  minTransfers: number;
  maxTransfers: number;
  minComf: number;
  maxComf: number;
  minCarb: number;
  maxCarb: number;
}

export function getNormalizationBounds(
  metricsList: JourneyOptimizationMetrics[]
): CandidateNormalizationBounds {
  if (metricsList.length === 0) {
    return {
      minCost: 0,
      maxCost: 0,
      minDur: 0,
      maxDur: 0,
      minTransfers: 0,
      maxTransfers: 0,
      minComf: 0,
      maxComf: 0,
      minCarb: 0,
      maxCarb: 0,
    };
  }

  return {
    minCost: Math.min(...metricsList.map((m) => m.totalCost)),
    maxCost: Math.max(...metricsList.map((m) => m.totalCost)),
    minDur: Math.min(...metricsList.map((m) => m.durationMinutes)),
    maxDur: Math.max(...metricsList.map((m) => m.durationMinutes)),
    minTransfers: Math.min(...metricsList.map((m) => m.transferCount)),
    maxTransfers: Math.max(...metricsList.map((m) => m.transferCount)),
    minComf: Math.min(...metricsList.map((m) => m.comfortScore)),
    maxComf: Math.max(...metricsList.map((m) => m.comfortScore)),
    minCarb: Math.min(...metricsList.map((m) => m.carbonKg)),
    maxCarb: Math.max(...metricsList.map((m) => m.carbonKg)),
  };
}

export function normalizeMetrics(
  m: JourneyOptimizationMetrics,
  b: CandidateNormalizationBounds
): Record<'cost' | 'duration' | 'transfers' | 'comfort' | 'carbon', number> {
  return {
    cost: normalizeMinimization(m.totalCost, b.minCost, b.maxCost),
    duration: normalizeMinimization(m.durationMinutes, b.minDur, b.maxDur),
    transfers: normalizeMinimization(m.transferCount, b.minTransfers, b.maxTransfers),
    comfort: normalizeMaximization(m.comfortScore, b.minComf, b.maxComf),
    carbon: normalizeMinimization(m.carbonKg, b.minCarb, b.maxCarb),
  };
}

export function normalizeWeights(
  w?: Partial<OptimizationWeights>
): Record<'cost' | 'duration' | 'comfort' | 'carbon' | 'transfers', number> {
  const raw = {
    cost: Math.max(0, w?.cost ?? 0.40),
    duration: Math.max(0, w?.duration ?? 0.30),
    comfort: Math.max(0, w?.comfort ?? 0.20),
    carbon: Math.max(0, w?.carbon ?? 0.10),
    transfers: Math.max(0, w?.transfers ?? 0.00),
  };
  const sum = raw.cost + raw.duration + raw.comfort + raw.carbon + raw.transfers;
  if (sum <= 1e-9) {
    return { cost: 0.40, duration: 0.30, comfort: 0.20, carbon: 0.10, transfers: 0.00 };
  }
  return {
    cost: Number((raw.cost / sum).toFixed(4)),
    duration: Number((raw.duration / sum).toFixed(4)),
    comfort: Number((raw.comfort / sum).toFixed(4)),
    carbon: Number((raw.carbon / sum).toFixed(4)),
    transfers: Number((raw.transfers / sum).toFixed(4)),
  };
}

export function calibrateWeights(
  w?: Partial<OptimizationWeights>,
  naturalLanguageQuery?: string
): Record<'cost' | 'duration' | 'comfort' | 'carbon' | 'transfers', number> {
  const costWt = w?.cost ?? 0.40;
  const durWt = w?.duration ?? 0.30;
  const comfWt = w?.comfort ?? 0.20;
  const carbWt = w?.carbon ?? 0.10;

  const q = (naturalLanguageQuery ?? '').toLowerCase();
  const queryPrefersCost =
    (q.includes('cheap') || q.includes('money') || q.includes('budget') || q.includes('cost') || q.includes('save')) &&
    !q.includes('over money') &&
    !q.includes('over cost');
  const queryPrefersSpeed =
    (q.includes('speed') || q.includes('fast') || q.includes('quick') || q.includes('urgent')) &&
    !q.includes('over speed');
  const queryPrefersGreen = q.includes('green') || q.includes('eco');

  const isCostDominant = costWt >= 0.5 || (costWt > durWt && (queryPrefersCost || costWt >= 0.45));
  const isSpeedDominant = durWt >= 0.45 || (durWt > costWt && (queryPrefersSpeed || durWt >= 0.40));
  const isGreenDominant = carbWt >= 0.3 || queryPrefersGreen;

  if (isCostDominant) {
    return { cost: 0.75, duration: 0.10, comfort: 0.08, carbon: 0.07, transfers: 0.0 };
  } else if (isSpeedDominant) {
    return { cost: 0.10, duration: 0.75, comfort: 0.08, carbon: 0.07, transfers: 0.0 };
  } else if (isGreenDominant) {
    return { cost: 0.15, duration: 0.10, comfort: 0.10, carbon: 0.65, transfers: 0.0 };
  }

  return normalizeWeights(w);
}

export function computeJourneyScore(
  metrics: JourneyOptimizationMetrics,
  normDict: Record<'cost' | 'duration' | 'transfers' | 'comfort' | 'carbon', number>,
  weights: Record<'cost' | 'duration' | 'comfort' | 'carbon' | 'transfers', number>
): JourneyScoreBreakdown {
  const costContrib = Number((normDict.cost * weights.cost).toFixed(4));
  const durContrib = Number((normDict.duration * weights.duration).toFixed(4));
  const comfContrib = Number((normDict.comfort * weights.comfort).toFixed(4));
  const carbContrib = Number((normDict.carbon * weights.carbon).toFixed(4));
  const transfContrib = Number((normDict.transfers * weights.transfers).toFixed(4));

  const totalScore = Number(
    Math.min(1.0, Math.max(0.0, costContrib + durContrib + comfContrib + carbContrib + transfContrib)).toFixed(4)
  );

  return {
    cost: {
      raw: metrics.totalCost,
      normalized: normDict.cost,
      weight: weights.cost,
      contribution: costContrib,
    },
    duration: {
      raw: metrics.durationMinutes,
      normalized: normDict.duration,
      weight: weights.duration,
      contribution: durContrib,
    },
    comfort: {
      raw: metrics.comfortScore,
      normalized: normDict.comfort,
      weight: weights.comfort,
      contribution: comfContrib,
    },
    carbon: {
      raw: metrics.carbonKg,
      normalized: normDict.carbon,
      weight: weights.carbon,
      contribution: carbContrib,
    },
    transfers: {
      raw: metrics.transferCount,
      normalized: normDict.transfers,
      weight: weights.transfers,
      contribution: transfContrib,
    },
    totalScore,
  };
}

export function dominates(
  a: JourneyOptimizationMetrics,
  b: JourneyOptimizationMetrics,
  tolerance = 1e-6
): boolean {
  const noWorse =
    a.totalCost <= b.totalCost + tolerance &&
    a.durationMinutes <= b.durationMinutes &&
    a.carbonKg <= b.carbonKg + tolerance &&
    a.transferCount <= b.transferCount &&
    a.comfortScore >= b.comfortScore - tolerance;

  if (!noWorse) return false;

  const strictlyBetter =
    a.totalCost < b.totalCost - tolerance ||
    a.durationMinutes < b.durationMinutes ||
    a.carbonKg < b.carbonKg - tolerance ||
    a.transferCount < b.transferCount ||
    a.comfortScore > b.comfortScore + tolerance;

  return strictlyBetter;
}

export function computeParetoFrontier(metricsList: JourneyOptimizationMetrics[]): boolean[] {
  const n = metricsList.length;
  if (n <= 1) return Array(n).fill(true);

  const isPareto = Array(n).fill(true);
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i !== j && dominates(metricsList[j], metricsList[i])) {
        isPareto[i] = false;
        break;
      }
    }
  }
  return isPareto;
}

export function formatDurationShort(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

export function generateDeterministicExplanation(
  targetId: string,
  targetTitle: string,
  metrics: JourneyOptimizationMetrics,
  allCandidates: Array<{ id: string; title: string }>,
  allMetrics: JourneyOptimizationMetrics[],
  weights: Record<string, number>,
  budgetMax?: number
): JourneyRecommendationExplanation {
  const reasons: string[] = [];
  const tradeoffs: string[] = [];

  let cheapestIdx = 0;
  let fastestIdx = 0;
  let greenestIdx = 0;

  for (let i = 0; i < allMetrics.length; i++) {
    if (allMetrics[i].totalCost < allMetrics[cheapestIdx].totalCost) cheapestIdx = i;
    if (allMetrics[i].durationMinutes < allMetrics[fastestIdx].durationMinutes) fastestIdx = i;
    if (allMetrics[i].carbonKg < allMetrics[greenestIdx].carbonKg) greenestIdx = i;
  }

  const cheapestCand = allCandidates[cheapestIdx];
  const cheapestMet = allMetrics[cheapestIdx];
  const fastestCand = allCandidates[fastestIdx];
  const fastestMet = allMetrics[fastestIdx];
  const greenestMet = allMetrics[greenestIdx];

  const costWt = weights.cost ?? 0.4;
  const durWt = weights.duration ?? 0.3;
  const carbWt = weights.carbon ?? 0.1;
  const comfWt = weights.comfort ?? 0.2;

  let headline = 'Best overall balance of cost, time and comfort';
  if (targetId === cheapestCand.id) {
    headline = 'Lowest cost multi-modal itinerary';
    reasons.push(`Guaranteed lowest fare: ₹${Math.round(metrics.totalCost).toLocaleString('en-IN')}`);
  } else if (targetId === fastestCand.id) {
    headline = 'Fastest door-to-door corridor';
    reasons.push(`Shortest transit duration: ${formatDurationShort(metrics.durationMinutes)}`);
  } else if (durWt >= 0.45 || (durWt > costWt && durWt >= 0.38)) {
    headline = 'Best match for your priority for speed';
  } else if (costWt >= 0.45 || (costWt > durWt && costWt >= 0.38)) {
    headline = 'Best match for your budget and cost savings';
  } else if (carbWt >= 0.30) {
    headline = 'Eco-conscious choice with minimal carbon emissions';
  } else if (comfWt >= 0.30) {
    headline = 'Maximized passenger comfort & premium transit link';
  }

  // Comparison vs cheapest
  if (metrics.totalCost === cheapestMet.totalCost) {
    if (targetId !== cheapestCand.id) {
      reasons.push('Zero premium: matches lowest fare on this route');
    }
  } else {
    const durSaved = cheapestMet.durationMinutes - metrics.durationMinutes;
    if (durSaved > 15) {
      reasons.push(`${formatDurationShort(durSaved)} faster than the cheapest option (${cheapestCand.title})`);
    }
    const extraCost = Math.round(metrics.totalCost - cheapestMet.totalCost);
    tradeoffs.push(`Costs ₹${extraCost.toLocaleString('en-IN')} more than the cheapest option (${cheapestCand.title})`);
  }

  // Comparison vs fastest
  if (metrics.durationMinutes === fastestMet.durationMinutes) {
    if (targetId !== fastestCand.id) {
      reasons.push('Matches the fastest flight speed on this corridor');
    }
  } else {
    const extraDur = metrics.durationMinutes - fastestMet.durationMinutes;
    if (extraDur > 20) {
      tradeoffs.push(`Takes ${formatDurationShort(extraDur)} longer than the express route (${fastestCand.title})`);
    }
    const costSaved = Math.round(fastestMet.totalCost - metrics.totalCost);
    if (costSaved > 200) {
      reasons.push(`Saves ₹${costSaved.toLocaleString('en-IN')} compared to the express flight route`);
    }
  }

  // Budget headroom
  if (budgetMax !== undefined && budgetMax > 0) {
    const underBudget = Math.round(budgetMax - metrics.totalCost);
    if (underBudget >= 0) {
      reasons.push(`₹${underBudget.toLocaleString('en-IN')} under your specified budget limit of ₹${Math.round(budgetMax).toLocaleString('en-IN')}`);
    } else {
      tradeoffs.push(`Exceeds target budget by ₹${Math.abs(underBudget).toLocaleString('en-IN')}`);
    }
  }

  // Transfers
  if (metrics.transferCount === 0) {
    reasons.push('Direct journey with 0 transfers');
  } else if (metrics.transferCount <= 2) {
    reasons.push(`Only ${metrics.transferCount} seamless intermodal transfers`);
  } else {
    tradeoffs.push(`Requires ${metrics.transferCount} transfers across transit hubs`);
  }

  // Carbon profile
  if (greenestMet.carbonKg > 0) {
    if (metrics.carbonKg === greenestMet.carbonKg) {
      reasons.push(`Lowest carbon emissions: ${metrics.carbonKg} kg CO₂`);
    } else if (metrics.carbonKg <= greenestMet.carbonKg * 1.3) {
      reasons.push(`Eco-friendly profile: ${metrics.carbonKg} kg CO₂`);
    }
  }

  // Comfort
  const comfortPct = Math.round(metrics.comfortScore * 100);
  if (comfortPct >= 80) {
    reasons.push(`High passenger comfort score: ${comfortPct}%`);
  }

  return {
    headline,
    reasons: reasons.slice(0, 4),
    tradeoffs: tradeoffs.slice(0, 3),
    comparedAgainst: targetId !== cheapestCand.id ? cheapestCand.title : fastestCand.title,
  };
}

/**
 * Optimizes a list of Journey candidate models deterministically.
 * Enforces hard budget constraints first.
 * Assigns metrics, scores, Pareto status, and deterministic explanations.
 * Returns sorted journeys with highest score first.
 */
export function optimizeCandidateJourneys(
  candidateJourneys: Journey[],
  weightsInput?: Partial<OptimizationWeights>,
  budgetMax?: number,
  naturalLanguageQuery?: string
): Journey[] {
  if (candidateJourneys.length === 0) return [];

  // 1. Enforce Hard Constraints First (budgetMax)
  let eligibleJourneys = candidateJourneys;
  if (budgetMax !== undefined && budgetMax > 0) {
    const withinBudget = candidateJourneys.filter((j) => j.totalPrice <= budgetMax);
    if (withinBudget.length > 0) {
      eligibleJourneys = withinBudget;
    }
  }

  // 2. Extract optimization metrics for eligible candidates
  const allMetrics: JourneyOptimizationMetrics[] = eligibleJourneys.map((j) => {
    const comfort = deriveJourneyComfortScore(
      j.modes,
      j.totalTransfers,
      j.totalDurationMinutes,
      j.comfortScore
    );
    return {
      totalCost: j.totalPrice,
      durationMinutes: j.totalDurationMinutes,
      transferCount: j.totalTransfers,
      comfortScore: comfort,
      carbonKg: Number(j.carbonKg.toFixed(2)),
    };
  });

  // 3. Calculate normalization bounds across candidates
  const bounds = getNormalizationBounds(allMetrics);

  // 4. Calibrate preference weights
  const weights = calibrateWeights(weightsInput, naturalLanguageQuery);

  // 5. Compute Pareto frontier
  const isParetoList = computeParetoFrontier(allMetrics);

  // 6. Score candidates and generate explanations
  const candidateSummaries = eligibleJourneys.map((j) => ({ id: j.id, title: j.title }));

  const optimizedJourneys: Journey[] = eligibleJourneys.map((j, idx) => {
    const metrics = allMetrics[idx];
    const isPareto = isParetoList[idx];
    const normDict = normalizeMetrics(metrics, bounds);
    const scoreBreakdown = computeJourneyScore(metrics, normDict, weights);

    const explanation = generateDeterministicExplanation(
      j.id,
      j.title,
      metrics,
      candidateSummaries,
      allMetrics,
      weights,
      budgetMax
    );

    const scaledScore = Math.round(scoreBreakdown.totalScore * 100);

    const optOutput: OptimizedJourneyOutput = {
      id: j.id,
      title: j.title,
      score: scoreBreakdown.totalScore,
      scaledScore,
      category: j.recommendationCategory,
      isParetoOptimal: isPareto,
      paretoRank: isPareto ? 1 : 2,
      metrics,
      scoreBreakdown,
      explanation,
    };

    return {
      ...j,
      isParetoOptimal: isPareto,
      optimization: optOutput,
      aiExplanation: {
        ...j.aiExplanation,
        score: scaledScore,
        rankReason: explanation.headline,
        tradeOffs: explanation.tradeoffs.length > 0 ? explanation.tradeoffs : j.aiExplanation.tradeOffs,
      },
    };
  });

  // 7. Sort by score descending (tie-breaking: lowest cost, lowest duration)
  optimizedJourneys.sort((a, b) => {
    const scoreA = a.optimization?.score ?? 0;
    const scoreB = b.optimization?.score ?? 0;
    if (Math.abs(scoreB - scoreA) > 1e-4) {
      return scoreB - scoreA;
    }
    if (a.totalPrice !== b.totalPrice) {
      return a.totalPrice - b.totalPrice;
    }
    return a.totalDurationMinutes - b.totalDurationMinutes;
  });

  return optimizedJourneys;
}
