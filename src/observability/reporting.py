from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


def _metric(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value if value is not None else "")


def _quality_summary(quality: dict[str, Any]) -> str:
    checks = quality.get("checks", [])
    lines = []
    for item in checks:
        status = "PASS" if item.get("passed") else "FAIL"
        lines.append(f"| {item.get('name', '')} | {status} | `{item.get('details', {})}` |")
    return "\n".join(lines)


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase."""
    text = f"""# Phase 1 Baseline Report

## Source

| Field | Value |
| --- | --- |
| Source API | {source_summary.get("source_api", "")} |
| Query | `{source_summary.get("query", "")}` |
| Filter | `{source_summary.get("filter", "")}` |
| Raw records | {source_summary.get("raw_records", "")} |
| Clean records | {source_summary.get("clean_records", "")} |
| Raw response | `{source_summary.get("raw_response_path", "")}` |
| Raw records path | `{source_summary.get("raw_records_path", "")}` |

## Evaluation

| Metric | Value |
| --- | ---: |
| Samples | {_metric(metrics, "samples")} |
| Retrieval hit rate | {_metric(metrics, "retrieval_hit_rate")} |
| Mean token F1 | {_metric(metrics, "mean_token_f1")} |
| Judge accuracy | {_metric(metrics, "judge_accuracy")} |
| Mean judge score | {_metric(metrics, "mean_judge_score")} |

## Data Quality

Overall status: {"PASS" if quality.get("passed") else "FAIL"}

| Check | Status | Details |
| --- | --- | --- |
{_quality_summary(quality)}

## Freshness

| Field | Value |
| --- | --- |
| Latest published | {freshness.get("latest_published", "")} |
| Oldest published | {freshness.get("oldest_published", "")} |
| Stale rows | {freshness.get("stale_rows", "")} |
| Total rows | {freshness.get("total_rows", "")} |
| Is fresh | {freshness.get("is_fresh", "")} |
"""
    write_text(Path(report_path), text)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Viet markdown report so sanh baseline/corrupted/repaired."""
    text = f"""# Corruption Impact Report

## Metrics Comparison

| Metric | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| Samples | {_metric(baseline_metrics, "samples")} | {_metric(corrupted_metrics, "samples")} | {_metric(repaired_metrics, "samples")} |
| Retrieval hit rate | {_metric(baseline_metrics, "retrieval_hit_rate")} | {_metric(corrupted_metrics, "retrieval_hit_rate")} | {_metric(repaired_metrics, "retrieval_hit_rate")} |
| Mean token F1 | {_metric(baseline_metrics, "mean_token_f1")} | {_metric(corrupted_metrics, "mean_token_f1")} | {_metric(repaired_metrics, "mean_token_f1")} |
| Judge accuracy | {_metric(baseline_metrics, "judge_accuracy")} | {_metric(corrupted_metrics, "judge_accuracy")} | {_metric(repaired_metrics, "judge_accuracy")} |
| Mean judge score | {_metric(baseline_metrics, "mean_judge_score")} | {_metric(corrupted_metrics, "mean_judge_score")} | {_metric(repaired_metrics, "mean_judge_score")} |

## Quality Status

| State | Overall | Total rows |
| --- | --- | ---: |
| Corrupted | {"PASS" if corrupted_quality.get("passed") else "FAIL"} | {corrupted_quality.get("total_rows", "")} |
| Repaired | {"PASS" if repaired_quality.get("passed") else "FAIL"} | {repaired_quality.get("total_rows", "")} |

## Freshness Status

| State | Is fresh | Stale rows | Latest published |
| --- | --- | ---: | --- |
| Corrupted | {corrupted_freshness.get("is_fresh", "")} | {corrupted_freshness.get("stale_rows", "")} | {corrupted_freshness.get("latest_published", "")} |
| Repaired | {repaired_freshness.get("is_fresh", "")} | {repaired_freshness.get("stale_rows", "")} | {repaired_freshness.get("latest_published", "")} |

## Interpretation

The corrupted run intentionally removes recent papers, damages summaries and titles, adds stale dates, and duplicates rows. The repaired run rebuilds the dataset from raw Crossref records, so metrics and quality checks should move back toward the baseline.
"""
    write_text(Path(report_path), text)
