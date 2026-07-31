from __future__ import annotations

import re
from typing import Any

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from config import BSE_XML_ENDPOINT, REQUEST_TIMEOUT_SECONDS


def _to_snake_case(name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", cleaned)
    return cleaned.lower()


def _extract_record(element: Any) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for child in element.find_all(recursive=False):
        if not getattr(child, "name", None):
            continue
        record[_to_snake_case(child.name)] = child.get_text(strip=True)
    return record


class BSEFilingsParser:
    def __init__(self, endpoint: str = BSE_XML_ENDPOINT) -> None:
        self.endpoint = endpoint

    async def fetch_xml(self, params: dict[str, Any] | None = None) -> str:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            return response.text

    @staticmethod
    def parse_xml(xml_text: str) -> pd.DataFrame:
        soup = BeautifulSoup(xml_text, "xml")
        candidate_records: list[dict[str, Any]] = []

        preferred_tags = ("Table", "table", "Row", "row", "Record", "record", "item", "Item")
        for tag in preferred_tags:
            rows = [_extract_record(node) for node in soup.find_all(tag)]
            rows = [row for row in rows if row]
            if rows:
                candidate_records = rows
                break

        if not candidate_records:
            for node in soup.find_all():
                children = [child for child in node.find_all(recursive=False) if getattr(child, "name", None)]
                if not children:
                    continue
                if all(not child.find(recursive=False) for child in children):
                    record = {
                        _to_snake_case(child.name): child.get_text(strip=True)
                        for child in children
                    }
                    if record:
                        candidate_records.append(record)

        if not candidate_records:
            return pd.DataFrame()

        max_width = max(len(record) for record in candidate_records)
        candidate_records = [record for record in candidate_records if len(record) == max_width]

        frame = pd.DataFrame(candidate_records)
        for column in frame.columns:
            if "date" in column:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
                continue
            as_numeric = pd.to_numeric(frame[column], errors="coerce")
            if as_numeric.notna().sum() >= max(1, int(0.7 * len(frame))):
                frame[column] = as_numeric

        return frame

    async def fetch_and_parse(self, params: dict[str, Any] | None = None) -> pd.DataFrame:
        xml_text = await self.fetch_xml(params=params)
        return self.parse_xml(xml_text)
