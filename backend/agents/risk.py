"""
FinSight — Risk Assessment Agent.
Calculates beta, VaR, Sharpe ratio, max drawdown, and volatility
for quantitative risk profiling.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from math import sqrt
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.models.schemas import OHLCVData, RiskMetrics

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# Indian T-bill rate (annualised risk-free rate)
RISK_FREE_RATE = 0.065


def _fetch_nifty(period: str = "1y") -> Optional[pd.Series]:
    """Synchronous helper — fetch Nifty 50 daily closes."""
    try:
        df = yf.download("^NSEI", period=period, interval="1d",
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        # Handle multi-level columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df["Close"]
    except Exception as exc:
        logger.warning("Nifty 50 fetch failed: %s", exc)
        return None


async def run(symbol: str, ohlcv: OHLCVData) -> RiskMetrics:
    """
    Calculate risk metrics from OHLCV price data and benchmark
    against Nifty 50.
    """
    loop = asyncio.get_event_loop()

    closes = pd.Series(ohlcv.closes, index=pd.to_datetime(ohlcv.dates))
    daily_returns = closes.pct_change().dropna()

    # ── Beta vs Nifty 50 ────────────────────────────────────────────
    nifty_closes = await loop.run_in_executor(_executor, _fetch_nifty)

    if nifty_closes is not None and len(nifty_closes) > 10:
        nifty_returns = nifty_closes.pct_change().dropna()

        # Align dates
        common_dates = daily_returns.index.intersection(nifty_returns.index)
        if len(common_dates) > 10:
            stock_r = daily_returns.loc[common_dates]
            nifty_r = nifty_returns.loc[common_dates]
            covariance = np.cov(stock_r, nifty_r)[0][1]
            nifty_var = np.var(nifty_r)
            beta = float(covariance / nifty_var) if nifty_var != 0 else 1.0
        else:
            beta = 1.0
    else:
        logger.info("Using default beta=1.0 for %s (Nifty data unavailable)", symbol)
        beta = 1.0

    # ── VaR 95% ─────────────────────────────────────────────────────
    var_95 = float(np.percentile(daily_returns, 5))

    # ── Annualised volatility ───────────────────────────────────────
    daily_std = float(daily_returns.std())
    volatility = daily_std * sqrt(252)

    # ── Sharpe ratio ────────────────────────────────────────────────
    annualized_return = float(daily_returns.mean()) * 252
    sharpe = (
        (annualized_return - RISK_FREE_RATE) / volatility
        if volatility != 0
        else 0.0
    )

    # ── Max drawdown ────────────────────────────────────────────────
    rolling_max = closes.cummax()
    drawdown = (closes - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min())

    # ── Risk level classification ───────────────────────────────────
    if volatility > 0.35 or beta > 1.5 or var_95 < -0.03:
        risk_level = "HIGH"
    elif volatility < 0.20 and beta < 0.8:
        risk_level = "LOW"
    else:
        risk_level = "MEDIUM"

    if beta < 0.8:
        beta_classification = "defensive beta"
    elif beta <= 1.2:
        beta_classification = "market-like beta"
    else:
        beta_classification = "high beta"

    if var_95 < -0.03:
        var_classification = "elevated downside tail risk"
    elif var_95 < -0.02:
        var_classification = "moderate downside tail risk"
    else:
        var_classification = "contained downside tail risk"

    if sharpe >= 1.0:
        sharpe_classification = "strong risk-adjusted returns"
    elif sharpe >= 0.3:
        sharpe_classification = "moderate risk-adjusted returns"
    elif sharpe >= 0:
        sharpe_classification = "weak risk-adjusted returns"
    else:
        sharpe_classification = "negative risk-adjusted returns"

    key_triggers = [
        f"Beta={beta:.2f} ({beta_classification})",
        f"VaR95={var_95:.2%} ({var_classification})",
        f"Sharpe={sharpe:.2f} ({sharpe_classification})",
    ]

    # ── Reasoning ───────────────────────────────────────────────────
    reasoning = (
        f"{symbol} has a beta of {beta:.2f} vs Nifty 50 with "
        f"annualised volatility of {volatility:.1%} and "
        f"VaR-95 of {var_95:.2%} daily. "
        f"The {risk_level} risk classification is based on a Sharpe ratio of "
        f"{sharpe:.2f} and max drawdown of {max_drawdown:.1%}."
    )

    logger.info(
        "%s risk: level=%s beta=%.2f vol=%.2f var95=%.4f sharpe=%.2f mdd=%.2f",
        symbol, risk_level, beta, volatility, var_95, sharpe, max_drawdown,
    )

    return RiskMetrics(
        symbol=symbol,
        beta=round(beta, 3),
        var_95=round(var_95, 4),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown=round(max_drawdown, 4),
        volatility_annualized=round(volatility, 4),
        risk_level=risk_level,
        reasoning=reasoning,
        key_triggers=key_triggers,
    )
