from __future__ import annotations

import html
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from core.config import Settings


CROSSREF_API_URL = "https://api.crossref.org/works"
RETRY_STATUS_CODES = {429, 503}


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _normalize_text(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        value = " ".join(str(part) for part in value if part)
    elif not isinstance(value, str):
        value = str(value)
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _first_text(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = _normalize_text(item)
            if text:
                return text
        return ""
    return _normalize_text(value)


def _parse_date(field: object) -> str:
    if not field:
        return ""
    if isinstance(field, dict):
        date_time = field.get("date-time")
        if isinstance(date_time, str) and date_time.strip():
            return date_time.split("T")[0]
        date_parts = field.get("date-parts")
        if isinstance(date_parts, list) and date_parts:
            first = date_parts[0]
            if isinstance(first, list) and first:
                parts: list[int] = []
                for part in first[:3]:
                    try:
                        parts.append(int(part))
                    except (TypeError, ValueError):
                        return ""
                year = parts[0]
                month = parts[1] if len(parts) > 1 else 1
                day = parts[2] if len(parts) > 2 else 1
                return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def _build_author_name(author: object) -> str:
    if not isinstance(author, dict):
        return _normalize_text(author)
    given = author.get("given", "") or ""
    family = author.get("family", "") or ""
    if given and family:
        return f"{given.strip()} {family.strip()}"
    if family:
        return family.strip()
    if given:
        return given.strip()
    return author.get("name", "").strip()


def _extract_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _normalize_text(item))]


def _extract_pdf_url(item: dict) -> str:
    links = item.get("link", [])
    if not isinstance(links, list):
        return ""
    for link in links:
        if not isinstance(link, dict):
            continue
        content_type = _normalize_text(link.get("content-type")).lower()
        if "pdf" in content_type:
            return _normalize_text(link.get("URL") or link.get("url"))
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord."""
    items = []
    message = payload.get("message", {})
    if not isinstance(message, dict):
        return []
    raw_items = message.get("items", [])
    if not isinstance(raw_items, list):
        return []

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        paper_id = _normalize_text(item.get("DOI")).lower()
        title = _first_text(item.get("title"))
        summary = _normalize_text(item.get("abstract") or "")
        if not summary:
            summary = _first_text(item.get("subtitle"))

        authors_raw = item.get("author") if isinstance(item.get("author"), list) else []
        authors = [name for author in authors_raw if (name := _build_author_name(author))]
        categories = _extract_string_list(item.get("subject"))
        primary_category = categories[0] if categories else ""

        published = _parse_date(item.get("issued") or item.get("published-print") or item.get("published-online"))
        updated = _parse_date(item.get("indexed") or item.get("created") or item.get("issued"))

        abs_url = _normalize_text(item.get("URL"))
        pdf_url = _extract_pdf_url(item)

        comment = _first_text(item.get("subtitle"))
        if not comment:
            comment = _first_text(item.get("container-title"))

        if not paper_id or not title or not summary:
            continue

        items.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    return items


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref API, luu raw response, parse thanh PaperRecord."""
    params = {
        "query": settings.source_query,
        "rows": settings.max_results,
    }
    if settings.source_filter:
        params["filter"] = settings.source_filter

    session = requests.Session()
    retries = 5
    backoff = 1.0
    response = None

    for attempt in range(1, retries + 1):
        try:
            response = session.get(CROSSREF_API_URL, params=params, timeout=30)
            if response.status_code in RETRY_STATUS_CODES:
                if attempt == retries:
                    response.raise_for_status()
                time.sleep(backoff)
                backoff *= 2
                continue
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(backoff)
            backoff *= 2
    if response is None:
        raise RuntimeError("Unable to fetch Crossref source records.")

    payload = response.json()
    settings.paths.raw_api_response.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.raw_api_response.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    records = parse_crossref_payload(payload)

    settings.paths.raw_records_json.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.raw_records_json.write_text(
        json.dumps([asdict(record) for record in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot va map thanh PaperRecord."""
    if not path.exists():
        return []

    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if not isinstance(payload, list):
        return []

    records: list[PaperRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        authors = item.get("authors") if isinstance(item.get("authors"), list) else []
        categories = item.get("categories") if isinstance(item.get("categories"), list) else []
        record = PaperRecord(
            paper_id=str(item.get("paper_id", "") or "").strip(),
            title=str(item.get("title", "") or "").strip(),
            summary=str(item.get("summary", "") or "").strip(),
            authors=[str(a).strip() for a in authors if str(a).strip()],
            categories=[str(c).strip() for c in categories if str(c).strip()],
            primary_category=str(item.get("primary_category", "") or "").strip(),
            published=str(item.get("published", "") or "").strip(),
            updated=str(item.get("updated", "") or "").strip(),
            abs_url=str(item.get("abs_url", "") or "").strip(),
            pdf_url=str(item.get("pdf_url", "") or "").strip(),
            comment=str(item.get("comment", "") or "").strip(),
        )
        if record.paper_id and record.title and record.summary:
            records.append(record)
    return records
