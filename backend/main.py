"""
FinSight — FastAPI application entry-point.
Provides REST + SSE endpoints for the multi-agent stock intelligence system.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.routes.stock import router as stock_router
from api.services.market_data import NSEMarketDataService
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from backend.database import (
    AgentOutputRow,
    SessionLocal,
    get_recent_runs,
    get_run,
    init_db,
    save_agent_output,
    save_run,
    update_run_status,
)
from backend.models.schemas import (
    AnalysisRequest,
    MLPrediction,
    MultiStockEDA,
    RunStatus,
)

if TYPE_CHECKING:
    from backend.orchestrator import run_analysis  # noqa: F401


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook."""
    init_db()
    app.state.market_data_service = NSEMarketDataService()
    try:
        yield
    finally:
        await app.state.market_data_service.close()


# ──────────────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FinSight — Indian Stock Intelligence",
    description="Autonomous multi-agent system for Indian equity analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stock_router)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _build_run_status(run_data: dict) -> RunStatus:
    """Convert the dict returned by database.get_run() into a RunStatus."""
    return RunStatus(
        run_id=run_data["run_id"],
        symbols=run_data["symbols"],
        status=run_data["status"],
        agents=run_data.get("agents", {}),
        results=run_data.get("results", {}),
        started_at=run_data["started_at"],
        completed_at=run_data.get("completed_at"),
    )


def _trigger_orchestrator(run_id: str, symbols: list[str]) -> None:
    """
    Import orchestrator at call-time to avoid circular import issues,
    then kick off analysis synchronously (called inside a BackgroundTask).
    """
    try:
        from backend.orchestrator import run_analysis  # lazy import

        run_analysis(run_id=run_id, symbols=symbols)
    except Exception as exc:
        logger.exception("Orchestrator task crashed for run %s", run_id)
        try:
            save_agent_output(
                run_id=run_id,
                symbol="ALL",
                agent_name="orchestrator",
                status="failed",
                signal=None,
                confidence=None,
                reasoning=f"Orchestrator bootstrap failed: {type(exc).__name__}: {exc}",
                data_dict=None,
            )
        except Exception:
            logger.exception("Failed to persist orchestrator failure for run %s", run_id)
        update_run_status(run_id, "failed")


def _get_agent_output_row(
    run_id: str,
    agent_name: str,
    symbol: str | None = None,
) -> AgentOutputRow | None:
    """Fetch latest agent_output row for run + agent (+ optional symbol)."""
    with SessionLocal() as session:
        stmt = select(AgentOutputRow).where(
            AgentOutputRow.run_id == run_id,
            AgentOutputRow.agent_name == agent_name,
        )
        if symbol is not None:
            stmt = stmt.where(AgentOutputRow.symbol == symbol)
        stmt = stmt.order_by(AgentOutputRow.id.desc())
        return session.scalar(stmt)


# ──────────────────────────────────────────────────────────────────────
# POST /analyze
# ──────────────────────────────────────────────────────────────────────
@app.post("/analyze")
async def analyze(request: AnalysisRequest, bg: BackgroundTasks) -> JSONResponse:
    """Accept an analysis request, persist it, and start the pipeline."""
    save_run(request.run_id, request.symbols)
    bg.add_task(_trigger_orchestrator, run_id=request.run_id, symbols=list(request.symbols))
    return JSONResponse(
        status_code=202,
        content={
            "run_id": request.run_id,
            "status": "started",
            "message": (
                f"Analysis started for {', '.join(request.symbols)}. "
                f"Track progress at /status/{request.run_id}"
            ),
        },
    )


# ──────────────────────────────────────────────────────────────────────
# GET /status/{run_id}
# ──────────────────────────────────────────────────────────────────────
@app.get("/status/{run_id}")
async def status(run_id: str) -> RunStatus:
    """Return the full RunStatus for a given run."""
    run_data = get_run(run_id)
    if run_data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return _build_run_status(run_data)


