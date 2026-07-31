"use client";

import { useState, useEffect, useMemo } from "react";
import { useParams } from "next/navigation";
import * as api from "@/lib/api";
import type { RunStatus } from "@/lib/api";
import IntelligenceFeed from "@/components/IntelligenceFeed";
import ChartRoom from "@/components/warroom/ChartRoom";
import VerdictPanel from "@/components/VerdictPanel";
import EvidenceTrail from "@/components/EvidenceTrail";
import { OHLCVPoint, AgentSignal } from "@/components/charts/CandlestickChart";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface IngestionPayload {
  dates: string[];
  opens: number[];
  highs: number[];
  lows: number[];
  closes: number[];
  volumes: number[];
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number");
}

function isIngestionPayload(value: unknown): value is IngestionPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Record<string, unknown>;
  return (
    isStringArray(payload.dates) &&
    isNumberArray(payload.opens) &&
    isNumberArray(payload.highs) &&
    isNumberArray(payload.lows) &&
    isNumberArray(payload.closes) &&
    isNumberArray(payload.volumes)
  );
}

function extractCriticChallenges(data: unknown): string[] {
  if (!data || typeof data !== "object") return [];
  const challenges = (data as { challenges?: unknown }).challenges;
  if (!Array.isArray(challenges)) return [];
  return challenges.filter((item): item is string => typeof item === "string");
}

