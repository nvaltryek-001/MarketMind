"use client";

interface CorrelationHeatmapProps {
  correlationGrid: {
    symbols: string[];
    matrix: number[][];
  };
}

export default function CorrelationHeatmap({
  correlationGrid,
}: CorrelationHeatmapProps) {
  const { symbols, matrix } = correlationGrid;
  const n = symbols.length;

  if (n <= 1) {
    return (
      <div className="flex items-center justify-center p-8 bg-slate-900/50 border border-slate-800 rounded-xl text-slate-400 text-sm">
        Add more symbols to see cross-stock correlation analysis.
      </div>
    );
  }

  const cellSize = { width: 80, height: 60 };
  const labelOffsetX = 100; // Space for left labels
  const labelOffsetY = 60; // Space for top labels
  const svgWidth = labelOffsetX + n * cellSize.width;
  const svgHeight = labelOffsetY + n * cellSize.height;

  // Helper to interpolate colors
  // -1.0 → #ef4444 (239, 68, 68)
  // 0.0  → #1e293b (30, 41, 59)
  // +1.0 → #10b981 (16, 185, 129)
  const getColor = (value: number) => {
    if (value === 1) return "#1e293b"; // Same stock, render as neutral or maybe slate
    
    // Normalize -1 to 1 into 0 to 1 for calculation
    if (value >= 0 && value < 1) {
      // Interpolate between neutral and green
      const r = Math.round(30 + (16 - 30) * value);
      const g = Math.round(41 + (185 - 41) * value);
      const b = Math.round(59 + (129 - 59) * value);
      return `rgb(${r}, ${g}, ${b})`;
    } else if (value < 0) {
      // Interpolate between neutral and red
      const absVal = Math.abs(value);
      const r = Math.round(30 + (239 - 30) * absVal);
      const g = Math.round(41 + (68 - 41) * absVal);
      const b = Math.round(59 + (68 - 59) * absVal);
      return `rgb(${r}, ${g}, ${b})`;
    }
    return "#1e293b"; 
  };

  return (
    <div className="w-full overflow-x-auto overflow-y-hidden pb-8">
      <div className="flex flex-col items-center">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          width={svgWidth}
          height={svgHeight}
          className="max-w-full font-sans"
        >
          {/* Top Labels */}
          {symbols.map((sym, i) => (
            <text
              key={`top-${sym}`}
              x={labelOffsetX + i * cellSize.width + cellSize.width / 2}
              y={labelOffsetY - 15}
              fill="#94a3b8"
              fontSize={12}
              fontWeight="bold"
              textAnchor="middle"
            >
              {sym}
            </text>
          ))}

          {/* Left Labels */}
          {symbols.map((sym, i) => (
            <text
              key={`left-${sym}`}
              x={labelOffsetX - 15}
              y={labelOffsetY + i * cellSize.height + cellSize.height / 2}
              fill="#94a3b8"
              fontSize={12}
              fontWeight="bold"
              textAnchor="end"
              dominantBaseline="middle"
            >
              {sym}
            </text>
          ))}

          {/* Grid Cells */}
          {matrix.map((row, i) =>
            row.map((val, j) => {
              const x = labelOffsetX + j * cellSize.width;
              const y = labelOffsetY + i * cellSize.height;
              const isDiagonal = i === j;
              const fillPattern = isDiagonal ? "#0f172a" : getColor(val);
              
              return (
                <g key={`cell-${i}-${j}`}>
                  <rect
                    x={x}
                    y={y}
                    width={cellSize.width}
                    height={cellSize.height}
                    fill={fillPattern}
                    stroke="#0f172a"
                    strokeWidth={2}
                  />
                  <text
                    x={x + cellSize.width / 2}
                    y={y + cellSize.height / 2}
                    fill={isDiagonal ? "#64748b" : "#ffffff"}
                    fontSize={13}
                    fontWeight="500"
                    textAnchor="middle"
                    dominantBaseline="central"
                  >
                    {isDiagonal ? "—" : val.toFixed(2)}
                  </text>
                </g>
              );
            })
          )}
        </svg>

        {/* Legend */}
        <div className="mt-6 flex flex-col items-center w-full max-w-sm">
          <div className="flex justify-between w-full text-xs text-slate-400 mb-1 px-1">
            <span>Negative (-1.0)</span>
            <span>Neutral (0)</span>
            <span>Positive (+1.0)</span>
          </div>
          <div className="h-3 w-full rounded-full bg-gradient-to-r from-red-500 via-slate-800 to-emerald-500"></div>
        </div>
      </div>
    </div>
  );
}
