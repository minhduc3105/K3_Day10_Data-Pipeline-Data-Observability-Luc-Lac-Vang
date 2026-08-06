from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import html
import json
import re
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_csv, write_json
from ingestion.crossref import PaperRecord


MIN_SUMMARY_CHARS = 100
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_BASE_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
]
_OUTPUT_COLUMNS = [
    *_BASE_COLUMNS,
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def _clean_text(value: object) -> str:
    """Remove Crossref HTML/XML markup and normalize its whitespace."""
    if not isinstance(value, str):
        return ""
    cleaned = html.unescape(_HTML_TAG_PATTERN.sub(" ", value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", cleaned)


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalize_authors(value: object) -> list[str]:
    """Flatten author lists, including the nested object shape returned by APIs."""
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if isinstance(value, dict):
        preferred = _clean_text(value.get("name")) or _clean_text(value.get("literal"))
        if preferred:
            return [preferred]
        full_name = _clean_text(" ".join(str(value[key]) for key in ("given", "family") if value.get(key)))
        if full_name:
            return [full_name]
        flattened: list[str] = []
        for nested_value in value.values():
            flattened.extend(_normalize_authors(nested_value))
        return _deduplicate(flattened)
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(_normalize_authors(item))
        return _deduplicate(flattened)
    return []


def _normalize_categories(value: object) -> list[str]:
    """Flatten category lists while retaining readable labels from nested objects."""
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if isinstance(value, dict):
        for key in ("name", "label", "title", "subject"):
            label = _clean_text(value.get(key))
            if label:
                return [label]
        flattened: list[str] = []
        for nested_value in value.values():
            flattened.extend(_normalize_categories(nested_value))
        return _deduplicate(flattened)
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(_normalize_categories(item))
        return _deduplicate(flattened)
    return []


def _normalize_date_column(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed", utc=True)
    return parsed.dt.strftime("%Y-%m-%d").fillna(""), parsed


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Return a retrieval-ready dataframe from raw Crossref paper records.

    Invalid publication dates are retained as blank values with a missing
    ``age_days`` value. This keeps date quality visible to observability checks
    without discarding otherwise useful retrieval content.
    """
    rows = [asdict(record) for record in records]
    if not rows:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    df = pd.DataFrame(rows)
    for column in _BASE_COLUMNS:
        if column not in df:
            df[column] = ""
    df = df[_BASE_COLUMNS].copy()

    df["paper_id"] = df["paper_id"].map(_clean_text)
    df["title"] = df["title"].map(_clean_text)
    df["summary"] = df["summary"].map(_clean_text)
    df["authors"] = df["authors"].map(_normalize_authors)
    df["categories"] = df["categories"].map(_normalize_categories)
    df["primary_category"] = df.apply(
        lambda row: _clean_text(row["primary_category"]) or (row["categories"][0] if row["categories"] else ""),
        axis=1,
    )
    for column in ("updated", "abs_url", "pdf_url", "comment"):
        df[column] = df[column].map(_clean_text)

    df["published"], published_dates = _normalize_date_column(df["published"])
    df["updated"], _ = _normalize_date_column(df["updated"])
    reference_date = pd.Timestamp(run_date)
    if reference_date.tzinfo is None:
        reference_date = reference_date.tz_localize("UTC")
    else:
        reference_date = reference_date.tz_convert("UTC")
    df["age_days"] = (reference_date.normalize() - published_dates.dt.normalize()).dt.days.astype("Int64")

    df["summary_chars"] = df["summary"].str.len()
    df = df.loc[(df["title"] != "") & (df["summary_chars"] >= MIN_SUMMARY_CHARS)].copy()
    df = df.drop_duplicates(subset="paper_id", keep="first")

    df["authors_joined"] = df["authors"].map(", ".join)
    df["categories_joined"] = df["categories"].map(", ".join)
    df["text_for_embedding"] = (
        "Title: "
        + df["title"]
        + " | Authors: "
        + df["authors_joined"]
        + " | Summary: "
        + df["summary"]
    )
    return df[_OUTPUT_COLUMNS].reset_index(drop=True)


def save_clean_artifacts(df: pd.DataFrame, settings: Settings) -> None:
    """Persist the retrieval-ready dataframe as the configured CSV and JSON artifacts."""
    write_csv(df, settings.paths.clean_csv)
    # Pandas converts nullable values, timestamps, and NumPy scalars to standard
    # JSON values before the project-wide JSON writer persists the snapshot.
    records: list[dict[str, Any]] = json.loads(df.to_json(orient="records", date_format="iso"))
    write_json(settings.paths.clean_json, records)
