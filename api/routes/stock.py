from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Request

from api.cache import ANALYSIS_TTL_SECONDS, LIVE_QUOTES_TTL_SECONDS, analysis_cache, live_quote_cache
from api.services.market_data import (
    InvalidSymbolError,
    NSEMarketDataService,
    SymbolNotFoundError,
    UpstreamServiceError,
)

router = APIRouter(prefix="/api/stock", tags=["stock"])


def _service(request: Request) -> NSEMarketDataService:
    return request.app.state.market_data_service


def _cache_key(route_name: str, symbol: str) -> str:
    return f"stock:{route_name}:{symbol}"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidSymbolError):
        return HTTPException(
            status_code=400,
            detail={
                "error": "invalid_symbol",
                "message": str(exc),
            },
        )
    if isinstance(exc, SymbolNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "error": "symbol_not_found",
                "message": str(exc),
            },
        )
    if isinstance(exc, UpstreamServiceError):
        return HTTPException(
            status_code=502,
            detail={
                "error": "upstream_service_error",
                "message": str(exc),
            },
        )

    return HTTPException(
        status_code=500,
        detail={
            "error": "internal_server_error",
            "message": "Unexpected error while processing request",
        },
    )


async def _ensure_symbol_exists(service: NSEMarketDataService, symbol: str) -> dict[str, Any]:
    key = _cache_key("snapshot", symbol)
    cached = live_quote_cache.get(key)
    if cached is not None:
        return cached

    snapshot = await service.get_snapshot(symbol)
    live_quote_cache.set(key, snapshot, LIVE_QUOTES_TTL_SECONDS)
    return snapshot


def sanitize_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol = symbol + ".NS"
    return symbol


def fetch_ohlcv(symbol: str, period: str = "6mo") -> list[dict[str, Any]] | None:
    clean_symbol = sanitize_symbol(symbol)
    try:
        df = yf.download(
            clean_symbol,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            # Try BSE suffix as fallback
            clean_symbol = symbol.upper() + ".BO"
            df = yf.download(
                clean_symbol,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(column[0]) for column in df.columns]

        df = df.reset_index()
        if "Date" not in df.columns and "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Date"})
        if "Date" not in df.columns and "index" in df.columns:
            df = df.rename(columns={"index": "Date"})
        if "Date" not in df.columns:
            return None

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        if df.empty:
            return None

        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df.columns = [str(c).lower() for c in df.columns]

        required_columns = ["date", "open", "high", "low", "close", "volume"]
        if not set(required_columns).issubset(set(df.columns)):
            return None

        return df[required_columns].to_dict("records")
    except Exception as e:
        print(f"OHLCV fetch failed for {clean_symbol}: {e}")
        return None


@router.get("/{symbol}/snapshot")
async def get_stock_snapshot(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        key = _cache_key("snapshot", clean_symbol)

        cached_payload = live_quote_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "snapshot": cached_payload,
            }

        payload = await service.get_snapshot(clean_symbol)
        live_quote_cache.set(key, payload, LIVE_QUOTES_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "snapshot": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/option-chain")
async def get_stock_option_chain(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        key = _cache_key("option_chain", clean_symbol)

        cached_payload = live_quote_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "option_chain": cached_payload,
            }

        payload = await service.get_option_chain(clean_symbol)
        live_quote_cache.set(key, payload, LIVE_QUOTES_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "option_chain": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/corporate-actions")
async def get_stock_corporate_actions(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        await _ensure_symbol_exists(service, clean_symbol)

        key = _cache_key("corporate_actions", clean_symbol)
        cached_payload = analysis_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "corporate_actions": cached_payload,
            }

        payload = await service.get_corporate_actions(clean_symbol)
        analysis_cache.set(key, payload, ANALYSIS_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "corporate_actions": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/shareholding")
async def get_stock_shareholding(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        await _ensure_symbol_exists(service, clean_symbol)

        key = _cache_key("shareholding", clean_symbol)
        cached_payload = analysis_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "shareholding": cached_payload,
            }

        payload = await service.get_shareholding(clean_symbol, quarters=8)
        analysis_cache.set(key, payload, ANALYSIS_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "shareholding": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/ohlcv")
async def get_stock_ohlcv(symbol: str, period: str = "6mo") -> dict[str, Any]:
    clean_symbol = sanitize_symbol(symbol)
    key = _cache_key("ohlcv", f"{clean_symbol}:{period}")

    cached_payload = live_quote_cache.get(key)
    if cached_payload is not None:
        return {
            "symbol": symbol,
            "period": period,
            "candles": cached_payload,
        }

    data = await asyncio.to_thread(fetch_ohlcv, symbol, period)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data found for {symbol}. Symbol may be delisted or invalid.",
        )

    live_quote_cache.set(key, data, LIVE_QUOTES_TTL_SECONDS)
    return {
        "symbol": symbol,
        "period": period,
        "candles": data,
    }
