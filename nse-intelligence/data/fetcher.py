from __future__ import annotations

import asyncio
import random
import time
from datetime import date, timedelta
from typing import Any

import httpx
import yfinance as yf

from config import DEFAULT_HEADERS, MIN_REQUEST_INTERVAL_SECONDS, NSE_BASE_URL, REQUEST_TIMEOUT_SECONDS


class NSEFetcher:
    _RETRIABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    _SESSION_BOOTSTRAP_URL = "https://www.nseindia.com"
    _SESSION_BOOTSTRAP_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    _BSE_FII_DII_URL = "https://api.bseindia.com/BseIndiaAPI/api/FiiDii/w"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 4,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=NSE_BASE_URL,
            headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        self._max_retries = max(1, max_retries)
        self._retry_backoff_seconds = max(0.1, retry_backoff_seconds)
        self.session_valid = False
        self._init_lock = asyncio.Lock()
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0

    async def _ensure_session(self, force_refresh: bool = False) -> None:
        if self.session_valid and not force_refresh:
            return

        async with self._init_lock:
            if self.session_valid and not force_refresh:
                return

            if force_refresh:
                self._client.cookies.clear()

            response = await self._client.get(
                self._SESSION_BOOTSTRAP_URL,
                headers=self._SESSION_BOOTSTRAP_HEADERS,
            )
            response.raise_for_status()

            # NSE anti-bot checks are less aggressive when there is a short delay
            # after session bootstrap and before API calls.
            await asyncio.sleep(1.5)
            self.session_valid = True

    async def _throttle(self) -> None:
        async with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_ts
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
            self._last_request_ts = time.monotonic()

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
    def _normalized_key(key: str) -> str:
        return "".join(ch for ch in key.lower() if ch.isalnum())

    @staticmethod
    def _pick_first(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
        lookup = {NSEFetcher._normalized_key(k): v for k, v in row.items()}
        for candidate in candidates:
            value = lookup.get(NSEFetcher._normalized_key(candidate))
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _extract_option_leg(leg: dict[str, Any] | None) -> dict[str, Any] | None:
        if not leg:
            return None

        return {
            "oi": NSEFetcher._to_float(leg.get("openInterest")),
            "oi_change": NSEFetcher._to_float(leg.get("changeinOpenInterest")),
            "iv": NSEFetcher._to_float(leg.get("impliedVolatility")),
            "ltp": NSEFetcher._to_float(leg.get("lastPrice")),
            "volume": NSEFetcher._to_float(leg.get("totalTradedVolume")),
            "change": NSEFetcher._to_float(leg.get("change")),
            "bid_qty": NSEFetcher._to_float(leg.get("bidQty")),
            "bid_price": NSEFetcher._to_float(leg.get("bidprice")),
            "ask_qty": NSEFetcher._to_float(leg.get("askQty")),
            "ask_price": NSEFetcher._to_float(leg.get("askPrice")),
            "raw": leg,
        }

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
                keys = {NSEFetcher._normalized_key(k) for k in row}
                has_period = any(token in keys for token in ("quarter", "qtr", "period", "date", "ason"))
                has_promoter = any("promoter" in token or token == "prandprgrp" for token in keys)
                if has_period:
                    value += 2
                if has_promoter:
                    value += 4
            return value

        return max(candidates, key=score)

    async def _get_json(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        referer_path: str = "/",
    ) -> dict[str, Any]:
        headers = {
            **DEFAULT_HEADERS,
            "accept": "application/json, text/plain, */*",
            "referer": f"{NSE_BASE_URL}{referer_path}",
        }

        async def request_once() -> dict[str, Any]:
            await self._throttle()
            response = await self._client.get(endpoint, params=params, headers=headers)
            if response.status_code in {401, 403}:
                self.session_valid = False
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower() and not response.text.lstrip().startswith(("{", "[")):
                raise ValueError("NSE returned a non-JSON response")

            return response.json()

        for attempt in range(1, self._max_retries + 1):
            try:
                await self._ensure_session()
                try:
                    return await request_once()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in {401, 403}:
                        raise

                    # One forced session refresh + one retry for 401/403 responses.
                    await self._ensure_session(force_refresh=True)
                    return await request_once()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code not in self._RETRIABLE_STATUS_CODES or attempt == self._max_retries:
                    raise
            except (httpx.TimeoutException, httpx.TransportError, ValueError):
                self.session_valid = False
                if attempt == self._max_retries:
                    raise

            # Exponential backoff with jitter to avoid tripping anti-scraping checks.
            backoff = self._retry_backoff_seconds * (2 ** (attempt - 1)) + random.uniform(0.0, 0.35)
            await asyncio.sleep(backoff)

        raise RuntimeError("Failed to fetch NSE data after retries")

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()
        raw = await self._get_json(
            "/api/quote-equity",
            params={"symbol": symbol_upper},
            referer_path=f"/get-quotes/equity?symbol={symbol_upper}",
        )

        price_info = raw.get("priceInfo", {})
        week_range = price_info.get("weekHighLow", {})
        security_wise_dp = raw.get("securityWiseDP", {})

        circuit_lower = (
            price_info.get("lowerCP")
            or price_info.get("lowerCircuitLimit")
            or price_info.get("lowerCircuit")
        )
        circuit_upper = (
            price_info.get("upperCP")
            or price_info.get("upperCircuitLimit")
            or price_info.get("upperCircuit")
        )

        return {
            "symbol": symbol_upper,
            "price": self._to_float(price_info.get("lastPrice")),
            "change": self._to_float(price_info.get("change")),
            "percent_change": self._to_float(price_info.get("pChange")),
            "fifty_two_week_high": self._to_float(week_range.get("max")),
            "fifty_two_week_low": self._to_float(week_range.get("min")),
            "delivery_percent": self._to_float(
                security_wise_dp.get("deliveryToTradedQuantity")
                or security_wise_dp.get("deliveryPercentage")
            ),
            "circuit_limits": {
                "lower": self._to_float(circuit_lower),
                "upper": self._to_float(circuit_upper),
            },
            "last_update": raw.get("metadata", {}).get("lastUpdateTime"),
            "raw": raw,
        }

    async def get_option_chain(self, symbol: str) -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()
        raw = await self._get_json(
            "/api/option-chain-equities",
            params={"symbol": symbol_upper},
            referer_path="/option-chain",
        )

        records = raw.get("records", {})
        chain_rows: list[dict[str, Any]] = []
        for item in records.get("data", []):
            chain_rows.append(
                {
                    "expiry_date": item.get("expiryDate"),
                    "strike_price": self._to_float(item.get("strikePrice")),
                    "CE": self._extract_option_leg(item.get("CE")),
                    "PE": self._extract_option_leg(item.get("PE")),
                }
            )

        return {
            "symbol": symbol_upper,
            "timestamp": records.get("timestamp"),
            "underlying_value": self._to_float(records.get("underlyingValue")),
            "data": chain_rows,
            "raw": raw,
        }

    async def get_shareholding(self, symbol: str) -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()
        raw = await self._get_json(
            "/api/corporate-share-holdings",
            params={"index": "equities", "symbol": symbol_upper},
            referer_path="/companies-listing/corporate-filings-shareholding-pattern",
        )

        rows = self._find_candidate_rows(raw)
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

        for row in rows:
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

            quarter_str = str(quarter).strip()
            if quarter_str in seen_quarters:
                continue
            seen_quarters.add(quarter_str)

            parsed.append(
                {
                    "quarter": quarter_str,
                    "promoter_holding_percent": self._to_float(promoter),
                    "raw": row,
                }
            )
            if len(parsed) == 8:
                break

        return {
            "symbol": symbol_upper,
            "quarters": parsed,
            "raw": raw,
        }

    async def get_corporate_actions(self, symbol: str) -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()
        today = date.today()
        start_date = today - timedelta(days=365 * 3)

        raw = await self._get_json(
            "/api/corporates-corporateActions",
            params={
                "index": "equities",
                "symbol": symbol_upper,
                "from_date": start_date.strftime("%d-%m-%Y"),
                "to_date": today.strftime("%d-%m-%Y"),
            },
            referer_path="/companies-listing/corporate-filings-actions",
        )

        if isinstance(raw, dict):
            payload = raw.get("data", [])
        elif isinstance(raw, list):
            payload = raw
        else:
            payload = []

        categories = {
            "dividend": ("dividend",),
            "bonus": ("bonus",),
            "split": ("split", "stock split"),
            "rights": ("rights", "right issue"),
        }

        filtered_actions: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            descriptor = " ".join(
                str(
                    item.get("purpose")
                    or item.get("subject")
                    or item.get("corpAnnouncement")
                    or item.get("caType")
                    or ""
                ).split()
            ).lower()

            action_type: str | None = None
            for name, tokens in categories.items():
                if any(token in descriptor for token in tokens):
                    action_type = name
                    break
            if action_type is None:
                continue

            filtered_actions.append(
                {
                    "action_type": action_type,
                    "purpose": item.get("purpose") or item.get("subject"),
                    "announcement_date": self._pick_first(
                        item,
                        (
                            "announcementDate",
                            "an_dt",
                            "boardMeetingDate",
                            "broadcastDate",
                            "date",
                        ),
                    ),
                    "ex_date": self._pick_first(item, ("exDate", "ex_date", "exDt")),
                    "record_date": self._pick_first(item, ("recordDate", "record_date", "recDate")),
                    "details": item,
                }
            )

        return {
            "symbol": symbol_upper,
            "from_date": start_date.isoformat(),
            "to_date": today.isoformat(),
            "actions": filtered_actions,
            "raw": raw,
        }

    async def fetch_quote_equity(self, symbol: str) -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()
        return await self._get_json(
            "/api/quote-equity",
            params={"symbol": symbol_upper},
            referer_path=f"/get-quotes/equity?symbol={symbol_upper}",
        )

    async def fetch_option_chain(self, symbol: str) -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()
        return await self._get_json(
            "/api/option-chain-equities",
            params={"symbol": symbol_upper},
            referer_path="/option-chain",
        )

    async def fetch_corporate_actions(self, index: str = "equities") -> dict[str, Any]:
        return await self._get_json(
            "/api/corporates-corporateActions",
            params={"index": index},
            referer_path="/companies-listing/corporate-filings-actions",
        )

    async def get_historical_ohlcv(self, symbol: str, period: str = "6mo") -> dict[str, Any]:
        symbol_upper = symbol.upper().strip()

        def _download_history() -> list[dict[str, Any]]:
            ticker = yf.Ticker(f"{symbol_upper}.NS")
            hist = ticker.history(period=period)
            if hist.empty:
                return []

            rows: list[dict[str, Any]] = []
            for timestamp, row in hist.iterrows():
                rows.append(
                    {
                        "date": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                        "open": self._to_float(row.get("Open")),
                        "high": self._to_float(row.get("High")),
                        "low": self._to_float(row.get("Low")),
                        "close": self._to_float(row.get("Close")),
                        "volume": self._to_float(row.get("Volume")),
                    }
                )
            return rows

        data = await asyncio.to_thread(_download_history)
        return {
            "symbol": symbol_upper,
            "period": period,
            "source": "yfinance",
            "data": data,
        }

    async def fetch_historical_ohlcv(self, symbol: str, period: str = "6mo") -> dict[str, Any]:
        return await self.get_historical_ohlcv(symbol=symbol, period=period)

    async def get_macro_flows(self) -> dict[str, Any]:
        try:
            await self._throttle()
            response = await self._client.get(
                self._BSE_FII_DII_URL,
                headers={
                    **DEFAULT_HEADERS,
                    "accept": "application/json, text/plain, */*",
                    "referer": "https://www.bseindia.com/",
                },
            )
            response.raise_for_status()
            return {
                "status": "ok",
                "source": "bse",
                "data": response.json(),
            }
        except (httpx.HTTPError, ValueError):
            def _derive_from_index() -> dict[str, Any]:
                nifty = yf.download("^NSEI", period="5d", interval="1d", progress=False)
                if nifty.empty:
                    five_day_return = 0.0
                else:
                    close_series = nifty["Close"]
                    if hasattr(close_series, "columns"):
                        close_series = close_series.iloc[:, 0]

                    if hasattr(close_series, "iloc") and len(close_series) >= 2:
                        start = float(close_series.iloc[0])
                        end = float(close_series.iloc[-1])
                        five_day_return = ((end - start) / start * 100) if start else 0.0
                    else:
                        five_day_return = 0.0

                return {
                    "fii_net": None,
                    "dii_net": None,
                    "fii_5d_trend": "unknown",
                    "dii_5d_trend": "unknown",
                    "source": "derived_from_index",
                    "nifty_5d_return": round(five_day_return, 2),
                    "macro_signal": (
                        "bullish"
                        if five_day_return > 1
                        else "bearish"
                        if five_day_return < -1
                        else "neutral"
                    ),
                }

            derived_payload = await asyncio.to_thread(_derive_from_index)
            return {
                "status": "ok",
                "source": "derived_from_index",
                "data": derived_payload,
            }

    async def fetch_macro_flows(self) -> dict[str, Any]:
        return await self.get_macro_flows()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "NSEFetcher":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
