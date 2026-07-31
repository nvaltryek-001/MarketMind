"use client";

import { useState, useEffect, useRef } from "react";
import type { AgentStatus } from "@/lib/api";

type AgentEvent = {
  id: string;
  timestamp: string;
  symbol: string;
  agent: string;
  status: "started" | "completed" | "failed";
  message: string;
  signal?: string;
  verdict?: string;
  tone: "neutral" | "green" | "amber" | "red";
};

type FilterType = "ALL" | "CONFLICTS" | "SIGNALS" | "DATA";

type StreamStatusPayload = {
  agents?: Record<string, AgentStatus>;
  results?: Record<string, { final_verdict?: string }>;
};

function formatMacroFlowMessage(data: Record<string, unknown> | null): string {
  const sourceRaw = typeof data?.source === "string" ? data.source.toLowerCase() : "";

  if (sourceRaw === "bse") {
    const fiiNet = typeof data?.fii_net === "number" ? data.fii_net : null;
    const diiNet = typeof data?.dii_net === "number" ? data.dii_net : null;

    const fiiTrendRaw = typeof data?.fii_5d_trend === "string" ? data.fii_5d_trend.toLowerCase() : "mixed";
    const diiTrendRaw = typeof data?.dii_5d_trend === "string" ? data.dii_5d_trend.toLowerCase() : "mixed";

    const fiiTrend = ["buying", "selling", "mixed"].includes(fiiTrendRaw) ? fiiTrendRaw : "mixed";
    const diiTrend = ["buying", "selling", "mixed"].includes(diiTrendRaw) ? diiTrendRaw : "mixed";

    const trend = fiiTrend === diiTrend ? fiiTrend : `FII ${fiiTrend}, DII ${diiTrend}`;
    const fiiText = fiiNet !== null ? fiiNet.toFixed(2) : "NA";
    const diiText = diiNet !== null ? diiNet.toFixed(2) : "NA";

    return `[MACRO] FII net: \u20b9${fiiText}Cr | DII net: \u20b9${diiText}Cr \u2014 ${trend}`;
  }

  const niftyReturn = typeof data?.nifty_5d_return === "number" ? data.nifty_5d_return : 0;
  const signalRaw = typeof data?.macro_signal === "string" ? data.macro_signal.toLowerCase() : "neutral";
  const signal = ["bullish", "bearish", "neutral"].includes(signalRaw) ? signalRaw : "neutral";

  return `[MACRO] Exchange APIs unavailable. Nifty 5D: ${niftyReturn.toFixed(2)}% \u2014 ${signal}`;
}

function signalToneClasses(tone: AgentEvent["tone"]): string {
  if (tone === "red") return "text-[var(--color-war-sell)]";
  if (tone === "amber") return "text-amber-700";
  if (tone === "green") return "text-emerald-700";
  return "text-[var(--color-war-text)]";
}

function rowToneClasses(tone: AgentEvent["tone"]): string {
  if (tone === "red") return "bg-[var(--color-war-sell)]/10 p-2 border border-[var(--color-war-sell)]";
  if (tone === "amber") return "bg-amber-100/60 p-2 border border-amber-500";
  if (tone === "green") return "bg-emerald-100/60 p-2 border border-emerald-500";
  return "";
}

function parseSymbolFromAgentKey(key: string, agentName: string): string {
  const prefix = `${agentName}_`;
  if (key.startsWith(prefix) && key.length > prefix.length) {
    return key.slice(prefix.length);
  }
  const lastUnderscore = key.lastIndexOf("_");
  if (lastUnderscore >= 0 && lastUnderscore < key.length - 1) {
    return key.slice(lastUnderscore + 1);
  }
  return "ALL";
}

// Typewriter Component
function TypewriterText({ text, speed = 40 }: { text: string; speed?: number }) {
  const [displayedText, setDisplayedText] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (currentIndex < text.length) {
      const timer = setTimeout(() => {
        setDisplayedText((prev) => prev + text[currentIndex]);
        setCurrentIndex((prev) => prev + 1);
      }, speed);
      return () => clearTimeout(timer);
    }
  }, [currentIndex, text, speed]);

  return <span>{displayedText}</span>;
}

