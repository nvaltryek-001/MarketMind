"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createChart, ColorType, CrosshairMode, CandlestickSeries, HistogramSeries, createSeriesMarkers } from "lightweight-charts";
import type {
  CandlestickData,
  HistogramData,
  IChartApi,
  ISeriesMarkersPluginApi,
  ISeriesApi,
  SeriesMarker,
  Time,
} from "lightweight-charts";

export interface OHLCVPoint {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface AgentSignal {
  agent: string;
  signal: string;
  date: string;
}

export interface CandlestickChartProps {
  symbol: string;
  data: OHLCVPoint[];
  signals: AgentSignal[];
  hoveredAgent: string | null;
  backtest?: {
    asOfDate: string;
    predicted: string;
    actual: string;
  };
}

type TimeRange = "1M" | "3M" | "6M" | "1Y";

const VALID_SYMBOL = /^[A-Z&]{2,20}$/;
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function markerTimeToMillis(value: Time): number {
  if (typeof value === "string") {
    return new Date(value).getTime();
  }
  if (typeof value === "number") {
    return value * 1000;
  }
  return new Date(value.year, value.month - 1, value.day).getTime();
}

export default function CandlestickChart({
  symbol,
  data,
  signals,
  hoveredAgent,
  backtest,
}: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const retryTimeoutRef = useRef<number | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const fetchChartDataRef = useRef<(
    targetSymbol: string,
    allowRetry?: boolean,
    rethrowOnError?: boolean
  ) => Promise<void>>(
    async () => {}
  );

  const [chartData, setChartData] = useState<OHLCVPoint[]>(data);
  const [chartError, setChartError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(data.length === 0);
  
  const [range, setRange] = useState<TimeRange>("6M");

  const clearRetryTimeout = useCallback(() => {
    if (retryTimeoutRef.current !== null) {
      window.clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }, []);

  const renderChart = useCallback((points: OHLCVPoint[]) => {
    setChartData(points);
    setChartError(null);
    setIsLoading(false);
  }, []);

  const showChartError = useCallback((message: string) => {
    setChartError(message);
    setIsLoading(false);
  }, []);

  const normalizeFetchedData = useCallback((payload: unknown): OHLCVPoint[] => {
    const rows = Array.isArray(payload)
      ? payload
      : payload &&
          typeof payload === "object" &&
          Array.isArray((payload as Record<string, unknown>).candles)
        ? ((payload as Record<string, unknown>).candles as unknown[])
        : [];

    if (!Array.isArray(rows)) return [];

    const points: OHLCVPoint[] = [];

    for (const row of rows) {
      if (!row || typeof row !== "object") {
        continue;
      }

      const record = row as Record<string, unknown>;
      const timeValue = record.time ?? record.date ?? record.Date;

      const openRaw = record.open ?? record.Open;
      const highRaw = record.high ?? record.High;
      const lowRaw = record.low ?? record.Low;
      const closeRaw = record.close ?? record.Close;
      const volumeRaw = record.volume ?? record.Volume;

      const open = Number(openRaw);
      const high = Number(highRaw);
      const low = Number(lowRaw);
      const close = Number(closeRaw);
      const volume = Number(volumeRaw);

      if (
        !timeValue ||
        Number.isNaN(open) ||
        Number.isNaN(high) ||
        Number.isNaN(low) ||
        Number.isNaN(close) ||
        Number.isNaN(volume)
      ) {
        continue;
      }

      points.push({
        time: String(timeValue),
        open,
        high,
        low,
        close,
        volume,
      });
    }

    points.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
    return points;
  }, []);

  const retryAfter = useCallback((delayMs: number, targetSymbol: string) => {
    clearRetryTimeout();
    retryTimeoutRef.current = window.setTimeout(() => {
      void fetchChartDataRef.current(targetSymbol, false, false);
    }, delayMs);
  }, [clearRetryTimeout]);

  const fetchChartData = useCallback(async (targetSymbol: string, allowRetry = true, rethrowOnError = false) => {
    const normalizedSymbol = targetSymbol.toUpperCase().trim();

    if (!normalizedSymbol || normalizedSymbol === "...") {
      setIsLoading(false);
      return;
    }

    if (!VALID_SYMBOL.test(normalizedSymbol)) {
      clearRetryTimeout();
      setChartData([]);
      showChartError("Invalid symbol format.");
      return;
    }

    const requestId = ++requestIdRef.current;

    requestControllerRef.current?.abort();
    clearRetryTimeout();

    const controller = new AbortController();
    requestControllerRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 8000);

    setIsLoading(true);
    setChartError(null);
    setChartData([]);

    try {
      const res = await fetch(`${API_BASE_URL}/api/stock/${encodeURIComponent(normalizedSymbol)}/ohlcv`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) {
        throw new Error(`request_failed_${res.status}`);
      }

      const data = await res.json();
      const candleCount =
        data &&
        typeof data === "object" &&
        Array.isArray((data as { candles?: unknown }).candles)
          ? (data as { candles: unknown[] }).candles.length
          : Array.isArray(data)
            ? data.length
            : 0;
      console.log("OHLCV candles received:", candleCount);

      if (candleCount === 0) {
        showChartError("Empty data");
        return;
      }

      const candles =
        data && typeof data === "object" && "candles" in data
          ? (data as { candles?: unknown }).candles
          : data;
      const normalized = normalizeFetchedData(candles);
      if (!normalized || normalized.length === 0) {
        throw new Error("empty");
      }

      if (requestId !== requestIdRef.current) {
        return;
      }

      renderChart(normalized);
    } catch (err) {
      clearTimeout(timeout);

      if (requestId !== requestIdRef.current) {
        return;
      }

      const errorName = err instanceof Error ? err.name : "";
      showChartError(
        errorName === "AbortError"
          ? "Data fetch timed out. Retrying..."
          : "Could not load price data."
      );

      if (allowRetry) {
        retryAfter(5000, normalizedSymbol);
      }

      if (rethrowOnError) {
        throw err;
      }
    }
  }, [clearRetryTimeout, normalizeFetchedData, renderChart, retryAfter, showChartError]);

  useEffect(() => {
    fetchChartDataRef.current = fetchChartData;
  }, [fetchChartData]);

  const handleRetry = useCallback(() => {
    if (!symbol || symbol === "...") {
      return;
    }
    void (async () => {
      try {
        await fetchChartData(symbol, true, true);
      } catch (e) {
        console.error("Chart load failed:", e);
        const message = e instanceof Error ? e.message : "Unknown error";
        showChartError(`Error: ${message}`);
      }
    })();
  }, [fetchChartData, showChartError, symbol]);

  useEffect(() => {
    if (!symbol || symbol === "...") {
      return;
    }

    void fetchChartData(symbol, true);

    return () => {
      requestIdRef.current += 1;
      requestControllerRef.current?.abort();
      clearRetryTimeout();
    };
  }, [clearRetryTimeout, fetchChartData, symbol]);

  // Filter data based on range
  const filteredData = useMemo(() => {
    if (!chartData.length) return [];
    const lastDate = new Date(chartData[chartData.length - 1].time);
    let monthsToSub = 0;
    if (range === "1M") monthsToSub = 1;
    if (range === "3M") monthsToSub = 3;
    if (range === "6M") monthsToSub = 6;
    if (range === "1Y") monthsToSub = 12;

    const startDate = new Date(lastDate);
    startDate.setMonth(startDate.getMonth() - monthsToSub);

    return chartData.filter((d) => new Date(d.time) >= startDate);
  }, [chartData, range]);

  useEffect(() => {
    if (!chartContainerRef.current || !filteredData.length) return;

    // Initialize Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#fdfdfc" },
        textColor: "#666",
      },
      grid: {
        vertLines: { color: "#e8e4db", style: 2 },
        horzLines: { color: "#e8e4db", style: 2 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: "#e8e4db",
      },
      timeScale: {
        borderColor: "#e8e4db",
        timeVisible: true,
      },
      autoSize: false,
    });
    chartRef.current = chart;

    // Add Candlestick Series (v5 API)
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#1B4332",
      downColor: "#7F1D1D",
      borderVisible: false,
      wickUpColor: "#1B4332",
      wickDownColor: "#7F1D1D",
    });
    candlestickSeriesRef.current = candlestickSeries;

