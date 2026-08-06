from __future__ import annotations

import json

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, json.loads(df.to_json(orient="records", date_format="iso")))


def _load_corrupted_csv(path) -> pd.DataFrame:
    dataframe = pd.read_csv(path)
    for column in ("paper_id", "title", "summary", "authors_joined", "categories_joined", "abs_url", "pdf_url", "text_for_embedding"):
        if column in dataframe:
            dataframe[column] = dataframe[column].fillna("").astype(str)
    return dataframe


def main() -> None:
    """Run controlled corruption, repair from raw data, and compare all states."""
    settings = load_settings()
    if not settings.paths.baseline_metrics.exists():
        raise FileNotFoundError("Baseline metrics are missing. Run script/run_phase1.py before the corruption flow.")
    if not settings.paths.clean_json.exists() or not settings.paths.eval_testset.exists():
        raise FileNotFoundError("Clean data or frozen test set is missing. Run script/run_phase1.py first.")

    clean_dataframe = pd.DataFrame(read_json(settings.paths.clean_json))
    corrupted_dataframe = corrupt_clean_dataframe(
        clean_dataframe,
        output_log_path=settings.paths.corruption_log,
        test_set_path=settings.paths.eval_testset,
    )
    _save_dataframe(corrupted_dataframe, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)

    # Read the persisted CSV to make the corrupted-data experiment use its own artifact.
    corrupted_from_csv = _load_corrupted_csv(settings.paths.corrupted_clean_csv)
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_from_csv,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_evaluation = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(corrupted_from_csv, settings, report_name="corrupted_quality")
    corrupted_freshness = build_freshness_report(
        corrupted_from_csv,
        settings,
        settings.paths.quality_dir / "corrupted_freshness_report.json",
    )

    # Repair starts from the raw snapshot, not from the corrupted dataframe.
    repaired_dataframe = build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), now_utc())
    _save_dataframe(repaired_dataframe, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    repaired_index = LocalEmbeddingIndex.build(
        repaired_dataframe,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_evaluation = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_dataframe, settings, report_name="repaired_quality")
    repaired_freshness = build_freshness_report(
        repaired_dataframe,
        settings,
        settings.paths.quality_dir / "repaired_freshness_report.json",
    )

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=read_json(settings.paths.baseline_metrics),
        corrupted_metrics=corrupted_evaluation.summary,
        repaired_metrics=repaired_evaluation.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(
        "Corruption flow complete: "
        f"corrupted_f1={corrupted_evaluation.summary['mean_token_f1']:.4f}, "
        f"repaired_f1={repaired_evaluation.summary['mean_token_f1']:.4f}"
    )
