"""
FinSight — Critic Agent.
Challenges synthesis outputs when agents disagree or confidence is weak.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from backend.models.schemas import CriticResult, SynthesisResult

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
CRITIC_MODEL = os.getenv("CRITIC_MODEL", "anthropic/claude-haiku-4-5")

_SYSTEM_PROMPT = (
    "You are a skeptical analyst. Be concise, specific, and evidence-driven."
)

_BONUS_KEYWORDS = ("debt", "leverage", "overvalued")


def should_challenge(agent_results: list[dict[str, Any]]) -> tuple[bool, str]:
    valid_results = [
        row
        for row in agent_results
        if str(row.get("verdict", "")).upper() != "INSUFFICIENT_DATA"
    ]
    if not valid_results:
        return True, "Insufficient valid agent outputs"

    verdicts = [str(row.get("verdict", "")).upper() for row in valid_results]
    unique_verdicts = set(verdicts)

    # Any disagreement at all = challenge required
    if len(unique_verdicts) > 1:
        conflicting = [
            f"{row.get('agent', 'unknown')}={str(row.get('verdict', 'HOLD')).upper()}"
            for row in valid_results
        ]
        return True, f"Conflicting signals detected: {', '.join(conflicting)}"

    # Low confidence = challenge required
    confidences = [
        float(row.get("confidence", 0.0))
        for row in valid_results
        if isinstance(row.get("confidence"), (int, float))
    ]
    avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0
    if avg_confidence < 0.5:
        return True, f"Low average confidence: {avg_confidence:.0%}"

    return False, ""


class CriticAgent:
    """Second-pass skeptic that stress-tests bullish synthesis calls."""

    @staticmethod
    def _normalize_confidence(raw_value: Any, default: float = 0.0) -> float:
        if isinstance(raw_value, (int, float)):
            return max(0.0, min(1.0, float(raw_value)))
        return max(0.0, min(1.0, float(default)))

    @staticmethod
    def _normalize_verdict(raw_value: Any, default: str = "HOLD") -> str:
        verdict = str(raw_value or default).upper()
        if verdict in {"BUY", "HOLD", "SELL", "INSUFFICIENT_DATA"}:
            return verdict
        return default

    def _collect_agent_results(self, agent_outputs: dict[str, Any]) -> list[dict[str, Any]]:
        agent_results: list[dict[str, Any]] = []

        for agent_name in ("technical", "fundamental", "sentiment", "risk", "ml_prediction"):
            output = agent_outputs.get(agent_name)
            if output is None:
                continue

            if agent_name == "risk":
                risk_level = str(getattr(output, "risk_level", "MEDIUM")).upper()
                verdict = {"LOW": "BUY", "MEDIUM": "HOLD", "HIGH": "SELL"}.get(risk_level, "HOLD")
                confidence = self._normalize_confidence(getattr(output, "confidence", None), 0.7)
            elif agent_name == "ml_prediction":
                model_valid = bool(getattr(output, "model_valid", True))
                verdict = (
                    "INSUFFICIENT_DATA"
                    if not model_valid
                    else self._normalize_verdict(getattr(output, "verdict", getattr(output, "signal", "HOLD")))
                )
                confidence = self._normalize_confidence(getattr(output, "prediction_confidence", None), 0.0)
            else:
                verdict = self._normalize_verdict(getattr(output, "signal", "HOLD"))
                confidence = self._normalize_confidence(getattr(output, "confidence", None), 0.0)

            agent_results.append(
                {
                    "agent": agent_name,
                    "verdict": verdict,
                    "confidence": confidence,
                }
            )

        return agent_results

    @staticmethod
    def _compute_penalty(challenges: list[str], reason: str) -> float:
        if not challenges:
            return 0.0

        if reason.startswith("Conflicting signals detected"):
            penalty = 0.08
        elif reason.startswith("Low average confidence"):
            penalty = 0.06
        else:
            penalty = 0.05

        joined = " ".join(challenges).lower()
        if any(keyword in joined for keyword in _BONUS_KEYWORDS):
            penalty += 0.03

        return round(min(max(penalty, 0.0), 0.15), 2)

    async def _run_llm_critic(
        self,
        symbol: str,
        synthesis_result: SynthesisResult,
        agent_results: list[dict[str, Any]],
        reason: str,
    ) -> str:
        if not OPENROUTER_API_KEY:
            logger.warning("OPENROUTER_API_KEY not set - critic skipped for %s", symbol)
            return reason

        confidence_pct = round(float(synthesis_result.overall_confidence) * 100, 1)

        user_prompt = (
            f"You are a skeptical analyst. Agents disagree: {reason}.\n"
            f"The synthesis verdict is {synthesis_result.final_verdict} at {confidence_pct}% confidence.\n"
            "Identify the STRONGEST argument against this verdict in 2 sentences.\n"
            "Be specific - reference the conflicting agent data.\n\n"
            f"Agent results:\n{json.dumps(agent_results, ensure_ascii=True)}\n\n"
            "Return plain text only."
        )

        payload = {
            "model": CRITIC_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 280,
        }
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present.
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )
        return content.strip()

    async def run(
        self,
        symbol: str,
        synthesis_result: SynthesisResult,
        agent_outputs: dict[str, Any],
    ) -> CriticResult:
        """
        Challenge bullish synthesis outputs and return confidence penalty.

        If all valid agents agree with the final verdict, returns a no-op penalty.
        """
        agent_results = self._collect_agent_results(agent_outputs)
        should_run, reason = should_challenge(agent_results)
        if not should_run:
            return CriticResult(symbol=symbol, challenges=[], confidence_penalty=0.0)

        critique = "All agents in agreement with sufficient confidence."
        try:
            critique = await self._run_llm_critic(symbol, synthesis_result, agent_results, reason)
        except Exception as exc:
            logger.error("Critic LLM call failed for %s: %s", symbol, exc)

        critique = (critique or "").strip() or reason
        challenges = [critique]

        penalty = self._compute_penalty(challenges, reason)
        return CriticResult(
            symbol=symbol,
            challenges=challenges,
            confidence_penalty=penalty,
        )


_critic_agent = CriticAgent()


async def run(
    symbol: str,
    synthesis_result: SynthesisResult,
    agent_outputs: dict[str, Any],
) -> CriticResult:
    """Module-level entry point matching other agent modules."""
    return await _critic_agent.run(symbol, synthesis_result, agent_outputs)
