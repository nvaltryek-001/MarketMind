"""
Promoter Velocity Engine.

Tracks the rate of promoter holding change (velocity + acceleration)
and converts it into a stock-level statistical signal.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


class PromoterVelocityEngine:
    """Statistical engine for promoter-holding momentum analysis."""

    def __init__(
        self,
        shareholding_history: dict[str, Any] | None = None,
        price_history: dict[str, Any] | None = None,
    ) -> None:
        self._shareholding_history: dict[str, Any] = {}
        self._price_history: dict[str, Any] = {}
        self._velocity_cache: dict[str, dict[str, Any]] = {}

        if shareholding_history:
            for symbol, data in shareholding_history.items():
                self.update_shareholding(symbol, data)

        if price_history:
            for symbol, data in price_history.items():
                self.update_price_history(symbol, data)

    def update_shareholding(self, symbol: str, shareholding_data: Any) -> None:
        """Register or replace shareholding history for a symbol."""
        clean_symbol = self._clean_symbol(symbol)
        self._shareholding_history[clean_symbol] = shareholding_data
        self._velocity_cache.pop(clean_symbol, None)

    def update_price_history(self, symbol: str, price_data: Any) -> None:
        """Register or replace price history for a symbol."""
        clean_symbol = self._clean_symbol(symbol)
        self._price_history[clean_symbol] = price_data

    def calculate_velocity(self, shareholding_data: Any) -> dict[str, Any]:
        """
        Compute promoter-holding velocity metrics.

        Returns quarter-on-quarter velocity, rolling 4-quarter average velocity,
        acceleration (change in velocity), and trend reversal points.
        """
        frame = self._normalize_shareholding_data(shareholding_data)
        if frame.empty:
            return self._empty_velocity_payload()

        frame["velocity"] = frame["promoter_holding_percent"].diff()
        frame["velocity_4q_avg"] = frame["velocity"].rolling(window=4, min_periods=1).mean()
        frame["acceleration"] = frame["velocity"].diff()

        sign_series = np.sign(frame["velocity"].replace(0.0, np.nan)).ffill()
        reversal_mask = (
            sign_series.ne(sign_series.shift(1))
            & sign_series.notna()
            & sign_series.shift(1).notna()
        )

        trend_reversal_points: list[dict[str, Any]] = []
        for index in frame.index[reversal_mask]:
            direction = "downtrend_to_uptrend" if sign_series.loc[index] > 0 else "uptrend_to_downtrend"
            trend_reversal_points.append(
                {
                    "quarter": str(frame.at[index, "quarter"]),
                    "quarter_date": self._fmt_date(frame.at[index, "quarter_date"]),
                    "velocity": self._to_optional_float(frame.at[index, "velocity"]),
                    "type": direction,
                }
            )

        series: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            series.append(
                {
                    "quarter": str(row["quarter"]),
                    "quarter_date": self._fmt_date(row["quarter_date"]),
                    "promoter_holding_percent": self._to_optional_float(row["promoter_holding_percent"]),
                    "velocity": self._to_optional_float(row["velocity"]),
                    "velocity_4q_avg": self._to_optional_float(row["velocity_4q_avg"]),
                    "acceleration": self._to_optional_float(row["acceleration"]),
                }
            )

        return {
            "latest_velocity": self._last_valid(frame["velocity"]),
            "latest_acceleration": self._last_valid(frame["acceleration"]),
            "latest_rolling_4q_avg": self._last_valid(frame["velocity_4q_avg"]),
            "trend_reversal_points": trend_reversal_points,
            "series": series,
        }

    def flag_anomaly(self, symbol: str) -> dict[str, Any]:
        """
        Flag acceleration anomalies using symbol-specific historical behavior.

        A symbol is flagged when the latest acceleration is beyond 1.5 standard
        deviations from its own historical acceleration baseline.
        """
        clean_symbol = self._clean_symbol(symbol)
        velocity_payload = self._get_velocity_payload(clean_symbol)
        series_frame = pd.DataFrame(velocity_payload.get("series", []))

        if series_frame.empty or "acceleration" not in series_frame.columns:
            return {
                "symbol": clean_symbol,
                "anomaly_flag": False,
                "z_score": None,
                "latest_acceleration": None,
                "baseline_mean": None,
                "baseline_std": None,
                "direction": "flat",
            }

        acceleration = pd.to_numeric(series_frame["acceleration"], errors="coerce").dropna()
        if acceleration.empty:
            return {
                "symbol": clean_symbol,
                "anomaly_flag": False,
                "z_score": None,
                "latest_acceleration": None,
                "baseline_mean": None,
                "baseline_std": None,
                "direction": "flat",
            }

        latest_acceleration = float(acceleration.iloc[-1])
        baseline = acceleration.iloc[:-1] if len(acceleration) >= 3 else acceleration

        baseline_mean = float(baseline.mean()) if not baseline.empty else 0.0
        baseline_std = float(baseline.std(ddof=0)) if len(baseline) > 1 else 0.0

        if baseline_std == 0.0:
            z_score = 0.0
            anomaly_flag = False
        else:
            z_score = (latest_acceleration - baseline_mean) / baseline_std
            anomaly_flag = abs(z_score) > 1.5

        direction = self._acceleration_direction(latest_acceleration)
        return {
            "symbol": clean_symbol,
            "anomaly_flag": anomaly_flag,
            "z_score": self._to_optional_float(z_score),
            "latest_acceleration": self._to_optional_float(latest_acceleration),
            "baseline_mean": self._to_optional_float(baseline_mean),
            "baseline_std": self._to_optional_float(baseline_std),
            "direction": direction,
        }

    def correlate_with_price(self, symbol: str) -> float:
        """
        Correlate promoter velocity with subsequent 30-day price change.

        Returns Pearson correlation coefficient in [-1, 1], or NaN if data is
        insufficient for stable estimation.
        """
        clean_symbol = self._clean_symbol(symbol)
        velocity_payload = self._get_velocity_payload(clean_symbol)
        series_frame = pd.DataFrame(velocity_payload.get("series", []))
        price_frame = self._normalize_price_data(self._price_history.get(clean_symbol))

        if series_frame.empty or price_frame.empty:
            return float("nan")

        series_frame["quarter_date"] = pd.to_datetime(series_frame["quarter_date"], errors="coerce")
        series_frame["velocity"] = pd.to_numeric(series_frame["velocity"], errors="coerce")

        aligned = series_frame.dropna(subset=["quarter_date", "velocity"])
        if aligned.empty:
            return float("nan")

        velocities: list[float] = []
        future_returns_30d: list[float] = []

        for _, row in aligned.iterrows():
            quarter_date = row["quarter_date"]
            velocity = float(row["velocity"])

            start_price = self._price_on_or_after(price_frame, quarter_date)
            end_price = self._price_on_or_after(price_frame, quarter_date + pd.Timedelta(days=30))

            if start_price is None or end_price is None or start_price <= 0:
                continue

            forward_return = (end_price - start_price) / start_price
            velocities.append(velocity)
            future_returns_30d.append(float(forward_return))

        if len(velocities) < 2:
            return float("nan")

        velocity_std = float(np.std(velocities, ddof=0))
        return_std = float(np.std(future_returns_30d, ddof=0))
        if velocity_std == 0.0 or return_std == 0.0:
            return float("nan")

        correlation = float(np.corrcoef(velocities, future_returns_30d)[0, 1])
        return float("nan") if np.isnan(correlation) else correlation

    def generate_signal(self, symbol: str) -> dict[str, Any]:
        """
        Generate an interpretable promoter-velocity signal.

        Output schema:
        {
            "velocity": float | None,
            "direction": "increasing" | "decreasing" | "flat",
            "anomaly_flag": bool,
            "historical_correlation": float | None,
            "signal_strength": int  # 0..100
        }
        """
        clean_symbol = self._clean_symbol(symbol)
        velocity_payload = self._get_velocity_payload(clean_symbol)
        latest_velocity = velocity_payload.get("latest_velocity")

        anomaly = self.flag_anomaly(clean_symbol)
        historical_correlation = self.correlate_with_price(clean_symbol)

        velocity_values = pd.Series(
            [row.get("velocity") for row in velocity_payload.get("series", [])],
            dtype="float64",
        ).dropna()

        if latest_velocity is None or velocity_values.empty:
            velocity_z = 0.0
        else:
            velocity_mean = float(velocity_values.mean())
            velocity_std = float(velocity_values.std(ddof=0))
            if velocity_std == 0.0:
                velocity_z = abs(float(latest_velocity))
            else:
                velocity_z = abs((float(latest_velocity) - velocity_mean) / velocity_std)

        velocity_score = min(velocity_z / 3.0, 1.0) * 100.0

        if np.isnan(historical_correlation):
            correlation_score = 0.0
            correlation_out: float | None = None
        else:
            correlation_score = min(abs(historical_correlation), 1.0) * 100.0
            correlation_out = round(float(historical_correlation), 4)

        anomaly_score = 100.0 if bool(anomaly.get("anomaly_flag")) else 35.0

        rolling_avg = velocity_payload.get("latest_rolling_4q_avg")
        if latest_velocity is None or rolling_avg is None:
            trend_consistency_score = 50.0
        elif float(latest_velocity) == 0.0 or float(rolling_avg) == 0.0:
            trend_consistency_score = 50.0
        elif np.sign(float(latest_velocity)) == np.sign(float(rolling_avg)):
            trend_consistency_score = 100.0
        else:
            trend_consistency_score = 20.0

        signal_strength = (
            0.45 * velocity_score
            + 0.35 * correlation_score
            + 0.10 * anomaly_score
            + 0.10 * trend_consistency_score
        )
        signal_strength_int = int(np.clip(round(signal_strength), 0, 100))

        return {
            "velocity": self._to_optional_float(latest_velocity),
            "direction": self._velocity_direction(latest_velocity),
            "anomaly_flag": bool(anomaly.get("anomaly_flag", False)),
            "historical_correlation": correlation_out,
            "signal_strength": signal_strength_int,
        }

    @staticmethod
    def _empty_velocity_payload() -> dict[str, Any]:
        return {
            "latest_velocity": None,
            "latest_acceleration": None,
            "latest_rolling_4q_avg": None,
            "trend_reversal_points": [],
            "series": [],
        }

    def _get_velocity_payload(self, symbol: str) -> dict[str, Any]:
        if symbol in self._velocity_cache:
            return self._velocity_cache[symbol]

        shareholding_data = self._shareholding_history.get(symbol)
        if shareholding_data is None:
            payload = self._empty_velocity_payload()
            self._velocity_cache[symbol] = payload
            return payload

        payload = self.calculate_velocity(shareholding_data)
        self._velocity_cache[symbol] = payload
        return payload

    def _normalize_shareholding_data(self, shareholding_data: Any) -> pd.DataFrame:
        frame: pd.DataFrame

        if isinstance(shareholding_data, pd.DataFrame):
            frame = shareholding_data.copy()
        elif isinstance(shareholding_data, dict):
            if isinstance(shareholding_data.get("quarters"), list):
                frame = pd.DataFrame(shareholding_data["quarters"])
            elif isinstance(shareholding_data.get("data"), list):
                frame = pd.DataFrame(shareholding_data["data"])
            else:
                frame = pd.DataFrame(shareholding_data)
        elif isinstance(shareholding_data, list):
            frame = pd.DataFrame(shareholding_data)
        else:
            frame = pd.DataFrame()

        if frame.empty:
            return pd.DataFrame(columns=["quarter", "quarter_date", "promoter_holding_percent"])

        quarter_col = self._pick_column(
            frame,
            [
                "quarter",
                "qtr",
                "period",
                "date",
                "asOn",
                "as_on",
                "quarterEnding",
            ],
        )
        promoter_col = self._pick_column(
            frame,
            [
                "promoter_holding_percent",
                "promoterAndPromoterGroup",
                "promoter_holding",
                "promoterHolding",
                "promoter",
                "pr_and_prgrp",
                "prAndPrgrp",
            ],
        )

        if quarter_col is None or promoter_col is None:
            return pd.DataFrame(columns=["quarter", "quarter_date", "promoter_holding_percent"])

        out = pd.DataFrame(
            {
                "quarter": frame[quarter_col].astype(str).str.strip(),
                "promoter_holding_percent": pd.to_numeric(frame[promoter_col], errors="coerce"),
            }
        )

        out = out.dropna(subset=["promoter_holding_percent"])
        out = out[out["quarter"] != ""]

        out["quarter_date"] = out["quarter"].apply(self._parse_quarter_to_datetime)
        out = out.dropna(subset=["quarter_date"])

        if out.empty:
            return out

        out = out.sort_values("quarter_date").drop_duplicates(subset=["quarter"], keep="last")
        out = out.reset_index(drop=True)
        return out

    def _normalize_price_data(self, price_data: Any) -> pd.DataFrame:
        frame: pd.DataFrame

        if isinstance(price_data, pd.DataFrame):
            frame = price_data.copy()
        elif isinstance(price_data, dict):
            dates = price_data.get("dates")
            closes = price_data.get("closes")
            if isinstance(dates, list) and isinstance(closes, list) and len(dates) == len(closes):
                frame = pd.DataFrame({"date": dates, "close": closes})
            elif isinstance(price_data.get("data"), list):
                frame = pd.DataFrame(price_data["data"])
            else:
                frame = pd.DataFrame(price_data)
        elif isinstance(price_data, list):
            frame = pd.DataFrame(price_data)
        else:
            frame = pd.DataFrame()

        if frame.empty:
            return pd.DataFrame(columns=["date", "close"])

        if "date" not in frame.columns and isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.reset_index().rename(columns={frame.index.name or "index": "date"})

        date_col = self._pick_column(
            frame,
            ["date", "dates", "datetime", "timestamp", "time", "day"],
        )
        close_col = self._pick_column(
            frame,
            ["close", "closes", "adj_close", "adjClose", "price", "last_price", "ltp"],
        )

        if date_col is None or close_col is None:
            return pd.DataFrame(columns=["date", "close"])

        out = pd.DataFrame(
            {
                "date": pd.to_datetime(frame[date_col], errors="coerce"),
                "close": pd.to_numeric(frame[close_col], errors="coerce"),
            }
        )
        out = out.dropna(subset=["date", "close"])

        if out.empty:
            return out

        out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        out = out.reset_index(drop=True)
        return out

    def _price_on_or_after(self, price_frame: pd.DataFrame, dt: pd.Timestamp) -> float | None:
        candidates = price_frame.loc[price_frame["date"] >= dt, "close"]
        if candidates.empty:
            return None
        value = float(candidates.iloc[0])
        return value if np.isfinite(value) else None

    def _parse_quarter_to_datetime(self, quarter_value: Any) -> pd.Timestamp | pd.NaT:
        if quarter_value is None or (isinstance(quarter_value, float) and np.isnan(quarter_value)):
            return pd.NaT

        if isinstance(quarter_value, pd.Timestamp):
            return quarter_value.normalize()

        text = str(quarter_value).strip()
        if not text:
            return pd.NaT

        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
        if pd.notna(parsed):
            return pd.Timestamp(parsed).normalize()

        upper = text.upper().replace(" ", "")

        # Example: Q1FY25, Q3FY2024, FY25Q2
        match_fy_q = re.match(r"^Q([1-4])FY(\d{2,4})$", upper)
        if match_fy_q:
            q = int(match_fy_q.group(1))
            fy_year = self._normalize_year(int(match_fy_q.group(2)))
            return self._fy_quarter_end(q, fy_year)

        match_q_fy = re.match(r"^FY(\d{2,4})Q([1-4])$", upper)
        if match_q_fy:
            fy_year = self._normalize_year(int(match_q_fy.group(1)))
            q = int(match_q_fy.group(2))
            return self._fy_quarter_end(q, fy_year)

        # Example: Q1-2024, 2024Q1
        match_calendar_q = re.match(r"^Q([1-4])[-_/]?(\d{2,4})$", upper)
        if match_calendar_q:
            q = int(match_calendar_q.group(1))
            year = self._normalize_year(int(match_calendar_q.group(2)))
            month = q * 3
            return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)

        match_calendar_q_alt = re.match(r"^(\d{2,4})Q([1-4])$", upper)
        if match_calendar_q_alt:
            year = self._normalize_year(int(match_calendar_q_alt.group(1)))
            q = int(match_calendar_q_alt.group(2))
            month = q * 3
            return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)

        return pd.NaT

    @staticmethod
    def _fy_quarter_end(quarter: int, fy_year: int) -> pd.Timestamp:
        # Indian FY: Q1=Jun(prev year), Q2=Sep(prev year), Q3=Dec(prev year), Q4=Mar(fy year)
        mapping = {
            1: (fy_year - 1, 6),
            2: (fy_year - 1, 9),
            3: (fy_year - 1, 12),
            4: (fy_year, 3),
        }
        year, month = mapping[quarter]
        return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)

    @staticmethod
    def _normalize_year(year: int) -> int:
        if year < 100:
            return 2000 + year
        return year

    @staticmethod
    def _pick_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate

        normalized_candidates = {PromoterVelocityEngine._normalized_name(name) for name in candidates}
        for column in frame.columns:
            if PromoterVelocityEngine._normalized_name(str(column)) in normalized_candidates:
                return str(column)
        return None

    @staticmethod
    def _normalized_name(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    @staticmethod
    def _last_valid(series: pd.Series) -> float | None:
        cleaned = pd.to_numeric(series, errors="coerce").dropna()
        if cleaned.empty:
            return None
        return float(round(float(cleaned.iloc[-1]), 4))

    @staticmethod
    def _to_optional_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (float, np.floating)) and np.isnan(value):
            return None
        if pd.isna(value):
            return None
        return float(round(float(value), 4))

    @staticmethod
    def _fmt_date(value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        return pd.Timestamp(value).strftime("%Y-%m-%d")

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _velocity_direction(velocity: float | None) -> str:
        if velocity is None:
            return "flat"
        if float(velocity) > 0.05:
            return "increasing"
        if float(velocity) < -0.05:
            return "decreasing"
        return "flat"

    @staticmethod
    def _acceleration_direction(acceleration: float) -> str:
        if acceleration > 0.0:
            return "accelerating_up"
        if acceleration < 0.0:
            return "accelerating_down"
        return "flat"