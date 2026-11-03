export interface JourneyOptimizationMetrics {
  totalCost: number;
  durationMinutes: number;
  transferCount: number;
  comfortScore: number; // [0.0, 1.0]
  carbonKg: number;
}

export interface ObjectiveScoreContribution {
  raw: number;
  normalized: number;   // [0.0, 1.0]
  weight: number;       // [0.0, 1.0]
  contribution: number; // normalized * weight
}

export interface JourneyScoreBreakdown {
  cost: ObjectiveScoreContribution;
  duration: ObjectiveScoreContribution;
  comfort: ObjectiveScoreContribution;
  carbon: ObjectiveScoreContribution;
  transfers?: ObjectiveScoreContribution;
  totalScore: number;   // [0.0, 1.0]
}

export interface JourneyRecommendationExplanation {
  headline: string;
  reasons: string[];
  tradeoffs: string[];
  comparedAgainst?: string;
}

export interface OptimizedJourneyOutput {
  id: string;
  title: string;
  score: number;        // composite score [0.0, 1.0]
  scaledScore: number;  // 0 - 100
  category: string;
  isParetoOptimal: boolean;
  paretoRank: number;
  metrics: JourneyOptimizationMetrics;
  scoreBreakdown: JourneyScoreBreakdown;
  explanation: JourneyRecommendationExplanation;
}

export interface OptimizationWeights {
  cost: number;
  duration: number;
  comfort: number;
  carbon: number;
  transfers?: number;
}

export interface OptimizationResponse {
  recommendedJourneyId: string;
  totalCandidates: number;
  eligibleCandidates: number;
  paretoFrontierCount: number;
  journeys: OptimizedJourneyOutput[];
}
