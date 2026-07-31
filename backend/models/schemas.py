"""
FinSight — Pydantic v2 schemas for the multi-agent stock intelligence system.
All models are fully implemented with validators and sensible defaults.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────────────
# 1. AnalysisRequest
# ──────────────────────────────────────────────────────────────────────
class AnalysisRequest(BaseModel):
    """Incoming request to analyse up to 5 Indian stock symbols."""

    symbols: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="List of NSE/BSE symbols to analyse (max 5)",
    )
    run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique run identifier (auto-generated UUID4)",
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def normalise_symbols(cls, v: list[str]) -> list[str]:
        """Upper-case and strip whitespace from every symbol."""
        return [s.strip().upper() for s in v]


# ──────────────────────────────────────────────────────────────────────
# 2. AgentStatus
# ──────────────────────────────────────────────────────────────────────
class AgentStatus(BaseModel):
    """Real-time status of a single agent during a run."""

    agent_name: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    signal: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    data: Optional[dict] = None
    completed_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# 3. OHLCVData
# ──────────────────────────────────────────────────────────────────────
class OHLCVData(BaseModel):
    """OHLCV price data for a given symbol."""

    symbol: str
    dates: list[str]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    current_price: float
    change_pct: float

    @model_validator(mode="after")
    def check_list_lengths(self) -> "OHLCVData":
        """Ensure all price/volume lists have the same length as dates."""
        expected = len(self.dates)
        for field_name in ("opens", "highs", "lows", "closes", "volumes"):
            actual = len(getattr(self, field_name))
            if actual != expected:
                raise ValueError(
                    f"Length of '{field_name}' ({actual}) does not match "
                    f"length of 'dates' ({expected})"
                )
        return self


# ──────────────────────────────────────────────────────────────────────
# 4. TechnicalSignals
# ──────────────────────────────────────────────────────────────────────
class TechnicalSignals(BaseModel):
    """Output of the Technical Analysis agent."""

    symbol: str
    rsi: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    bb_middle: float
    sma_50: float
    sma_200: float
    trend: Literal["bullish", "bearish", "sideways"]
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_triggers: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# 5. FundamentalData
# ──────────────────────────────────────────────────────────────────────
class FundamentalData(BaseModel):
    """Output of the Fundamental Analysis agent."""

    symbol: str
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    eps: Optional[float] = None
    revenue_growth: Optional[float] = None
    roe: Optional[float] = None
    sector: str
    sector_pe_avg: float
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_triggers: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# 6. SentimentData
# ──────────────────────────────────────────────────────────────────────
class SentimentData(BaseModel):
    """Output of the News Sentiment agent."""

    symbol: str
    headlines: list[str] = Field(default_factory=list)
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    sentiment_label: Literal["positive", "negative", "neutral"]
    key_themes: list[str] = Field(default_factory=list)
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_triggers: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# 7. RiskMetrics
# ──────────────────────────────────────────────────────────────────────
class RiskMetrics(BaseModel):
    """Output of the Risk Assessment agent."""

    symbol: str
    beta: float
    var_95: float = Field(description="Value-at-Risk at 95% confidence")
    sharpe_ratio: float
    max_drawdown: float
    volatility_annualized: float
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    reasoning: str
    key_triggers: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# 8. Macro Result
# ──────────────────────────────────────────────────────────────────────
class MacroResult(BaseModel):
    """Output of the Macro Flow agent using exchange/derived flow signals."""

    fii_net_5d: float
    dii_net_5d: float
    macro_signal: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence_multiplier: float = Field(ge=0.5, le=1.5)
    reasoning: str
    source: Literal["BSE", "derived_from_index"] = "BSE"
    date: Optional[str] = None
    fii_net: Optional[float] = None
    dii_net: Optional[float] = None
    fii_5d_trend: Optional[Literal["buying", "selling", "mixed", "unknown"]] = None
    dii_5d_trend: Optional[Literal["buying", "selling", "mixed", "unknown"]] = None
    nifty_5d_return: Optional[float] = None


# ──────────────────────────────────────────────────────────────────────
# 9. ML Prediction
# ──────────────────────────────────────────────────────────────────────
class FeatureImportance(BaseModel):
    """Relative importance of an engineered ML feature."""

    feature_name: str
    importance: float = Field(ge=0.0, le=1.0)
    category: str  # "momentum", "volatility", "volume", "calendar", "technical"


class ModelMetrics(BaseModel):
    """Evaluation metrics for the 3-class direction classifier."""

    accuracy: float
    precision: float
    recall: float
    f1_score: float
    confusion_matrix: list[list[int]]  # 3x3 for DOWN/SIDEWAYS/UP
    class_labels: list[str]  # ["DOWN", "SIDEWAYS", "UP"]
    training_samples: int
    test_samples: int


class MLPrediction(BaseModel):
    """Output of the ML Prediction agent."""

    symbol: str
    prediction_horizon: str  # "5-day direction"
    regime: str = Field(default="sideways")  # "bull", "bear", "sideways"
    predicted_direction: str  # "UP", "DOWN", "SIDEWAYS"
    prediction_confidence: float = Field(ge=0.0, le=1.0)
    feature_importances: list[FeatureImportance]  # top 10
    model_metrics: ModelMetrics
    model_name: str  # "Regime-Aware GradientBoosting Ensemble"
    feature_count: int  # total features engineered
    signal: str  # "BUY" if UP, "SELL" if DOWN, "HOLD" if SIDEWAYS
    reasoning: str  # 2-sentence explanation
    key_triggers: list[str] = Field(default_factory=list)
    verdict: str = Field(default="HOLD")
    model_valid: bool = Field(default=True)
    suppression_reason: Optional[str] = None
    weight_override: Optional[float] = None
    score_override: Optional[int] = None


# ──────────────────────────────────────────────────────────────────────
# 10. SynthesisResult
# ──────────────────────────────────────────────────────────────────────
class SynthesisResult(BaseModel):
    """Final synthesised verdict produced by the Meta-Synthesis agent."""

    symbol: str
    final_verdict: Literal["BUY", "SELL", "HOLD"]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    weighted_score: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Raw weighted score before verdict bucketing",
    )
    price_target_pct: float
    summary: str
    detailed_report: str
    agent_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Weight given to each agent in the final synthesis",
    )
    logic_map: list[dict] = Field(
        default_factory=list,
        description=(
            "Per-agent decision breakdown including signal, applied weight, "
            "and key trigger strings"
        ),
    )
    card_data: dict[str, dict] = Field(
        default_factory=dict,
        description="Frontend-ready per-agent card payload with verdict/score/triggers/weight",
    )
    conflict_notes: Optional[str] = None
    macro_warning: Optional[str] = None
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ──────────────────────────────────────────────────────────────────────
# 11. CriticResult
# ──────────────────────────────────────────────────────────────────────
class CriticResult(BaseModel):
    """Output of the Critic agent that challenges bullish synthesis."""

    symbol: str
    challenges: list[str] = Field(default_factory=list)
    confidence_penalty: float = Field(ge=0.0, le=0.15)


# ──────────────────────────────────────────────────────────────────────
# 12. RunStatus
# ──────────────────────────────────────────────────────────────────────
class RunStatus(BaseModel):
    """Top-level status object for a complete analysis run."""

    run_id: str
    symbols: list[str]
    status: Literal["running", "completed", "failed"]
    agents: dict[str, AgentStatus] = Field(default_factory=dict)
    results: dict[str, SynthesisResult] = Field(default_factory=dict)
    started_at: datetime
    completed_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────────
# 13. EDA — Exploratory Data Analysis
# ──────────────────────────────────────────────────────────────────────
class DistributionStats(BaseModel):
    """Statistical summary of a numeric distribution."""

    mean: float
    median: float
    std: float
    skewness: float
    kurtosis: float
    min: float
    max: float
    is_normal: bool  # True if Shapiro-Wilk p-value > 0.05
    percentile_25: float
    percentile_75: float


class CorrelationPair(BaseModel):
    """Pairwise correlation between two symbols' daily returns."""

    symbol_a: str
    symbol_b: str
    correlation: float
    relationship: str  # "strong positive", "moderate positive",
    #                    "weak", "moderate negative", "strong negative"


