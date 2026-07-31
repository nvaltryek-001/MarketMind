// ---------------------------------------------------------------------------
// Signal color utilities
// ---------------------------------------------------------------------------

export function getSignalColor(signal: string | null): string {
  switch (signal) {
    case "BUY":
      return "text-emerald-400";
    case "SELL":
      return "text-red-400";
    case "HOLD":
      return "text-amber-400";
    default:
      return "text-slate-400";
  }
}

export function getSignalBg(signal: string | null): string {
  switch (signal) {
    case "BUY":
      return "bg-emerald-500/10 border border-emerald-500/30";
    case "SELL":
      return "bg-red-500/10 border border-red-500/30";
    case "HOLD":
      return "bg-amber-500/10 border border-amber-500/30";
    default:
      return "bg-slate-500/10 border border-slate-700";
  }
}

// ---------------------------------------------------------------------------
// Status / formatting utilities
// ---------------------------------------------------------------------------

export function getStatusIcon(status: string): string {
  switch (status) {
    case "completed":
      return "✓";
    case "running":
      return "⟳";
    case "failed":
      return "✗";
    case "pending":
      return "○";
    default:
      return "○";
  }
}

export function formatConfidence(confidence: number | null): string {
  if (confidence === null || confidence === undefined) return "—";
  return `${Math.round(confidence * 100)}%`;
}

export function formatPriceTarget(pct: number): string {
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Agent display name mapping
// ---------------------------------------------------------------------------

const AGENT_NAME_MAP: Record<string, string> = {
  data_ingestion: "Data Ingestion",
  technical: "Technical Analysis",
  fundamental: "Fundamental Analysis",
  sentiment: "Sentiment Analysis",
  ml_prediction: "ML Prediction",
  risk: "Risk Assessment",
  synthesis: "Synthesis",
};

export function agentDisplayName(agentName: string): string {
  return (
    AGENT_NAME_MAP[agentName] ??
    agentName
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}
