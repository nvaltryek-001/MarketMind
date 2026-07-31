from __future__ import annotations

import asyncio
import math
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.cache import ANALYSIS_TTL_SECONDS, LIVE_QUOTES_TTL_SECONDS, analysis_cache, live_quote_cache
from api.services.market_data import (
    InvalidSymbolError,
    NSEMarketDataService,
    SymbolNotFoundError,
    UpstreamServiceError,
)
from engines.expiry_pattern import ExpiryPatternEngine
from engines.filing_anomaly import FilingAnomalyDetector
from engines.promoter_velocity import PromoterVelocityEngine

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _service(request: Request) -> NSEMarketDataService:
    return request.app.state.market_data_service


def _cache_key(route_name: str, symbol: str) -> str:
    return f"analysis:{route_name}:{symbol}"


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
            "message": "Unexpected error while processing analysis",
        },
    )


async def _ensure_symbol_exists(service: NSEMarketDataService, symbol: str) -> dict[str, Any]:
    key = f"stock:snapshot:{symbol}"
    cached = live_quote_cache.get(key)
    if cached is not None:
        return cached

    snapshot = await service.get_snapshot(symbol)
    live_quote_cache.set(key, snapshot, LIVE_QUOTES_TTL_SECONDS)
    return snapshot


def _safe_float(value: Any, precision: int = 4) -> float | None:
    if value is None:
        return None

    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(as_float):
        return None

    return round(as_float, precision)


async def _build_promoter_velocity(service: NSEMarketDataService, symbol: str) -> dict[str, Any]:
    shareholding_payload, price_history = await asyncio.gather(
        service.get_shareholding(symbol, quarters=8),
        service.get_price_history(symbol, period="2y", interval="1d"),
    )

    engine = PromoterVelocityEngine(
        shareholding_history={symbol: shareholding_payload.get("quarters", [])},
        price_history={symbol: price_history.get("data", [])},
    )

    velocity = engine.calculate_velocity(shareholding_payload.get("quarters", []))
    anomaly = engine.flag_anomaly(symbol)
    signal = engine.generate_signal(symbol)
    correlation = engine.correlate_with_price(symbol)

    return {
        "symbol": symbol,
        "velocity": velocity,
        "anomaly": anomaly,
        "signal": signal,
        "historical_correlation_30d": _safe_float(correlation),
        "quarters_analyzed": len(shareholding_payload.get("quarters", [])),
    }


async def _build_expiry_pattern(service: NSEMarketDataService, symbol: str) -> dict[str, Any]:
    price_history = await service.get_price_history(symbol, period="2y", interval="1d")

    engine = ExpiryPatternEngine(eod_history={symbol: price_history.get("data", [])})
    window_returns = engine.calculate_expiry_window_returns(symbol, lookback_months=12)
    pattern = engine.detect_pattern(symbol)
    current_signal = engine.get_current_expiry_signal(symbol)

    return {
        "symbol": symbol,
        "pattern": pattern,
        "current_signal": current_signal,
        "window_returns": window_returns,
    }


async def _build_filing_flags(symbol: str) -> dict[str, Any]:
    detector = FilingAnomalyDetector()
    return await asyncio.to_thread(detector.score_risk, symbol)


def _expiry_opportunity_score(expiry_payload: dict[str, Any]) -> float:
    current_signal = expiry_payload.get("current_signal", {})
    directional_bias = str(current_signal.get("directional_bias") or "neutral").lower()
    confidence = float(current_signal.get("pattern_confidence") or 0.0)

    if directional_bias == "bullish":
        return min(100.0, 50.0 + confidence * 0.5)
    if directional_bias == "bearish":
        return max(0.0, 50.0 - confidence * 0.5)
    return 50.0


