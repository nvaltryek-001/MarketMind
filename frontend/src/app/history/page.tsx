"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import type { RecentRun } from "@/lib/api";

function StatusBadge({ status }: { status: string }) {
  let classes = "";
  const label = status.toUpperCase();
  switch (status) {
    case "completed":
      classes = "bg-[var(--color-war-buy)] text-white px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-widest";
      break;
    case "running":
      classes = "bg-amber-600 text-white px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-widest animate-pulse";
      break;
    case "failed":
      classes = "bg-[var(--color-war-sell)] text-white px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-widest";
      break;
    default:
      classes = "bg-[var(--color-war-muted)] text-white px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-widest";
  }
  return <span className={classes}>{label}</span>;
}

function formatDuration(startedAt: string, completedAt: string | null): string {
  if (!completedAt) return "In progress...";
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  const diffMs = end - start;
  if (diffMs < 1000) return "<1s";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSec = seconds % 60;
  return `${minutes}m ${remainingSec}s`;
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <tr key={i} className="border-t border-[var(--color-war-border)]">
          {Array.from({ length: 6 }).map((_, j) => (
            <td key={j} className="px-4 py-3">
              <div className="h-4 bg-[var(--color-war-border)] animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default function HistoryPage() {
  const [runs, setRuns] = useState<RecentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchRuns() {
      try {
        const data = await api.getRecentRuns();
        setRuns(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load runs");
      } finally {
        setLoading(false);
      }
    }
    fetchRuns();
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-war-bg)] py-8 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-6 border-b-2 border-[var(--color-war-text)] pb-4">
          <h1 className="text-3xl font-serif font-bold text-[var(--color-war-text)] uppercase tracking-wide">
            Mission Archive
          </h1>
          <span className="font-mono text-[10px] text-[var(--color-war-muted)] uppercase tracking-widest mt-2">
            — Declassified Analysis Runs
          </span>
        </div>

        {error && (
          <div className="bg-red-50 border border-[var(--color-war-sell)] p-4 mb-6">
            <p className="text-xs font-mono text-[var(--color-war-sell)] font-bold uppercase tracking-widest">
              [ERROR] {error}
            </p>
          </div>
        )}

        <div className="border border-[var(--color-war-border)] bg-[#fdfdfc] overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-[var(--color-war-text)] bg-[var(--color-war-bg)]">
                <th className="px-4 py-3 text-[10px] font-mono font-bold text-[var(--color-war-text)] uppercase tracking-widest">
                  Run ID
                </th>
                <th className="px-4 py-3 text-[10px] font-mono font-bold text-[var(--color-war-text)] uppercase tracking-widest">
                  Targets
                </th>
                <th className="px-4 py-3 text-[10px] font-mono font-bold text-[var(--color-war-text)] uppercase tracking-widest">
                  Status
                </th>
                <th className="px-4 py-3 text-[10px] font-mono font-bold text-[var(--color-war-text)] uppercase tracking-widest">
                  Initiated
                </th>
                <th className="px-4 py-3 text-[10px] font-mono font-bold text-[var(--color-war-text)] uppercase tracking-widest">
                  Duration
                </th>
                <th className="px-4 py-3 text-[10px] font-mono font-bold text-[var(--color-war-text)] uppercase tracking-widest">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && <SkeletonRows />}

              {!loading && runs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <p className="text-sm font-mono text-[var(--color-war-muted)] uppercase tracking-widest">
                        No intelligence runs in archive.
                      </p>
                      <Link
                        href="/"
                        className="text-[var(--color-war-text)] hover:underline text-sm font-mono font-bold uppercase tracking-widest"
                      >
                        Initiate First Analysis →
                      </Link>
                    </div>
                  </td>
                </tr>
              )}

              {!loading &&
                runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className="border-t border-[var(--color-war-border)] hover:bg-[#F0EDE5] transition-colors"
                  >
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono text-[var(--color-war-text)]">
                        {run.run_id.slice(0, 8)}...
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {run.symbols.map((sym) => (
                          <span
                            key={sym}
                            className="bg-[var(--color-war-bg)] border border-[var(--color-war-border)] text-[var(--color-war-text)] text-[10px] font-mono font-bold px-2 py-0.5 uppercase tracking-wider"
                          >
                            {sym}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-3 text-[var(--color-war-muted)] text-sm font-mono">
                      {new Date(run.started_at).toLocaleString("en-IN", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-war-muted)] text-sm font-mono">
                      {formatDuration(run.started_at, run.completed_at)}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/run/${run.run_id}`}
                        className="text-[var(--color-war-text)] hover:underline text-xs font-mono font-bold uppercase tracking-widest"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
