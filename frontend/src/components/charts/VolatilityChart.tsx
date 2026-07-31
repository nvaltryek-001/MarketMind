"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface VolatilityChartProps {
  symbol: string;
  volData: {
    dates: string[];
    values: number[];
  };
}

export default function VolatilityChart({
  symbol,
  volData,
}: VolatilityChartProps) {
  // Take last 180 data points
  const dataLength = volData.dates.length;
  const itemsToTake = Math.min(180, dataLength);
  const startIndex = dataLength - itemsToTake;

  const data = Array.from({ length: itemsToTake }, (_, i) => {
    const idx = startIndex + i;
    return {
      date: volData.dates[idx],
      vol: volData.values[idx] * 100, // Assuming raw values are decimals, convert to %
    };
  });

  return (
    <div className="w-full h-[220px] relative">
      <div className="absolute top-2 right-2 z-10 font-mono text-[10px] uppercase tracking-widest text-[var(--color-war-muted)]">
        {symbol}
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(value, index) => {
              if (index % 30 !== 0) return "";
              const date = new Date(String(value));
              return date.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              });
            }}
            stroke="#64748b"
            fontSize={12}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={(value) => `${String(value)}%`}
            domain={[0, "auto"]}
            stroke="#64748b"
            fontSize={12}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f172a",
              borderColor: "#1e293b",
              borderRadius: "0.5rem",
              color: "#f8fafc",
            }}
            formatter={(value) => {
              const numeric = typeof value === "number" ? value : Number(value ?? 0);
              return [`${numeric.toFixed(2)}%`, "Vol"];
            }}
            labelFormatter={(label) => `Date: ${String(label ?? "")}`}
          />
          <ReferenceLine
            y={20}
            label={{ position: "insideTopLeft", value: "Low", fill: "#10b981", fontSize: 10 }}
            stroke="#10b981"
            strokeDasharray="3 3"
          />
          <ReferenceLine
            y={35}
            label={{ position: "insideTopLeft", value: "Medium", fill: "#f59e0b", fontSize: 10 }}
            stroke="#f59e0b"
            strokeDasharray="3 3"
          />
          <ReferenceLine
            y={50}
            label={{ position: "insideTopLeft", value: "High", fill: "#ef4444", fontSize: 10 }}
            stroke="#ef4444"
            strokeDasharray="3 3"
          />
          <Area
            type="monotone"
            dataKey="vol"
            stroke="#6366f1"
            strokeWidth={1.5}
            fill="#6366f1"
            fillOpacity={0.15}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
