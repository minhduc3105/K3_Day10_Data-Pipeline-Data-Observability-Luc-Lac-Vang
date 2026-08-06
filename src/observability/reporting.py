from __future__ import annotations

from typing import Any

from core.utils import write_text


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a concise, auditable report for the baseline pipeline run."""
    lines = [
        "# Phase 1 Baseline Report",
        "",
        "## Source",
        "",
        f"- Source: {source_summary['source_api']}",
        f"- Query: {source_summary['query']}",
        f"- Filter: {source_summary['filter']}",
        f"- Raw records: {source_summary['raw_records']}",
        f"- Clean records: {source_summary['clean_records']}",
        "",
        "## Evaluation",
        "",
        f"- Samples: {metrics['samples']}",
        f"- Retrieval hit rate: {metrics['retrieval_hit_rate']:.4f}",
        f"- Mean token F1: {metrics['mean_token_f1']:.4f}",
        f"- Judge accuracy: {metrics['judge_accuracy']:.4f}",
        f"- Mean judge score: {metrics['mean_judge_score']:.4f}",
        "",
        "## Data Quality",
        "",
        f"- Valid: {quality['is_valid']}",
        f"- Rows: {quality['total_rows']}",
        "",
        "## Freshness",
        "",
        f"- Latest published: {freshness['latest_published'] or 'unknown'}",
        f"- Oldest published: {freshness['oldest_published'] or 'unknown'}",
        f"- Stale rows: {freshness['stale_rows']}",
        f"- Missing publication dates: {freshness['missing_published']}",
        f"- Fresh: {freshness['is_fresh']}",
    ]
    write_text(report_path, "\n".join(lines) + "\n")


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
    """Write a side-by-side baseline, corrupted, and repaired comparison."""
    states = [
        ("Baseline", baseline_metrics, None, None),
        ("Corrupted", corrupted_metrics, corrupted_quality, corrupted_freshness),
        ("Repaired", repaired_metrics, repaired_quality, repaired_freshness),
    ]
    lines = [
        "# Corruption Comparison Report",
        "",
        "| State | Samples | Retrieval hit rate | Mean token F1 | Judge accuracy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics, _, _ in states:
        lines.append(
            f"| {name} | {metrics['samples']} | {metrics['retrieval_hit_rate']:.4f} | "
            f"{metrics['mean_token_f1']:.4f} | {metrics['judge_accuracy']:.4f} |"
        )

    lines.extend(["", "## Data quality and freshness", ""])
    for name, _, quality, freshness in states[1:]:
        lines.extend(
            [
                f"### {name}",
                "",
                f"- Data quality valid: {quality['is_valid']}",
                f"- Total rows: {quality['total_rows']}",
                f"- Stale rows: {freshness['stale_rows']}",
                f"- Missing publication dates: {freshness['missing_published']}",
                f"- Fresh: {freshness['is_fresh']}",
                "",
            ]
        )
    write_text(report_path, "\n".join(lines))
