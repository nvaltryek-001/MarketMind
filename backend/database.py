"""
FinSight — SQLAlchemy + SQLite persistence layer.
All CRUD functions are fully implemented.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.models.schemas import AgentStatus, RunStatus, SynthesisResult

# ──────────────────────────────────────────────────────────────────────
# Engine / Session setup
# ──────────────────────────────────────────────────────────────────────
_DB_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_DB_DIR, "finsight.db")
DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────────────────────────────
# ORM Models
# ──────────────────────────────────────────────────────────────────────
class AnalysisRunRow(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    symbols_json: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AgentOutputRow(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    signal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SynthesisResultRow(Base):
    __tablename__ = "synthesis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    price_target_pct: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detailed_report: Mapped[str] = mapped_column(Text, nullable=False)
    agent_weights_json: Mapped[str] = mapped_column(Text, nullable=False)
    conflict_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_session() -> Session:
    return SessionLocal()


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine, checkfirst=True)


def save_run(run_id: str, symbols: list[str]) -> None:
    """Insert a new analysis run."""
    with _get_session() as session:
        row = AnalysisRunRow(
            id=run_id,
            symbols_json=json.dumps(symbols),
            status="running",
            started_at=_utcnow(),
        )
        session.add(row)
        session.commit()


def update_run_status(
    run_id: str,
    status: str,
    completed_at: Optional[datetime] = None,
) -> None:
    """Update the status (and optionally completed_at) of a run."""
    with _get_session() as session:
        row = session.scalar(select(AnalysisRunRow).where(AnalysisRunRow.id == run_id))
        if row is None:
            return
        row.status = status
        if completed_at is not None:
            row.completed_at = completed_at
        elif status in ("completed", "failed"):
            row.completed_at = _utcnow()
        session.commit()


def save_agent_output(
    run_id: str,
    symbol: str,
    agent_name: str,
    status: str,
    signal: Optional[str],
    confidence: Optional[float],
    reasoning: Optional[str],
    data_dict: Optional[dict[str, Any]],
) -> None:
    """Upsert an agent's output for a given run + symbol + agent_name."""
    with _get_session() as session:
        existing = session.scalar(
            select(AgentOutputRow).where(
                AgentOutputRow.run_id == run_id,
                AgentOutputRow.symbol == symbol,
                AgentOutputRow.agent_name == agent_name,
            )
        )

        if existing is not None:
            existing.status = status
            existing.signal = signal
            existing.confidence = confidence
            existing.reasoning = reasoning
            existing.data_json = json.dumps(data_dict) if data_dict else None
            if status in ("completed", "failed"):
                existing.completed_at = _utcnow()
        else:
            row = AgentOutputRow(
                run_id=run_id,
                symbol=symbol,
                agent_name=agent_name,
                status=status,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                data_json=json.dumps(data_dict) if data_dict else None,
                completed_at=_utcnow() if status in ("completed", "failed") else None,
            )
            session.add(row)

        session.commit()


def save_synthesis_result(run_id: str, result: SynthesisResult) -> None:
    """Persist a SynthesisResult for a given run."""
    with _get_session() as session:
        row = SynthesisResultRow(
            run_id=run_id,
            symbol=result.symbol,
            verdict=result.final_verdict,
            confidence=result.overall_confidence,
            price_target_pct=result.price_target_pct,
            summary=result.summary,
            detailed_report=result.detailed_report,
            agent_weights_json=json.dumps(result.agent_weights),
            conflict_notes=result.conflict_notes,
            generated_at=result.generated_at,
        )
        session.add(row)
        session.commit()


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    """
    Return the full run including all agent outputs and synthesis results,
    assembled into the shape expected by RunStatus.
    Returns None if the run does not exist.
    """
    with _get_session() as session:
        run_row = session.scalar(select(AnalysisRunRow).where(AnalysisRunRow.id == run_id))
        if run_row is None:
            return None

        symbols: list[str] = json.loads(run_row.symbols_json)

        # ── Agent outputs ───────────────────────────────────────────
        agent_rows = session.scalars(
            select(AgentOutputRow).where(AgentOutputRow.run_id == run_id)
        ).all()
        agents: dict[str, AgentStatus] = {}
        synthesis_macro_warnings: dict[str, Optional[str]] = {}
        synthesis_logic_maps: dict[str, list[dict[str, Any]]] = {}
        synthesis_card_payloads: dict[str, dict[str, Any]] = {}
        synthesis_weighted_scores: dict[str, float] = {}
        for a in agent_rows:
            key = f"{a.agent_name}_{a.symbol}"
            parsed_data = json.loads(a.data_json) if a.data_json else None

            if a.agent_name == "synthesis" and isinstance(parsed_data, dict):
                macro_warning = parsed_data.get("macro_warning")
                if isinstance(macro_warning, str) and macro_warning.strip():
                    synthesis_macro_warnings[a.symbol] = macro_warning.strip()
                elif macro_warning is None:
                    synthesis_macro_warnings[a.symbol] = None

                weighted_score = parsed_data.get("weighted_score")
                if isinstance(weighted_score, (int, float)):
                    synthesis_weighted_scores[a.symbol] = float(weighted_score)

                logic_map = parsed_data.get("logic_map")
                if isinstance(logic_map, list):
                    synthesis_logic_maps[a.symbol] = [
                        row for row in logic_map if isinstance(row, dict)
                    ]

                card_data = parsed_data.get("card_data")
                if isinstance(card_data, dict):
                    synthesis_card_payloads[a.symbol] = card_data

            agents[key] = AgentStatus(
                agent_name=a.agent_name,
                status=a.status,
                signal=a.signal,
                confidence=a.confidence,
                reasoning=a.reasoning,
                data=parsed_data,
                completed_at=a.completed_at,
            )

        # ── Synthesis results ───────────────────────────────────────
        synth_rows = session.scalars(
            select(SynthesisResultRow).where(SynthesisResultRow.run_id == run_id)
        ).all()
        results: dict[str, SynthesisResult] = {}
        for s in synth_rows:
            results[s.symbol] = SynthesisResult(
                symbol=s.symbol,
                final_verdict=s.verdict,
                overall_confidence=s.confidence,
                weighted_score=synthesis_weighted_scores.get(s.symbol, 0.0),
                price_target_pct=s.price_target_pct,
                summary=s.summary,
                detailed_report=s.detailed_report,
                agent_weights=json.loads(s.agent_weights_json),
                logic_map=synthesis_logic_maps.get(s.symbol, []),
                card_data=synthesis_card_payloads.get(s.symbol, {}),
                conflict_notes=s.conflict_notes,
                macro_warning=synthesis_macro_warnings.get(s.symbol),
                generated_at=s.generated_at,
            )

        return {
            "run_id": run_row.id,
            "symbols": symbols,
            "status": run_row.status,
            "agents": agents,
            "results": results,
            "started_at": run_row.started_at,
            "completed_at": run_row.completed_at,
        }


def get_recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    """Return the *limit* most recent runs (lightweight, no agent details)."""
    with _get_session() as session:
        rows = session.scalars(
            select(AnalysisRunRow)
            .order_by(AnalysisRunRow.started_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "run_id": r.id,
                "symbols": json.loads(r.symbols_json),
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]
