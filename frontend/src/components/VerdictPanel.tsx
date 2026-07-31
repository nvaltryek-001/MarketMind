"use client";

import { useState, useMemo } from "react";
import type { SynthesisResult, AgentStatus } from "@/lib/api";

interface VerdictPanelProps {
  symbol: string;
  synthesis: SynthesisResult | null;
  agents: Record<string, AgentStatus>;
}

type SignalVerdict = "BUY" | "HOLD" | "SELL";

type AgentSynthesisSignal = {
  verdict: SignalVerdict | "INSUFFICIENT_DATA";
  weight: number;
  confidence: number;
};

function toRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function readStringField(
  value: Record<string, unknown> | null,
  key: string
): string | null {
  if (!value) return null;
  const raw = value[key];
  return typeof raw === "string" ? raw : null;
}

function readNumberField(
  value: Record<string, unknown> | null,
  key: string
): number | null {
  if (!value) return null;
  const raw = value[key];
  return typeof raw === "number" ? raw : null;
}

function clampUnitInterval(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function normalizeVerdict(
  value: string | null | undefined
): SignalVerdict | "INSUFFICIENT_DATA" {
  const verdict = (value || "").toUpperCase();
  if (verdict === "INSUFFICIENT_DATA") return "INSUFFICIENT_DATA";
  if (verdict === "BUY" || verdict === "SELL" || verdict === "HOLD") return verdict;
  return "HOLD";
}

function isSignalVerdict(value: string): value is SignalVerdict {
  return value === "BUY" || value === "HOLD" || value === "SELL";
}

function computeWeightedVerdict(agentSignals: AgentSynthesisSignal[]): SignalVerdict {
  const verdictWeights: Record<SignalVerdict, number> = {
    BUY: 0,
    HOLD: 0,
    SELL: 0,
  };

  for (const agent of agentSignals) {
    if (agent.verdict === "INSUFFICIENT_DATA") continue;
    verdictWeights[agent.verdict] += Math.max(0, agent.weight);
  }

  const maxWeight = Math.max(
    verdictWeights.BUY,
    verdictWeights.HOLD,
    verdictWeights.SELL
  );
  if (maxWeight <= 0) {
    return "HOLD";
  }

  const winners = (Object.entries(verdictWeights) as Array<[SignalVerdict, number]>)
    .filter(([, weight]) => Math.abs(weight - maxWeight) < 1e-9)
    .map(([verdict]) => verdict);

  if (winners.length === 1) {
    return winners[0];
  }

  if (winners.includes("HOLD")) return "HOLD";
  if (winners.includes("BUY")) return "BUY";
  return "SELL";
}

function computeSynthesisConfidence(
  agentSignals: AgentSynthesisSignal[],
  majorityVerdict?: SignalVerdict
): number {
  const valid = agentSignals.filter(
    (agent) => agent.verdict !== "INSUFFICIENT_DATA" && agent.weight > 0
  );
  if (valid.length === 0) {
    return 0.1;
  }

  const totalWeight = valid.reduce((sum, agent) => sum + agent.weight, 0);
  if (totalWeight <= 0) {
    return 0.1;
  }

  let selectedVerdict: SignalVerdict;
  if (majorityVerdict) {
    selectedVerdict = majorityVerdict;
  } else {
    const counts: Record<SignalVerdict, number> = { BUY: 0, HOLD: 0, SELL: 0 };
    for (const agent of valid) {
      counts[agent.verdict] += 1;
    }
    selectedVerdict = (Object.entries(counts) as Array<[SignalVerdict, number]>).sort(
      (a, b) => b[1] - a[1]
    )[0][0];
  }

  const agreeingWeight = valid
    .filter((agent) => agent.verdict === selectedVerdict)
    .reduce((sum, agent) => sum + agent.weight, 0);
  const agreementRatio = agreeingWeight / totalWeight;

  const avgConfidence =
    valid.reduce(
      (sum, agent) => sum + clampUnitInterval(agent.confidence) * agent.weight,
      0
    ) / totalWeight;

  const confidence = agreementRatio * 0.6 + avgConfidence * 0.4;
  return Math.round(clampUnitInterval(confidence) * 1000) / 1000;
}

function computeDirectionArrow(
  verdict: SignalVerdict,
  agentSignals: AgentSynthesisSignal[]
): "↗" | "↘" | "→" {
  const conflictWeights: Record<SignalVerdict, number> = {
    BUY: 0,
    HOLD: 0,
    SELL: 0,
  };

  for (const agent of agentSignals) {
    if (agent.verdict === "INSUFFICIENT_DATA") continue;
    if (agent.verdict === verdict) continue;
    conflictWeights[agent.verdict] += Math.max(0, agent.weight);
  }

  const highestConflict = (Object.entries(conflictWeights) as Array<
    [SignalVerdict, number]
  >).sort((a, b) => b[1] - a[1])[0];

  if (!highestConflict || highestConflict[1] <= 0) {
    return "→";
  }
  if (highestConflict[0] === "SELL") {
    return "↘";
  }
  if (highestConflict[0] === "BUY") {
    return "↗";
  }
  return "→";
}

export default function VerdictPanel({ symbol, synthesis, agents }: VerdictPanelProps) {
  const baseWeights = useMemo<Record<string, number>>(() => {
    if (!synthesis?.agent_weights) return {};

    const initial: Record<string, number> = {};
    for (const [k, v] of Object.entries(synthesis.agent_weights)) {
      initial[k] = v * 100;
    }
    return initial;
  }, [synthesis]);

  const [customWeights, setCustomWeights] = useState<Record<string, number> | null>(null);

  const effectiveCustomWeights = useMemo(() => {
    if (!customWeights) return null;
    const baseKeys = Object.keys(baseWeights);
    if (baseKeys.length === 0) return null;
    const hasAllKeys = baseKeys.every((k) => Object.prototype.hasOwnProperty.call(customWeights, k));
    return hasAllKeys ? customWeights : null;
  }, [customWeights, baseWeights]);

  const weights = effectiveCustomWeights ?? baseWeights;
  const isCustom = effectiveCustomWeights !== null;

  const mlData = toRecord(agents["ml"]?.data) ?? toRecord(agents["ml_prediction"]?.data);
  const mlModelMetrics = toRecord(mlData ? mlData.model_metrics : null);
  const mlTrainingSamplesRaw = readNumberField(mlModelMetrics, "training_samples");
  const mlTrainingSamples = mlTrainingSamplesRaw !== null ? Math.max(0, Math.round(mlTrainingSamplesRaw)) : 0;
  const mlVerdict = (
    readStringField(mlData, "verdict") ||
    readStringField(mlData, "signal") ||
    ""
  ).toUpperCase();
  const mlModelValidRaw = mlData ? mlData.model_valid : null;
  const mlModelValid = typeof mlModelValidRaw === "boolean" ? mlModelValidRaw : true;
  const isMlSuppressed =
    !mlModelValid || mlVerdict === "INSUFFICIENT_DATA" || mlVerdict === "SUPPRESSED";

  // Constrained weight editor logic
  const handleWeightChange = (agent: string, newTarget: number) => {
    if (Object.keys(weights).length === 0) return;

    setCustomWeights((prev) => {
      const source = prev ?? weights;
      const lockedAgents = new Set<string>(
        isMlSuppressed ? ["ml_prediction"] : []
      );
      if (lockedAgents.has(agent)) {
        return source;
      }

      const oldVal = source[agent] || 0;
      let delta = newTarget - oldVal;

      const others = Object.keys(source).filter(
        (k) => k !== agent && !lockedAgents.has(k)
      );
      const remainingSum = others.reduce((sum, k) => sum + source[k], 0);

      // Bound delta so we don't drop others below 0
      if (delta > remainingSum) delta = remainingSum;

      const newWeights = { ...source };
      newWeights[agent] = oldVal + delta;

      for (const k of others) {
        if (remainingSum <= 0) {
          newWeights[k] = 0;
        } else {
          newWeights[k] -= delta * (source[k] / remainingSum);
        }
      }

      return newWeights;
    });
  };

  const regime = (readStringField(mlData, "regime") || "UNKNOWN").toUpperCase();

  const riskData = toRecord(agents["risk"]?.data) ?? toRecord(agents["risk_assessment"]?.data);
  const riskLevel = (readStringField(riskData, "risk_level") || "UNKNOWN").toUpperCase();

  const macroData = toRecord(agents["macro"]?.data) ?? toRecord(agents["macro_flow"]?.data);
  const macroSignal = readStringField(macroData, "macro_signal")?.toUpperCase();
  const fiiNet = readNumberField(macroData, "fii_net_5d");

  const activeWeightTotal = useMemo(() => {
    return Object.entries(weights).reduce((sum, [agentName, weight]) => {
      if (isMlSuppressed && agentName === "ml_prediction") {
        return sum;
      }
      return sum + weight;
    }, 0);
  }, [weights, isMlSuppressed]);

  const synthesisSignals = useMemo<AgentSynthesisSignal[]>(() => {
    if (!synthesis) return [];

    const result: AgentSynthesisSignal[] = [];
    for (const [agentName, weightPct] of Object.entries(weights)) {
      const status = agents[agentName];
      const statusData = toRecord(status?.data);
      const cardEntry = synthesis.card_data?.[agentName];

      let verdictRaw: string | null =
        (typeof cardEntry?.verdict === "string" ? cardEntry.verdict : null) ||
        readStringField(statusData, "verdict") ||
        readStringField(statusData, "signal") ||
        status?.signal ||
        "HOLD";

      if (agentName === "risk") {
        const riskSignalFromLevel = (
          readStringField(statusData, "risk_level") || "MEDIUM"
        ).toUpperCase();
        verdictRaw =
          verdictRaw ||
          (riskSignalFromLevel === "LOW"
            ? "BUY"
            : riskSignalFromLevel === "HIGH"
            ? "SELL"
            : "HOLD");
      }

      const verdict =
        agentName === "ml_prediction" && isMlSuppressed
          ? "INSUFFICIENT_DATA"
          : normalizeVerdict(verdictRaw);

      const confidenceRaw =
        typeof cardEntry?.confidence === "number"
          ? cardEntry.confidence
          : agentName === "ml_prediction"
          ? (readNumberField(statusData, "prediction_confidence") ??
            readNumberField(statusData, "confidence") ??
            status?.confidence ??
            0)
          : agentName === "risk"
          ? (readNumberField(statusData, "confidence") ?? status?.confidence ?? 0.7)
          : (readNumberField(statusData, "confidence") ?? status?.confidence ?? 0);

      result.push({
        verdict,
        weight: Math.max(0, weightPct / 100),
        confidence: clampUnitInterval(confidenceRaw),
      });
    }

    return result;
  }, [synthesis, agents, weights, isMlSuppressed]);

  // Determine actual confidence using either backend or local recalculation.
  const recalculated = useMemo(() => {
    if (!synthesis || !isCustom) {
      return {
        verdict: synthesis?.final_verdict || "PENDING",
        confidence: clampUnitInterval(synthesis?.overall_confidence || 0),
      };
    }

    const verdict = computeWeightedVerdict(synthesisSignals);
    const confidence = computeSynthesisConfidence(synthesisSignals, verdict);
    return { verdict, confidence };
  }, [synthesis, synthesisSignals, isCustom]);

  const verdictArrow = useMemo(() => {
    if (!isSignalVerdict(recalculated.verdict)) {
      return null;
    }
    return computeDirectionArrow(recalculated.verdict, synthesisSignals);
  }, [recalculated.verdict, synthesisSignals]);

  const confidenceDisplay = useMemo(() => {
    const computedConfidence = clampUnitInterval(recalculated.confidence);
    const minimumDisplayedConfidence = 0.25;
    const floored = computedConfidence < minimumDisplayedConfidence;
    return {
      computedConfidence,
      displayConfidence: Math.max(computedConfidence, minimumDisplayedConfidence),
      label: floored
        ? "< 25%"
        : `${(Math.max(computedConfidence, minimumDisplayedConfidence) * 100).toFixed(1)}%`,
      isFloored: floored,
    };
  }, [recalculated.confidence]);

  const getVerdictLabelColor = (v: string) => {
    if (v === "BUY") return "text-[var(--color-war-buy)]";
    if (v === "SELL") return "text-[var(--color-war-sell)]";
    return "text-[var(--color-war-text)]";
  };

  const getVerdictBadgeColor = (v: string) => {
    if (v === "BUY") return "bg-[var(--color-war-buy)] text-white";
    if (v === "SELL") return "bg-[var(--color-war-sell)] text-white";
    return "bg-[var(--color-war-text)] text-white";
  };

  return (
    <div className="h-full flex flex-col border-l border-[var(--color-war-border)] bg-[#F5F2EC] overflow-y-auto">
      {/* 1. Newspaper-style header */}
      <div className="p-8 pb-6 border-b-2 border-[var(--color-war-text)]">
        <div className="flex justify-between items-center mb-4">
          <span className="font-mono text-[10px] uppercase tracking-widest text-[#666]">
            {new Date().toLocaleDateString("en-GB").replace(/\//g, ".")}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-[#666]">
            NSE INTELLIGENCE REPORT
          </span>
        </div>

        <h1 className="font-serif text-[48px] font-black text-[var(--color-war-text)] leading-tight mb-4 tracking-tighter">
          {symbol}:{" "}
          <span className={getVerdictLabelColor(recalculated.verdict)}>
            {recalculated.verdict}
          </span>
          {verdictArrow ? (
            <span className="ml-3 align-middle text-[0.6em] font-sans font-semibold text-[#666]">
              {verdictArrow}
            </span>
          ) : null}
        </h1>

        <div className="font-mono text-[11px] uppercase tracking-wider text-[var(--color-war-text)] flex flex-wrap gap-x-4 gap-y-2 border-t border-[var(--color-war-border)] pt-4">
          <span>
            Confidence: <strong className="font-sans font-black">{confidenceDisplay.label}</strong>
          </span>
          <span className="text-[#ccc]">|</span>
          <span>Regime: <strong className="font-sans font-black">{regime}</strong></span>
          <span className="text-[#ccc]">|</span>
          <span>Risk: <strong className="font-sans font-black">{riskLevel}</strong></span>
        </div>

        {confidenceDisplay.isFloored && (
          <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-[#666]">
            Computed confidence below 25%; displayed as &lt; 25%.
          </p>
        )}

        {confidenceDisplay.computedConfidence < 0.35 && (
          <div className="confidence-warn">
            LOW CONVICTION — insufficient signal alignment. Do not act on this signal alone.
          </div>
        )}
      </div>

      <div className="p-8 space-y-8 flex-1">
        {/* 3. Macro warning bar */}
        {macroSignal === "BEARISH" && (
          <div className="bg-[#facc15] border border-[#ca8a04] px-4 py-3 font-mono text-xs font-bold text-[#854d0e] flex items-center shadow-sm">
            ⚠ MACRO WARNING: FIIs net sold ₹{fiiNet?.toFixed(2)}Cr in last 5 days
          </div>
        )}

        {/* 2. Weight editor */}
        <div className="border border-[var(--color-war-border)] bg-[#fdfdfc] p-6 shadow-sm">
          <div className="flex justify-between items-end mb-6 border-b border-[var(--color-war-border)] pb-2">
            <h3 className="font-serif text-lg font-bold text-[var(--color-war-text)] tracking-tight">
              Conviction Engine (What-If)
            </h3>
            <span className="font-mono text-[10px] uppercase tracking-widest text-[#888]">
              {isCustom ? "Scenario: Custom weights" : "Default weights"}
            </span>
          </div>

          <div className="space-y-4">
            {Object.keys(weights).length === 0 ? (
              <p className="font-mono text-xs text-[var(--color-war-muted)]">Awaiting agent weights...</p>
            ) : null}

            {Object.entries(weights).map(([agentName, weight]) => {
              const isMlSlider = agentName === "ml_prediction";
              const isDisabled = isMlSlider && isMlSuppressed;

              return (
              <div key={agentName} className="flex flex-col gap-1">
                <div className="flex justify-between items-center text-[10px] font-mono uppercase tracking-widest">
                  <span className="font-bold text-[var(--color-war-text)]">{agentName}</span>
                  <span className="text-[var(--color-war-muted)]">{isDisabled ? "SUPPRESSED" : `${weight.toFixed(0)}%`}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={weight}
                  disabled={isDisabled}
                  onChange={(e) => handleWeightChange(agentName, parseFloat(e.target.value))}
                  className={`w-full appearance-none h-[2px] bg-[var(--color-war-border)] outline-none ${isDisabled ? "opacity-30 cursor-not-allowed" : "cursor-pointer"}`}
                  style={{
                    background: isDisabled
                      ? "var(--color-war-border)"
                      : `linear-gradient(to right, var(--color-war-text) 0%, var(--color-war-text) ${weight}%, var(--color-war-border) ${weight}%, var(--color-war-border) 100%)`
                  }}
                />

                {isDisabled && (
                  <p className="text-[10px] text-[#666] italic leading-snug">
                    Model suppressed — insufficient training data ({mlTrainingSamples} samples)
                  </p>
                )}
              </div>
              );
            })}

            {isMlSuppressed && (
              <div className="pt-1">
                <p className="font-mono text-[9px] uppercase tracking-widest text-[var(--color-war-muted)]">
                  Active weight total (excluding ML): {activeWeightTotal.toFixed(0)}%
                </p>
                <p className="font-mono text-[9px] text-[var(--color-war-muted)]">
                  weights redistribute when ML suppressed
                </p>
              </div>
            )}
          </div>

          <div className="mt-6 flex justify-between items-center bg-[#F5F2EC] p-3 border border-[var(--color-war-border)]">
            <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-war-text)]">
              Real-time Output:
            </span>
            <span className={`px-2 py-1 font-mono text-[11px] font-bold uppercase tracking-wider ${getVerdictBadgeColor(recalculated.verdict)}`}>
              {recalculated.verdict} / {confidenceDisplay.label}
            </span>
          </div>
          
          {isCustom && (
            <button 
              onClick={() => setCustomWeights(null)}
              className="mt-3 w-full border border-[var(--color-war-border)] py-1.5 font-mono text-[9px] uppercase tracking-widest text-[var(--color-war-muted)] hover:bg-[#e8e4db] transition-colors"
            >
              Reset to Base Defaults
            </button>
          )}
        </div>

        {/* 4. Mock Backtest Accuracy Badge */}
        <div className="border border-[var(--color-war-border)] bg-[#fdfdfc] p-4 text-center">
          <span className="font-mono text-xs uppercase tracking-widest text-[var(--color-war-muted)]">
            AI accuracy on {symbol}: <strong className="text-[var(--color-war-text)]">7/10 past predictions correct</strong>
          </span>
        </div>
      </div>
    </div>
  );
}
