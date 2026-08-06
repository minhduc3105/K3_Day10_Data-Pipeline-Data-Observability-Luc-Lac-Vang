from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import read_json, write_json, write_text


CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 30

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


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


def _clean_text(value: object) -> str:
    """Convert Crossref's HTML-rich metadata to one line of plain text."""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", html.unescape(_HTML_TAG_PATTERN.sub(" ", value))).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", cleaned)


def _first_nonempty_text(*values: object) -> str:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return ""


def _date_from_crossref(value: object) -> str:
    """Return an ISO date from a Crossref date object, or an empty string."""
    if not isinstance(value, dict):
        return ""

    date_time = value.get("date-time")
    if isinstance(date_time, str):
        try:
            return datetime.fromisoformat(date_time.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass

    date_parts = value.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts or not isinstance(date_parts[0], list):
        return ""
    parts = date_parts[0]
    if not parts:
        return ""

    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return datetime(year, month, day, tzinfo=UTC).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _parse_authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    authors: list[str] = []
    for author in value:
        if not isinstance(author, dict):
            continue
        name = _first_nonempty_text(
            author.get("name"),
            author.get("literal"),
            " ".join(str(part) for part in (author.get("given"), author.get("family")) if part),
        )
        if name:
            authors.append(name)
    return authors


def _parse_categories(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(category for item in value if (category := _clean_text(item))))


def _pdf_url(item: dict[str, Any]) -> str:
    links = item.get("link")
    if not isinstance(links, list):
        return ""
    for link in links:
        if not isinstance(link, dict):
            continue
        content_type = str(link.get("content-type", "")).lower()
        if "pdf" in content_type:
            return _clean_text(link.get("URL"))
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref Works response into valid, flat ``PaperRecord`` objects.

    A record is retained only when it has a DOI, title, and an abstract (or
    description).  Crossref represents several fields as HTML and several
    publication date variants, so these are normalized here rather than later
    in the pipeline.
    """
    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    items = message.get("items", []) if isinstance(message, dict) else []
    if not isinstance(items, list):
        return []

    records: list[PaperRecord] = []
    seen_paper_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = _clean_text(item.get("DOI"))
        title_value = item.get("title")
        title = _first_nonempty_text(*(title_value if isinstance(title_value, list) else [title_value]))
        summary = _first_nonempty_text(item.get("abstract"), item.get("description"))
        if not paper_id or not title or not summary or paper_id.lower() in seen_paper_ids:
            continue

        categories = _parse_categories(item.get("subject"))
        published = _first_nonempty_text(
            _date_from_crossref(item.get("published-print")),
            _date_from_crossref(item.get("published-online")),
            _date_from_crossref(item.get("published")),
            _date_from_crossref(item.get("issued")),
        )
        updated = _first_nonempty_text(
            _date_from_crossref(item.get("updated")),
            _date_from_crossref(item.get("indexed")),
            _date_from_crossref(item.get("created")),
            published,
        )
        resource = item.get("resource")
        resource_url = ""
        if isinstance(resource, dict) and isinstance(resource.get("primary"), dict):
            resource_url = resource["primary"].get("URL", "")
        abs_url = _first_nonempty_text(item.get("URL"), resource_url)

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=_pdf_url(item),
                comment=_first_nonempty_text(item.get("publisher"), item.get("container-title")),
            )
        )
        seen_paper_ids.add(paper_id.lower())
    return records


def _retry_delay(response: requests.Response | None, retry_number: int) -> float:
    """Respect Retry-After when present; otherwise use exponential backoff."""
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError):
                pass
    return float(2 ** (retry_number - 1))


def _request_crossref(params: dict[str, object]) -> requests.Response:
    """Request Crossref, retrying transient HTTP and connection failures."""
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (educational pipeline)"}
    last_response: requests.Response | None = None
    last_error: requests.RequestException | None = None

    for retry_number in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            last_response = response
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response
        except requests.RequestException as error:
            last_error = error
            response = None

        if retry_number == MAX_RETRIES:
            break
        time.sleep(_retry_delay(response, retry_number + 1))

    if last_response is not None:
        last_response.raise_for_status()
    if last_error is not None:
        raise last_error
    raise RuntimeError("Crossref request failed without a response.")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref Works and persist both source and normalized raw artifacts."""
    params: dict[str, object] = {
        "query.bibliographic": settings.source_query,
        "rows": settings.max_results,
    }
    if settings.source_filter.strip():
        params["filter"] = settings.source_filter.strip()

    response = _request_crossref(params)
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError("Crossref returned an invalid JSON response.") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Crossref returned a JSON payload that is not an object.")

    # Preserve the original HTTP body for auditability; fall back to serialization
    # for lightweight response doubles used by callers/tests.
    raw_body = getattr(response, "text", None)
    write_text(
        settings.paths.raw_api_response,
        raw_body if isinstance(raw_body, str) else json.dumps(payload, ensure_ascii=False),
    )

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load the normalized raw-record snapshot created by ``fetch_source_records``."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list of PaperRecord values in {path}.")

    records: list[PaperRecord] = []
    required_fields = set(PaperRecord.__dataclass_fields__)
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Record {index} in {path} is not a JSON object.")
        missing = required_fields - item.keys()
        if missing:
            raise ValueError(f"Record {index} in {path} is missing fields: {', '.join(sorted(missing))}.")
        records.append(PaperRecord(**{field: item[field] for field in required_fields}))
    return records