# ──────────────────────────────────────────────────────────────────────
# GET /stream/{run_id}  (SSE)
# ──────────────────────────────────────────────────────────────────────
@app.get("/stream/{run_id}")
async def stream(run_id: str) -> EventSourceResponse:
    """
    Server-Sent Events stream that polls the DB every 1.5 s and pushes
    agent-status updates as JSON.  Closes when the run completes or fails.
    """
    # Validate the run exists before opening the stream
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    async def event_generator() -> AsyncGenerator[dict, None]:
        previous_snapshot: str = ""
        while True:
            run_data = get_run(run_id)
            if run_data is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "run_not_found"}),
                }
                break

            run_status = _build_run_status(run_data)
            current_snapshot = run_status.model_dump_json()

            # Only push when something changed
            if current_snapshot != previous_snapshot:
                yield {
                    "event": "status",
                    "data": current_snapshot,
                }
                previous_snapshot = current_snapshot

            if run_status.status in ("completed", "failed"):
                yield {
                    "event": "done",
                    "data": json.dumps({"status": run_status.status}),
                }
                break

            await asyncio.sleep(1.5)

    return EventSourceResponse(event_generator())


# ──────────────────────────────────────────────────────────────────────
# GET /runs
# ──────────────────────────────────────────────────────────────────────
@app.get("/runs")
async def runs() -> list[dict]:
    """Return the last 10 runs with their status and symbols."""
    return get_recent_runs(limit=10)


# ──────────────────────────────────────────────────────────────────────
# GET /report/{run_id}/{symbol}
# ──────────────────────────────────────────────────────────────────────
@app.get("/report/{run_id}/{symbol}")
async def report(run_id: str, symbol: str) -> JSONResponse:
    """Return the full detailed_report text for a specific symbol."""
    run_data = get_run(run_id)
    if run_data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    symbol_upper = symbol.strip().upper()
    results: dict = run_data.get("results", {})

    if symbol_upper not in results:
        raise HTTPException(
            status_code=404,
            detail=f"No synthesis result for symbol '{symbol_upper}' in run '{run_id}'",
        )

    synthesis = results[symbol_upper]
    return JSONResponse(
        content={
            "run_id": run_id,
            "symbol": symbol_upper,
            "verdict": synthesis.final_verdict,
            "confidence": synthesis.overall_confidence,
            "summary": synthesis.summary,
            "detailed_report": synthesis.detailed_report,
            "logic_map": synthesis.logic_map,
            "generated_at": synthesis.generated_at.isoformat(),
        }
    )


# ──────────────────────────────────────────────────────────────────────
# GET /eda/{run_id}
# ──────────────────────────────────────────────────────────────────────
@app.get("/eda/{run_id}")
async def get_eda(run_id: str) -> MultiStockEDA:
    """Return run-level MultiStockEDA for a completed run."""
    run_data = get_run(run_id)
    if run_data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if run_data["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is not completed yet")

    row = _get_agent_output_row(run_id=run_id, agent_name="eda")
    if row is None or row.data_json is None:
        raise HTTPException(
            status_code=404,
            detail=f"No EDA output found for run '{run_id}'",
        )
    if row.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"EDA output for run '{run_id}' is not completed",
        )

    try:
        return MultiStockEDA.model_validate(json.loads(row.data_json))
    except Exception as exc:
        logger.exception("Failed to parse EDA output for run %s: %s", run_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Stored EDA result is invalid",
        ) from exc


# ──────────────────────────────────────────────────────────────────────
# GET /ml/{run_id}/{symbol}
# ──────────────────────────────────────────────────────────────────────
@app.get("/ml/{run_id}/{symbol}")
async def get_ml_prediction(run_id: str, symbol: str) -> MLPrediction:
    """Return ML prediction output for a specific symbol in a completed run."""
    run_data = get_run(run_id)
    if run_data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if run_data["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is not completed yet")

    symbol_upper = symbol.strip().upper()
    row = _get_agent_output_row(
        run_id=run_id,
        agent_name="ml_prediction",
        symbol=symbol_upper,
    )
    if row is None or row.data_json is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No ML prediction found for symbol '{symbol_upper}' "
                f"in run '{run_id}'"
            ),
        )
    if row.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"ML prediction for symbol '{symbol_upper}' "
                f"in run '{run_id}' is not completed"
            ),
        )

    try:
        return MLPrediction.model_validate(json.loads(row.data_json))
    except Exception as exc:
        logger.exception(
            "Failed to parse ML output for run %s symbol %s: %s",
            run_id,
            symbol_upper,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Stored ML prediction is invalid",
        ) from exc


# ──────────────────────────────────────────────────────────────────────
# GET /health
# ──────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict:
    """Simple liveness probe."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
