from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from data.bse_parser import BSEFilingsParser
from data.fetcher import NSEFetcher
from data.parser import parse_corporate_actions, parse_option_chain, parse_quote_equity


def dataframe_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.nse_fetcher = NSEFetcher()
    app.state.bse_parser = BSEFilingsParser()
    yield
    await app.state.nse_fetcher.close()


app = FastAPI(
    title="NSE Intelligence API",
    description="FastAPI backend for NSE and BSE market intelligence.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/nse/quote/{symbol}")
async def nse_quote(symbol: str) -> dict[str, Any]:
    try:
        raw = await app.state.nse_fetcher.fetch_quote_equity(symbol=symbol)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"NSE quote fetch failed: {exc}") from exc

    normalized = dataframe_to_records(parse_quote_equity(raw))
    return {"symbol": symbol.upper(), "raw": raw, "normalized": normalized}


@app.get("/nse/options/{symbol}")
async def nse_options(symbol: str) -> dict[str, Any]:
    try:
        raw = await app.state.nse_fetcher.fetch_option_chain(symbol=symbol)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"NSE option chain fetch failed: {exc}") from exc

    normalized = dataframe_to_records(parse_option_chain(raw))
    return {"symbol": symbol.upper(), "raw": raw, "normalized": normalized}


@app.get("/nse/corporate-actions")
async def nse_corporate_actions(index: str = Query(default="equities")) -> dict[str, Any]:
    try:
        raw = await app.state.nse_fetcher.fetch_corporate_actions(index=index)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"NSE corporate actions fetch failed: {exc}") from exc

    normalized = dataframe_to_records(parse_corporate_actions(raw))
    return {"index": index, "raw": raw, "normalized": normalized}


@app.get("/bse/filings")
async def bse_filings(
    page_no: int = Query(default=1, ge=1, alias="pageno"),
    category: str | None = Query(default=None, alias="strCat"),
    sub_category: str | None = Query(default=None, alias="strPrevSubCategory"),
) -> dict[str, Any]:
    params: dict[str, Any] = {"pageno": page_no}
    if category:
        params["strCat"] = category
    if sub_category:
        params["strPrevSubCategory"] = sub_category

    try:
        xml_text = await app.state.bse_parser.fetch_xml(params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"BSE XML fetch failed: {exc}") from exc

    normalized = dataframe_to_records(app.state.bse_parser.parse_xml(xml_text))
    return {
        "endpoint": app.state.bse_parser.endpoint,
        "params": params,
        "normalized": normalized,
    }