export default function IntelligenceFeed({ runId }: { runId: string }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [filter, setFilter] = useState<FilterType>("ALL");
  const [isHovering, setIsHovering] = useState(false);
  
  const containerRef = useRef<HTMLDivElement>(null);
  const prevAgentsRef = useRef<Record<string, AgentStatus>>({});

  useEffect(() => {
    const sseUrl = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/stream/${runId}`;
    const source = new EventSource(sseUrl);

    source.addEventListener("status", (e) => {
      try {
        const raw = JSON.parse(e.data) as StreamStatusPayload;
        const agents = raw.agents ?? {};
        const results = raw.results ?? {};
        const newEvents: AgentEvent[] = [];

        for (const [key, agent] of Object.entries(agents)) {
          const prev = prevAgentsRef.current[key];
          
          if (!prev && agent.status === "pending") {
            continue; // Skip initial pending
          }

          if (prev?.status !== agent.status && agent.status) {
            let statusEnum: "started" | "completed" | "failed" = "started";
            let msg = `Agent initiated protocol: ${agent.agent_name}`;
            let tone: AgentEvent["tone"] = "neutral";
            const symbol = parseSymbolFromAgentKey(key, agent.agent_name);
            const finalVerdictRaw = results[symbol]?.final_verdict;
            const finalVerdict = typeof finalVerdictRaw === "string" ? finalVerdictRaw.toUpperCase() : null;
            const data = agent.data && typeof agent.data === "object"
              ? (agent.data as Record<string, unknown>)
              : null;
            const isMacroAgent = agent.agent_name.toLowerCase() === "macro";
            const dataVerdictRaw = data?.verdict;
            const dataVerdict = typeof dataVerdictRaw === "string" ? dataVerdictRaw.toUpperCase() : null;
            const modelValid = data?.model_valid;
            const isModelValid = typeof modelValid === "boolean" ? modelValid : true;
            const suppressionReasonRaw = data?.suppression_reason;
            const suppressionReason = typeof suppressionReasonRaw === "string" ? suppressionReasonRaw : null;
            const triggersRaw = data?.triggers;
            const triggers = Array.isArray(triggersRaw)
              ? triggersRaw.filter((t): t is string => typeof t === "string" && t.trim().length > 0)
              : [];
            const verdict = isMacroAgent ? undefined : dataVerdict || agent.signal || undefined;
            
            if (agent.status === "failed") {
              statusEnum = "failed";
              if (isMacroAgent) {
                msg = formatMacroFlowMessage(data);
                tone = "amber";
              } else {
                msg = agent.reasoning || "Critical failure encountered during processing.";
                tone = "red";
              }
            } else if (agent.status === "completed") {
              statusEnum = "completed";
              if (isMacroAgent) {
                msg = formatMacroFlowMessage(data);
                tone = "neutral";
              } else {
                msg = agent.reasoning || "Analysis criteria satisfied.";

                const suppressedVerdict = verdict === "INSUFFICIENT_DATA" || verdict === "SUPPRESSED" || !isModelValid;
                if (suppressedVerdict) {
                  tone = "red";
                  msg = suppressionReason || triggers[0] || msg;
                } else if (
                  finalVerdict &&
                  verdict &&
                  ["BUY", "SELL", "HOLD"].includes(verdict) &&
                  verdict !== finalVerdict
                ) {
                  tone = "amber";
                  msg = `${msg} Conflicts with final verdict ${finalVerdict}.`;
                } else if (
                  finalVerdict &&
                  verdict &&
                  ["BUY", "SELL", "HOLD"].includes(verdict) &&
                  verdict === finalVerdict
                ) {
                  tone = "green";
                }
              }
            }
            
            // Only assign valid signal if completed
            let sig: string | undefined;
            if (agent.status === "completed" && (agent.signal === "BUY" || agent.signal === "SELL" || agent.signal === "HOLD")) {
              sig = agent.signal;
            }

            newEvents.push({
              id: `${key}_${agent.status}_${Date.now()}`,
              timestamp: new Date().toLocaleTimeString("en-GB", { hour12: false }),
              symbol,
              agent: agent.agent_name.toUpperCase(),
              status: statusEnum,
              message: msg,
              signal: sig,
              verdict,
              tone,
            });
          }
          prevAgentsRef.current[key] = { ...agent };
        }

        if (newEvents.length > 0) {
          setEvents((current) => [...current, ...newEvents]);
        }
      } catch (err) {
        console.error("SSE parse error", err);
      }
    });

    source.addEventListener("done", () => {
      source.close();
    });

    return () => source.close();
  }, [runId]);

  useEffect(() => {
    if (!isHovering && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [events, isHovering]);

  const filteredEvents = events.filter((e) => {
    if (filter === "ALL") return true;
    if (filter === "CONFLICTS") return e.tone === "amber" || e.tone === "red";
    if (filter === "SIGNALS") return !!e.verdict;
    if (filter === "DATA") return e.status === "started";
    return true;
  });

  return (
    <div className="h-full flex flex-col bg-[#050505] font-mono border-r border-[var(--color-war-border)]">
      {/* Filter Bar */}
      <div className="flex bg-[var(--color-war-bg)] border-b border-[var(--color-war-border)] h-[40px] items-center px-4 gap-4 shrink-0">
        {(["ALL", "CONFLICTS", "SIGNALS", "DATA"] as FilterType[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs uppercase tracking-widest px-2 py-1 transition-colors ${
              filter === f 
                ? "bg-[var(--color-war-text)] text-[var(--color-war-bg)]" 
                : "text-[var(--color-war-muted)] hover:text-[var(--color-war-text)] hover:bg-[#e8e4db]"
            }`}
          >
            [{f}]
          </button>
        ))}
      </div>

      {/* Log Container */}
      <div 
        ref={containerRef}
        className="flex-1 overflow-y-auto p-4 space-y-3 bg-[var(--color-war-bg)]"
        onMouseEnter={() => setIsHovering(true)}
        onMouseLeave={() => setIsHovering(false)}
      >
        {events.length === 0 && (
          <div className="text-xs text-[var(--color-war-muted)] uppercase tracking-widest">
            Establishing connection...
          </div>
        )}
        
        {filteredEvents.map((evt) => {
          const isFailed = evt.status === "failed";
          const rowTone = rowToneClasses(evt.tone);
          const textTone = signalToneClasses(evt.tone);
          
          return (
            <div 
              key={evt.id} 
              className={`flex items-start gap-4 text-xs ${rowTone} ${isFailed ? "animate-pulse" : ""}`}
            >
              <span className="w-20 shrink-0 text-[var(--color-war-muted)] pt-[2px]">
                {evt.timestamp}
              </span>
              <div className="flex-1 break-words">
                <span className={`font-bold mr-2 uppercase ${textTone}`}>
                  [{evt.agent} {evt.symbol !== "ALL" ? `· ${evt.symbol}` : ""}]
                </span>
                
                <span className={evt.tone === "red" ? "text-[var(--color-war-sell)] font-bold" : "text-[var(--color-war-text)]"}>
                  <TypewriterText text={evt.message} speed={40} />
                </span>

                {evt.verdict && (
                  <span className={`ml-3 px-1 border font-bold ${
                    evt.verdict === "BUY" ? "text-emerald-700 border-emerald-700" 
                    : evt.verdict === "SELL" ? "text-red-700 border-red-700"
                    : evt.verdict === "INSUFFICIENT_DATA" || evt.verdict === "SUPPRESSED" ? "text-slate-600 border-slate-500"
                    : "text-amber-700 border-amber-700"
                  }`}>
                    {evt.verdict}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
