"""
FinSight — Meta-Synthesis Agent.
Combines technical, fundamental, sentiment, risk, and ML prediction outputs
into a unified investment verdict with a detailed research report.
"""

from __future__ import annotations

from collections import Counter
import logging
import os
from datetime import datetime, timezone

import httpx

from backend.models.schemas import (
    FundamentalData,
    MacroResult,
    MLPrediction,
    RiskMetrics,
    SentimentData,
    SynthesisResult,
    TechnicalSignals,
)

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "anthropic/claude-haiku-4-5")

AGENT_BASE_WEIGHTS: dict[str, float] = {
    "technical": 0.22,
    "fundamental": 0.30,
    "sentiment": 0.13,
    "risk": 0.20,
    "ml_prediction": 0.15,
}

_SIGNAL_MAP = {"BUY": 1, "HOLD": 0, "SELL": -1}
_SYNTHESIS_VERDICTS = {"BUY", "HOLD", "SELL"}


def _detect_conflicts(
    tech_signal: str,
    fund_signal: str,
    sent_signal: str,
    ml_signal: str,
) -> str | None:
    """Return a note if any two agents directly conflict (BUY vs SELL)."""
    agents = {
        "Technical": tech_signal,
        "Fundamental": fund_signal,
        "Sentiment": sent_signal,
        "ML": ml_signal,
    }
    conflicts: list[str] = []
    names = list(agents.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            sig_a, sig_b = agents[a], agents[b]
            if (sig_a == "BUY" and sig_b == "SELL") or (
                sig_a == "SELL" and sig_b == "BUY"
            ):
                conflicts.append(
                    f"{a} ({sig_a}) conflicts with {b} ({sig_b})"
                )
    return "; ".join(conflicts) if conflicts else None


def _estimate_price_target(verdict: str, confidence: float) -> float:
    """Estimate price target percentage change based on verdict and confidence."""
    if verdict == "BUY":
        return round(8.0 + 7.0 * confidence, 1)  # +8% to +15%
    elif verdict == "SELL":
        return round(-5.0 - 7.0 * confidence, 1)  # -5% to -12%
    else:
        return round(-2.0 + 5.0 * confidence, 1)  # -2% to +3%


def _confidence_to_score(confidence: float) -> float:
    return round(max(0.0, min(10.0, float(confidence) * 10.0)), 2)


def _normalized_triggers(triggers: list[str] | None, fallback: list[str]) -> list[str]:
    cleaned = [str(item).strip() for item in (triggers or []) if str(item).strip()]
    return cleaned if cleaned else fallback


def _clamp_unit_interval(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _compute_weighted_verdict(agent_results: list[dict[str, object]]) -> str:
    verdict_weights = {"BUY": 0.0, "HOLD": 0.0, "SELL": 0.0}
    for agent in agent_results:
        verdict = str(agent.get("verdict", "HOLD")).upper()
        if verdict not in verdict_weights:
            continue
        weight = max(0.0, float(agent.get("weight", 0.0)))
        verdict_weights[verdict] += weight

    max_weight = max(verdict_weights.values())
    if max_weight <= 0.0:
        return "HOLD"

    winners = [
        verdict
        for verdict, weight in verdict_weights.items()
        if abs(weight - max_weight) < 1e-9
    ]
    if len(winners) == 1:
        return winners[0]

    # Conservative tie-break keeps HOLD preferred over directional calls.
    for fallback_verdict in ("HOLD", "BUY", "SELL"):
        if fallback_verdict in winners:
            return fallback_verdict
    return "HOLD"


def compute_synthesis_confidence(
    agent_results: list[dict[str, object]],
    majority_verdict: str | None = None,
) -> float:
    valid: list[dict[str, object]] = []
    for agent in agent_results:
        verdict = str(agent.get("verdict", "HOLD")).upper()
        if verdict == "INSUFFICIENT_DATA":
            continue
        if verdict not in _SYNTHESIS_VERDICTS:
            verdict = "HOLD"

        weight = max(0.0, float(agent.get("weight", 0.0)))
        valid.append(
            {
                "verdict": verdict,
                "weight": weight,
                "confidence": _clamp_unit_interval(agent.get("confidence", 0.0)),
            }
        )

    if not valid:
        return 0.1

    total_weight = sum(float(agent["weight"]) for agent in valid)
    if total_weight <= 0.0:
        return 0.1

    selected_verdict = (majority_verdict or "").upper()
    if selected_verdict not in _SYNTHESIS_VERDICTS:
        verdicts = [str(agent["verdict"]) for agent in valid]
        selected_verdict = Counter(verdicts).most_common(1)[0][0]

    agreeing_weight = sum(
        float(agent["weight"])
        for agent in valid
        if str(agent["verdict"]) == selected_verdict
    )
    agreement_ratio = agreeing_weight / total_weight

    avg_conf = (
        sum(float(agent["confidence"]) * float(agent["weight"]) for agent in valid)
        / total_weight
    )

    confidence = (agreement_ratio * 0.6) + (avg_conf * 0.4)
    return round(max(0.0, min(1.0, confidence)), 3)


async def _generate_report(
    symbol: str,
    verdict: str,
    confidence: float,
    technical: TechnicalSignals,
    fundamental: FundamentalData,
    sentiment: SentimentData,
    risk: RiskMetrics,
    ml_prediction: MLPrediction,
    macro_result: MacroResult,
    conflict_notes: str | None,
) -> str:
    """Call OpenRouter to generate a detailed research report."""
    if not OPENROUTER_API_KEY:
        return _fallback_report(
            symbol,
            verdict,
            confidence,
            technical,
            fundamental,
            sentiment,
            risk,
            ml_prediction,
            macro_result,
        )

    system_prompt = (
        "You are a SEBI-registered equity research analyst writing "
        "institutional-grade research reports for Indian retail investors. "
        "Write clearly, use data-driven arguments, and avoid speculation."
    )

    user_prompt = f"""Write a 400-word equity research report for {symbol} (NSE).

PRE-CALCULATED VERDICT: {verdict} (Confidence: {confidence:.0%})

TECHNICAL DATA:
- RSI (14): {technical.rsi:.1f}
- MACD: {technical.macd:.4f} (Signal: {technical.macd_signal:.4f})
- Bollinger Bands: Lower {technical.bb_lower:.2f} | Middle {technical.bb_middle:.2f} | Upper {technical.bb_upper:.2f}
- SMA-50: {technical.sma_50:.2f} | SMA-200: {technical.sma_200:.2f}
- Trend: {technical.trend}
- Technical Signal: {technical.signal} ({technical.confidence:.0%})

FUNDAMENTAL DATA:
- Sector: {fundamental.sector}
- PE Ratio: {fundamental.pe_ratio or 'N/A'} (Sector Avg: {fundamental.sector_pe_avg:.1f})
- P/B Ratio: {fundamental.pb_ratio or 'N/A'}
- Debt-to-Equity: {fundamental.debt_to_equity or 'N/A'}
- EPS: {fundamental.eps or 'N/A'}
- Revenue Growth: {f'{fundamental.revenue_growth:.1%}' if fundamental.revenue_growth else 'N/A'}
- ROE: {f'{fundamental.roe:.1%}' if fundamental.roe else 'N/A'}
- Fundamental Signal: {fundamental.signal} ({fundamental.confidence:.0%})

SENTIMENT DATA:
- Score: {sentiment.sentiment_score:.2f} ({sentiment.sentiment_label})
- Key Themes: {', '.join(sentiment.key_themes)}
- Sentiment Signal: {sentiment.signal} ({sentiment.confidence:.0%})

ML PREDICTION DATA:
- Horizon: {ml_prediction.prediction_horizon}
- Predicted Direction: {ml_prediction.predicted_direction}
- ML Signal: {ml_prediction.signal} ({ml_prediction.prediction_confidence:.0%})
- Model: {ml_prediction.model_name}
- Test F1 Score: {ml_prediction.model_metrics.f1_score:.0%}
- Top Features: {', '.join(f.feature_name for f in ml_prediction.feature_importances[:3]) if ml_prediction.feature_importances else 'N/A'}

RISK DATA:
- Beta vs Nifty 50: {risk.beta:.2f}
- VaR (95%): {risk.var_95:.2%}
- Annualized Volatility: {risk.volatility_annualized:.1%}
- Sharpe Ratio: {risk.sharpe_ratio:.2f}
- Max Drawdown: {risk.max_drawdown:.1%}
- Risk Level: {risk.risk_level}

MACRO FLOW DATA (NSE FII/DII):
- FII Net (5D): {macro_result.fii_net_5d:+.2f} Cr
- DII Net (5D): {macro_result.dii_net_5d:+.2f} Cr
- Macro Signal: {macro_result.macro_signal}
- Confidence Multiplier Applied: {macro_result.confidence_multiplier:.1f}x

{f'CONFLICTS: {conflict_notes}' if conflict_notes else 'No agent conflicts detected.'}

Structure the report with these sections:
1. **Executive Summary** — 2-3 sentences with the verdict
2. **Technical Picture** — Key indicator readings and trend
3. **Fundamental Health** — Valuation, profitability, debt
4. **Market Sentiment** — News themes and market mood
5. **ML Outlook** — Model direction signal, confidence, and key drivers
6. **Risk Assessment** — Volatility, beta, drawdown profile
7. **Macro Flows** — FII/DII context and how it impacts conviction
8. **Investment Verdict** — Final recommendation with rationale

End with: "Disclaimer: This report is AI-generated for educational purposes only and does not constitute investment advice. Consult a SEBI-registered advisor before making investment decisions."
"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": SYNTHESIS_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    except Exception as exc:
        logger.error("Report generation failed for %s: %s", symbol, exc)
        return _fallback_report(
            symbol,
            verdict,
            confidence,
            technical,
            fundamental,
            sentiment,
            risk,
            ml_prediction,
            macro_result,
        )


def _fallback_report(
    symbol: str,
    verdict: str,
    confidence: float,
    technical: TechnicalSignals,
    fundamental: FundamentalData,
    sentiment: SentimentData,
    risk: RiskMetrics,
    ml_prediction: MLPrediction,
    macro_result: MacroResult,
) -> str:
    """Generate a template-based report when LLM is unavailable."""
    return f"""# {symbol} — Equity Research Report

## Executive Summary
Based on multi-factor analysis, {symbol} receives a **{verdict}** recommendation with {confidence:.0%} confidence. This assessment integrates technical, fundamental, sentiment, and risk analysis.

## Technical Picture
The stock shows a {technical.trend} trend with RSI at {technical.rsi:.1f}. MACD is {'above' if technical.macd > technical.macd_signal else 'below'} the signal line. Price is trading {'above' if technical.sma_50 > technical.sma_200 else 'below'} the golden cross zone (SMA-50 vs SMA-200). Technical signal: {technical.signal}.

## Fundamental Health
Operating in the {fundamental.sector} sector, the company has a PE of {fundamental.pe_ratio or 'N/A'} vs sector average of {fundamental.sector_pe_avg:.1f}. Debt-to-equity stands at {fundamental.debt_to_equity or 'N/A'} with ROE of {f'{fundamental.roe:.1%}' if fundamental.roe else 'N/A'}. Fundamental signal: {fundamental.signal}.

## Market Sentiment
Current sentiment is {sentiment.sentiment_label} (score: {sentiment.sentiment_score:.2f}). Key themes: {', '.join(sentiment.key_themes)}. Sentiment signal: {sentiment.signal}.

## ML Outlook
The {ml_prediction.model_name} forecasts a {ml_prediction.predicted_direction} move over the next 5 trading days with {ml_prediction.prediction_confidence:.0%} confidence, mapping to an {ml_prediction.signal} signal. The model achieved {ml_prediction.model_metrics.f1_score:.0%} weighted F1 on held-out test data.

## Risk Assessment
{symbol} has a beta of {risk.beta:.2f} vs Nifty 50 with annualised volatility of {risk.volatility_annualized:.1%}. VaR-95 is {risk.var_95:.2%} daily, and max drawdown is {risk.max_drawdown:.1%}. Risk level: {risk.risk_level}.

## Macro Flows
NSE FII/DII activity over the last 5 sessions shows FII net flow of {macro_result.fii_net_5d:+.2f} Cr and DII net flow of {macro_result.dii_net_5d:+.2f} Cr. This maps to a {macro_result.macro_signal} macro signal and applies a {macro_result.confidence_multiplier:.1f}x confidence multiplier.

## Investment Verdict
**{verdict}** with {confidence:.0%} confidence.

Disclaimer: This report is AI-generated for educational purposes only and does not constitute investment advice. Consult a SEBI-registered advisor before making investment decisions.
"""


async def run(
    symbol: str,
    technical: TechnicalSignals,
    fundamental: FundamentalData,
    sentiment: SentimentData,
    risk: RiskMetrics,
    ml_prediction: MLPrediction,
    macro_result: MacroResult,
) -> SynthesisResult:
    """
    Synthesise all agent outputs into a final verdict and report.
    """
    # ── 1. Adjust weights based on risk ─────────────────────────────
    weights = AGENT_BASE_WEIGHTS.copy()
    if risk.risk_level == "HIGH":
        weights["technical"] -= 0.05
        weights["fundamental"] += 0.05

    ml_model_valid = bool(getattr(ml_prediction, "model_valid", True))
    if not ml_model_valid:
        weights["ml_prediction"] = 0.0

    # ── 2. Convert signals to numeric ───────────────────────────────
    tech_num = _SIGNAL_MAP.get(technical.signal, 0)
    fund_num = _SIGNAL_MAP.get(fundamental.signal, 0)
    sent_num = _SIGNAL_MAP.get(sentiment.signal, 0)
    ml_signal_for_score = ml_prediction.signal if ml_model_valid else "HOLD"
    ml_num = _SIGNAL_MAP.get(ml_signal_for_score, 0)

    # Risk doesn't produce BUY/SELL directly — use inverse of risk
    risk_num = {"LOW": 1, "MEDIUM": 0, "HIGH": -1}.get(risk.risk_level, 0)

    # ── 3. Weighted score ───────────────────────────────────────────
    tech_contribution = tech_num * technical.confidence * weights["technical"]
    fund_contribution = fund_num * fundamental.confidence * weights["fundamental"]
    sent_contribution = sent_num * sentiment.confidence * weights["sentiment"]
    risk_contribution = risk_num * 0.7 * weights["risk"]  # use moderate confidence for risk
    ml_contribution = ml_num * ml_prediction.prediction_confidence * weights["ml_prediction"]

    weighted_score = (
        tech_contribution
        + fund_contribution
        + sent_contribution
        + risk_contribution
        + ml_contribution
    )

    # ── 4. Decision logic traceability map ──────────────────────────
    risk_signal = {"LOW": "BUY", "MEDIUM": "HOLD", "HIGH": "SELL"}.get(
        risk.risk_level,
        "HOLD",
    )

    technical_triggers = _normalized_triggers(
        list(getattr(technical, "key_triggers", [])),
        [
            f"RSI at {technical.rsi:.1f}",
            f"Trend classified as {technical.trend}",
        ],
    )
    fundamental_triggers = _normalized_triggers(
        list(getattr(fundamental, "key_triggers", [])),
        [
            f"Sector valuation context: {fundamental.sector}",
            "Fundamental signal generated from valuation, growth, and leverage",
        ],
    )

    sentiment_triggers = _normalized_triggers(
        list(getattr(sentiment, "key_triggers", [])),
        [
            f"Sentiment score={sentiment.sentiment_score:.2f} ({sentiment.sentiment_label})",
            (
                f"Themes: {', '.join(sentiment.key_themes[:3])}"
                if sentiment.key_themes
                else "Themes unavailable from sentiment feed"
            ),
        ],
    )

    ml_triggers = _normalized_triggers(
        list(getattr(ml_prediction, "key_triggers", [])),
        [
            (
                f"Predicted direction={ml_prediction.predicted_direction} "
                f"for {ml_prediction.prediction_horizon} ({ml_prediction.signal})"
            ),
            f"Model confidence={ml_prediction.prediction_confidence:.0%}",
        ],
    )
    risk_triggers = _normalized_triggers(
        list(getattr(risk, "key_triggers", [])),
        [
            f"Risk profile={risk.risk_level}",
            f"Volatility annualized={risk.volatility_annualized:.1%}",
        ],
    )

    ml_weight_override = getattr(ml_prediction, "weight_override", None)
    ml_card_weight = (
        float(ml_weight_override)
        if isinstance(ml_weight_override, (int, float))
        else weights["ml_prediction"]
    )

    technical_score = _confidence_to_score(technical.confidence)
    fundamental_score = _confidence_to_score(fundamental.confidence)
    sentiment_score = _confidence_to_score(sentiment.confidence)
    risk_confidence = 0.7
    risk_score = float({"LOW": 8, "MEDIUM": 5, "HIGH": 2}.get(risk.risk_level, 5))
    ml_confidence = round(max(0.0, min(1.0, float(ml_prediction.prediction_confidence))), 4)
    ml_score_override = getattr(ml_prediction, "score_override", None)
    ml_score = (
        float(ml_score_override)
        if isinstance(ml_score_override, (int, float))
        else _confidence_to_score(ml_prediction.prediction_confidence)
    )
    ml_verdict = str(getattr(ml_prediction, "verdict", ml_prediction.signal)).upper()
    if ml_verdict not in {"BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"}:
        ml_verdict = "HOLD"

    card_data: dict[str, dict] = {
        "technical": {
            "agent": "technical",
            "verdict": technical.signal,
            "weight": round(weights["technical"], 4),
            "score": technical_score,
            "weighted_score": round(technical_score * float(weights["technical"]), 4),
            "triggers": technical_triggers,
            "confidence": round(float(technical.confidence), 4),
        },
        "fundamental": {
            "agent": "fundamental",
            "verdict": fundamental.signal,
            "weight": round(weights["fundamental"], 4),
            "score": fundamental_score,
            "weighted_score": round(fundamental_score * float(weights["fundamental"]), 4),
            "triggers": fundamental_triggers,
            "confidence": round(float(fundamental.confidence), 4),
        },
        "sentiment": {
            "agent": "sentiment",
            "verdict": sentiment.signal,
            "weight": round(weights["sentiment"], 4),
            "score": sentiment_score,
            "weighted_score": round(sentiment_score * float(weights["sentiment"]), 4),
            "triggers": sentiment_triggers,
            "confidence": round(float(sentiment.confidence), 4),
        },
        "risk": {
            "agent": "risk",
            "verdict": risk_signal,
            "score": risk_score,
            "weight": round(weights["risk"], 4),
            "weighted_score": round(risk_score * float(weights["risk"]), 4),
            "triggers": risk_triggers,
            "confidence": risk_confidence,
        },
        "ml_prediction": {
            "agent": "ml_prediction",
            "verdict": ml_verdict,
            "weight": round(ml_card_weight, 4),
            "score": ml_score,
            "weighted_score": round(ml_score * float(ml_card_weight), 4),
            "triggers": ml_triggers,
            "confidence": ml_confidence,
        },
    }

    # Explicit mapping expected by the card renderer.
    card_data["technical"]["triggers"] = card_data["technical"].get("triggers", [])
    card_data["fundamental"]["triggers"] = card_data["fundamental"].get("triggers", [])
    card_data["sentiment"]["triggers"] = card_data["sentiment"].get("triggers", [])
    card_data["risk"]["triggers"] = card_data["risk"].get("triggers", [])
    card_data["ml_prediction"]["triggers"] = card_data["ml_prediction"].get("triggers", [])

    logic_map: list[dict] = [
        {
            "agent": "technical",
            "signal": card_data["technical"]["verdict"],
            "weight": card_data["technical"]["weight"],
            "score": card_data["technical"]["score"],
            "confidence": card_data["technical"]["confidence"],
            "weighted_score": card_data["technical"]["weighted_score"],
            "contribution": card_data["technical"]["weighted_score"],
            "triggers": card_data["technical"]["triggers"],
            # Backward-compatible keys for older clients.
            "weight_applied": card_data["technical"]["weight"],
            "key_triggers": card_data["technical"]["triggers"],
        },
        {
            "agent": "fundamental",
            "signal": card_data["fundamental"]["verdict"],
            "weight": card_data["fundamental"]["weight"],
            "score": card_data["fundamental"]["score"],
            "confidence": card_data["fundamental"]["confidence"],
            "weighted_score": card_data["fundamental"]["weighted_score"],
            "contribution": card_data["fundamental"]["weighted_score"],
            "triggers": card_data["fundamental"]["triggers"],
            "weight_applied": card_data["fundamental"]["weight"],
            "key_triggers": card_data["fundamental"]["triggers"],
        },
        {
            "agent": "sentiment",
            "signal": card_data["sentiment"]["verdict"],
            "weight": card_data["sentiment"]["weight"],
            "score": card_data["sentiment"]["score"],
            "confidence": card_data["sentiment"]["confidence"],
            "weighted_score": card_data["sentiment"]["weighted_score"],
            "contribution": card_data["sentiment"]["weighted_score"],
            "triggers": card_data["sentiment"]["triggers"],
            "weight_applied": card_data["sentiment"]["weight"],
            "key_triggers": card_data["sentiment"]["triggers"],
        },
        {
            "agent": "risk",
            "signal": card_data["risk"]["verdict"],
            "weight": card_data["risk"]["weight"],
            "score": card_data["risk"]["score"],
            "confidence": card_data["risk"]["confidence"],
            "weighted_score": card_data["risk"]["weighted_score"],
            "contribution": card_data["risk"]["weighted_score"],
            "triggers": card_data["risk"]["triggers"],
            "weight_applied": card_data["risk"]["weight"],
            "key_triggers": card_data["risk"]["triggers"],
        },
        {
            "agent": "ml_prediction",
            "signal": card_data["ml_prediction"]["verdict"],
            "weight": card_data["ml_prediction"]["weight"],
            "score": card_data["ml_prediction"]["score"],
            "confidence": card_data["ml_prediction"]["confidence"],
            "weighted_score": card_data["ml_prediction"]["weighted_score"],
            "contribution": card_data["ml_prediction"]["weighted_score"],
            "triggers": card_data["ml_prediction"]["triggers"],
            "weight_applied": card_data["ml_prediction"]["weight"],
            "key_triggers": card_data["ml_prediction"]["triggers"],
        },
    ]

    # ── 5. Final verdict + confidence from agreement ───────────────
    agent_results: list[dict[str, object]] = []
    for details in card_data.values():
        verdict = str(details.get("verdict", "HOLD")).upper()
        if verdict not in {"BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"}:
            verdict = "HOLD"

        agent_results.append(
            {
                "verdict": verdict,
                "weight": max(0.0, float(details.get("weight", 0.0))),
                "confidence": _clamp_unit_interval(details.get("confidence", 0.0)),
            }
        )

    verdict = _compute_weighted_verdict(agent_results)
    base_confidence = compute_synthesis_confidence(
        agent_results,
        majority_verdict=verdict,
    )
    overall_confidence = round(
        max(0.0, min(base_confidence * macro_result.confidence_multiplier, 1.0)),
        3,
    )

    # ── 6. Conflict detection ───────────────────────────────────────
    conflict_notes = _detect_conflicts(
        technical.signal,
        fundamental.signal,
        sentiment.signal,
        ml_prediction.signal,
    )

    macro_warning = None
    if macro_result.macro_signal == "BEARISH" and verdict == "BUY":
        macro_warning = (
            "Macro conflict: BUY verdict while FII 5-day net flow is strongly "
            "negative (BEARISH macro signal)."
        )
        if conflict_notes:
            conflict_notes = f"{conflict_notes}; {macro_warning}"
        else:
            conflict_notes = macro_warning

    # ── 7. Price target estimate ────────────────────────────────────
    price_target_pct = _estimate_price_target(verdict, overall_confidence)

    # ── 8. Generate detailed report ─────────────────────────────────
    detailed_report = await _generate_report(
        symbol, verdict, overall_confidence,
        technical, fundamental, sentiment, risk, ml_prediction,
        macro_result,
        conflict_notes,
    )

    # ── Summary ─────────────────────────────────────────────────────
    summary = (
        f"{verdict} {symbol} with {overall_confidence:.0%} confidence. "
        f"Technical: {technical.signal}, Fundamental: {fundamental.signal}, "
        f"Sentiment: {sentiment.signal}, ML: {card_data['ml_prediction']['verdict']}, "
        f"Risk: {risk.risk_level}, Macro: {macro_result.macro_signal}."
    )

    logger.info(
        "%s synthesis: verdict=%s confidence=%.2f weighted_score=%.4f macro=%s multiplier=%.2f",
        symbol,
        verdict,
        overall_confidence,
        weighted_score,
        macro_result.macro_signal,
        macro_result.confidence_multiplier,
    )

    return SynthesisResult(
        symbol=symbol,
        final_verdict=verdict,
        overall_confidence=overall_confidence,
        weighted_score=round(weighted_score, 4),
        price_target_pct=price_target_pct,
        summary=summary,
        detailed_report=detailed_report,
        agent_weights=weights,
        logic_map=logic_map,
        card_data=card_data,
        conflict_notes=conflict_notes,
        macro_warning=macro_warning,
        generated_at=datetime.now(timezone.utc),
    )
