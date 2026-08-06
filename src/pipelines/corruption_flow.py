from __future__ import annotations

import json

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _dataframe_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", force_ascii=True))


def main() -> None:
    """Xay dung corruption -> evaluate -> repair -> compare flow."""
    settings = load_settings()

    if not settings.paths.clean_csv.exists() or not settings.paths.baseline_metrics.exists() or not settings.paths.eval_testset.exists():
        from pipelines.phase1 import main as run_phase1

        run_phase1()

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_df = pd.read_csv(settings.paths.clean_csv)
    if baseline_df.empty:
        raise RuntimeError("Baseline clean dataset is empty; run phase1 first.")

    corrupted_df = corrupt_clean_dataframe(baseline_df, settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _dataframe_records(corrupted_df))

    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings=settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_eval = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings=settings, report_name="corrupted_quality")
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "corrupted_freshness_report.json",
    )

    raw_records = load_raw_records(settings.paths.raw_records_json)
    if not raw_records:
        raw_records = fetch_source_records(settings)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    if repaired_df.empty:
        raise RuntimeError("Repair from raw records produced an empty dataframe.")
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _dataframe_records(repaired_df))

    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings=settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_eval = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings=settings, report_name="repaired_quality")
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "repaired_freshness_report.json",
    )

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_eval.summary,
        repaired_metrics=repaired_eval.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    print("Corruption flow complete.")
    print(f"Corrupted metrics: {settings.paths.corrupted_metrics}")
    print(f"Repaired metrics: {settings.paths.repaired_metrics}")
    print(f"Comparison report: {settings.paths.comparison_report}")
