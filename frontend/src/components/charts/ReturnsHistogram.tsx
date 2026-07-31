"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";

interface ReturnsHistogramProps {
  symbol: string;
  histogram: {
    bins: number[];
    counts: number[];
  };
}

export default function ReturnsHistogram({
  symbol,
  histogram,
}: ReturnsHistogramProps) {
  // Bins are decimal returns — multiply by 100 for percentage display
  const data = histogram.bins.map((bin, i) => {
    const val = bin * 100;
    return {
      binValue: val,
      bin: `${val > 0 ? "+" : ""}${val.toFixed(1)}%`,
      count: histogram.counts[i] || 0,
    };
  });

  // Find the closest bin to zero for the reference line
  let closestToZero = data[0]?.bin;
  let minAbs = Infinity;
  for (const item of data) {
    if (Math.abs(item.binValue) < minAbs) {
      minAbs = Math.abs(item.binValue);
      closestToZero = item.bin;
    }
  }

  return (
    <div className="w-full h-[220px] relative">
      <div className="absolute top-2 right-2 z-10 font-mono text-[10px] uppercase tracking-widest text-[var(--color-war-muted)]">
        {symbol}
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="bin"
            stroke="#64748b"
            fontSize={12}
            tickLine={false}
            axisLine={false}
            interval={4} // Show roughly every 5th label (0-indexed)
          />
          <YAxis
            label={{
              value: "Frequency",
              angle: -90,
              position: "insideLeft",
              fill: "#64748b",
              fontSize: 12,
            }}
            stroke="#64748b"
            fontSize={12}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: "#1e293b" }}
            contentStyle={{
              backgroundColor: "#0f172a",
              borderColor: "#1e293b",
              borderRadius: "0.5rem",
              color: "#f8fafc",
            }}
            formatter={(value) => {
              const numeric = typeof value === "number" ? value : Number(value ?? 0);
              return [numeric, "Count"];
            }}
            labelFormatter={(label) => `Return: ${String(label ?? "")}`}
          />
          <ReferenceLine x={closestToZero} stroke="#94a3b8" />
          <Bar dataKey="count" name="Count" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.binValue < 0 ? "#ef4444" : "#10b981"}
                fillOpacity={0.7}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
