from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _to_snake_case(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", cleaned)
    return cleaned.lower()


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized.columns = [_to_snake_case(str(col)) for col in normalized.columns]
    return normalized


def parse_quote_equity(raw: dict[str, Any]) -> pd.DataFrame:
    info = raw.get("info", {})
    metadata = raw.get("metadata", {})
    price_info = raw.get("priceInfo", {})
    security_info = raw.get("securityInfo", {})

    intra_day = price_info.get("intraDayHighLow", {})
    week_range = price_info.get("weekHighLow", {})

    row = {
        "symbol": info.get("symbol"),
        "company_name": info.get("companyName"),
        "industry": info.get("industry"),
        "isin": info.get("isin"),
        "listing_date": security_info.get("listingDate"),
        "last_price": price_info.get("lastPrice"),
        "previous_close": price_info.get("previousClose"),
        "open": price_info.get("open"),
        "close": price_info.get("close"),
        "intra_day_low": intra_day.get("min"),
        "intra_day_high": intra_day.get("max"),
        "week_52_low": week_range.get("min"),
        "week_52_high": week_range.get("max"),
        "last_update_time": metadata.get("lastUpdateTime"),
    }

    frame = pd.DataFrame([row])
    numeric_columns = [
        "last_price",
        "previous_close",
        "open",
        "close",
        "intra_day_low",
        "intra_day_high",
        "week_52_low",
        "week_52_high",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for column in ["listing_date", "last_update_time"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")

    return frame


def parse_option_chain(raw: dict[str, Any]) -> pd.DataFrame:
    records = raw.get("records", {})
    rows: list[dict[str, Any]] = []

    for item in records.get("data", []):
        common = {
            "symbol": records.get("underlying"),
            "expiry_date": item.get("expiryDate"),
            "strike_price": item.get("strikePrice"),
            "snapshot_time": records.get("timestamp"),
        }

        for option_type in ("CE", "PE"):
            leg = item.get(option_type)
            if not leg:
                continue

            rows.append(
                {
                    **common,
                    "option_type": option_type,
                    "open_interest": leg.get("openInterest"),
                    "change_in_open_interest": leg.get("changeinOpenInterest"),
                    "total_traded_volume": leg.get("totalTradedVolume"),
                    "implied_volatility": leg.get("impliedVolatility"),
                    "last_price": leg.get("lastPrice"),
                    "change": leg.get("change"),
                    "bid_quantity": leg.get("bidQty"),
                    "bid_price": leg.get("bidprice"),
                    "ask_quantity": leg.get("askQty"),
                    "ask_price": leg.get("askPrice"),
                    "underlying_value": leg.get("underlyingValue"),
                }
            )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    numeric_columns = [
        "strike_price",
        "open_interest",
        "change_in_open_interest",
        "total_traded_volume",
        "implied_volatility",
        "last_price",
        "change",
        "bid_quantity",
        "bid_price",
        "ask_quantity",
        "ask_price",
        "underlying_value",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["expiry_date"] = pd.to_datetime(frame["expiry_date"], errors="coerce")
    frame["snapshot_time"] = pd.to_datetime(frame["snapshot_time"], errors="coerce")
    return frame


def parse_corporate_actions(raw: dict[str, Any] | list[dict[str, Any]]) -> pd.DataFrame:
    payload = raw.get("data", []) if isinstance(raw, dict) else raw
    frame = pd.json_normalize(payload)
    if frame.empty:
        return frame

    frame = _normalize_columns(frame)
    for column in frame.columns:
        if "date" in column:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")

    return frame
