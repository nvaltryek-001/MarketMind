"""
FinSight — Technical Analysis Agent.
Calculates RSI, MACD, Bollinger Bands, SMA-50/200 and derives a
weighted-score trading signal.
"""

from __future__ import annotations

import logging

import pandas as pd

try:
    import pandas_ta as ta  # noqa: F401
except ModuleNotFoundError:
    import pandas_ta_classic as ta  # type: ignore[import-not-found]  # noqa: F401

from backend.models.schemas import OHLCVData, TechnicalSignals

logger = logging.getLogger(__name__)


async def run(symbol: str, ohlcv: OHLCVData) -> TechnicalSignals:
    """
    Run technical analysis on OHLCV data and return a signal with
    confidence score and human-readable reasoning.
    """
    # ── Build DataFrame ─────────────────────────────────────────────
    df = pd.DataFrame(
        {
            "Open": ohlcv.opens,
            "High": ohlcv.highs,
            "Low": ohlcv.lows,
            "Close": ohlcv.closes,
            "Volume": ohlcv.volumes,
        },
        index=pd.to_datetime(ohlcv.dates),
    )

    # ── Indicators ──────────────────────────────────────────────────
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=200, append=True)

    latest = df.iloc[-1]
    price = float(latest["Close"])

    # Extract indicator values (handle column name variations)
    rsi = float(latest.get("RSI_14", 50.0))

    macd_val = float(latest.get("MACD_12_26_9", 0.0))
    macd_signal = float(latest.get("MACDs_12_26_9", 0.0))

    bb_upper = float(latest.get("BBU_20_2.0", price * 1.02))
    bb_lower = float(latest.get("BBL_20_2.0", price * 0.98))
    bb_middle = float(latest.get("BBM_20_2.0", price))

    sma_50 = float(latest.get("SMA_50", price))
    sma_200 = float(latest.get("SMA_200", price))

    # ── Trend determination ─────────────────────────────────────────
    if price > sma_50 > sma_200:
        trend = "bullish"
    elif price < sma_50 < sma_200:
        trend = "bearish"
    else:
        trend = "sideways"

    # ── Weighted scoring system ─────────────────────────────────────
    score = 0
    key_triggers: list[str] = []

    # RSI
    rsi_contrib = 0
    if rsi < 30:
        rsi_contrib = 2
        key_triggers.append(f"RSI oversold at {rsi:.1f}")
    elif rsi < 50:
        rsi_contrib = 1
    elif rsi > 70:
        rsi_contrib = -2
        key_triggers.append(f"RSI overbought at {rsi:.1f}")
    else:  # 50–70
        rsi_contrib = -1
    score += rsi_contrib

    # MACD vs signal line
    macd_contrib = 0
    if macd_val > macd_signal:
        macd_contrib = 2
        key_triggers.append("MACD crossed above signal line")
    else:
        macd_contrib = -2
        key_triggers.append("MACD remains below signal line")
    score += macd_contrib

    # Bollinger Band position
    bb_contrib = 0
    if price < bb_lower:
        bb_contrib = 1
        key_triggers.append("Price at lower Bollinger Band — potential bounce")
    elif price > bb_upper:
        bb_contrib = -1
        key_triggers.append("Price at upper Bollinger Band — near-term stretch risk")
    score += bb_contrib

    if price > sma_200:
        key_triggers.append("Price above 200 SMA — uptrend structure")
    else:
        key_triggers.append("Price below 200 SMA — long-term trend pressure")

    # Trend
    if trend == "bullish":
        score += 2
    elif trend == "bearish":
        score -= 2

    # Golden cross zone
    if sma_50 > sma_200:
        score += 1
    else:
        score -= 1

    # ── Signal & confidence ─────────────────────────────────────────
    if score > 3:
        signal = "BUY"
    elif score < -3:
        signal = "SELL"
    else:
        signal = "HOLD"

    max_possible = 8
    confidence = round(min(abs(score) / max_possible, 1.0), 2)
    if len(key_triggers) < 2:
        key_triggers.append(f"RSI at {rsi:.1f} indicates balanced momentum")
    if len(key_triggers) < 2:
        key_triggers.append("Price is consolidating around moving-average support/resistance")

    # ── Human-readable reasoning ────────────────────────────────────
    reasoning = (
        f"{symbol} shows a {trend} trend with RSI at {rsi:.1f} and "
        f"MACD {'above' if macd_val > macd_signal else 'below'} the signal line. "
        f"Price is {'near lower Bollinger Band suggesting oversold conditions' if price < bb_lower else 'near upper Bollinger Band suggesting overbought conditions' if price > bb_upper else 'within Bollinger Bands'} "
        f"with SMA-50 {'above' if sma_50 > sma_200 else 'below'} SMA-200, "
        f"yielding a composite technical score of {score}/{max_possible}."
    )

    logger.info(
        "%s technical: signal=%s confidence=%.2f trend=%s rsi=%.1f score=%d",
        symbol, signal, confidence, trend, rsi, score,
    )

    return TechnicalSignals(
        symbol=symbol,
        rsi=round(rsi, 2),
        macd=round(macd_val, 4),
        macd_signal=round(macd_signal, 4),
        bb_upper=round(bb_upper, 2),
        bb_lower=round(bb_lower, 2),
        bb_middle=round(bb_middle, 2),
        sma_50=round(sma_50, 2),
        sma_200=round(sma_200, 2),
        trend=trend,
        signal=signal,
        confidence=confidence,
        reasoning=reasoning,
        key_triggers=key_triggers,
    )
