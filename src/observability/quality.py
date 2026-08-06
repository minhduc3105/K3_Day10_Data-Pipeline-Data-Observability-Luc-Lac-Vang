from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


def _nonempty(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip() != ""


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Measure the baseline completeness and uniqueness requirements."""
    total_rows = len(df)
    paper_ids = df.get("paper_id", pd.Series(dtype="object"))
    titles = df.get("title", pd.Series(dtype="object"))
    summaries = df.get("summary", pd.Series(dtype="object"))
    summary_lengths = summaries.fillna("").astype(str).str.len()

    checks = {
        "row_count": {"passed": total_rows > 0, "observed": total_rows, "expected": "> 0"},
        "paper_id_complete": {
            "passed": len(paper_ids) == total_rows and bool(_nonempty(paper_ids).all()),
            "observed_missing": int((~_nonempty(paper_ids)).sum()),
        },
        "paper_id_unique": {
            "passed": len(paper_ids) == total_rows and bool(paper_ids.is_unique),
            "observed_duplicates": int(paper_ids.duplicated().sum()),
        },
        "title_complete": {
            "passed": len(titles) == total_rows and bool(_nonempty(titles).all()),
            "observed_missing": int((~_nonempty(titles)).sum()),
        },
        "summary_min_length": {
            "passed": len(summaries) == total_rows and bool((summary_lengths >= 100).all()),
            "observed_below_100_chars": int((summary_lengths < 100).sum()),
        },
    }
    report = {
        "report_name": report_name,
        "total_rows": total_rows,
        "is_valid": all(check["passed"] for check in checks.values()),
        "checks": checks,
    }
    write_json(settings.paths.quality_dir / f"{report_name}.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarize publication-date freshness using the configured age threshold."""
    published = pd.to_datetime(df.get("published", pd.Series(dtype="object")), errors="coerce", utc=True)
    age_days = pd.to_numeric(df.get("age_days", pd.Series(dtype="object")), errors="coerce")
    valid_dates = published.dropna()
    stale_rows = int((age_days > settings.freshness_threshold_days).sum())
    missing_published = int(published.isna().sum())
    report = {
        "latest_published": valid_dates.max().date().isoformat() if not valid_dates.empty else None,
        "oldest_published": valid_dates.min().date().isoformat() if not valid_dates.empty else None,
        "stale_rows": stale_rows,
        "missing_published": missing_published,
        "total_rows": len(df),
        "freshness_threshold_days": settings.freshness_threshold_days,
        "is_fresh": len(df) > 0 and stale_rows == 0 and missing_published == 0,
    }
    write_json(report_path, report)
    return report
