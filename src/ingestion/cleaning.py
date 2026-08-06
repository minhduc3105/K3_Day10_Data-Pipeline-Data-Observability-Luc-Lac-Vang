from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from ingestion.crossref import PaperRecord
from core.utils import compact_join, normalize_whitespace


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed."""
    rows: list[dict[str, object]] = []
    run_ts = pd.Timestamp(run_date)
    if run_ts.tzinfo is None:
        run_ts = run_ts.tz_localize(UTC)
    else:
        run_ts = run_ts.tz_convert(UTC)

    for record in records:
        title = normalize_whitespace(record.title)
        summary = normalize_whitespace(record.summary)
        paper_id = normalize_whitespace(record.paper_id).lower()
        authors = [normalize_whitespace(author) for author in record.authors if normalize_whitespace(author)]
        categories = [normalize_whitespace(category) for category in record.categories if normalize_whitespace(category)]
        primary_category = normalize_whitespace(record.primary_category) or (categories[0] if categories else "unknown")
        authors_joined = compact_join(authors) or "Unknown authors"
        categories_joined = compact_join(categories) or primary_category

        published_ts = pd.to_datetime(record.published, errors="coerce", utc=True)
        updated_ts = pd.to_datetime(record.updated, errors="coerce", utc=True)
        age_days = None
        if not pd.isna(published_ts):
            age_days = max(0, int((run_ts.normalize() - published_ts.normalize()).days))

        if not paper_id or not title or not summary:
            continue
        if len(summary) < 40:
            continue

        published = published_ts.date().isoformat() if not pd.isna(published_ts) else ""
        updated = updated_ts.date().isoformat() if not pd.isna(updated_ts) else ""
        text_for_embedding = normalize_whitespace(
            "\n".join(
                [
                    f"Title: {title}",
                    f"Authors: {authors_joined}",
                    f"Categories: {categories_joined}",
                    f"Published: {published or 'unknown'}",
                    f"Summary: {summary}",
                ]
            )
        )

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": primary_category,
                "published": published,
                "updated": updated,
                "abs_url": normalize_whitespace(record.abs_url),
                "pdf_url": normalize_whitespace(record.pdf_url),
                "comment": normalize_whitespace(record.comment),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": len(summary),
                "age_days": age_days,
                "text_for_embedding": text_for_embedding,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=[
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
                "authors_joined",
                "categories_joined",
                "summary_chars",
                "age_days",
                "text_for_embedding",
            ]
        )

    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    df = df[df["title"].str.len() > 0]
    df = df[df["summary_chars"] >= 40]
    df = df.sort_values(["published", "paper_id"], ascending=[False, True], na_position="last").reset_index(drop=True)
    return df
