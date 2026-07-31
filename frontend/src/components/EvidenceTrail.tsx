"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";

export interface EvidenceTrailProps {
  logicMap: Array<{
    agent: string;
    signal: string;
    weight: number;
    score?: number;
    confidence?: number;
    weightedScore?: number;
    contribution?: number;
    triggers?: string[];
  }>;
  criticChallenges: string[];
  hoveredAgent: string | null;
  onHoverAgent: (agent: string | null) => void;
}

export default function EvidenceTrail({
  logicMap,
  criticChallenges,
  hoveredAgent,
  onHoverAgent,
}: EvidenceTrailProps) {
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  const getSignalColor = (signal: string) => {
    if (signal === "BUY") return "text-[var(--color-war-buy)]";
    if (signal === "SELL") return "text-[var(--color-war-sell)]";
    if (signal === "INSUFFICIENT_DATA" || signal === "SUPPRESSED") return "text-slate-500";
    return "text-[var(--color-war-text)]";
  };

  const getBorderColor = (signal: string) => {
    if (signal === "BUY") return "border-[var(--color-war-buy)]";
    if (signal === "SELL") return "border-[var(--color-war-sell)]";
    if (signal === "INSUFFICIENT_DATA" || signal === "SUPPRESSED") return "border-slate-300";
    return "border-[var(--color-war-border)]";
  };

  return (
    <div className="flex flex-col bg-[var(--color-war-bg)] border-t border-[var(--color-war-border)]">
      {/* Evidence Strip */}
      <div className="signal-cards-row flex overflow-x-auto p-4 gap-4 items-stretch">
        {logicMap.length === 0 ? (
          <div className="w-full flex items-center justify-center font-mono text-xs text-[var(--color-war-muted)] uppercase tracking-wider h-full border border-dashed border-[var(--color-war-border)]">
            Awaiting logic map synthesis...
          </div>
        ) : (
          logicMap.map((lm, idx) => {
            const isHovered = hoveredAgent === lm.agent;
            const isExpanded = expandedAgent === lm.agent;
            const isSuppressed = lm.signal === "INSUFFICIENT_DATA" || lm.signal === "SUPPRESSED";
            const score = typeof lm.score === "number" ? lm.score : 0;
            const confidence = typeof lm.confidence === "number" ? lm.confidence : 0;
            const weightedScore =
              typeof lm.weightedScore === "number"
                ? lm.weightedScore
                : typeof lm.contribution === "number"
                  ? lm.contribution
                  : score * lm.weight;
            const agentData = lm;
            console.log(agentData);

            return (
              <div
                key={idx}
                onMouseEnter={() => onHoverAgent(lm.agent)}
                onMouseLeave={() => onHoverAgent(null)}
                onClick={() => setExpandedAgent(isExpanded ? null : lm.agent)}
                className={`signal-card min-w-[280px] flex-1 basis-0 h-auto flex flex-col border transition-all cursor-pointer ${
                  isHovered ? "ring-1 ring-offset-1 ring-[var(--color-war-text)]" : ""
                } ${getBorderColor(lm.signal)} ${isSuppressed ? "bg-slate-100 opacity-80" : "bg-[#fdfdfc]"}`}
              >
                <div className="evidence-header flex justify-between items-start p-3 border-b border-[var(--color-war-border)]">
                  <div className="flex flex-col gap-1">
                    <span className="evidence-agent font-sans font-bold text-[11px] uppercase tracking-widest text-[#444]">
                      {lm.agent}
                    </span>
                    <span className="evidence-weight font-mono text-[9px] text-[var(--color-war-muted)] uppercase tracking-wider">
                      {(lm.weight * 100).toFixed(0)}% weight
                    </span>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className={`evidence-signal font-mono text-xs font-bold ${getSignalColor(lm.signal)}`}>
                      {lm.signal}
                    </span>
                    <span className="font-mono text-[9px] text-[var(--color-war-muted)] uppercase tracking-wider">
                      score {score.toFixed(2)} | conf {(confidence * 100).toFixed(0)}%
                    </span>
                    {isSuppressed && (
                      <span className="font-mono text-[9px] uppercase tracking-wider text-slate-500">
                        Suppressed
                      </span>
                    )}
                    {weightedScore !== undefined && (
                      <span className="font-mono text-[9px] text-[var(--color-war-muted)]">
                        {(weightedScore > 0 ? "+" : "") + weightedScore.toFixed(2)} to score
                      </span>
                    )}
                  </div>
                </div>

                <div className="evidence-triggers triggers flex-1 overflow-visible p-3 font-serif text-sm text-black leading-snug">
                  <ul className="list-disc pl-4 space-y-1">
                    {lm.triggers && lm.triggers.length > 0 ? (
                      lm.triggers.map((t, tIdx) => <li key={tIdx}>{t}</li>)
                    ) : (
                      <li className="text-[var(--color-war-muted)] italic list-none -ml-4">No specific triggers exported.</li>
                    )}
                  </ul>
                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-dashed border-[var(--color-war-border)]">
                      <p className="font-mono text-[9px] uppercase tracking-widest text-[var(--color-war-muted)]">
                        RAW AGENT EXPORT: <br/> [DATA ENCRYPTED OR UNAVAILABLE FOR {lm.agent}]
                      </p>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Critic's Challenges */}
      {criticChallenges.length > 0 && (
        <div className="bg-[#fcf8f8] border-t border-[var(--color-war-sell)] p-4 max-h-[140px] overflow-y-auto">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-[var(--color-war-sell)]" />
            <h3 className="font-mono text-xs font-bold uppercase tracking-widest text-[var(--color-war-sell)]">
              CRITIC&apos;S CHALLENGES
            </h3>
          </div>
          <div className="flex gap-4 overflow-x-auto pb-2">
            {criticChallenges.map((challenge, cIdx) => (
              <div
                key={cIdx}
                className="min-w-[300px] w-[300px] bg-white border border-[var(--color-war-sell)] p-3 text-sm font-serif text-black leading-snug shrink-0"
              >
                {challenge}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
