"use client";

import CandlestickChart, { OHLCVPoint, AgentSignal } from "../charts/CandlestickChart";

interface ChartRoomProps {
  symbol: string;
  data: OHLCVPoint[];
  signals: AgentSignal[];
  hoveredAgent: string | null;
}

export default function ChartRoom({ symbol, data, signals, hoveredAgent }: ChartRoomProps) {
  return (
    <div className="h-full flex flex-col bg-[#fdfdfc]">
      <div className="p-4 border-b border-[var(--color-war-border)] bg-[var(--color-war-bg)] flex justify-between items-center z-10 shrink-0">
        <div>
          <h2 className="text-xl font-serif font-bold text-[var(--color-war-text)] uppercase tracking-wide">
            The Chart Room: {symbol}
          </h2>
          <p className="text-[10px] font-mono text-[var(--color-war-muted)] uppercase tracking-widest mt-1">
            Price Action & Technical Overlay
          </p>
        </div>
      </div>

      {/* Chart Area */}
      <div className="flex-1 relative">
        <CandlestickChart 
          symbol={symbol} 
          data={data} 
          signals={signals} 
          hoveredAgent={hoveredAgent} 
        />
      </div>
    </div>
  );
}