def _build_composite_score(
    promoter_payload: dict[str, Any],
    expiry_payload: dict[str, Any],
    filing_payload: dict[str, Any],
) -> dict[str, Any]:
    promoter_strength = float(promoter_payload.get("signal", {}).get("signal_strength") or 0.0)
    expiry_score = _expiry_opportunity_score(expiry_payload)
    filing_risk = float(filing_payload.get("risk_score") or 0.0)

    composite_score = round(
        (0.45 * promoter_strength) + (0.25 * expiry_score) + (0.30 * (100.0 - filing_risk)),
        2,
    )

    if composite_score >= 70:
        outlook = "strong_opportunity"
    elif composite_score >= 55:
        outlook = "opportunity"
    elif composite_score >= 45:
        outlook = "neutral"
    elif composite_score >= 30:
        outlook = "caution"
    else:
        outlook = "high_risk"

    return {
        "composite_score": composite_score,
        "outlook": outlook,
        "component_scores": {
            "promoter_signal_strength": round(promoter_strength, 2),
            "expiry_pattern_opportunity": round(expiry_score, 2),
            "filing_resilience": round(100.0 - filing_risk, 2),
            "filing_risk": round(filing_risk, 2),
        },
        "weights": {
            "promoter_signal_strength": 0.45,
            "expiry_pattern_opportunity": 0.25,
            "filing_resilience": 0.30,
        },
    }


@router.get("/{symbol}/promoter-velocity")
async def get_promoter_velocity(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        key = _cache_key("promoter_velocity", clean_symbol)

        cached_payload = analysis_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "analysis": cached_payload,
            }

        await _ensure_symbol_exists(service, clean_symbol)
        payload = await _build_promoter_velocity(service, clean_symbol)
        analysis_cache.set(key, payload, ANALYSIS_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "analysis": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/expiry-pattern")
async def get_expiry_pattern(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        key = _cache_key("expiry_pattern", clean_symbol)

        cached_payload = analysis_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "analysis": cached_payload,
            }

        await _ensure_symbol_exists(service, clean_symbol)
        payload = await _build_expiry_pattern(service, clean_symbol)
        analysis_cache.set(key, payload, ANALYSIS_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "analysis": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/filing-flags")
async def get_filing_flags(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        key = _cache_key("filing_flags", clean_symbol)

        cached_payload = analysis_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "analysis": cached_payload,
            }

        await _ensure_symbol_exists(service, clean_symbol)
        payload = await _build_filing_flags(clean_symbol)
        analysis_cache.set(key, payload, ANALYSIS_TTL_SECONDS)
        return {
            "symbol": clean_symbol,
            "cached": False,
            "analysis": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/{symbol}/composite-score")
async def get_composite_score(symbol: str, request: Request) -> dict[str, Any]:
    service = _service(request)
    try:
        clean_symbol = service.normalize_symbol(symbol)
        key = _cache_key("composite_score", clean_symbol)

        cached_payload = analysis_cache.get(key)
        if cached_payload is not None:
            return {
                "symbol": clean_symbol,
                "cached": True,
                "analysis": cached_payload,
            }

        await _ensure_symbol_exists(service, clean_symbol)

        promoter_key = _cache_key("promoter_velocity", clean_symbol)
        expiry_key = _cache_key("expiry_pattern", clean_symbol)
        filing_key = _cache_key("filing_flags", clean_symbol)

        promoter_payload = analysis_cache.get(promoter_key)
        expiry_payload = analysis_cache.get(expiry_key)
        filing_payload = analysis_cache.get(filing_key)

        if promoter_payload is None:
            promoter_payload = await _build_promoter_velocity(service, clean_symbol)
            analysis_cache.set(promoter_key, promoter_payload, ANALYSIS_TTL_SECONDS)
        if expiry_payload is None:
            expiry_payload = await _build_expiry_pattern(service, clean_symbol)
            analysis_cache.set(expiry_key, expiry_payload, ANALYSIS_TTL_SECONDS)
        if filing_payload is None:
            filing_payload = await _build_filing_flags(clean_symbol)
            analysis_cache.set(filing_key, filing_payload, ANALYSIS_TTL_SECONDS)

        composite = _build_composite_score(promoter_payload, expiry_payload, filing_payload)
        payload = {
            "symbol": clean_symbol,
            "composite": composite,
            "inputs": {
                "promoter_velocity_signal": promoter_payload.get("signal"),
                "expiry_pattern_signal": expiry_payload.get("current_signal"),
                "filing_risk": {
                    "risk_score": filing_payload.get("risk_score"),
                    "flags_found": filing_payload.get("flags_found"),
                    "latest_flag_date": filing_payload.get("latest_flag_date"),
                },
            },
        }
        analysis_cache.set(key, payload, ANALYSIS_TTL_SECONDS)

        return {
            "symbol": clean_symbol,
            "cached": False,
            "analysis": payload,
        }
    except Exception as exc:
        raise _http_error(exc) from exc
