"""
FinSight — Exploratory Data Analysis Agent.
Performs comprehensive statistical EDA on OHLCV data: distribution analysis,
outlier detection, volatility regime classification, cross-symbol correlation,
and generates chart-ready data arrays for the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

import numpy as np
import pandas as pd
from scipy import stats

from backend.models.schemas import (
    CorrelationPair,
    DistributionStats,
    EDAResult,
    MultiStockEDA,
    OHLCVData,
    OutlierInfo,
    VolatilityRegime,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _compute_distribution_stats(
    series: pd.Series,
    *,
    run_normality_test: bool = True,
) -> DistributionStats:
    """Compute descriptive statistics for a numeric series."""
    clean = series.dropna()

    # Shapiro-Wilk (needs ≤ 5000 samples)
    is_normal = False
    if run_normality_test and len(clean) >= 3:
        sample = clean.sample(n=min(50, len(clean)), random_state=42)
        try:
            _, p_value = stats.shapiro(sample)
            is_normal = p_value > 0.05
        except Exception:
            is_normal = False

    return DistributionStats(
        mean=float(clean.mean()),
        median=float(clean.median()),
        std=float(clean.std()),
        skewness=float(stats.skew(clean)),
        kurtosis=float(stats.kurtosis(clean)),
        min=float(clean.min()),
        max=float(clean.max()),
        is_normal=is_normal,
        percentile_25=float(np.percentile(clean, 25)),
        percentile_75=float(np.percentile(clean, 75)),
    )


def _detect_outliers(
    daily_returns: pd.Series,
    volumes: pd.Series,
    dates: list[str],
) -> list[OutlierInfo]:
    """Detect volume spikes, price gap-ups and gap-downs via z-scores."""
    outliers: list[OutlierInfo] = []
    threshold = 2.5
    n_dates = len(dates)

    # --- Volume spikes ---
    vol_std = volumes.std()
    if vol_std > 0:
        vol_z = (volumes - volumes.mean()) / vol_std
        vol_outlier_mask = vol_z.abs() > threshold
        for idx in vol_z[vol_outlier_mask].index:
            if idx < n_dates:
                outliers.append(
                    OutlierInfo(
                        date=dates[idx],
                        value=float(volumes.iloc[idx]) if idx < len(volumes) else 0.0,
                        z_score=round(float(vol_z.loc[idx]), 2),
                        event_type="volume spike",
                    )
                )

    # --- Price gap ups / downs ---
    ret_std = daily_returns.std()
    if ret_std > 0:
        ret_z = (daily_returns - daily_returns.mean()) / ret_std
        for idx in ret_z.dropna().index:
            z = float(ret_z.loc[idx])
            if abs(z) > threshold and idx < n_dates:
                event_type = "price gap up" if z > 0 else "price gap down"
                outliers.append(
                    OutlierInfo(
                        date=dates[idx],
                        value=round(float(daily_returns.loc[idx]) * 100, 2),
                        z_score=round(z, 2),
                        event_type=event_type,
                    )
                )

    # Sort by abs(z_score) descending, take top 5
    outliers.sort(key=lambda o: abs(o.z_score), reverse=True)
    return outliers[:5]


def _classify_regime(annualised_vol: float) -> str:
    """Map annualised volatility to a regime label."""
    if annualised_vol < 0.20:
        return "low"
    elif annualised_vol < 0.35:
        return "medium"
    elif annualised_vol < 0.50:
        return "high"
    return "extreme"


def _regime_boundary(regime: str) -> float:
    """Return the lower boundary of the given regime."""
    return {"low": 0.0, "medium": 0.20, "high": 0.35, "extreme": 0.50}[regime]


def _find_regime_start(
    rolling_vol: pd.Series, regime: str, dates: list[str],
) -> str:
    """Find the approximate date the current regime began."""
    boundary = _regime_boundary(regime)
    upper = {"low": 0.20, "medium": 0.35, "high": 0.50, "extreme": float("inf")}[
        regime
    ]
    clean_vol = rolling_vol.dropna()
    # Walk backwards to find when we entered this regime
    for i in range(len(clean_vol) - 1, -1, -1):
        v = clean_vol.iloc[i]
        if not (boundary <= v < upper):
            # The regime started the day *after* this one
            start_idx = min(i + 1, len(clean_vol) - 1)
            # Map back to the dates array
            date_idx = clean_vol.index[start_idx]
            if date_idx < len(dates):
                return dates[date_idx]
            return dates[-1]
    # The entire history is in this regime
    first_idx = clean_vol.index[0]
    if first_idx < len(dates):
        return dates[first_idx]
    return dates[0]


def _classify_relationship(corr: float) -> str:
    """Classify a correlation coefficient into a human-readable label."""
    if corr > 0.7:
        return "strong positive"
    elif corr > 0.4:
        return "moderate positive"
    elif corr > -0.4:
        return "weak"
    elif corr > -0.7:
        return "moderate negative"
    return "strong negative"


# ──────────────────────────────────────────────────────────────────────
# Single-stock EDA
# ──────────────────────────────────────────────────────────────────────

async def analyze_single(symbol: str, ohlcv: OHLCVData) -> EDAResult:
    """
    Full exploratory data analysis on one stock's OHLCV data.
    """
    closes = pd.Series(ohlcv.closes, dtype=float)
    volumes = pd.Series(ohlcv.volumes, dtype=float)
    daily_returns = closes.pct_change().dropna()

    # ── 1. Returns distribution ─────────────────────────────────────
    returns_dist = _compute_distribution_stats(
        daily_returns, run_normality_test=True,
    )

    # ── 2. Volume distribution ──────────────────────────────────────
    volume_dist = _compute_distribution_stats(
        volumes, run_normality_test=False,
    )
    # Volume is never normally distributed
    volume_dist.is_normal = False

    # ── 3. Outlier detection ────────────────────────────────────────
    outliers = _detect_outliers(daily_returns, volumes, ohlcv.dates)

    # ── 4. Volatility regime ────────────────────────────────────────
    rolling_vol_30 = daily_returns.rolling(30).std() * np.sqrt(252)
    rolling_vol_clean = rolling_vol_30.dropna()
    if len(rolling_vol_clean) > 0:
        current_vol = float(rolling_vol_clean.iloc[-1])
        percentile = float(
            stats.percentileofscore(rolling_vol_clean, current_vol)
        )
    else:
        current_vol = float(daily_returns.std() * np.sqrt(252)) if len(daily_returns) > 1 else 0.25
        percentile = 50.0
    regime = _classify_regime(current_vol)
    avg_daily_move_pct = float(daily_returns.abs().mean() * 100) if len(daily_returns) > 0 else 1.0
    regime_started = _find_regime_start(rolling_vol_30, regime, ohlcv.dates)

    volatility_regime = VolatilityRegime(
        regime=regime,
        current_percentile=round(percentile, 1),
        avg_daily_move_pct=round(avg_daily_move_pct, 2),
        regime_started_approx=regime_started,
    )

    # ── 5. Chart data ──────────────────────────────────────────────

    # Returns histogram
    hist, bin_edges = np.histogram(daily_returns, bins=30)
    bins = [
        round((float(bin_edges[i]) + float(bin_edges[i + 1])) / 2, 6)
        for i in range(30)
    ]
    returns_histogram = {"bins": bins, "counts": hist.tolist()}

    # Rolling volatility (30d)
    rolling_vol_clean_chart = rolling_vol_30.dropna()
    vol_start = len(ohlcv.dates) - len(rolling_vol_clean_chart)
    rolling_volatility_30d = {
        "dates": ohlcv.dates[vol_start:],
        "values": (rolling_vol_clean_chart * 100).round(2).tolist(),
    }

    # Volume / MA-20 ratio
    vol_ma20 = volumes.rolling(20).mean()
    ratio = (volumes / vol_ma20).round(2)
    ratio_clean = ratio.dropna()
    ratio_start = len(ohlcv.dates) - len(ratio_clean)
    volume_ma_ratio = {
        "dates": ohlcv.dates[ratio_start:],
        "values": ratio_clean.tolist(),
    }

    # Price vs SMA50/200 — last 180 data points
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()
    n_points = min(180, len(closes))
    price_vs_sma = {
        "dates": ohlcv.dates[-n_points:],
        "price": closes.iloc[-n_points:].round(2).tolist(),
        "sma50": sma50.iloc[-n_points:].round(2).tolist(),
        "sma200": sma200.iloc[-n_points:].round(2).tolist(),
    }

    # ── 6. Key insights (4 programmatic bullet points) ──────────────

    # Insight 1: returns distribution
    skew_val = returns_dist.skewness
    skew_dir = "positively" if skew_val > 0 else "negatively"
    skew_interpretation = (
        "more frequent small gains with rare large drops"
        if skew_val > 0
        else "more frequent small losses with rare large gains"
    )
    insight_1 = (
        f"Returns are {skew_dir} skewed (skewness={skew_val:.2f}), "
        f"suggesting {skew_interpretation}."
    )

    # Insight 2: volatility
    insight_2 = (
        f"Current annualized volatility is {current_vol * 100:.1f}%, "
        f"in the {regime} regime and higher than "
        f"{percentile:.0f}% of historical readings."
    )

    # Insight 3: outliers
    n_outliers = len(outliers)
    if n_outliers > 0:
        largest = outliers[0]
        insight_3 = (
            f"Detected {n_outliers} significant price/volume events "
            f"in the past year, the largest being a {largest.event_type} "
            f"of {largest.value:.1f}{'%' if 'gap' in largest.event_type else ''} "
            f"on {largest.date}."
        )
    else:
        insight_3 = (
            "No significant outlier events detected in the past year, "
            "suggesting relatively stable price and volume behaviour."
        )

    # Insight 4: trend from SMA positioning
    current_price = closes.iloc[-1]
    sma50_val = sma50.iloc[-1]
    sma200_val = sma200.iloc[-1]

    if pd.notna(sma50_val) and pd.notna(sma200_val):
        if current_price > sma50_val > sma200_val:
            insight_4 = (
                "Price is trading above both SMA50 and SMA200, confirming a "
                "strong uptrend structure."
            )
        elif current_price < sma50_val and sma50_val < sma200_val:
            insight_4 = (
                "Price is below both moving averages, indicating a "
                "bearish trend structure."
            )
        else:
            insight_4 = (
                "Mixed moving average positioning suggests a "
                "transitional phase."
            )
    else:
        insight_4 = (
            "Insufficient data for SMA200 calculation; trend assessment "
            "requires a longer price history."
        )

    key_insights = [insight_1, insight_2, insight_3, insight_4]

    logger.info(
        "%s EDA complete: regime=%s vol=%.1f%% outliers=%d",
        symbol, regime, current_vol * 100, n_outliers,
    )

    return EDAResult(
        symbol=symbol,
        returns_distribution=returns_dist,
        volume_distribution=volume_dist,
        outliers=outliers,
        volatility_regime=volatility_regime,
        returns_histogram=returns_histogram,
        rolling_volatility_30d=rolling_volatility_30d,
        volume_ma_ratio=volume_ma_ratio,
        price_vs_sma=price_vs_sma,
        key_insights=key_insights,
    )


# ──────────────────────────────────────────────────────────────────────
# Multi-stock EDA entry point
# ──────────────────────────────────────────────────────────────────────

async def run(
    run_id: str,
    symbols: list[str],
    ohlcv_dict: dict[str, OHLCVData],
) -> MultiStockEDA:
    """
    Run EDA on all symbols and compute cross-symbol correlation.

    Parameters
    ----------
    run_id : str
        Unique run identifier.
    symbols : list[str]
        List of stock symbols to analyse.
    ohlcv_dict : dict[str, OHLCVData]
        Pre-fetched OHLCV data keyed by symbol.
    """
    # ── 1. Run single-stock EDA concurrently ────────────────────────
    tasks = [analyze_single(sym, ohlcv_dict[sym]) for sym in symbols]
    results = await asyncio.gather(*tasks)
    individual_eda = {r.symbol: r for r in results}

    # ── 2. Correlation matrix ───────────────────────────────────────
    # Build DataFrame of daily returns
    returns_df = pd.DataFrame()
    for sym in symbols:
        closes = pd.Series(ohlcv_dict[sym].closes, dtype=float)
        returns_df[sym] = closes.pct_change().dropna()

    corr_matrix_df = returns_df.corr()

    # Pairwise correlation list
    correlation_pairs: list[CorrelationPair] = []
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            corr_val = float(corr_matrix_df.iloc[i, j])
            correlation_pairs.append(
                CorrelationPair(
                    symbol_a=symbols[i],
                    symbol_b=symbols[j],
                    correlation=round(corr_val, 3),
                    relationship=_classify_relationship(corr_val),
                )
            )

    # Correlation grid for heatmap
    correlation_grid = {
        "symbols": symbols,
        "matrix": corr_matrix_df.round(3).values.tolist(),
    }

    # ── 3. Portfolio summary ────────────────────────────────────────
    n = len(symbols)
    symbols_joined = ", ".join(symbols)

    if n == 1:
        regime = individual_eda[symbols[0]].volatility_regime.regime
        portfolio_summary = (
            f"Analyzed 1 stock: {symbols_joined}. "
            f"Single-stock analysis — correlation metrics not applicable. "
            f"The volatility regime is currently {regime}."
        )
    else:
        # Find highest correlation pair
        if correlation_pairs:
            strongest = max(correlation_pairs, key=lambda p: abs(p.correlation))
            diversification = (
                "limited" if abs(strongest.correlation) > 0.6 else "good"
            )
        else:
            strongest = None
            diversification = "undetermined"

        # Most common regime across stocks
        regimes = [
            individual_eda[sym].volatility_regime.regime for sym in symbols
        ]
        most_common_regime = Counter(regimes).most_common(1)[0][0]

        if strongest:
            portfolio_summary = (
                f"Analyzed {n} stocks: {symbols_joined}. "
                f"The highest correlation pair is "
                f"{strongest.symbol_a}-{strongest.symbol_b} at "
                f"{strongest.correlation:.2f}, suggesting {diversification} "
                f"diversification benefit. "
                f"Average portfolio volatility regime is {most_common_regime}."
            )
        else:
            portfolio_summary = (
                f"Analyzed {n} stocks: {symbols_joined}. "
                f"Average portfolio volatility regime is {most_common_regime}."
            )

    logger.info(
        "Multi-stock EDA complete for run %s: %d symbols", run_id, n,
    )

    return MultiStockEDA(
        run_id=run_id,
        symbols=symbols,
        individual_eda=individual_eda,
        correlation_matrix=correlation_pairs,
        correlation_grid=correlation_grid,
        portfolio_summary=portfolio_summary,
    )
