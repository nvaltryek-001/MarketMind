"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";

export default function HomePage() {
  const [symbolInput, setSymbolInput] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleStartAnalysis = async () => {
    const symbols = symbolInput
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0)
      .slice(0, 5);

    if (symbols.length === 0) {
      setError("Enter at least one stock symbol to proceed.");
      return;
    }

    setIsStarting(true);
    setError(null);

    try {
      const { run_id } = await api.startAnalysis(symbols);
      router.push(`/run/${run_id}`);
    } catch (startErr) {
      setError(
        startErr instanceof Error
          ? startErr.message
          : "Failed to initialize terminal routine"
      );
      setIsStarting(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xl border border-[var(--color-war-border)] bg-white p-8">
        <h1 className="text-3xl font-serif font-bold text-[var(--color-war-text)] mb-2 uppercase tracking-wide">
          Intelligence Terminal
        </h1>
        <p className="text-sm font-mono text-[var(--color-war-muted)] mb-8 uppercase tracking-widest border-b border-[var(--color-war-border)] pb-4">
          Awaiting input parameters...
        </p>

        <div className="space-y-4">
          <div>
            <label
              htmlFor="symbolInput"
              className="block text-xs font-mono font-bold text-[var(--color-war-text)] mb-2 uppercase tracking-widest"
            >
              Target Assets (NSE Symbols)
            </label>
            <input
              id="symbolInput"
              type="text"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isStarting) {
                  handleStartAnalysis();
                }
              }}
              placeholder="RELIANCE, TCS, HDFCBANK"
              className="w-full bg-transparent border border-[var(--color-war-border)] px-4 py-3 font-mono text-[var(--color-war-text)] placeholder-[var(--color-war-muted)] focus:outline-none focus:border-[var(--color-war-text)] transition-colors"
            />
            <p className="text-[10px] font-mono text-[var(--color-war-muted)] mt-2 uppercase tracking-widest">
              Limit: 5 Assets per run. Comma-separated.
            </p>
          </div>

          <button
            onClick={handleStartAnalysis}
            disabled={isStarting}
            className="w-full mt-6 bg-[var(--color-war-text)] hover:bg-[#333] disabled:bg-[var(--color-war-muted)] disabled:cursor-not-allowed text-white font-mono font-bold uppercase tracking-widest py-4 transition-colors cursor-pointer"
          >
            {isStarting ? "Initializing..." : "Initiate Protocol"}
          </button>

          {error && (
            <div className="mt-4 border border-[var(--color-war-sell)] bg-red-50 p-3">
              <p className="text-xs font-mono text-[var(--color-war-sell)] font-bold uppercase tracking-widest">
                [ERROR] {error}
              </p>
            </div>
          )}
        </div>
      </div>
      
      <footer className="mt-12 text-center text-[10px] font-mono text-[var(--color-war-muted)] uppercase tracking-wider">
        System active. Unauthorized access logged.
      </footer>
    </div>
  );
}
