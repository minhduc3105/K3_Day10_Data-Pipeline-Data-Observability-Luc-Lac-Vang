from __future__ import annotations

from datetime import datetime
from pathlib import Path
import html
import re

import pandas as pd

from core.utils import compact_join, normalize_whitespace, write_csv, write_json
from ingestion.crossref import PaperRecord

MIN_SUMMARY_CHARS = 100

_TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_markup(value: str) -> str:
    """Remove XML/HTML tags (``<jats:p>``, ``<b>``, ...) and unescape entities."""
    if not value:
        return ""
    without_tags = _TAG_PATTERN.sub(" ", value)
    return normalize_whitespace(html.unescape(without_tags))


def _parse_published(value: str) -> str:
    """Normalize a date string to ``YYYY-MM-DD``; empty string when unparsable."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into a dataframe ready for embedding."""
    run_day = run_date.date()
    rows: list[dict] = []

    for record in records:
        title = strip_markup(record.title)
        summary = strip_markup(record.summary)

        # Drop junk rows: missing title or too-short abstract.
        if not title or len(summary) < MIN_SUMMARY_CHARS:
            continue

        authors = [normalize_whitespace(author) for author in record.authors]
        categories = [normalize_whitespace(category) for category in record.categories]
        published = _parse_published(record.published)
        if not published:
            continue

        age_days = (run_day - datetime.fromisoformat(published).date()).days
        authors_joined = compact_join(authors)
        categories_joined = compact_join(categories)

        rows.append(
            {
                "paper_id": record.paper_id.strip(),
                "title": title,
                "summary": summary,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "primary_category": normalize_whitespace(record.primary_category),
                "published": published,
                "updated": _parse_published(record.updated) or published,
                "abs_url": record.abs_url.strip(),
                "pdf_url": record.pdf_url.strip(),
                "comment": strip_markup(record.comment),
                "summary_chars": len(summary),
                "age_days": age_days,
                "text_for_embedding": (
                    f"Title: {title} | Authors: {authors_joined} | Summary: {summary}"
                ),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.drop_duplicates(subset="paper_id", keep="first")
    df = df.sort_values(["published", "paper_id"], ascending=[False, True])
    return df.reset_index(drop=True)


def save_clean_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    """Persist the cleaned dataframe to CSV and JSON."""
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))
