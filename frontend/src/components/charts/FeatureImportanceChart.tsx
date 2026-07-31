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
  Legend,
} from "recharts";

interface FeatureImportanceChartProps {
  importances: Array<{
    feature_name: string;
    importance: number;
    category: string;
  }>;
}

const CATEGORY_COLORS: Record<string, string> = {
  momentum: "#6366f1", // indigo
  volatility: "#f59e0b", // amber
  volume: "#10b981", // emerald
  calendar: "#ec4899", // pink
  technical: "#3b82f6", // blue
};

export default function FeatureImportanceChart({
  importances,
}: FeatureImportanceChartProps) {
  // Sort by importance descending and take top 10
  const sortedData = [...importances]
    .sort((a, b) => b.importance - a.importance)
    .slice(0, 10)
    .map((item) => ({
      ...item,
      cleanName: item.feature_name.replace(/_/g, " "),
      displayImp: item.importance * 100,
    }));

  return (
    <div className="w-full h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          layout="vertical"
          data={sortedData}
          margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
        >
          <CartesianGrid stroke="#1e293b" horizontal={false} />
          <XAxis
            type="number"
            domain={[0, 100]}
            tickFormatter={(val) => `${val}%`}
            stroke="#64748b"
            fontSize={12}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            type="category"
            dataKey="cleanName"
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            width={120}
          />
          <Tooltip
            cursor={{ fill: "#1e293b" }}
            contentStyle={{
              backgroundColor: "#0f172a",
              borderColor: "#1e293b",
              borderRadius: "0.5rem",
              color: "#f8fafc",
            }}
            formatter={(value, _name, item) => {
              const numeric = typeof value === "number" ? value : Number(value ?? 0);
              const payload = item?.payload as { category?: unknown } | undefined;
              const category = typeof payload?.category === "string" ? payload.category : "unknown";
              return [`${numeric.toFixed(1)}%`, `Importance (${category})`];
            }}
          />
          <Bar
            dataKey="displayImp"
            radius={[0, 4, 4, 0]}
            label={{
              position: "right",
              fill: "#94a3b8",
              fontSize: 10,
              formatter: (value: unknown) => {
                const numeric = typeof value === "number" ? value : Number(value ?? 0);
                return `${numeric.toFixed(1)}%`;
              },
            }}
          >
            {sortedData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={CATEGORY_COLORS[entry.category] || "#64748b"}
              />
            ))}
          </Bar>
          <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
