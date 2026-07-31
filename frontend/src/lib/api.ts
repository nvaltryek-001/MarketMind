import axios, { AxiosError } from "axios";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 60000,
});

// ---------------------------------------------------------------------------
// Types — matching the FastAPI backend exactly
// ---------------------------------------------------------------------------

export interface AgentStatus {
  agent_name: string;
  status: "pending" | "running" | "completed" | "failed";
  signal: "BUY" | "SELL" | "HOLD" | null;
  confidence: number | null;
  reasoning: string | null;
  data: Record<string, unknown> | null;
  completed_at: string | null;
}

export interface SynthesisResult {
  symbol: string;
  final_verdict: "BUY" | "SELL" | "HOLD";
  overall_confidence: number;
  price_target_pct: number;
  summary: string;
  detailed_report: string;
  agent_weights: Record<string, number>;
  logic_map: Array<{
    agent: string;
    signal: string;
    weight: number;
    score?: number;
    confidence?: number;
    weighted_score?: number;
    contribution?: number;
    triggers?: string[];
  }>;
  card_data?: Record<
    string,
    {
      agent: "technical" | "fundamental" | "sentiment" | "risk" | "ml_prediction";
      verdict: "BUY" | "HOLD" | "SELL" | "INSUFFICIENT_DATA";
      score: number;
      weight: number;
      weighted_score: number;
      triggers: string[];
      confidence: number;
    }
  >;
  conflict_notes: string | null;
  generated_at: string;
}

/**
 * Backend RunStatus has agents as a FLAT dict with keys like "technical_RELIANCE".
 * We transform this to nested structure in getRunStatus().
 */
export interface RunStatusRaw {
  run_id: string;
  symbols: string[];
  status: "running" | "completed" | "failed";
  agents: Record<string, AgentStatus>;
  results: Record<string, SynthesisResult>;
  started_at: string;
  completed_at: string | null;
}

/**
 * Frontend-friendly RunStatus with agents nested by symbol.
 */
export interface RunStatus {
  run_id: string;
  symbols: string[];
  status: "running" | "completed" | "failed";
  agents: Record<string, Record<string, AgentStatus>>;
  results: Record<string, SynthesisResult>;
  started_at: string;
  completed_at: string | null;
}

export interface AnalysisRequest {
  symbols: string[];
}

export interface RecentRun {
  run_id: string;
  symbols: string[];
  status: string;
  started_at: string;
  completed_at: string | null;
}

export interface ReportResponse {
  run_id: string;
  symbol: string;
  verdict: string;
  confidence: number;
  summary: string;
  detailed_report: string;
  generated_at: string;
}

export interface EDAResult {
  symbol: string;
  returns_distribution: {
    mean: number;
    median: number;
    std: number;
    skewness: number;
    kurtosis: number;
    min: number;
    max: number;
    is_normal: boolean;
    percentile_25: number;
    percentile_75: number;
  };
  outliers: Array<{
    date: string;
    value: number;
    z_score: number;
    event_type: string;
  }>;
  volatility_regime: {
    regime: string;
    current_percentile: number;
    avg_daily_move_pct: number;
    regime_started_approx: string;
  };
  returns_histogram: { bins: number[]; counts: number[] };
  rolling_volatility_30d: { dates: string[]; values: number[] };
  volume_ma_ratio: { dates: string[]; values: number[] };
  price_vs_sma: {
    dates: string[];
    price: number[];
    sma50: number[];
    sma200: number[];
  };
  key_insights: string[];
}

export interface MultiStockEDA {
  run_id: string;
  symbols: string[];
  individual_eda: Record<string, EDAResult>;
  correlation_matrix: Array<{
    symbol_a: string;
    symbol_b: string;
    correlation: number;
    relationship: string;
  }>;
  correlation_grid: { symbols: string[]; matrix: number[][] };
  portfolio_summary: string;
}

export interface MLPrediction {
  symbol: string;
  prediction_horizon: string;
  regime: "bull" | "bear" | "sideways";
  predicted_direction: "UP" | "DOWN" | "SIDEWAYS";
  prediction_confidence: number;
  feature_importances: Array<{
    feature_name: string;
    importance: number;
    category: string;
  }>;
  model_metrics: {
    accuracy: number;
    precision: number;
    recall: number;
    f1_score: number;
    confusion_matrix: number[][];
    class_labels: string[];
    training_samples: number;
    test_samples: number;
  };
  model_name: string;
  feature_count: number;
  signal: string;
  reasoning: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    if (err.response?.data?.detail) {
      return String(err.response.data.detail);
    }
    if (err.message) {
      return err.message;
    }
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "An unknown error occurred";
}

/**
 * Transform the backend's flat agent dict (keys like "technical_RELIANCE")
 * into a nested dict: { "RELIANCE": { "technical": AgentStatus, ... } }
 */
function transformAgents(
  flatAgents: Record<string, AgentStatus>,
  symbols: string[]
): Record<string, Record<string, AgentStatus>> {
  const nested: Record<string, Record<string, AgentStatus>> = {};

  // Initialize empty dicts for each symbol
  for (const sym of symbols) {
    nested[sym] = {};
  }

  // Parse keys: "agent_name_SYMBOL" — but agent_name can have underscores
  // The backend uses key = f"{agent_name}_{symbol}"
  for (const [key, agentStatus] of Object.entries(flatAgents)) {
    // The AgentStatus has .agent_name which we can use to extract the symbol
    const agentName = agentStatus.agent_name;
    // key = "agent_name_SYMBOL", so symbol = key.slice(agentName.length + 1)
    const symbol = key.slice(agentName.length + 1);

    if (!nested[symbol]) {
      nested[symbol] = {};
    }
    nested[symbol][agentName] = agentStatus;
  }

  return nested;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function startAnalysis(
  symbols: string[]
): Promise<{ run_id: string }> {
  try {
    const payload: AnalysisRequest = { symbols };
    const response = await apiClient.post<{
      run_id: string;
      status: string;
      message: string;
    }>("/analyze", payload);
    return { run_id: response.data.run_id };
  } catch (err) {
    throw new Error(extractErrorMessage(err));
  }
}

export async function getRunStatus(runId: string): Promise<RunStatus> {
  try {
    const response = await apiClient.get<RunStatusRaw>(`/status/${runId}`);
    const raw = response.data;

    // Transform flat agents to nested structure
    return {
      ...raw,
      agents: transformAgents(raw.agents, raw.symbols),
    };
  } catch (err) {
    throw new Error(extractErrorMessage(err));
  }
}

export async function getRecentRuns(): Promise<RecentRun[]> {
  try {
    const response = await apiClient.get<RecentRun[]>("/runs");
    return response.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err));
  }
}

export async function getReport(
  runId: string,
  symbol: string
): Promise<string> {
  try {
    const response = await apiClient.get<ReportResponse>(
      `/report/${runId}/${symbol}`
    );
    return response.data.detailed_report;
  } catch (err) {
    throw new Error(extractErrorMessage(err));
  }
}

export async function getEDA(runId: string): Promise<MultiStockEDA> {
  try {
    const response = await apiClient.get<MultiStockEDA>(`/eda/${runId}`);
    return response.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err));
  }
}

export async function getMLPrediction(
  runId: string,
  symbol: string
): Promise<MLPrediction> {
  try {
    const response = await apiClient.get<MLPrediction>(`/ml/${runId}/${symbol}`);
    return response.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err));
  }
}
