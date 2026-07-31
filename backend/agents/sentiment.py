"""
FinSight — Sentiment Analysis Agent.
Fetches news headlines from Google News RSS, then uses an LLM via
OpenRouter to assess market sentiment and produce a trading signal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import feedparser
import httpx

from backend.models.schemas import OHLCVData, SentimentData

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# ── Configuration ───────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
SENTIMENT_MODEL = os.getenv("SENTIMENT_MODEL", "anthropic/claude-haiku-4-5")

_SYSTEM_PROMPT = (
    "You are a financial sentiment analyzer. Analyze these news headlines "
    "about an Indian stock. Return ONLY valid JSON with these exact keys: "
    "sentiment_score (float -1.0 to 1.0), "
    "sentiment_label (exactly one of: positive, negative, neutral), "
    "key_themes (array of 3 strings, each max 5 words), "
    "signal (exactly one of: BUY, SELL, HOLD), "
    "confidence (float 0.0 to 1.0), "
    "reasoning (string, max 2 sentences). "
    "Do not include any text outside the JSON object."
)


def _fetch_headlines(symbol: str) -> tuple[list[str], bool]:
    """Synchronous helper — fetch headlines from Google News RSS."""
    clean = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
    url = (
        f"https://news.google.com/rss/search?"
        f"q={clean}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"
    )
    try:
        feed = feedparser.parse(url)
        headlines = [entry.title for entry in feed.entries[:10] if getattr(entry, "title", None)]
        if len(headlines) >= 4:
            return headlines, False
    except Exception as exc:
        logger.warning("feedparser failed for %s: %s", clean, exc)

    logger.info("Insufficient live headlines for %s", clean)
    return [], True


def _price_action_profile(symbol: str, ohlcv: Optional[OHLCVData]) -> tuple[float, str, str, float, str]:
    if ohlcv is None or len(ohlcv.closes) < 6:
        return 0.0, "neutral", "HOLD", 0.35, "Price action unavailable — retaining neutral fallback"

    try:
        start_close = float(ohlcv.closes[-6])
        end_close = float(ohlcv.closes[-1])
        if start_close == 0:
            raise ValueError("start_close is zero")
        return_5d = ((end_close - start_close) / start_close) * 100
    except Exception:
        return 0.0, "neutral", "HOLD", 0.35, "Price action unavailable — retaining neutral fallback"

    if return_5d > 2.0:
        score = min(return_5d / 8.0, 1.0)
        return (
            score,
            "positive",
            "BUY",
            min(0.45 + min(abs(return_5d) / 20.0, 0.35), 0.8),
            f"Price momentum positive ({return_5d:.2f}% over 5 sessions)",
        )
    if return_5d < -2.0:
        score = max(return_5d / 8.0, -1.0)
        return (
            score,
            "negative",
            "SELL",
            min(0.45 + min(abs(return_5d) / 20.0, 0.35), 0.8),
            f"Price momentum negative ({return_5d:.2f}% over 5 sessions)",
        )

    return (
        0.0,
        "neutral",
        "HOLD",
        0.4,
        f"Price momentum muted ({return_5d:.2f}% over 5 sessions)",
    )


def _fallback_sentiment(
    symbol: str,
    headlines: list[str],
    ohlcv: Optional[OHLCVData],
    reason: str,
) -> SentimentData:
    """Return a deterministic sentiment fallback with price-action triggers."""
    score, label, signal, confidence, momentum_trigger = _price_action_profile(symbol, ohlcv)

    reason_lc = reason.lower()
    if "sparse" in reason_lc or "insufficient" in reason_lc:
        primary_trigger = (
            "Insufficient news volume for sentiment signal — defaulting to price-action sentiment"
        )
    else:
        primary_trigger = (
            "Primary sentiment feed unavailable — defaulting to price-action sentiment"
        )

    triggers = [
        primary_trigger,
        momentum_trigger,
    ]

    return SentimentData(
        symbol=symbol,
        headlines=headlines,
        sentiment_score=round(score, 2),
        sentiment_label=label,
        key_themes=["price-action fallback", "thin news flow", "short-horizon momentum"],
        signal=signal,
        confidence=round(confidence, 2),
        reasoning=f"{reason}. {momentum_trigger}.",
        key_triggers=triggers,
    )


async def _call_openrouter(headlines: list[str]) -> str:
    """Call OpenRouter chat completion and return the raw model content."""
    payload = {
        "model": SENTIMENT_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Headlines: {json.dumps(headlines)}",
            },
        ],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(2):
            try:
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Strip markdown fences if present
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(
                        line for line in lines if not line.strip().startswith("```")
                    )

                return content
            except httpx.RequestError as exc:
                if attempt == 0:
                    logger.warning(
                        "OpenRouter network error, retrying once in 2s: %s", exc
                    )
                    await asyncio.sleep(2)
                    continue
                raise

    # Defensive fallback; loop always returns or raises.
    raise RuntimeError("OpenRouter request unexpectedly produced no response")


async def run(symbol: str, ohlcv: Optional[OHLCVData] = None) -> SentimentData:
    """
    Fetch news headlines and analyse sentiment via LLM.
    Falls back to price-action-derived sentiment when news coverage is thin
    or LLM output is unavailable.
    """
    loop = asyncio.get_event_loop()
    headlines, insufficient_news = await loop.run_in_executor(_executor, _fetch_headlines, symbol)

    logger.info("%s sentiment: fetched %d headlines", symbol, len(headlines))

    if insufficient_news:
        return _fallback_sentiment(
            symbol=symbol,
            headlines=headlines,
            ohlcv=ohlcv,
            reason="Headline coverage is too sparse for stable NLP sentiment",
        )

    # If no API key, use deterministic price-action fallback.
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set — using price-action fallback")
        return _fallback_sentiment(
            symbol=symbol,
            headlines=headlines,
            ohlcv=ohlcv,
            reason="LLM sentiment provider is unavailable",
        )

    try:
        raw_content = await _call_openrouter(headlines)

        try:
            result: dict[str, Any] = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Sentiment JSON parsing failed for %s: %s", symbol, exc)
            return _fallback_sentiment(
                symbol=symbol,
                headlines=headlines,
                ohlcv=ohlcv,
                reason="Sentiment parser could not decode LLM response",
            )

        # Validate and clamp values
        sentiment_score = max(-1.0, min(1.0, float(result.get("sentiment_score", 0.0))))
        sentiment_label = result.get("sentiment_label", "neutral")
        if sentiment_label not in ("positive", "negative", "neutral"):
            sentiment_label = "neutral"

        signal = result.get("signal", "HOLD")
        if signal not in ("BUY", "SELL", "HOLD"):
            signal = "HOLD"

        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

        key_themes = result.get("key_themes", [])
        if not isinstance(key_themes, list) or len(key_themes) < 1:
            key_themes = ["market analysis", "stock performance", "sector trends"]

        key_triggers: list[str] = []
        if sentiment_score >= 0.25:
            key_triggers.append(f"Headline sentiment skewed positive (score {sentiment_score:.2f})")
        elif sentiment_score <= -0.25:
            key_triggers.append(f"Headline sentiment skewed negative (score {sentiment_score:.2f})")
        else:
            key_triggers.append(f"Headline sentiment mixed (score {sentiment_score:.2f})")

        if key_themes:
            key_triggers.append(f"Dominant themes: {', '.join(key_themes[:3])}")

        if len(key_triggers) < 2:
            key_triggers.append("News signal quality is moderate; confidence remains constrained")

        reasoning = str(result.get("reasoning", f"Sentiment analysis for {symbol}."))

        logger.info(
            "%s sentiment: label=%s score=%.2f signal=%s confidence=%.2f",
            symbol, sentiment_label, sentiment_score, signal, confidence,
        )

        return SentimentData(
            symbol=symbol,
            headlines=headlines,
            sentiment_score=round(sentiment_score, 2),
            sentiment_label=sentiment_label,
            key_themes=key_themes[:5],
            signal=signal,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            key_triggers=key_triggers,
        )

    except Exception as exc:
        logger.error("Sentiment LLM call failed for %s: %s", symbol, exc)
        return _fallback_sentiment(
            symbol=symbol,
            headlines=headlines,
            ohlcv=ohlcv,
            reason="Sentiment LLM request failed",
        )