    // Set Data
    const mappedCandles: CandlestickData<Time>[] = filteredData.map((d) => ({
      time: d.time as Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    candlestickSeries.setData(mappedCandles);

    // Add Volume Series as Overlay (v5 API)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "#26a69a",
      priceFormat: {
        type: "volume",
      },
      priceScaleId: "", // overlay
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    const mappedVolume: HistogramData<Time>[] = filteredData.map((d) => ({
      time: d.time as Time,
      value: d.volume,
      color: d.close >= d.open ? "rgba(27, 67, 50, 0.4)" : "rgba(127, 29, 29, 0.4)",
    }));
    volumeSeries.setData(mappedVolume);

    // Apply markers
    applyMarkers(candlestickSeries);

    // Fit content
    chart.timeScale().fitContent();

    // Resize observer
    const handleResize = () => {
      if (chartContainerRef.current) {
        const width = chartContainerRef.current.clientWidth;
        const height = chartContainerRef.current.clientHeight;
        chart.applyOptions({
          width: width > 0 ? width : 640,
          height: height > 0 ? height : 280,
        });
      }
    };
    window.addEventListener("resize", handleResize);
    
    // Initial sizing
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
      if (markersRef.current) {
        try { markersRef.current.detach(); } catch { /* ignore */ }
        markersRef.current = null;
      }
      chart.remove();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredData]); 

  // Function to apply dynamic markers (v5 API - createSeriesMarkers)
  const applyMarkers = (series?: ISeriesApi<"Candlestick", Time>) => {
    const targetSeries = series || candlestickSeriesRef.current;
    if (!targetSeries) return;

    // Clean up previous markers
    if (markersRef.current) {
      try { markersRef.current.detach(); } catch { /* ignore */ }
      markersRef.current = null;
    }
    
    const markers: SeriesMarker<Time>[] = [];

    // Agent Signals
    signals.forEach(s => {
      const dataPoint = filteredData.find(d => d.time === s.date);
      if (dataPoint) {
        markers.push({
          time: s.date,
          position: s.signal === "BUY" ? "belowBar" : "aboveBar",
          color: s.signal === "BUY" ? "#1B4332" : "#7F1D1D",
          shape: s.signal === "BUY" ? "arrowUp" : "arrowDown",
          text: `${s.agent}: ${s.signal}`,
          size: hoveredAgent === s.agent ? 2 : 1,
        });
      }
    });

    // Backtest marker
    if (backtest) {
      const dataPoint = filteredData.find(d => d.time === backtest.asOfDate);
      if (dataPoint) {
        markers.push({
          time: backtest.asOfDate,
          position: "aboveBar",
          color: "#ca8a04",
          shape: "arrowDown",
          text: `[BACKTEST] Predicted: ${backtest.predicted} | Actual: ${backtest.actual}`,
          size: 2,
        });
      }
    }
    
    // lightweight-charts requires markers to be sorted by time
    markers.sort((a, b) => markerTimeToMillis(a.time) - markerTimeToMillis(b.time));

    if (markers.length > 0) {
      markersRef.current = createSeriesMarkers<Time>(targetSeries, markers);
    }
  };

  // Re-apply markers when hoveredAgent changes
  useEffect(() => {
    applyMarkers();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredAgent, signals, backtest]);

  return (
    <div className="h-full w-full flex flex-col relative">
      {/* Overlay Toolbar */}
      <div className="absolute top-4 left-4 z-10 flex bg-[var(--color-war-bg)] border border-[var(--color-war-border)] h-[32px] gap-px shadow-sm">
        {(["1M", "3M", "6M", "1Y"] as TimeRange[]).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`font-mono text-[10px] uppercase tracking-widest px-4 transition-colors ${
              range === r
                ? "bg-[var(--color-war-text)] text-white"
                : "bg-transparent text-[var(--color-war-muted)] hover:bg-[#e8e4db]"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      <div className="absolute top-4 right-4 z-10 px-3 h-[32px] flex items-center bg-[var(--color-war-bg)] border border-[var(--color-war-border)] font-mono text-[10px] uppercase tracking-widest text-[var(--color-war-muted)]">
        {symbol}
      </div>

      {isLoading && !chartError && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-[#fdfdfc]">
          <div className="ohlcv-spinner" aria-hidden="true" />
          <p className="font-mono text-xs text-[var(--color-war-muted)] uppercase tracking-widest">
            Synthesizing OHLCV data...
          </p>
        </div>
      )}

      {chartError && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-[#fdfdfc] px-6">
          <p className="font-mono text-xs uppercase tracking-widest text-[#7F1D1D] text-center">
            {chartError}
          </p>
          <button
            onClick={handleRetry}
            className="h-8 px-4 border border-[#7F1D1D] text-[#7F1D1D] font-mono text-[10px] uppercase tracking-widest hover:bg-[#7F1D1D] hover:text-white transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Chart Canvas Container */}
      <div ref={chartContainerRef} className="flex-1 w-full h-full min-h-[280px]" />
    </div>
  );
}
