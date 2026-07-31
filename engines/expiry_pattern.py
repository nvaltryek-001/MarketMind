"""
Expiry Pattern Engine.

Maps how a stock/index behaves around derivative expiry windows using
historical NSE EOD OHLC data.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd


class ExpiryPatternEngine:
    """Detects recurring pre- and post-expiry behavior per symbol."""

    def __init__(
        self,
        eod_history: dict[str, Any] | None = None,
        nse_holidays: list[str | pd.Timestamp] | None = None,
        eod_loader: Callable[[str], Any] | None = None,
    ) -> None:
        self._eod_history: dict[str, pd.DataFrame] = {}
        self._window_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self._pattern_cache: dict[str, dict[str, Any]] = {}
        self._signal_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._expiry_cache: dict[tuple[int, int], dict[str, Any]] = {}
        self._eod_loader = eod_loader

        self._nse_holidays: set[pd.Timestamp] = set()
        if nse_holidays:
            for value in nse_holidays:
                dt = pd.to_datetime(value, errors="coerce")
                if pd.notna(dt):
                    self._nse_holidays.add(pd.Timestamp(dt).normalize())

        if eod_history:
            for symbol, data in eod_history.items():
                self.update_eod_data(symbol, data)

    def update_eod_data(self, symbol: str, eod_data: Any) -> None:
        """Register or replace NSE EOD history for a symbol/index."""
        clean_symbol = self._clean_symbol(symbol)
        frame = self._normalize_eod_data(eod_data)
        self._eod_history[clean_symbol] = frame

        for key in list(self._window_cache):
            if key[0] == clean_symbol:
                self._window_cache.pop(key, None)
        self._pattern_cache.pop(clean_symbol, None)

        today_key = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
        self._signal_cache.pop((clean_symbol, today_key), None)

    def get_expiry_dates(self, year: int, month: int) -> dict[str, Any]:
        """
        Return adjusted NSE weekly and monthly expiry dates for a month.

        Weekly expiries are all adjusted Thursdays excluding the monthly expiry.
        Monthly expiry is the last adjusted Thursday of the month.
        """
        cache_key = (int(year), int(month))
        if cache_key in self._expiry_cache:
            return self._expiry_cache[cache_key]

        month_start = pd.Timestamp(year=int(year), month=int(month), day=1)
        month_end = month_start + pd.offsets.MonthEnd(0)

        raw_thursdays = pd.date_range(month_start, month_end, freq="W-THU")

        adjusted_expiries: list[pd.Timestamp] = []
        for dt in raw_thursdays:
            adjusted_expiries.append(self._adjust_to_previous_trading_day(pd.Timestamp(dt).normalize()))

        unique_expiries = sorted(set(adjusted_expiries))
        monthly_expiry = unique_expiries[-1] if unique_expiries else None
        weekly_expiries = [dt for dt in unique_expiries if dt != monthly_expiry]

        payload = {
            "year": int(year),
            "month": int(month),
            "weekly_expiry_dates": [dt.strftime("%Y-%m-%d") for dt in weekly_expiries],
            "monthly_expiry_date": monthly_expiry.strftime("%Y-%m-%d") if monthly_expiry is not None else None,
            "all_expiry_dates": [dt.strftime("%Y-%m-%d") for dt in unique_expiries],
        }
        self._expiry_cache[cache_key] = payload
        return payload

    def calculate_expiry_window_returns(self, symbol: str, lookback_months: int = 12) -> list[dict[str, Any]]:
        """
        For each historical expiry in lookback, compute:
        - T-5 to T-1 return
        - T-1 to T+1 return
        - Max intraday spike on expiry day
        """
        clean_symbol = self._clean_symbol(symbol)
        lookback = max(int(lookback_months), 1)
        cache_key = (clean_symbol, lookback)
        if cache_key in self._window_cache:
            return self._window_cache[cache_key]

        frame = self._get_eod_frame(clean_symbol)
        if frame.empty:
            self._window_cache[cache_key] = []
            return []

        as_of_date = min(frame["date"].max(), pd.Timestamp.today().normalize())
        start_date = (as_of_date - pd.DateOffset(months=lookback - 1)).replace(day=1)

        months = pd.period_range(start=start_date, end=as_of_date, freq="M")

        records: list[dict[str, Any]] = []
        seen_expiry_trade_dates: set[pd.Timestamp] = set()

        trading_dates = frame["date"]
        close_series = frame["close"]
        open_series = frame["open"]
        high_series = frame["high"]
        low_series = frame["low"]

        for period in months:
            expiry_info = self.get_expiry_dates(period.year, period.month)
            monthly_raw = expiry_info.get("monthly_expiry_date")
            weekly_raw = expiry_info.get("weekly_expiry_dates", [])

            monthly_date = pd.to_datetime(monthly_raw, errors="coerce") if monthly_raw else pd.NaT
            weekly_dates = [pd.to_datetime(value, errors="coerce") for value in weekly_raw]

            expiry_entries: list[tuple[pd.Timestamp, str]] = []
            if pd.notna(monthly_date):
                expiry_entries.append((pd.Timestamp(monthly_date).normalize(), "monthly"))

            for dt in weekly_dates:
                if pd.notna(dt):
                    expiry_entries.append((pd.Timestamp(dt).normalize(), "weekly"))

            for expiry_date, expiry_type in sorted(expiry_entries, key=lambda item: item[0]):
                if expiry_date > as_of_date:
                    continue

                idx = self._index_on_or_before(trading_dates, expiry_date)
                if idx is None:
                    continue

                expiry_trade_date = pd.Timestamp(trading_dates.iloc[idx]).normalize()
                if expiry_trade_date in seen_expiry_trade_dates:
                    continue

                if idx < 5 or idx + 1 >= len(frame):
                    continue

                seen_expiry_trade_dates.add(expiry_trade_date)

                pre_start_close = float(close_series.iloc[idx - 5])
                pre_end_close = float(close_series.iloc[idx - 1])
                around_start_close = float(close_series.iloc[idx - 1])
                around_end_close = float(close_series.iloc[idx + 1])

                if pre_start_close <= 0 or around_start_close <= 0:
                    continue

                t_minus_5_to_t_minus_1_return = (pre_end_close / pre_start_close) - 1.0
                t_minus_1_to_t_plus_1_return = (around_end_close / around_start_close) - 1.0

                day_open = float(open_series.iloc[idx])
                day_high = float(high_series.iloc[idx])
                day_low = float(low_series.iloc[idx])

                if day_open <= 0:
                    max_intraday_spike = 0.0
                else:
                    up_spike = (day_high - day_open) / day_open
                    down_spike = (day_open - day_low) / day_open
                    max_intraday_spike = max(abs(up_spike), abs(down_spike))

                records.append(
                    {
                        "symbol": clean_symbol,
                        "expiry_date": expiry_trade_date.strftime("%Y-%m-%d"),
                        "expiry_type": expiry_type,
                        "t_minus_5_to_t_minus_1_return": round(float(t_minus_5_to_t_minus_1_return), 6),
                        "t_minus_1_to_t_plus_1_return": round(float(t_minus_1_to_t_plus_1_return), 6),
                        "max_intraday_spike": round(float(max_intraday_spike), 6),
                    }
                )

        records = sorted(records, key=lambda row: row["expiry_date"])
        self._window_cache[cache_key] = records
        return records

    def detect_pattern(self, symbol: str) -> dict[str, Any]:
        """
        Return dominant expiry behavior pattern with confidence score.

        Patterns:
        - expiry_rally
        - expiry_selloff
        - pin_to_strike
        - no_pattern
        """
        clean_symbol = self._clean_symbol(symbol)
        if clean_symbol in self._pattern_cache:
            return self._pattern_cache[clean_symbol]

        rows = self.calculate_expiry_window_returns(clean_symbol, lookback_months=12)
        if len(rows) < 4:
            payload = {
                "symbol": clean_symbol,
                "dominant_pattern": "no_pattern",
                "confidence_score": 20,
                "sample_size": len(rows),
                "pattern_scores": {
                    "expiry_rally": 0.0,
                    "expiry_selloff": 0.0,
                    "pin_to_strike": 0.0,
                },
            }
            self._pattern_cache[clean_symbol] = payload
            return payload

        frame = pd.DataFrame(rows)
        pre = pd.to_numeric(frame["t_minus_5_to_t_minus_1_return"], errors="coerce").to_numpy()
        around = pd.to_numeric(frame["t_minus_1_to_t_plus_1_return"], errors="coerce").to_numpy()
        spike = pd.to_numeric(frame["max_intraday_spike"], errors="coerce").to_numpy()

        valid_mask = np.isfinite(pre) & np.isfinite(around) & np.isfinite(spike)
        pre = pre[valid_mask]
        around = around[valid_mask]
        spike = spike[valid_mask]

        n = len(pre)
        if n < 4:
            payload = {
                "symbol": clean_symbol,
                "dominant_pattern": "no_pattern",
                "confidence_score": 20,
                "sample_size": n,
                "pattern_scores": {
                    "expiry_rally": 0.0,
                    "expiry_selloff": 0.0,
                    "pin_to_strike": 0.0,
                },
            }
            self._pattern_cache[clean_symbol] = payload
            return payload

        pin_return_threshold = max(float(np.nanpercentile(np.abs(around), 40)), 0.0025)
        pin_spike_threshold = max(float(np.nanpercentile(spike, 40)), 0.01)

        rally_hits = (pre > 0.0) & (around > 0.0)
        selloff_hits = (pre < 0.0) & (around < 0.0)
        pin_hits = (np.abs(around) <= pin_return_threshold) & (spike <= pin_spike_threshold)

        scores = {
            "expiry_rally": float(np.mean(rally_hits)),
            "expiry_selloff": float(np.mean(selloff_hits)),
            "pin_to_strike": float(np.mean(pin_hits)),
        }

        sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        winner, winner_score = sorted_scores[0]
        second_score = sorted_scores[1][1]

        if winner_score < 0.45 or (winner_score - second_score) < 0.08:
            dominant_pattern = "no_pattern"
        else:
            dominant_pattern = winner

        if dominant_pattern == "no_pattern":
            confidence = 100.0 * (1.0 - winner_score)
        else:
            base_confidence = winner_score * 100.0
            separation = max(winner_score - second_score, 0.0) * 100.0
            sample_factor = min(1.0, np.log1p(n) / np.log1p(24.0))
            confidence = 0.65 * base_confidence + 0.25 * separation + 0.10 * (sample_factor * 100.0)

        payload = {
            "symbol": clean_symbol,
            "dominant_pattern": dominant_pattern,
            "confidence_score": int(np.clip(round(confidence), 0, 100)),
            "sample_size": n,
            "pattern_scores": {name: round(value, 4) for name, value in scores.items()},
        }
        self._pattern_cache[clean_symbol] = payload
        return payload

    def get_current_expiry_signal(self, symbol: str) -> dict[str, Any]:
        """
        Return expected behavior for today relative to upcoming expiry.
        """
        clean_symbol = self._clean_symbol(symbol)
        today = pd.Timestamp.today().normalize()
        signal_cache_key = (clean_symbol, today.strftime("%Y-%m-%d"))
        if signal_cache_key in self._signal_cache:
            return self._signal_cache[signal_cache_key]

        pattern = self.detect_pattern(clean_symbol)
        next_expiry = self._get_next_expiry_date(today)
        previous_expiry = self._get_previous_expiry_date(today)

        trading_days_to_next = self._trading_days_between(today, next_expiry) if next_expiry is not None else None
        trading_days_since_prev = self._trading_days_between(previous_expiry, today) if previous_expiry is not None else None

        if previous_expiry is not None and trading_days_since_prev is not None and 1 <= trading_days_since_prev <= 5:
            phase = "post_expiry_window"
        elif next_expiry is not None and trading_days_to_next == 0:
            phase = "expiry_day"
        elif next_expiry is not None and trading_days_to_next is not None and 1 <= trading_days_to_next <= 5:
            phase = "pre_expiry_window"
        else:
            phase = "outside_window"

        expected_behavior, directional_bias = self._expected_behavior_for_phase(
            dominant_pattern=pattern["dominant_pattern"],
            phase=phase,
        )

        payload = {
            "symbol": clean_symbol,
            "today": today.strftime("%Y-%m-%d"),
            "next_expiry_date": next_expiry.strftime("%Y-%m-%d") if next_expiry is not None else None,
            "days_to_next_expiry": int((next_expiry - today).days) if next_expiry is not None else None,
            "trading_days_to_next_expiry": trading_days_to_next,
            "phase": phase,
            "dominant_pattern": pattern["dominant_pattern"],
            "pattern_confidence": pattern["confidence_score"],
            "expected_behavior": expected_behavior,
            "directional_bias": directional_bias,
        }
        self._signal_cache[signal_cache_key] = payload
        return payload

    def _get_eod_frame(self, symbol: str) -> pd.DataFrame:
        frame = self._eod_history.get(symbol)
        if frame is not None:
            return frame

        if self._eod_loader is None:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        loaded = self._eod_loader(symbol)
        frame = self._normalize_eod_data(loaded)
        self._eod_history[symbol] = frame
        return frame

    def _normalize_eod_data(self, eod_data: Any) -> pd.DataFrame:
        frame: pd.DataFrame

        if isinstance(eod_data, pd.DataFrame):
            frame = eod_data.copy()
        elif isinstance(eod_data, dict):
            dates = eod_data.get("dates")
            closes = eod_data.get("closes")
            opens = eod_data.get("opens")
            highs = eod_data.get("highs")
            lows = eod_data.get("lows")

            if (
                isinstance(dates, list)
                and isinstance(closes, list)
                and len(dates) == len(closes)
            ):
                frame = pd.DataFrame(
                    {
                        "date": dates,
                        "close": closes,
                        "open": opens if isinstance(opens, list) and len(opens) == len(dates) else closes,
                        "high": highs if isinstance(highs, list) and len(highs) == len(dates) else closes,
                        "low": lows if isinstance(lows, list) and len(lows) == len(dates) else closes,
                    }
                )
            elif isinstance(eod_data.get("data"), list):
                frame = pd.DataFrame(eod_data["data"])
            else:
                frame = pd.DataFrame(eod_data)
        elif isinstance(eod_data, list):
            frame = pd.DataFrame(eod_data)
        else:
            frame = pd.DataFrame()

        if frame.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        if "date" not in frame.columns and isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.reset_index().rename(columns={frame.index.name or "index": "date"})

        date_col = self._pick_column(frame, ["date", "datetime", "timestamp", "time", "day", "dates"])
        close_col = self._pick_column(frame, ["close", "adj_close", "adjclose", "closes", "price", "ltp"])
        open_col = self._pick_column(frame, ["open", "opens"]) or close_col
        high_col = self._pick_column(frame, ["high", "highs"]) or close_col
        low_col = self._pick_column(frame, ["low", "lows"]) or close_col

        if date_col is None or close_col is None:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        out = pd.DataFrame(
            {
                "date": pd.to_datetime(frame[date_col], errors="coerce"),
                "open": pd.to_numeric(frame[open_col], errors="coerce"),
                "high": pd.to_numeric(frame[high_col], errors="coerce"),
                "low": pd.to_numeric(frame[low_col], errors="coerce"),
                "close": pd.to_numeric(frame[close_col], errors="coerce"),
            }
        )
        out = out.dropna(subset=["date", "close"])

        if out.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        out["open"] = out["open"].fillna(out["close"])
        out["high"] = out[["high", "open", "close"]].max(axis=1)
        out["low"] = out[["low", "open", "close"]].min(axis=1)

        out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        return out.reset_index(drop=True)

    def _get_next_expiry_date(self, today: pd.Timestamp) -> pd.Timestamp | None:
        candidates: list[pd.Timestamp] = []
        current_month = today.to_period("M")
        month_span = [current_month, current_month + 1, current_month + 2]

        for period in month_span:
            info = self.get_expiry_dates(period.year, period.month)
            for date_str in info.get("all_expiry_dates", []):
                dt = pd.to_datetime(date_str, errors="coerce")
                if pd.notna(dt):
                    candidates.append(pd.Timestamp(dt).normalize())

        future = sorted(set(dt for dt in candidates if dt >= today))
        return future[0] if future else None

    def _get_previous_expiry_date(self, today: pd.Timestamp) -> pd.Timestamp | None:
        candidates: list[pd.Timestamp] = []
        current_month = today.to_period("M")
        month_span = [current_month - 2, current_month - 1, current_month]

        for period in month_span:
            info = self.get_expiry_dates(period.year, period.month)
            for date_str in info.get("all_expiry_dates", []):
                dt = pd.to_datetime(date_str, errors="coerce")
                if pd.notna(dt):
                    candidates.append(pd.Timestamp(dt).normalize())

        past = sorted(set(dt for dt in candidates if dt <= today))
        return past[-1] if past else None

    def _trading_days_between(self, start: pd.Timestamp | None, end: pd.Timestamp | None) -> int | None:
        if start is None or end is None:
            return None

        if end < start:
            return -self._trading_days_between(end, start)

        days = pd.date_range(start, end, freq="D")
        trading_days = [
            d for d in days
            if d.weekday() < 5 and d.normalize() not in self._nse_holidays
        ]

        if not trading_days:
            return 0
        return len(trading_days) - 1

    def _expected_behavior_for_phase(self, dominant_pattern: str, phase: str) -> tuple[str, str]:
        if dominant_pattern == "expiry_rally":
            if phase == "pre_expiry_window":
                return "historical upward drift into expiry", "bullish"
            if phase == "expiry_day":
                return "historical upside bias with elevated intraday swings", "bullish"
            if phase == "post_expiry_window":
                return "historical mild continuation after expiry", "bullish"
            return "no immediate expiry edge yet; watch for rally setup inside T-5", "neutral"

        if dominant_pattern == "expiry_selloff":
            if phase == "pre_expiry_window":
                return "historical downward drift into expiry", "bearish"
            if phase == "expiry_day":
                return "historical downside bias with elevated intraday swings", "bearish"
            if phase == "post_expiry_window":
                return "historical weak follow-through after expiry", "bearish"
            return "no immediate expiry edge yet; watch for selloff setup inside T-5", "neutral"

        if dominant_pattern == "pin_to_strike":
            if phase in {"pre_expiry_window", "expiry_day"}:
                return "historically range-bound price action with pin behavior", "neutral"
            if phase == "post_expiry_window":
                return "historically low-conviction moves right after expiry", "neutral"
            return "no immediate expiry edge; pin behavior usually appears near expiry", "neutral"

        return "historically inconsistent expiry behavior", "neutral"

    def _adjust_to_previous_trading_day(self, dt: pd.Timestamp) -> pd.Timestamp:
        adjusted = dt.normalize()
        while adjusted.weekday() >= 5 or adjusted in self._nse_holidays:
            adjusted -= pd.Timedelta(days=1)
        return adjusted

    @staticmethod
    def _index_on_or_before(series: pd.Series, target_date: pd.Timestamp) -> int | None:
        candidates = series[series <= target_date]
        if candidates.empty:
            return None
        return int(candidates.index[-1])

    @staticmethod
    def _pick_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate

        normalized_candidates = {ExpiryPatternEngine._normalized_name(name) for name in candidates}
        for column in frame.columns:
            if ExpiryPatternEngine._normalized_name(str(column)) in normalized_candidates:
                return str(column)
        return None

    @staticmethod
    def _normalized_name(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        return symbol.strip().upper()