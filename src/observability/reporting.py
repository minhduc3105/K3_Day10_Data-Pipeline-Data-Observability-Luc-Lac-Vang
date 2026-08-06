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
        f"- Mean field-aware score: {metrics.get('mean_field_score', metrics['mean_token_f1']):.4f}",
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
    baseline_quality: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    baseline_freshness: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write a side-by-side baseline, corrupted, and repaired comparison."""
    metrics_by_state = [baseline_metrics, corrupted_metrics, repaired_metrics]
    frozen_hashes = {metrics.get("frozen_test_set_hash") for metrics in metrics_by_state}
    sample_counts = {metrics.get("frozen_test_set_samples", metrics.get("samples")) for metrics in metrics_by_state}
    if None in frozen_hashes or len(frozen_hashes) != 1 or len(sample_counts) != 1:
        raise ValueError("Cannot compare runs created from different frozen test sets.")
    states = [
        ("Baseline", baseline_metrics, baseline_quality, baseline_freshness),
        ("Corrupted", corrupted_metrics, corrupted_quality, corrupted_freshness),
        ("Repaired", repaired_metrics, repaired_quality, repaired_freshness),
    ]
    lines = [
        "# Corruption Comparison Report",
        "",
        "| State | Samples | Retrieval hit rate | Mean token F1 | Field-aware score | Judge accuracy |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics, _, _ in states:
        lines.append(
            f"| {name} | {metrics['samples']} | {metrics['retrieval_hit_rate']:.4f} | "
            f"{metrics['mean_token_f1']:.4f} | {metrics.get('mean_field_score', metrics['mean_token_f1']):.4f} | {metrics['judge_accuracy']:.4f} |"
        )

    lines.extend(["", "## Data quality and freshness", "", "| State | Valid | Rows | Duplicate rows | Stale rows | Missing dates |", "| --- | --- | ---: | ---: | ---: | ---: |"])
    for name, _, quality, freshness in states:
        duplicate_rows = quality["checks"]["paper_id_unique"]["observed_duplicates"]
        lines.append(
            f"| {name} | {quality['is_valid']} | {quality['total_rows']} | {duplicate_rows} | "
            f"{freshness['stale_rows']} | {freshness['missing_published']} |"
        )
    lines.extend(["", f"Frozen test-set SHA-256: `{next(iter(frozen_hashes))}`", "", "![Comparison chart](corruption_metrics.svg)", ""])
    write_text(report_path, "\n".join(lines))
    _write_comparison_svg(report_path.with_name("corruption_metrics.svg"), states)


def _write_comparison_svg(path, states) -> None:
    """Create a dependency-free chart for the three experimental states."""
    colors = ["#2563eb", "#dc2626", "#16a34a"]
    metric_names = ["Hit rate", "Token F1", "Judge accuracy", "Stale rows", "Duplicate rows"]
    values = []
    for _, metrics, quality, freshness in states:
        values.append(
            [
                metrics["retrieval_hit_rate"],
                metrics["mean_token_f1"],
                metrics["judge_accuracy"],
                freshness["stale_rows"],
                quality["checks"]["paper_id_unique"]["observed_duplicates"],
            ]
        )
    maxima = [max(1.0, max(row[index] for row in values)) for index in range(len(metric_names))]
    fragments = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="360" viewBox="0 0 900 360">',
        '<rect width="900" height="360" fill="#ffffff"/>',
        '<text x="30" y="32" font-family="Arial" font-size="20" font-weight="bold">Baseline vs Corrupted vs Repaired</text>',
    ]
    for metric_index, metric_name in enumerate(metric_names):
        x = 35 + metric_index * 170
        fragments.append(f'<text x="{x}" y="70" font-family="Arial" font-size="13">{metric_name}</text>')
        for state_index, (state_name, _, _, _) in enumerate(states):
            value = values[state_index][metric_index]
            bar_height = 190 * value / maxima[metric_index]
            bar_x = x + state_index * 42
            bar_y = 285 - bar_height
            fragments.append(f'<rect x="{bar_x}" y="{bar_y:.1f}" width="30" height="{bar_height:.1f}" fill="{colors[state_index]}"/>')
            fragments.append(f'<text x="{bar_x}" y="305" font-family="Arial" font-size="10">{state_name[:4]}</text>')
            fragments.append(f'<text x="{bar_x}" y="{bar_y - 6:.1f}" font-family="Arial" font-size="10">{value:.3g}</text>')
    fragments.append('</svg>')
    write_text(path, "".join(fragments))