export default function WarRoomPage() {
  const params = useParams();
  const runId = params.runId as string;

  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [activeSymbol, setActiveSymbol] = useState<string>("");

  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);
  
  useEffect(() => {
    // We use EventSource to trigger status refetches
    const sseUrl = `${API_BASE_URL}/stream/${runId}`;

    const updateStatus = () => {
      api.getRunStatus(runId).then((rs) => {
        setRunStatus(rs);
        setActiveSymbol((prev) => (!prev && rs.symbols.length > 0 ? rs.symbols[0] : prev));
      }).catch(console.error);
    };

    // Fetch status immediately on mount
    updateStatus();

    const source = new EventSource(sseUrl);

    source.addEventListener("status", () => {
      updateStatus();
    });

    source.addEventListener("done", () => {
      source.close();
      updateStatus();
    });

    source.addEventListener("error", () => {
      source.close();
    });

    return () => {
      source.close();
    };
  }, [runId]);

  const chartData = useMemo<OHLCVPoint[]>(() => {
    if (!activeSymbol || !runStatus) return [];

    const ingestionAgent = runStatus.agents[activeSymbol]?.["data_ingestion"];
    if (!isIngestionPayload(ingestionAgent?.data)) return [];

    const d = ingestionAgent.data;
    const length = Math.min(
      d.dates.length,
      d.opens.length,
      d.highs.length,
      d.lows.length,
      d.closes.length,
      d.volumes.length
    );

    const mapped: OHLCVPoint[] = [];
    for (let i = 0; i < length; i++) {
      mapped.push({
        time: d.dates[i],
        open: d.opens[i],
        high: d.highs[i],
        low: d.lows[i],
        close: d.closes[i],
        volume: d.volumes[i],
      });
    }
    return mapped;
  }, [activeSymbol, runStatus]);

  const synthesis = runStatus?.results[activeSymbol];
  const logicMap = useMemo(() => {
    const orderedAgents = [
      "technical",
      "fundamental",
      "sentiment",
      "risk",
      "ml_prediction",
    ];

    const cardData = synthesis?.card_data;
    if (
      cardData &&
      typeof cardData === "object" &&
      Object.keys(cardData).length > 0
    ) {
      return orderedAgents
        .map((agentName) => {
          const rawAgent = cardData[agentName];
          if (!rawAgent || typeof rawAgent !== "object") {
            return null;
          }

          const agentData = rawAgent as Record<string, unknown>;
          const score = typeof agentData.score === "number" ? agentData.score : 0;
          const weight = typeof agentData.weight === "number" ? agentData.weight : 0;
          const confidence =
            typeof agentData.confidence === "number" ? agentData.confidence : 0;
          const weightedScore =
            typeof agentData.weighted_score === "number"
              ? agentData.weighted_score
              : score * weight;

          const rawTriggers = Array.isArray(agentData.triggers)
            ? agentData.triggers
            : [];
          const triggers = rawTriggers
            .filter((item): item is string => typeof item === "string")
            .map((item) => item.trim())
            .filter(Boolean);

          return {
            agent: agentName,
            signal:
              typeof agentData.verdict === "string" ? agentData.verdict : "HOLD",
            weight,
            score,
            confidence,
            weightedScore,
            contribution: weightedScore,
            triggers,
          };
        })
        .filter(
          (
            item
          ): item is {
            agent: string;
            signal: string;
            weight: number;
            score: number;
            confidence: number;
            weightedScore: number;
            contribution: number;
            triggers: string[];
          } => item !== null
        );
    }

    const rawMap = synthesis?.logic_map || [];
    return rawMap.map((row) => {
      const record = row as Record<string, unknown>;
      const rawTriggers =
        (Array.isArray(record.triggers) && record.triggers) ||
        (Array.isArray(record.key_triggers) && record.key_triggers) ||
        (Array.isArray(record.specific_triggers) && record.specific_triggers) ||
        [];

      const triggers = rawTriggers
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter(Boolean);

      const weight =
        typeof record.weight === "number"
          ? record.weight
          : typeof record.weight_applied === "number"
            ? record.weight_applied
            : 0;
      const score = typeof record.score === "number" ? record.score : 0;
      const confidence = typeof record.confidence === "number" ? record.confidence : 0;
      const weightedScore =
        typeof record.weighted_score === "number"
          ? record.weighted_score
          : typeof record.contribution === "number"
            ? record.contribution
            : score * weight;

      return {
        agent: typeof record.agent === "string" ? record.agent : "unknown",
        signal:
          typeof record.signal === "string"
            ? record.signal
            : typeof record.verdict === "string"
              ? record.verdict
              : "HOLD",
        weight,
        score,
        confidence,
        weightedScore,
        contribution: weightedScore,
        triggers,
      };
    });
  }, [synthesis]);
  const criticAgent = runStatus?.agents[activeSymbol]?.["critic"];
  const criticChallenges = extractCriticChallenges(criticAgent?.data);

  // Generate signals based on logic map, anchoring them to the latest date
  const latestDate = chartData.length > 0 ? chartData[chartData.length - 1].time : "";
  const signals: AgentSignal[] = latestDate ? logicMap.map((lm) => ({
    agent: lm.agent,
    signal: lm.signal,
    date: latestDate,
  })) : [];

  return (
    <div className="flex flex-col h-[calc(100vh-48px)]">
      {/* Ticker Selector if multiple */}
      {runStatus && runStatus.symbols.length > 1 && (
        <div className="flex bg-[var(--color-war-border)] h-8 border-b border-[var(--color-war-border)] gap-px">
          {runStatus.symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setActiveSymbol(sym)}
              className={`px-6 h-full font-mono text-[10px] uppercase tracking-widest transition-colors ${
                activeSymbol === sym
                  ? "bg-[var(--color-war-text)] text-white"
                  : "bg-[var(--color-war-bg)] text-[var(--color-war-muted)] hover:bg-[#e8e4db]"
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
      )}

      {/* Main 3-Panel Layout */}
      <div className="flex-1 flex w-full overflow-hidden bg-[var(--color-war-border)] gap-px">
        {/* LEFT PANEL (28%) */}
        <div className="w-[28%] bg-black h-full overflow-hidden">
          <IntelligenceFeed runId={runId} />
        </div>

        {/* CENTER PANEL (44%) */}
        <div className="w-[44%] bg-[var(--color-war-bg)] h-full overflow-hidden flex flex-col">
          <div className="flex-1 overflow-hidden">
            <ChartRoom 
              symbol={activeSymbol || "..."} 
              data={chartData} 
              signals={signals} 
              hoveredAgent={hoveredAgent} 
            />
          </div>
          <EvidenceTrail 
            logicMap={logicMap}
            criticChallenges={criticChallenges}
            hoveredAgent={hoveredAgent}
            onHoverAgent={setHoveredAgent}
          />
        </div>

        {/* RIGHT PANEL (28%) */}
        <div className="w-[28%] bg-[var(--color-war-bg)] h-full overflow-hidden">
          <VerdictPanel
            symbol={activeSymbol || "..."}
            synthesis={synthesis || null}
            agents={runStatus?.agents[activeSymbol] || {}}
          />
        </div>
      </div>
    </div>
  );
}
