from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from core.config import Settings
from core.utils import normalize_whitespace, write_json


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


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload into list of PaperRecord.

    Extracts DOI, title, abstract, authors, subjects, dates, and URLs
    from the Crossref API response.
    """
    records = []
    items = payload.get("message", {}).get("items", [])

    for item in items:
        # Extract DOI as paper_id
        doi = item.get("DOI", "")
        if not doi:
            continue

        # Extract title
        title_list = item.get("title", [])
        title = normalize_whitespace(title_list[0]) if title_list else ""
        if not title:
            continue

        # Extract abstract/summary
        abstract = item.get("abstract", "")
        if not abstract:
            continue
        summary = normalize_whitespace(abstract)

        # Extract authors
        authors = []
        for author in item.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)

        # Extract subjects/categories
        categories = item.get("subject", [])
        primary_category = categories[0] if categories else "Unknown"

        # Extract dates
        published_parts = item.get("published", {}).get("date-parts", [[]])
        if published_parts and published_parts[0]:
            date_parts = published_parts[0]
            year = date_parts[0] if len(date_parts) > 0 else 1970
            month = date_parts[1] if len(date_parts) > 1 else 1
            day = date_parts[2] if len(date_parts) > 2 else 1
            published = f"{year:04d}-{month:02d}-{day:02d}"
        else:
            published = "1970-01-01"

        # Updated date - use published if not available
        updated = published

        # Extract URLs
        abs_url = item.get("URL", f"https://doi.org/{doi}")
        # Crossref doesn't provide direct PDF links, use DOI link
        pdf_url = abs_url

        # Extract comment (not typically in Crossref, use empty string)
        comment = ""

        record = PaperRecord(
            paper_id=doi,
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
        records.append(record)

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch papers from Crossref API with retry logic.

    Implements exponential backoff for rate limiting (429) and
    service unavailable (503) errors.
    """
    base_url = "https://api.crossref.org/works"

    # Build query parameters
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "mailto": "student@example.com",  # Polite pool access
    }

    # Retry configuration
    max_retries = 5
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            response = requests.get(base_url, params=params, timeout=30)

            # Check for rate limiting or service issues
            if response.status_code in {429, 503}:
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    print(f"Status {response.status_code}, retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    raise RuntimeError(
                        f"Failed after {max_retries} retries: HTTP {response.status_code}"
                    )

            # Raise for other HTTP errors
            response.raise_for_status()

            # Parse response
            payload = response.json()

            # Save raw response
            write_json(settings.paths.raw_api_response, payload)
            print(f"Saved raw response to {settings.paths.raw_api_response}")

            # Parse into records
            records = parse_crossref_payload(payload)
            print(f"Parsed {len(records)} records from Crossref")

            # Save parsed records
            records_data = [asdict(r) for r in records]
            write_json(settings.paths.raw_records_json, records_data)
            print(f"Saved parsed records to {settings.paths.raw_records_json}")

            return records

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                print(f"Request error: {e}, retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Failed to fetch from Crossref after {max_retries} retries: {e}")

    return []


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load raw records from JSON file and convert to PaperRecord objects."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for item in data:
        record = PaperRecord(
            paper_id=item["paper_id"],
            title=item["title"],
            summary=item["summary"],
            authors=item["authors"],
            categories=item["categories"],
            primary_category=item["primary_category"],
            published=item["published"],
            updated=item["updated"],
            abs_url=item["abs_url"],
            pdf_url=item["pdf_url"],
            comment=item["comment"],
        )
        records.append(record)

    return records
