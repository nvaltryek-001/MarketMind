"""
Filing Anomaly Detector.

Parses BSE XML announcement filings and detects high-risk signals that can
be overlooked in routine headline tracking.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any

import httpx
import numpy as np
import pandas as pd


class FilingAnomalyDetector:
    """Detect filing anomalies from recent BSE announcement filings."""

    BSE_XML_ENDPOINT = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

    def __init__(
        self,
        endpoint: str | None = None,
        timeout_seconds: float = 20.0,
        max_pages: int = 15,
        related_party_threshold_inr: float = 100_000_000.0,
    ) -> None:
        self.endpoint = endpoint or self.BSE_XML_ENDPOINT
        self.timeout_seconds = float(timeout_seconds)
        self.max_pages = max(1, int(max_pages))
        self.related_party_threshold_inr = float(related_party_threshold_inr)

        self._headers = {
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "accept": "application/xml, text/xml, */*",
            "x-requested-with": "XMLHttpRequest",
        }

        self._filings_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self._risk_cache: dict[tuple[str, int], dict[str, Any]] = {}

        self._auditor_keywords = (
            "resignation of auditor",
            "appointment of statutory auditor",
        )
        self._going_concern_keywords = (
            "going concern",
            "material uncertainty",
        )
        self._pledge_keywords = (
            "creation of pledge",
            "encumbrance",
        )
        self._registered_address_keywords = (
            "registered address",
            "registered office",
            "change in registered office",
            "shift in registered office",
            "change of registered office",
        )

    def fetch_recent_filings(self, symbol: str, days: int = 90) -> list[dict[str, Any]]:
        """Fetch and parse recent BSE announcement filings for a symbol."""
        clean_symbol = self._clean_symbol(symbol)
        lookback_days = max(int(days), 1)
        cache_key = (clean_symbol, lookback_days)

        if cache_key in self._filings_cache:
            return list(self._filings_cache[cache_key])

        cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=lookback_days)
        parsed_filings: list[dict[str, Any]] = []

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=self._headers,
        ) as client:
            for page_no in range(1, self.max_pages + 1):
                xml_payload = self._fetch_filings_page(client=client, page_no=page_no, symbol=clean_symbol)
                if not xml_payload:
                    break

                rows = self._extract_records_from_xml(xml_payload)
                if not rows:
                    break

                page_dates: list[pd.Timestamp] = []
                for row in rows:
                    filing = self._standardize_filing_row(row)
                    filing_date = self._parse_date(filing.get("date"))

                    if filing_date is not None:
                        page_dates.append(filing_date)

                    if not self._matches_symbol(clean_symbol, row=row, filing=filing):
                        continue

                    if filing_date is not None and filing_date < cutoff:
                        continue

                    filing["symbol"] = clean_symbol
                    parsed_filings.append(filing)

                # BSE pages are usually reverse-chronological; once a page is fully
                # older than lookback, subsequent pages are likely older too.
                if page_dates and max(page_dates) < cutoff:
                    break

        unique = self._deduplicate_filings(parsed_filings)
        unique.sort(
            key=lambda item: pd.to_datetime(item.get("date"), errors="coerce"),
            reverse=True,
        )

        self._filings_cache[cache_key] = unique
        return list(unique)

    def parse_filing(self, xml_content: str) -> dict[str, Any]:
        """
        Parse a filing XML payload and extract normalized core fields.

        Returns a dict with keys: filing_type, date, headline, content_text.
        """
        rows = self._extract_records_from_xml(xml_content)
        if not rows:
            return {
                "filing_type": "unknown",
                "date": None,
                "headline": "",
                "content_text": "",
            }

        return self._standardize_filing_row(rows[0])

    def detect_red_flags(self, filings: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect filing red flags from parsed filing dictionaries."""
        flags: list[dict[str, Any]] = []

        for filing in filings:
            filing_type = str(filing.get("filing_type") or "unknown")
            headline = str(filing.get("headline") or "").strip()
            content_text = str(filing.get("content_text") or "").strip()
            filing_date = filing.get("date")

            haystack = f"{filing_type} {headline} {content_text}".lower()

            if self._contains_any(haystack, self._auditor_keywords):
                flags.append(
                    self._build_flag(
                        flag_type="auditor_change_or_resignation",
                        flag_label="Auditor resignation/change",
                        date=filing_date,
                        headline=headline,
                        severity=1.0,
                        evidence=self._first_match(haystack, self._auditor_keywords),
                    )
                )

            if self._contains_any(haystack, self._going_concern_keywords):
                severity = 1.25 if "material uncertainty" in haystack else 1.1
                flags.append(
                    self._build_flag(
                        flag_type="going_concern_qualification",
                        flag_label="Going concern qualification",
                        date=filing_date,
                        headline=headline,
                        severity=severity,
                        evidence=self._first_match(haystack, self._going_concern_keywords),
                    )
                )

            if self._related_party_above_threshold(haystack):
                amount = self._extract_max_inr_amount(haystack)
                evidence = (
                    f"related party transaction with estimated amount Rs.{amount:,.0f}"
                    if amount is not None
                    else "related party transaction disclosure marked as material"
                )
                flags.append(
                    self._build_flag(
                        flag_type="related_party_transaction_above_threshold",
                        flag_label="Related party transaction above threshold",
                        date=filing_date,
                        headline=headline,
                        severity=1.1,
                        evidence=evidence,
                    )
                )

            if self._contains_any(haystack, self._pledge_keywords):
                flags.append(
                    self._build_flag(
                        flag_type="promoter_pledge_creation",
                        flag_label="Promoter pledge creation",
                        date=filing_date,
                        headline=headline,
                        severity=1.0,
                        evidence=self._first_match(haystack, self._pledge_keywords),
                    )
                )

            if self._is_registered_address_change(haystack):
                flags.append(
                    self._build_flag(
                        flag_type="registered_address_change",
                        flag_label="Sudden change in registered address",
                        date=filing_date,
                        headline=headline,
                        severity=0.85,
                        evidence="registered office/address change language found",
                    )
                )

        counts: dict[str, int] = {}
        for flag in flags:
            flag_type = str(flag["flag_type"])
            counts[flag_type] = counts.get(flag_type, 0) + 1

        latest_flag_date = self._latest_flag_date(flags)
        return {
            "total_flags": len(flags),
            "flags": flags,
            "flags_by_type": counts,
            "latest_flag_date": latest_flag_date,
        }

    def score_risk(self, symbol: str) -> dict[str, Any]:
        """
        Score filing risk for a symbol on a 0-100 scale.

        Returns a structured dict containing:
        - risk_score
        - flags_found
        - latest_flag_date
        """
        clean_symbol = self._clean_symbol(symbol)
        cache_key = (clean_symbol, 90)
        if cache_key in self._risk_cache:
            return dict(self._risk_cache[cache_key])

        filings = self.fetch_recent_filings(clean_symbol, days=90)
        red_flag_result = self.detect_red_flags(filings)
        flags = red_flag_result["flags"]

        weights = {
            "auditor_change_or_resignation": 24.0,
            "going_concern_qualification": 28.0,
            "related_party_transaction_above_threshold": 20.0,
            "promoter_pledge_creation": 22.0,
            "registered_address_change": 14.0,
        }

        today = pd.Timestamp.today().normalize()
        risk_score = 0.0
        labels: set[str] = set()

        for flag in flags:
            flag_type = str(flag.get("flag_type") or "")
            labels.add(str(flag.get("flag_label") or flag_type))

            weight = weights.get(flag_type, 10.0)
            severity = float(flag.get("severity") or 1.0)

            flag_date = self._parse_date(flag.get("date"))
            if flag_date is None:
                recency_multiplier = 0.6
            else:
                age_days = max((today - flag_date).days, 0)
                if age_days <= 30:
                    recency_multiplier = 1.0
                elif age_days <= 60:
                    recency_multiplier = 0.75
                else:
                    recency_multiplier = 0.55

            risk_score += weight * severity * recency_multiplier

        risk_score_int = int(np.clip(round(risk_score), 0, 100))

        payload = {
            "symbol": clean_symbol,
            "risk_score": risk_score_int,
            "flags_found": sorted(labels),
            "latest_flag_date": red_flag_result.get("latest_flag_date"),
            "total_flags": red_flag_result.get("total_flags", 0),
            "flag_details": flags,
        }

        self._risk_cache[cache_key] = payload
        return dict(payload)

    def _fetch_filings_page(self, client: httpx.Client, page_no: int, symbol: str) -> str:
        params_candidates = [
            {
                "pageno": page_no,
                "strSearch": symbol,
            },
            {
                "pageno": page_no,
            },
        ]

        for params in params_candidates:
            try:
                response = client.get(self.endpoint, params=params)
                response.raise_for_status()
                content = response.text.strip()
                if content:
                    return content
            except httpx.HTTPError:
                continue

        return ""

    def _standardize_filing_row(self, row: dict[str, Any]) -> dict[str, Any]:
        filing_type = self._extract_with_candidates(
            row,
            [
                "filing_type",
                "announcement_type",
                "category_name",
                "category",
                "sub_category",
                "newssub",
                "subject",
            ],
        )
        headline = self._extract_with_candidates(
            row,
            [
                "headline",
                "title",
                "subject",
                "news_subject",
                "head_line",
                "description",
            ],
        )
        content_text = self._extract_with_candidates(
            row,
            [
                "content_text",
                "details",
                "detail",
                "description",
                "message",
                "announcement",
                "particulars",
                "text",
                "brief",
            ],
        )
        date_value = self._extract_date_field(row)

        return {
            "filing_type": filing_type or "unknown",
            "date": date_value,
            "headline": (headline or "").strip(),
            "content_text": (content_text or "").strip(),
        }

    def _extract_date_field(self, row: dict[str, Any]) -> str | None:
        best_key = None
        for key in row:
            key_norm = self._normalized_name(key)
            if "date" in key_norm or key_norm.endswith("dt"):
                best_key = key
                break

        if best_key is None:
            return None

        parsed = self._parse_date(row.get(best_key))
        if parsed is None:
            return None
        return parsed.strftime("%Y-%m-%d")

    def _matches_symbol(self, symbol: str, row: dict[str, Any], filing: dict[str, Any]) -> bool:
        direct_keys = [
            "symbol",
            "scrip",
            "scripcode",
            "scrip_cd",
            "security",
            "securitycode",
            "company_name",
            "company",
        ]

        symbol_lower = symbol.lower()
        for key in direct_keys:
            value = self._extract_with_candidates(row, [key])
            if value and symbol_lower == value.strip().lower():
                return True

        # Fallback text match across relevant fields.
        haystack = (
            f"{filing.get('headline', '')} "
            f"{filing.get('content_text', '')} "
            f"{filing.get('filing_type', '')}"
        ).lower()
        return re.search(rf"\b{re.escape(symbol_lower)}\b", haystack) is not None

    def _extract_records_from_xml(self, xml_content: str) -> list[dict[str, str]]:
        text = (xml_content or "").strip()
        if not text:
            return []

        records: list[dict[str, str]] = []

        sanitized = self._sanitize_xml(text)
        try:
            root = ET.fromstring(sanitized)
            records = self._extract_records_from_element_tree(root)
        except ET.ParseError:
            records = self._extract_records_with_regex(sanitized)

        if not records:
            return []

        max_width = max(len(record) for record in records)
        return [record for record in records if len(record) == max_width]

    def _extract_records_from_element_tree(self, root: ET.Element) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []

        preferred_tags = {"table", "row", "record", "item"}
        preferred_nodes = [
            node for node in root.iter()
            if self._normalized_name(self._strip_xml_ns(node.tag)) in preferred_tags
        ]

        candidate_nodes = preferred_nodes if preferred_nodes else list(root.iter())

        for node in candidate_nodes:
            children = [child for child in list(node) if isinstance(child.tag, str)]
            if not children:
                continue
            if any(list(child) for child in children):
                continue

            row: dict[str, str] = {}
            for child in children:
                key = self._to_snake_case(self._strip_xml_ns(child.tag))
                value = self._clean_text(child.text)
                if key and value:
                    row[key] = value

            if row:
                records.append(row)

        return records

    def _extract_records_with_regex(self, xml_text: str) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        tag_pattern = r"(?:Table|table|Row|row|Record|record|Item|item)"
        block_pattern = re.compile(rf"<({tag_pattern})\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
        field_pattern = re.compile(r"<([A-Za-z0-9_:\-]+)\b[^>]*>(.*?)</\1>", re.DOTALL)

        for _, body in block_pattern.findall(xml_text):
            row: dict[str, str] = {}
            for raw_key, raw_value in field_pattern.findall(body):
                key = self._to_snake_case(self._strip_xml_ns(raw_key))
                value = self._clean_text(re.sub(r"<[^>]+>", " ", raw_value))
                if key and value:
                    row[key] = value

            if row:
                records.append(row)

        return records

    def _sanitize_xml(self, xml_text: str) -> str:
        text = xml_text.lstrip("\ufeff")
        # Escape bare ampersands that can break XML parsing.
        return re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
            "&amp;",
            text,
        )

    def _deduplicate_filings(self, filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str | None, str, str]] = set()

        for filing in filings:
            key = (
                filing.get("date"),
                str(filing.get("headline") or "").strip().lower(),
                str(filing.get("filing_type") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(filing)

        return out

    def _build_flag(
        self,
        flag_type: str,
        flag_label: str,
        date: str | None,
        headline: str,
        severity: float,
        evidence: str,
    ) -> dict[str, Any]:
        return {
            "flag_type": flag_type,
            "flag_label": flag_label,
            "date": date,
            "headline": headline,
            "severity": round(float(severity), 3),
            "evidence": evidence,
        }

    def _related_party_above_threshold(self, text: str) -> bool:
        related_party_terms = (
            "related party transaction",
            "related party transactions",
            "rpt",
        )

        if not self._contains_any(text, related_party_terms):
            return False

        amount = self._extract_max_inr_amount(text)
        if amount is not None:
            return amount >= self.related_party_threshold_inr

        material_terms = ("material", "materiality", "approval threshold")
        return self._contains_any(text, material_terms)

    def _extract_max_inr_amount(self, text: str) -> float | None:
        pattern = re.compile(
            r"(?:rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d+)?)\s*(crore|cr|lakh|lakhs|million|billion)?",
            re.IGNORECASE,
        )

        max_amount: float | None = None
        for raw_value, unit in pattern.findall(text):
            try:
                numeric = float(raw_value.replace(",", ""))
            except ValueError:
                continue

            unit_norm = unit.lower() if unit else ""
            multiplier = 1.0
            if unit_norm in {"crore", "cr"}:
                multiplier = 10_000_000.0
            elif unit_norm in {"lakh", "lakhs"}:
                multiplier = 100_000.0
            elif unit_norm == "million":
                multiplier = 1_000_000.0
            elif unit_norm == "billion":
                multiplier = 1_000_000_000.0

            amount = numeric * multiplier
            if max_amount is None or amount > max_amount:
                max_amount = amount

        return max_amount

    def _is_registered_address_change(self, text: str) -> bool:
        if not self._contains_any(text, self._registered_address_keywords):
            return False

        change_terms = (
            "change",
            "shift",
            "relocation",
            "moved",
            "transfer",
        )
        return self._contains_any(text, change_terms)

    def _latest_flag_date(self, flags: list[dict[str, Any]]) -> str | None:
        parsed_dates = [self._parse_date(item.get("date")) for item in flags]
        parsed_dates = [dt for dt in parsed_dates if dt is not None]
        if not parsed_dates:
            return None
        latest = max(parsed_dates)
        return latest.strftime("%Y-%m-%d")

    def _extract_with_candidates(self, row: dict[str, Any], candidates: list[str]) -> str:
        for candidate in candidates:
            if candidate in row and row[candidate] not in (None, ""):
                return self._clean_text(str(row[candidate]))

        normalized_candidates = {self._normalized_name(name) for name in candidates}
        for key, value in row.items():
            if self._normalized_name(key) in normalized_candidates and value not in (None, ""):
                return self._clean_text(str(value))

        return ""

    @staticmethod
    def _clean_text(text: str | None) -> str:
        if text is None:
            return ""
        unescaped = unescape(str(text))
        return " ".join(unescaped.split())

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def _first_match(text: str, keywords: tuple[str, ...]) -> str:
        lowered = text.lower()
        for keyword in keywords:
            if keyword in lowered:
                return keyword
        return ""

    @staticmethod
    def _to_snake_case(name: str) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_")
        cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", cleaned)
        return cleaned.lower()

    @staticmethod
    def _normalized_name(name: str) -> str:
        return "".join(ch for ch in str(name).lower() if ch.isalnum())

    @staticmethod
    def _strip_xml_ns(tag: str) -> str:
        return str(tag).split("}")[-1]

    @staticmethod
    def _parse_date(value: Any) -> pd.Timestamp | None:
        if value is None or value == "":
            return None

        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed).normalize()

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        return symbol.strip().upper()