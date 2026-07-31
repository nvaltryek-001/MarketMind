"""
FinSight — ML Prediction Agent.
Engineers multi-factor features from OHLCV data and trains a
time-series-aware classifier for 5-day direction prediction.
"""

from __future__ import annotations

import asyncio
import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.models.schemas import (
    FeatureImportance,
    MLPrediction,
    ModelMetrics,
    OHLCVData,
)

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 100
MIN_WEIGHTED_F1 = 0.4


FEATURE_CATEGORIES: dict[str, list[str]] = {
    "momentum": [
        "return_1d",
        "return_3d",
        "return_5d",
        "return_10d",
        "return_20d",
        "rsi_14",
        "momentum_10",
        "rate_of_change_5",
    ],
    "volatility": [
        "volatility_5d",
        "volatility_10d",
        "volatility_20d",
        "atr_14",
        "bb_width",
        "high_low_range",
    ],
    "volume": [
        "volume_ratio_5d",
        "volume_ratio_20d",
        "obv_change_5d",
        "volume_momentum",
    ],
    "calendar": [
        "day_of_week",
        "month",
        "quarter",
        "is_month_end",
    ],
    "technical": [
        "sma_ratio_50",
        "sma_ratio_200",
        "price_vs_bb_upper",
        "macd_histogram",
        "adx_14",
    ],
}

REGIMES: tuple[str, str, str] = ("bull", "bear", "sideways")


def _zero_metrics(training_samples: int, test_samples: int) -> ModelMetrics:
    return ModelMetrics(
        accuracy=0.0,
        precision=0.0,
        recall=0.0,
        f1_score=0.0,
        confusion_matrix=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        class_labels=["DOWN", "SIDEWAYS", "UP"],
        training_samples=training_samples,
        test_samples=test_samples,
    )


