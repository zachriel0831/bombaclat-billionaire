"""SEC EDGAR filings source.

Polls the EDGAR submissions API for tracked tickers and emits one
``NewsItem`` per recent filing with form type, accession number, and
filing URL surfaced to the analysis pipeline."""

from __future__ import annotations

import logging
import re
from typing import Any

from news_collector.http_client import http_get_json_with_headers
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import parse_datetime, sort_timestamp, stable_id


logger = logging.getLogger(__name__)


def _normalize_ticker(raw: str) -> str | None:
    """正規化 normalize ticker 對應的資料或結果。"""
    text = (raw or "").strip().upper()
    if not text:
        return None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", text):
        return None
    return text


class SecFilingsSource(NewsSource):
    """封裝 Sec Filings Source 相關資料與行為。"""
    name = "sec_filings"
    ticker_map_url = "https://www.sec.gov/files/company_tickers.json"
    submissions_url_template = "https://data.sec.gov/submissions/CIK{cik}.json"

    def __init__(
        self,
        user_agent: str,
        tracked_tickers: list[str],
        allowed_forms: list[str],
        timeout_seconds: int = 15,
        max_filings_per_company: int = 5,
    ) -> None:
        """初始化物件狀態與必要依賴。"""
        self._user_agent = user_agent.strip()
        self._tracked_tickers = tracked_tickers
        self._allowed_forms = {form.strip().upper() for form in allowed_forms if form.strip()}
        self._timeout_seconds = timeout_seconds
        self._max_filings_per_company = max(1, int(max_filings_per_company))

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        """執行 fetch 方法的主要邏輯。"""
        if not self._user_agent:
            raise ValueError("SEC_USER_AGENT is required for SEC EDGAR access")

        ticker_map = self._load_ticker_map()
        items: list[NewsItem] = []
        for raw_ticker in self._tracked_tickers:
            ticker = _normalize_ticker(raw_ticker)
            if not ticker:
                logger.warning("SEC skip invalid ticker=%s", raw_ticker)
                continue

            company = ticker_map.get(ticker)
            if not company:
                logger.warning("SEC ticker not found in official mapping ticker=%s", ticker)
                continue

            items.extend(
                self._fetch_company_filings(
                    ticker=ticker,
                    cik=str(company["cik"]).zfill(10),
                    company_title=str(company["title"]),
                )
            )

        deduped = self._dedupe(items)
        deduped.sort(key=lambda x: sort_timestamp(x.published_at), reverse=True)
        return deduped[: max(int(limit), 1)]

    def _load_ticker_map(self) -> dict[str, dict[str, str]]:
        """載入 load ticker map 對應的資料或結果。"""
        payload = http_get_json_with_headers(
            self.ticker_map_url,
            timeout=self._timeout_seconds,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        result: dict[str, dict[str, str]] = {}
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            ticker = _normalize_ticker(str(value.get("ticker") or ""))
            cik = str(value.get("cik_str") or "").strip()
            title = str(value.get("title") or "").strip()
            if ticker and cik and title:
                result[ticker] = {"cik": cik, "title": title}
        return result

    def _fetch_company_filings(self, ticker: str, cik: str, company_title: str) -> list[NewsItem]:
        """抓取 fetch company filings 對應的資料或結果。"""
        payload = http_get_json_with_headers(
            self.submissions_url_template.format(cik=cik),
            timeout=self._timeout_seconds,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        recent = payload.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return []

        total_rows = len(recent.get("form", [])) if isinstance(recent.get("form"), list) else 0
        if total_rows <= 0:
            return []

        items: list[NewsItem] = []
        for idx in range(total_rows):
            form = str(self._col(recent, "form", idx) or "").strip().upper()
            if not form or (self._allowed_forms and form not in self._allowed_forms):
                continue

            accession = str(self._col(recent, "accessionNumber", idx) or "").strip()
            filing_date = str(self._col(recent, "filingDate", idx) or "").strip()
            acceptance_time = str(self._col(recent, "acceptanceDateTime", idx) or "").strip()
            description = str(self._col(recent, "primaryDocDescription", idx) or "").strip()
            primary_document = str(self._col(recent, "primaryDocument", idx) or "").strip()
            published_at = parse_datetime(acceptance_time or filing_date)
            title = f"{ticker} filed {form}"
            if description and description.upper() != form:
                title = f"{title}: {description}"

            url = self._build_filing_index_url(cik=cik, accession=accession)
            summary_parts = [company_title, f"filed {form}"]
            if filing_date:
                summary_parts.append(f"on {filing_date}")
            if description and description.upper() != form:
                summary_parts.append(f"({description})")
            if primary_document:
                summary_parts.append(f"doc={primary_document}")

            items.append(
                NewsItem(
                    id=stable_id("sec", ticker, accession, form),
                    source=f"sec:{ticker}",
                    title=title,
                    url=url,
                    published_at=published_at,
                    summary=" ".join(summary_parts),
                    tags=sorted({"sec", f"ticker:{ticker}", f"form:{form.lower()}"}),
                    raw={
                        "ticker": ticker,
                        "company_title": company_title,
                        "cik": cik,
                        "form": form,
                        "filing_date": filing_date,
                        "acceptance_time": acceptance_time,
                        "accession_number": accession,
                        "primary_document": primary_document,
                        "primary_document_description": description,
                    },
                )
            )

            if len(items) >= self._max_filings_per_company:
                break

        return items

    @staticmethod
    def _col(columns: dict[str, Any], key: str, idx: int) -> Any:
        """執行 col 方法的主要邏輯。"""
        values = columns.get(key)
        if not isinstance(values, list):
            return None
        if idx < 0 or idx >= len(values):
            return None
        return values[idx]

    @staticmethod
    def _build_filing_index_url(cik: str, accession: str) -> str:
        """建立 build filing index url 對應的資料或結果。"""
        cik_no_leading = str(int(str(cik or "0")))
        accession_clean = accession.replace("-", "").strip()
        if not accession_clean:
            return "https://www.sec.gov/search-filings"
        return f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading}/{accession_clean}/{accession}-index.htm"

    @staticmethod
    def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
        """依穩定鍵移除重複資料。"""
        seen: set[str] = set()
        result: list[NewsItem] = []
        for item in items:
            key = item.url or item.id
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