class OutlierInfo(BaseModel):
    """A single detected outlier event in price or volume data."""

    date: str
    value: float
    z_score: float
    event_type: str  # "volume spike", "price gap up", "price gap down",
    #                  "volatility spike"


class VolatilityRegime(BaseModel):
    """Current volatility regime classification."""

    regime: str  # "low", "medium", "high", "extreme"
    current_percentile: float  # where current vol sits in historical dist
    avg_daily_move_pct: float
    regime_started_approx: str  # date string


class EDAResult(BaseModel):
    """Full exploratory data analysis result for a single stock."""

    symbol: str
    returns_distribution: DistributionStats
    volume_distribution: DistributionStats
    outliers: list[OutlierInfo]  # top 5 most significant
    volatility_regime: VolatilityRegime
    # For charts — raw data arrays for frontend rendering
    returns_histogram: dict  # {"bins": list[float], "counts": list[int]}
    rolling_volatility_30d: dict  # {"dates": list[str], "values": list[float]}
    volume_ma_ratio: dict  # {"dates": list[str], "values": list[float]}
    #                        ratio of daily volume to 20d avg volume
    price_vs_sma: dict  # {"dates": list[str], "price": list[float],
    #                      "sma50": list[float], "sma200": list[float]}
    key_insights: list[str]  # 4 human-readable bullet points


class MultiStockEDA(BaseModel):
    """Aggregated EDA results across multiple stocks."""

    run_id: str
    symbols: list[str]
    individual_eda: dict[str, EDAResult]
    correlation_matrix: list[CorrelationPair]  # all pairs
    correlation_grid: dict  # {"symbols": list[str], "matrix": list[list[float]]}
    #                         for heatmap rendering
    portfolio_summary: str  # 3-sentence LLM-generated portfolio EDA summary