def _suppressed_prediction(
    symbol: str,
    reason: str,
    trigger_message: str,
    metrics: ModelMetrics,
) -> MLPrediction:
    return MLPrediction(
        symbol=symbol,
        prediction_horizon="5-day direction",
        regime="sideways",
        predicted_direction="SIDEWAYS",
        prediction_confidence=0.5,
        feature_importances=[],
        model_metrics=metrics,
        model_name="Suppressed",
        feature_count=0,
        signal="HOLD",
        reasoning=reason,
        key_triggers=[trigger_message],
        verdict="INSUFFICIENT_DATA",
        model_valid=False,
        suppression_reason=reason,
        weight_override=0.0,
        score_override=5,
    )


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input df has columns: Open, High, Low, Close, Volume.
    Returns the dataframe with all engineered features appended.
    """
    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        missing = ", ".join(sorted(missing_cols))
        raise ValueError(f"Missing OHLCV columns: {missing}")

    out = df.copy()

    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"]

    # Momentum features
    out["return_1d"] = close.pct_change(1)
    out["return_3d"] = close.pct_change(3)
    out["return_5d"] = close.pct_change(5)
    out["return_10d"] = close.pct_change(10)
    out["return_20d"] = close.pct_change(20)

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    out["rsi_14"] = 100 - (100 / (1 + rs))

    out["momentum_10"] = close - close.shift(10)
    out["rate_of_change_5"] = (close - close.shift(5)) / close.shift(5) * 100

    # Volatility features
    returns = close.pct_change()
    out["volatility_5d"] = returns.rolling(5).std() * np.sqrt(252)
    out["volatility_10d"] = returns.rolling(10).std() * np.sqrt(252)
    out["volatility_20d"] = returns.rolling(20).std() * np.sqrt(252)

    high_low = high - low
    high_close = (high - close.shift(1)).abs()
    low_close = (low - close.shift(1)).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    out["atr_14"] = true_range.rolling(14).mean()

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    out["bb_width"] = (bb_upper - bb_lower) / sma20
    out["high_low_range"] = (high - low) / close

    # Volume features
    out["volume_ratio_5d"] = volume / volume.rolling(5).mean()
    out["volume_ratio_20d"] = volume / volume.rolling(20).mean()

    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    out["obv_change_5d"] = obv.pct_change(5)
    out["volume_momentum"] = volume.pct_change(5)

    # Calendar features
    if isinstance(out.index, pd.DatetimeIndex):
        calendar_index = out.index
    else:
        # Fallback when no datetime index is supplied.
        calendar_index = pd.to_datetime(
            out.reset_index(drop=True).index,
            unit="D",
            origin="2000-01-01",
        )

    out["day_of_week"] = calendar_index.dayofweek
    out["month"] = calendar_index.month
    out["quarter"] = calendar_index.quarter
    out["is_month_end"] = calendar_index.is_month_end.astype(int)

    # Technical features
    out["sma_ratio_50"] = close / close.rolling(50).mean()
    out["sma_ratio_200"] = close / close.rolling(200).mean()
    out["price_vs_bb_upper"] = (close - bb_upper) / bb_upper

    macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    macd_signal = macd_line.ewm(span=9).mean()
    out["macd_histogram"] = macd_line - macd_signal

    up_move = high.diff()
    down_move = -low.diff()

    dm_plus = up_move.clip(lower=0)
    dm_minus = down_move.clip(lower=0)

    dm_plus[dm_plus < down_move.clip(lower=0)] = 0
    dm_minus[dm_minus < up_move.clip(lower=0)] = 0

    di_plus = (dm_plus.rolling(14).mean() / out["atr_14"]) * 100
    di_minus = (dm_minus.rolling(14).mean() / out["atr_14"]) * 100

    dx = (di_plus - di_minus).abs() / (di_plus + di_minus) * 100
    out["adx_14"] = dx.rolling(14).mean()

    return out


def create_labels(closes: pd.Series, horizon: int = 5) -> pd.Series:
    """
    Create 3-class direction labels for a future return horizon.

    0: DOWN (< -2%), 1: SIDEWAYS ([-2%, +2%]), 2: UP (> +2%)
    """
    if horizon <= 0:
        raise ValueError("horizon must be > 0")

    future_return = (closes.shift(-horizon) - closes) / closes

    labels = pd.Series(1, index=closes.index, dtype="int64")
    labels[future_return > 0.02] = 2
    labels[future_return < -0.02] = 0

    return labels.iloc[:-horizon]


def _feature_columns() -> list[str]:
    columns: list[str] = []
    for feature_list in FEATURE_CATEGORIES.values():
        columns.extend(feature_list)
    return columns


def _feature_category(feature_name: str) -> str:
    for category, names in FEATURE_CATEGORIES.items():
        if feature_name in names:
            return category
    return "other"


def _regime_inputs(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if "Close" not in df.columns:
        raise ValueError("detect_regime requires a DataFrame with a 'Close' column")

    close = df["Close"].astype(float)
    returns = close.pct_change()

    # Rolling 20-day realized volatility (in decimal terms, e.g. 0.012 == 1.2%).
    rolling_volatility = returns.rolling(20).std()

    # 50-day SMA slope as daily percent change of the SMA value.
    sma_50 = close.rolling(50).mean()

    # When only a short window is supplied (e.g. last 30 days at inference),
    # use the longest available rolling window to preserve trend direction.
    if sma_50.notna().sum() < 2:
        adaptive_window = max(5, min(50, len(close)))
        sma_50 = close.rolling(adaptive_window, min_periods=2).mean()

    sma_slope_pct = sma_50.pct_change() * 100

    return rolling_volatility, sma_slope_pct


def detect_regime(df: pd.DataFrame) -> str:
    """
    Classify market regime based on volatility and SMA slope thresholds.

    - bull: vol < 1.2% and slope > 0
    - bear: vol > 2.0% or slope < -0.5%
    - sideways: otherwise
    """
    if df.empty:
        return "sideways"

    rolling_volatility, sma_slope_pct = _regime_inputs(df)

    latest_vol = float(rolling_volatility.iloc[-1]) if pd.notna(rolling_volatility.iloc[-1]) else 0.0
    latest_slope = float(sma_slope_pct.iloc[-1]) if pd.notna(sma_slope_pct.iloc[-1]) else 0.0

    if latest_vol < 0.012 and latest_slope > 0:
        return "bull"
    if latest_vol > 0.02 or latest_slope < -0.5:
        return "bear"
    return "sideways"


def _detect_regime_series(df: pd.DataFrame) -> pd.Series:
    rolling_volatility, sma_slope_pct = _regime_inputs(df)
    regimes = pd.Series("sideways", index=df.index, dtype="object")

    bull_mask = (rolling_volatility < 0.012) & (sma_slope_pct > 0)
    bear_mask = (rolling_volatility > 0.02) | (sma_slope_pct < -0.5)

    regimes[bull_mask] = "bull"
    regimes[bear_mask] = "bear"

    return regimes.fillna("sideways")


class RegimeAwareGradientBoosting:
    """Regime-aware ensemble of GradientBoosting classifiers."""

    def __init__(self) -> None:
        self.models: dict[str, Pipeline] = {}

    @staticmethod
    def _build_pipeline() -> Pipeline:
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    GradientBoostingClassifier(
                        n_estimators=100,
                        learning_rate=0.1,
                        max_depth=4,
                        subsample=0.8,
                        random_state=42,
                    ),
                ),
            ]
        )

    def _train_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        training_market_df: pd.DataFrame,
    ) -> None:
        """
        Train one model per regime.
        If a regime subset has < 60 samples, fall back to the full training set.
        """
        regime_by_date = (
            _detect_regime_series(training_market_df)
            .reindex(X_train.index)
            .fillna("sideways")
        )

        for regime in REGIMES:
            subset_idx = regime_by_date[regime_by_date == regime].index

            X_subset = X_train.loc[subset_idx]
            y_subset = y_train.loc[subset_idx]

            # Also fall back when the subset does not contain at least 2 classes.
            if len(X_subset) < 60 or y_subset.nunique() < 2:
                X_subset = X_train
                y_subset = y_train

            pipeline = self._build_pipeline()
            pipeline.fit(X_subset, y_subset)
            self.models[regime] = pipeline

    def predict(
        self,
        features: pd.DataFrame,
        recent_market_df: pd.DataFrame,
    ) -> tuple[int, np.ndarray, str]:
        if not self.models:
            raise ValueError("Model ensemble is not trained")

        regime = detect_regime(recent_market_df.tail(30))
        model = self.models.get(regime)

        if model is None:
            regime = "sideways"
            model = self.models.get("sideways") or next(iter(self.models.values()))

        predicted_class = int(model.predict(features)[0])
        probabilities = model.predict_proba(features)[0]
        return predicted_class, probabilities, regime

    def predict_batch(
        self,
        features: pd.DataFrame,
        market_df: pd.DataFrame,
    ) -> np.ndarray:
        predictions: list[int] = []

        for idx in features.index:
            recent_window = market_df.loc[:idx].tail(30)
            predicted_class, _, _ = self.predict(features.loc[[idx]], recent_window)
            predictions.append(predicted_class)

        return np.asarray(predictions, dtype=int)


async def run(symbol: str, ohlcv: OHLCVData) -> MLPrediction:
    """
    Run the ML prediction pipeline on OHLCV data.
    """
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

    feature_df = engineer_features(df)
    labels = create_labels(feature_df["Close"], horizon=5)

    feature_columns = _feature_columns()

    aligned_features = feature_df.iloc[:-5][feature_columns]
    dataset = aligned_features.join(labels.rename("target"), how="inner").dropna()

    X = dataset[feature_columns]
    y = dataset["target"].astype(int)

    total_samples = len(X)
    if total_samples < MIN_TRAINING_SAMPLES:
        message = (
            f"ML model requires 100+ samples. Current: {total_samples}. "
            "Prediction suppressed."
        )
        logger.warning("[ML] %s %s", symbol, message)
        return _suppressed_prediction(
            symbol=symbol,
            reason=message,
            trigger_message=message,
            metrics=_zero_metrics(training_samples=total_samples, test_samples=0),
        )

    if len(X) < 30:
        raise ValueError("Insufficient data for ML")

    tscv = TimeSeriesSplit(n_splits=5)
    train_idx, test_idx = list(tscv.split(X))[-1]

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    if y_train.nunique() < 2:
        raise ValueError("Insufficient class diversity for ML")

    ensemble = RegimeAwareGradientBoosting()
    loop = asyncio.get_running_loop()

    train_market_df = feature_df.loc[X_train.index, ["Close"]]
    full_market_df = feature_df.loc[X.index, ["Close"]]

    await loop.run_in_executor(
        None,
        lambda: ensemble._train_model(X_train, y_train, train_market_df),
    )

    y_pred = await loop.run_in_executor(
        None,
        lambda: ensemble.predict_batch(X_test, full_market_df),
    )

    metrics = ModelMetrics(
        accuracy=float(accuracy_score(y_test, y_pred)),
        precision=float(
            precision_score(y_test, y_pred, average="weighted", zero_division=0)
        ),
        recall=float(recall_score(y_test, y_pred, average="weighted", zero_division=0)),
        f1_score=float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
        confusion_matrix=confusion_matrix(y_test, y_pred, labels=[0, 1, 2]).tolist(),
        class_labels=["DOWN", "SIDEWAYS", "UP"],
        training_samples=len(X_train),
        test_samples=len(X_test),
    )

    weighted_f1 = metrics.f1_score
    if weighted_f1 < MIN_WEIGHTED_F1:
        warning = (
            f"Model below F1 threshold ({MIN_WEIGHTED_F1}). "
            "Predictions will be suppressed."
        )
        logger.warning("[ML] %s %s", symbol, warning)
        return _suppressed_prediction(
            symbol=symbol,
            reason=warning,
            trigger_message=warning,
            metrics=metrics,
        )

    latest_features = X.iloc[[-1]]

    latest_window = full_market_df.loc[: latest_features.index[-1]].tail(30)
    predicted_class, probabilities, active_regime = await loop.run_in_executor(
        None,
        lambda: ensemble.predict(latest_features, latest_window),
    )

    confidence = float(np.max(probabilities))
    direction = ["DOWN", "SIDEWAYS", "UP"][predicted_class]

    selected_model = ensemble.models.get(active_regime)
    if selected_model is None:
        selected_model = ensemble.models.get("sideways") or next(iter(ensemble.models.values()))

    importances = selected_model.named_steps["model"].feature_importances_
    feat_imp_df = (
        pd.DataFrame(
            {
                "feature": X.columns,
                "importance": importances,
            }
        )
        .sort_values("importance", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )

    total_importance = float(feat_imp_df["importance"].sum())
    if total_importance > 0:
        feat_imp_df["normalized_importance"] = feat_imp_df["importance"] / total_importance
    else:
        feat_imp_df["normalized_importance"] = 1.0 / max(len(feat_imp_df), 1)

    feature_importances = [
        FeatureImportance(
            feature_name=str(row["feature"]),
            importance=float(row["normalized_importance"]),
            category=_feature_category(str(row["feature"])),
        )
        for _, row in feat_imp_df.iterrows()
    ]

    if direction == "UP":
        signal = "BUY"
    elif direction == "DOWN":
        signal = "SELL"
    else:
        signal = "HOLD"

    top_feature = str(feat_imp_df.iloc[0]["feature"]) if not feat_imp_df.empty else "N/A"
    reasoning = (
        f"The regime-aware GradientBoosting ensemble selected the '{active_regime}' model and predicts "
        f"a {direction} move in the next 5 trading days with {confidence:.0%} confidence. "
        f"Across {len(X_train)} training samples and {len(X.columns)} engineered features, it achieved "
        f"{metrics.f1_score:.0%} weighted F1 on the held-out test set, with "
        f"{top_feature} being the most predictive feature."
    )

    key_triggers = [
        f"Model predicts {direction} over 5 trading days",
        f"Prediction confidence at {confidence:.0%}",
        f"Active regime classified as {active_regime}",
    ]
    if top_feature != "N/A":
        key_triggers.append(f"Top feature driver: {top_feature}")

    return MLPrediction(
        symbol=symbol,
        prediction_horizon="5-day direction",
        regime=active_regime,
        predicted_direction=direction,
        prediction_confidence=confidence,
        feature_importances=feature_importances,
        model_metrics=metrics,
        model_name="Regime-Aware GradientBoosting Ensemble",
        feature_count=len(feature_columns),
        signal=signal,
        reasoning=reasoning,
        key_triggers=key_triggers,
        verdict=signal,
        model_valid=True,
    )