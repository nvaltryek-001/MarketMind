"""
FinSight — Data Ingestion Agent.
Fetches 1-year daily OHLCV data from Yahoo Finance for Indian NSE/BSE symbols.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import pandas as pd
import yfinance as yf

from backend.models.schemas import OHLCVData

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


def _fetch_ohlcv(yf_symbol: str) -> Optional[pd.DataFrame]:
    """
    Synchronous helper — download 1 year of daily OHLCV data.
    Returns None if the download yields no rows.
    """
    try:
        df = yf.download(
            yf_symbol,
            period="1y",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        logger.warning("yfinance download failed for %s: %s", yf_symbol, exc)
        return None


def _fetch_ticker_info(yf_symbol: str) -> dict:
    """Fetch Ticker.fast_info for current price / change."""
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.fast_info
        return {
            "current_price": float(info.get("lastPrice", 0) or info.get("last_price", 0)),
            "previous_close": float(info.get("previousClose", 0) or info.get("previous_close", 0)),
        }
    except Exception as exc:
        logger.warning("Ticker info fetch failed for %s: %s", yf_symbol, exc)
        return {"current_price": 0.0, "previous_close": 0.0}


async def run(symbol: str) -> OHLCVData:
    """
    Fetch 1 year of daily OHLCV data for an NSE symbol using yfinance.

    Tries ``SYMBOL.NS`` first, then ``SYMBOL.BO`` as fallback.  Returns
    an :class:`OHLCVData` instance or raises :class:`ValueError` if no
    data can be found after both attempts.
    """
    loop = asyncio.get_event_loop()

    # Strip any existing suffix the user may have passed
    clean_symbol = symbol.replace(".NS", "").replace(".BO", "").strip().upper()

    df: Optional[pd.DataFrame] = None
    resolved_symbol: str = ""

    for suffix in (".NS", ".BO"):
        yf_symbol = f"{clean_symbol}{suffix}"
        logger.info("Trying yfinance download for %s …", yf_symbol)
        df = await loop.run_in_executor(_executor, _fetch_ohlcv, yf_symbol)
        if df is not None and not df.empty:
            resolved_symbol = yf_symbol
            break

    if df is None or df.empty:
        raise ValueError(
            f"No OHLCV data found for '{clean_symbol}' on NSE (.NS) or BSE (.BO)."
        )

    logger.info(
        "Fetched %d rows for %s (resolved as %s)",
        len(df), clean_symbol, resolved_symbol,
    )

    # ── Flatten multi-level columns if present ──────────────────────
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # ── Current price & change percentage ───────────────────────────
    ticker_info = await loop.run_in_executor(
        _executor, _fetch_ticker_info, resolved_symbol,
    )

    current_price = ticker_info["current_price"]
    previous_close = ticker_info["previous_close"]

    # Fallback: use last close from OHLCV data
    if current_price == 0.0:
        current_price = float(df["Close"].iloc[-1])
    if previous_close == 0.0:
        previous_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else current_price

    change_pct = (
        ((current_price - previous_close) / previous_close * 100)
        if previous_close != 0
        else 0.0
    )

    # ── Build OHLCVData ─────────────────────────────────────────────
    return OHLCVData(
        symbol=clean_symbol,
        dates=[d.strftime("%Y-%m-%d") for d in df.index],
        opens=[float(v) for v in df["Open"]],
        highs=[float(v) for v in df["High"]],
        lows=[float(v) for v in df["Low"]],
        closes=[float(v) for v in df["Close"]],
        volumes=[float(v) for v in df["Volume"]],
        current_price=round(current_price, 2),
        change_pct=round(change_pct, 2),
    )
