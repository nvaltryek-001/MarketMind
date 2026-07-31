from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd
import yfinance as yf

NSE_BASE_URL = "https://www.nseindia.com"
DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": NSE_BASE_URL,
    "x-requested-with": "XMLHttpRequest",
    "connection": "keep-alive",
}

RETRIABLE_STATUS_CODES = {401, 403, 408, 429, 500, 502, 503, 504}
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]{0,19}$")


class InvalidSymbolError(ValueError):
    """Raised when the supplied symbol does not match accepted format."""


class SymbolNotFoundError(LookupError):
    """Raised when the symbol appears invalid or delisted upstream."""


class UpstreamServiceError(RuntimeError):
    """Raised when an upstream market-data service cannot be reached."""


class NSEMarketDataService:
    """NSE/BSE market-data access layer with retries and symbol validation."""

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_retries: int = 4,
        retry_backoff_seconds: float = 0.8,
        min_request_interval_seconds: float = 0.4,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=NSE_BASE_URL,
            headers=DEFAULT_HEADERS,
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.1, float(retry_backoff_seconds))
        self._min_request_interval_seconds = max(0.0, float(min_request_interval_seconds))

        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    def normalize_symbol(self, symbol: str) -> str:
        clean_symbol = (symbol or "").strip().upper()
        if not clean_symbol:
            raise InvalidSymbolError("Symbol is required")
        if not SYMBOL_PATTERN.match(clean_symbol):
            raise InvalidSymbolError(
                "Invalid symbol format. Use NSE cash-market symbol, e.g. RELIANCE or TCS."
            )
        return clean_symbol

    async def _ensure_session(self, force_refresh: bool = False) -> None:
        if self._initialized and not force_refresh:
            return

        async with self._init_lock:
            if self._initialized and not force_refresh:
                return

            if force_refresh:
                self._client.cookies.clear()

            landing_headers = {
                **DEFAULT_HEADERS,
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "upgrade-insecure-requests": "1",
                "referer": NSE_BASE_URL,
            }

            for path in ("/", "/option-chain"):
                response = await self._client.get(path, headers=landing_headers)
                response.raise_for_status()

            self._initialized = True

    async def _throttle(self) -> None:
        if self._min_request_interval_seconds <= 0:
            return

        async with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_ts
            if elapsed < self._min_request_interval_seconds:
                await asyncio.sleep(self._min_request_interval_seconds - elapsed)
            self._last_request_ts = time.monotonic()

    async def _request_json(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        referer_path: str = "/",
        symbol_hint: str | None = None,
    ) -> dict[str, Any]:
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._ensure_session()
                await self._throttle()

                headers = {
                    **DEFAULT_HEADERS,
                    "accept": "application/json, text/plain, */*",
                    "referer": f"{NSE_BASE_URL}{referer_path}",
                }
                response = await self._client.get(endpoint, params=params, headers=headers)

                if response.status_code == 404 and symbol_hint:
                    raise SymbolNotFoundError(f"Symbol '{symbol_hint}' is invalid or delisted")

                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                body = response.text.lstrip()
                if "json" not in content_type.lower() and not body.startswith(("{", "[")):
                    raise UpstreamServiceError("NSE returned non-JSON response")

                payload = response.json()
                if isinstance(payload, list):
                    payload = {"data": payload}

                if not isinstance(payload, dict):
                    raise UpstreamServiceError("Unexpected NSE response shape")

                message = str(
                    payload.get("message") or payload.get("msg") or payload.get("error") or ""
                ).strip()
                if symbol_hint and message and self._looks_like_missing_symbol(message):
                    raise SymbolNotFoundError(f"Symbol '{symbol_hint}' is invalid or delisted")

                return payload
            except SymbolNotFoundError:
                raise
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code in {401, 403, 429}:
                    await self._ensure_session(force_refresh=True)

                if status_code == 404 and symbol_hint:
                    raise SymbolNotFoundError(f"Symbol '{symbol_hint}' is invalid or delisted") from exc

                if status_code not in RETRIABLE_STATUS_CODES or attempt == self._max_retries:
                    raise UpstreamServiceError(
                        f"NSE request failed with HTTP {status_code}"
                    ) from exc
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
                await self._ensure_session(force_refresh=True)
                if attempt == self._max_retries:
                    raise UpstreamServiceError("NSE request timed out or failed") from exc

            backoff = self._retry_backoff_seconds * (2 ** (attempt - 1)) + random.uniform(0.0, 0.2)
            await asyncio.sleep(backoff)

        raise UpstreamServiceError("NSE request retries exhausted")

    async def get_snapshot(self, symbol: str) -> dict[str, Any]:
        clean_symbol = self.normalize_symbol(symbol)
        raw = await self._request_json(
            "/api/quote-equity",
            params={"symbol": clean_symbol},
            referer_path=f"/get-quotes/equity?symbol={clean_symbol}",
            symbol_hint=clean_symbol,
        )

        price_info = raw.get("priceInfo", {})
        last_price = self._to_float(price_info.get("lastPrice"))
        if last_price is None:
            raise SymbolNotFoundError(f"Symbol '{clean_symbol}' is invalid or delisted")

        week_range = price_info.get("weekHighLow", {})
        security_dp = raw.get("securityWiseDP", {})
        metadata = raw.get("metadata", {})
        info = raw.get("info", {})
        security_info = raw.get("securityInfo", {})

        quote = {
            "price": last_price,
            "change": self._to_float(price_info.get("change")),
            "percent_change": self._to_float(price_info.get("pChange")),
            "open": self._to_float(price_info.get("open")),
            "close": self._to_float(price_info.get("close")),
            "previous_close": self._to_float(price_info.get("previousClose")),
            "day_high": self._to_float(price_info.get("intraDayHighLow", {}).get("max")),
            "day_low": self._to_float(price_info.get("intraDayHighLow", {}).get("min")),
            "fifty_two_week_high": self._to_float(week_range.get("max")),
            "fifty_two_week_low": self._to_float(week_range.get("min")),
            "last_update": metadata.get("lastUpdateTime"),
        }

        basic_metrics = {
            "isin": info.get("isin"),
            "listing_date": security_info.get("listingDate"),
            "face_value": self._to_float(security_info.get("faceValue")),
            "issued_size": self._to_float(security_info.get("issuedSize")),
            "delivery_percent": self._to_float(
                security_dp.get("deliveryToTradedQuantity") or security_dp.get("deliveryPercentage")
            ),
            "circuit_limits": {
                "lower": self._to_float(
                    price_info.get("lowerCP")
                    or price_info.get("lowerCircuitLimit")
                    or price_info.get("lowerCircuit")
                ),
                "upper": self._to_float(
                    price_info.get("upperCP")
                    or price_info.get("upperCircuitLimit")
                    or price_info.get("upperCircuit")
                ),
            },
        }

        return {
            "symbol": clean_symbol,
            "company_name": info.get("companyName"),
            "industry": info.get("industry"),
            "quote": quote,
            "basic_metrics": basic_metrics,
        }

    async def get_option_chain(self, symbol: str) -> dict[str, Any]:
        clean_symbol = self.normalize_symbol(symbol)
        raw = await self._request_json(
            "/api/option-chain-equities",
            params={"symbol": clean_symbol},
            referer_path="/option-chain",
            symbol_hint=clean_symbol,
        )

        records = raw.get("records", {})
        rows = records.get("data", [])
        if not isinstance(rows, list) or not rows:
            raise SymbolNotFoundError(
                f"Option chain is unavailable for symbol '{clean_symbol}'"
            )

        chain_rows: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue

            strike_price = self._to_float(item.get("strikePrice"))
            if strike_price is None:
                continue

            chain_rows.append(
                {
                    "expiry_date": item.get("expiryDate"),
                    "strike_price": strike_price,
                    "CE": self._extract_option_leg(item.get("CE")),
                    "PE": self._extract_option_leg(item.get("PE")),
                }
            )

        if not chain_rows:
            raise SymbolNotFoundError(
                f"Option chain is unavailable for symbol '{clean_symbol}'"
            )

        analytics = self._compute_option_chain_analytics(chain_rows)
        return {
            "symbol": clean_symbol,
            "timestamp": records.get("timestamp"),
            "underlying_value": self._to_float(records.get("underlyingValue")),
            "option_chain": chain_rows,
            "analytics": analytics,
        }

    async def get_corporate_actions(self, symbol: str) -> dict[str, Any]:
        clean_symbol = self.normalize_symbol(symbol)
        today = date.today()
        start_date = today - timedelta(days=365 * 3)

        raw = await self._request_json(
            "/api/corporates-corporateActions",
            params={
                "index": "equities",
                "symbol": clean_symbol,
                "from_date": start_date.strftime("%d-%m-%Y"),
                "to_date": today.strftime("%d-%m-%Y"),
            },
            referer_path="/companies-listing/corporate-filings-actions",
            symbol_hint=clean_symbol,
        )

        payload = raw.get("data", []) if isinstance(raw, dict) else []
        actions: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            actions.append(
                {
                    "action_type": item.get("caType") or item.get("purpose") or item.get("subject") or "unknown",
                    "purpose": item.get("purpose") or item.get("subject"),
                    "announcement_date": self._normalize_date(
                        self._pick_first(
                            item,
                            (
                                "announcementDate",
                                "an_dt",
                                "boardMeetingDate",
                                "broadcastDate",
                                "date",
                            ),
                        )
                    ),
                    "ex_date": self._normalize_date(self._pick_first(item, ("exDate", "ex_date", "exDt"))),
                    "record_date": self._normalize_date(
                        self._pick_first(item, ("recordDate", "record_date", "recDate"))
                    ),
                    "details": item,
                }
            )

        actions.sort(key=lambda row: row.get("announcement_date") or "", reverse=True)
        return {
            "symbol": clean_symbol,
            "from_date": start_date.isoformat(),
            "to_date": today.isoformat(),
            "count": len(actions),
            "actions": actions,
        }

    async def get_shareholding(self, symbol: str, quarters: int = 8) -> dict[str, Any]:
        clean_symbol = self.normalize_symbol(symbol)
        raw = await self._request_json(
            "/api/corporate-share-holdings",
            params={"index": "equities", "symbol": clean_symbol},
            referer_path="/companies-listing/corporate-filings-shareholding-pattern",
            symbol_hint=clean_symbol,
        )

        quarter_keys = (
            "quarter",
            "qtr",
            "period",
            "date",
            "asOn",
            "as_on",
            "quarterEnding",
        )
        promoter_keys = (
            "promoterAndPromoterGroup",
            "promoter_holding",
            "promoterHolding",
            "promoter",
            "pr_and_prgrp",
            "prAndPrgrp",
        )

        parsed: list[dict[str, Any]] = []
        seen_quarters: set[str] = set()
        for row in self._find_candidate_rows(raw):
            quarter = self._pick_first(row, quarter_keys)
            promoter = self._pick_first(row, promoter_keys)

            if promoter is None:
                for key, value in row.items():
                    normalized = self._normalized_key(key)
                    if "promoter" in normalized and "non" not in normalized and "public" not in normalized:
                        promoter = value
                        break

            if quarter in (None, "") or promoter in (None, ""):
                continue

            quarter_value = str(quarter).strip()
            if quarter_value in seen_quarters:
                continue
            seen_quarters.add(quarter_value)

            parsed.append(
                {
                    "quarter": quarter_value,
                    "promoter_holding_percent": self._to_float(promoter),
                    "raw": row,
                }
            )
            if len(parsed) >= max(1, int(quarters)):
                break

        return {
            "symbol": clean_symbol,
            "quarters": parsed,
            "count": len(parsed),
        }

    async def get_price_history(
        self,
        symbol: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> dict[str, Any]:
        clean_symbol = self.normalize_symbol(symbol)
        history = await asyncio.to_thread(self._download_price_history, clean_symbol, period, interval)
        if history.empty:
            raise SymbolNotFoundError(
                f"Could not load price history for symbol '{clean_symbol}'"
            )

        records = [
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
            }
            for _, row in history.iterrows()
        ]

        return {
            "symbol": clean_symbol,
            "period": period,
            "interval": interval,
            "data": records,
        }

    @staticmethod
    def _download_price_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
        for suffix in (".NS", ".BO"):
            ticker = f"{symbol}{suffix}"
            try:
                frame = yf.download(
                    ticker,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
            except Exception:
                continue

            normalized = NSEMarketDataService._normalize_history_frame(frame)
            if not normalized.empty:
                return normalized

        return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

    @staticmethod
    def _normalize_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        history = frame.copy()
        if isinstance(history.columns, pd.MultiIndex):
            history.columns = [str(column[0]) for column in history.columns]

        history = history.reset_index()
        date_column = "Date" if "Date" in history.columns else "Datetime"
        if date_column not in history.columns:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        required_columns = {"Open", "High", "Low", "Close"}
        if not required_columns.issubset(set(history.columns)):
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        normalized = pd.DataFrame(
            {
                "date": pd.to_datetime(history[date_column], errors="coerce"),
                "open": pd.to_numeric(history["Open"], errors="coerce"),
                "high": pd.to_numeric(history["High"], errors="coerce"),
                "low": pd.to_numeric(history["Low"], errors="coerce"),
                "close": pd.to_numeric(history["Close"], errors="coerce"),
            }
        )

        normalized = normalized.dropna(subset=["date", "close"])
        if normalized.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

        normalized["open"] = normalized["open"].fillna(normalized["close"])
        normalized["high"] = normalized[["high", "open", "close"]].max(axis=1)
        normalized["low"] = normalized[["low", "open", "close"]].min(axis=1)

        normalized = normalized.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        return normalized.reset_index(drop=True)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip().replace(",", "")
        if text.endswith("%"):
            text = text[:-1].strip()
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _normalized_key(value: str) -> str:
        return "".join(ch for ch in str(value).lower() if ch.isalnum())

    @staticmethod
    def _pick_first(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
        lookup = {NSEMarketDataService._normalized_key(key): val for key, val in row.items()}
        for candidate in candidates:
            candidate_value = lookup.get(NSEMarketDataService._normalized_key(candidate))
            if candidate_value not in (None, ""):
                return candidate_value
        return None

    @staticmethod
    def _find_candidate_rows(node: Any) -> list[dict[str, Any]]:
        candidates: list[list[dict[str, Any]]] = []

        def walk(value: Any) -> None:
            if isinstance(value, list):
                dict_rows = [item for item in value if isinstance(item, dict)]
                if dict_rows:
                    candidates.append(dict_rows)
                for item in value:
                    walk(item)
                return

            if isinstance(value, dict):
                for item in value.values():
                    walk(item)

        walk(node)
        if not candidates:
            return []

        def score(rows: list[dict[str, Any]]) -> int:
            value = 0
            for row in rows:
                keys = {NSEMarketDataService._normalized_key(key) for key in row}
                has_period = any(token in keys for token in ("quarter", "qtr", "period", "date", "ason"))
                has_promoter = any("promoter" in token or token == "prandprgrp" for token in keys)
                if has_period:
                    value += 2
                if has_promoter:
                    value += 4
            return value

        return max(candidates, key=score)

    @staticmethod
    def _extract_option_leg(leg: dict[str, Any] | None) -> dict[str, Any] | None:
        if not leg:
            return None

        return {
            "oi": NSEMarketDataService._to_float(leg.get("openInterest")),
            "oi_change": NSEMarketDataService._to_float(leg.get("changeinOpenInterest")),
            "iv": NSEMarketDataService._to_float(leg.get("impliedVolatility")),
            "ltp": NSEMarketDataService._to_float(leg.get("lastPrice")),
            "change": NSEMarketDataService._to_float(leg.get("change")),
            "volume": NSEMarketDataService._to_float(leg.get("totalTradedVolume")),
        }

    @staticmethod
    def _normalize_date(value: Any) -> str | None:
        if value in (None, ""):
            return None
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return str(value)
        return pd.Timestamp(parsed).strftime("%Y-%m-%d")

    def _compute_option_chain_analytics(self, chain_rows: list[dict[str, Any]]) -> dict[str, Any]:
        total_call_oi = 0.0
        total_put_oi = 0.0
        call_oi_by_strike: list[tuple[float, float]] = []
        put_oi_by_strike: list[tuple[float, float]] = []

        for row in chain_rows:
            strike = float(row["strike_price"])
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}

            call_oi = float(ce.get("oi") or 0.0)
            put_oi = float(pe.get("oi") or 0.0)

            total_call_oi += call_oi
            total_put_oi += put_oi

            call_oi_by_strike.append((strike, call_oi))
            put_oi_by_strike.append((strike, put_oi))

        pcr = round(total_put_oi / total_call_oi, 4) if total_call_oi > 0 else None
        max_pain = self._compute_max_pain(chain_rows)
        oi_buildup = self._compute_oi_buildup(chain_rows)

        top_call_strikes = sorted(call_oi_by_strike, key=lambda item: item[1], reverse=True)[:5]
        top_put_strikes = sorted(put_oi_by_strike, key=lambda item: item[1], reverse=True)[:5]

        return {
            "pcr": pcr,
            "max_pain": max_pain,
            "total_call_oi": int(total_call_oi),
            "total_put_oi": int(total_put_oi),
            "oi_buildup": oi_buildup,
            "top_call_oi_strikes": [
                {"strike_price": strike, "oi": int(oi)}
                for strike, oi in top_call_strikes
            ],
            "top_put_oi_strikes": [
                {"strike_price": strike, "oi": int(oi)}
                for strike, oi in top_put_strikes
            ],
        }

    @staticmethod
    def _compute_max_pain(chain_rows: list[dict[str, Any]]) -> dict[str, Any]:
        strikes = sorted({float(row["strike_price"]) for row in chain_rows})
        if not strikes:
            return {"strike_price": None, "total_pain": None}

        pain_values: list[tuple[float, float]] = []
        for settlement_strike in strikes:
            total_pain = 0.0
            for row in chain_rows:
                strike = float(row["strike_price"])
                call_oi = float((row.get("CE") or {}).get("oi") or 0.0)
                put_oi = float((row.get("PE") or {}).get("oi") or 0.0)

                total_pain += max(0.0, settlement_strike - strike) * call_oi
                total_pain += max(0.0, strike - settlement_strike) * put_oi

            pain_values.append((settlement_strike, total_pain))

        max_pain_strike, min_total_pain = min(pain_values, key=lambda item: item[1])
        return {
            "strike_price": max_pain_strike,
            "total_pain": round(min_total_pain, 2),
        }

    def _compute_oi_buildup(self, chain_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
        summary = {
            "call": {
                "long_buildup": 0,
                "short_buildup": 0,
                "short_covering": 0,
                "long_unwinding": 0,
                "neutral": 0,
            },
            "put": {
                "long_buildup": 0,
                "short_buildup": 0,
                "short_covering": 0,
                "long_unwinding": 0,
                "neutral": 0,
            },
        }

        for row in chain_rows:
            for leg_name, side in (("CE", "call"), ("PE", "put")):
                leg = row.get(leg_name)
                if not leg:
                    continue
                bucket = self._classify_oi_signal(leg.get("oi_change"), leg.get("change"))
                summary[side][bucket] += 1

        return summary

    @staticmethod
    def _classify_oi_signal(oi_change: Any, premium_change: Any) -> str:
        oi = NSEMarketDataService._to_float(oi_change)
        price_delta = NSEMarketDataService._to_float(premium_change)
        if oi is None or price_delta is None or oi == 0 or price_delta == 0:
            return "neutral"

        if oi > 0 and price_delta > 0:
            return "long_buildup"
        if oi > 0 and price_delta < 0:
            return "short_buildup"
        if oi < 0 and price_delta > 0:
            return "short_covering"
        if oi < 0 and price_delta < 0:
            return "long_unwinding"
        return "neutral"

    @staticmethod
    def _looks_like_missing_symbol(message: str) -> bool:
        normalized = message.lower()
        tokens = (
            "invalid",
            "not found",
            "does not exist",
            "symbol not",
            "not traded",
            "valid symbol",
        )
        return any(token in normalized for token in tokens)
