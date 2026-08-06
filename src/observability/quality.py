from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Tao bo data quality checks va ghi JSON report."""
    settings.paths.quality_dir.mkdir(parents=True, exist_ok=True)
    total_rows = int(len(df))

    def check(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
        return {"name": name, "passed": bool(passed), "details": details}

    paper_id_not_null = int(df["paper_id"].notna().sum()) if "paper_id" in df else 0
    duplicate_paper_ids = int(df["paper_id"].duplicated().sum()) if "paper_id" in df else total_rows
    title_not_null = int(df["title"].fillna("").astype(str).str.strip().ne("").sum()) if "title" in df else 0
    summary_lengths = df["summary"].fillna("").astype(str).str.len() if "summary" in df else pd.Series([], dtype=int)
    short_summaries = int((summary_lengths < 40).sum()) if not summary_lengths.empty else total_rows
    age_days = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df else pd.Series([], dtype=float)
    stale_rows = int((age_days > settings.freshness_threshold_days).sum()) if not age_days.empty else total_rows

    checks = [
        check("row_count_positive", total_rows > 0, {"total_rows": total_rows}),
        check(
            "paper_id_not_null",
            paper_id_not_null == total_rows and total_rows > 0,
            {"non_null": paper_id_not_null, "total_rows": total_rows},
        ),
        check("paper_id_unique", duplicate_paper_ids == 0, {"duplicate_rows": duplicate_paper_ids}),
        check(
            "title_not_blank",
            title_not_null == total_rows and total_rows > 0,
            {"non_blank": title_not_null, "total_rows": total_rows},
        ),
        check(
            "summary_min_length",
            short_summaries == 0 and total_rows > 0,
            {"min_chars": 40, "short_rows": short_summaries},
        ),
        check(
            "freshness_threshold",
            stale_rows == 0 and total_rows > 0,
            {"threshold_days": settings.freshness_threshold_days, "stale_rows": stale_rows},
        ),
    ]
    report = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_rows": total_rows,
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }
    write_json(settings.paths.quality_dir / f"{report_name}.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness report va ghi JSON."""
    total_rows = int(len(df))
    published = pd.to_datetime(df["published"], errors="coerce", utc=True) if "published" in df else pd.Series([])
    valid_published = published.dropna()
    age_days = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df else pd.Series([], dtype=float)
    stale_rows = int((age_days > settings.freshness_threshold_days).sum()) if not age_days.empty else total_rows

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_api": settings.source_api,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "latest_published": valid_published.max().date().isoformat() if not valid_published.empty else "",
        "oldest_published": valid_published.min().date().isoformat() if not valid_published.empty else "",
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": total_rows > 0 and stale_rows == 0,
    }
    write_json(Path(report_path), report)
    return report
