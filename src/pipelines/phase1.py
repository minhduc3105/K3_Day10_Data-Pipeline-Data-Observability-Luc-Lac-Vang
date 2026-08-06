from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe, save_clean_artifacts
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Run the reproducible baseline pipeline from raw data through reporting."""
    settings = load_settings()

    if settings.refresh_source or not settings.paths.raw_records_json.exists():
        records = fetch_source_records(settings)
    else:
        records = load_raw_records(settings.paths.raw_records_json)

    cleaned = build_clean_dataframe(records, now_utc())
    save_clean_artifacts(cleaned, settings)
    index = LocalEmbeddingIndex.build(cleaned, settings)

    if settings.refresh_test_set or not settings.paths.eval_testset.exists():
        build_test_set(cleaned, settings.paths.eval_testset)

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    quality = run_data_quality_checks(cleaned, settings, report_name="baseline_quality")
    freshness = build_freshness_report(cleaned, settings, settings.paths.freshness_report)
    source_summary = {
        "source_api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "raw_records": len(records),
        "clean_records": len(cleaned),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )
    print(
        f"Baseline complete: {len(cleaned)} clean records, "
        f"retrieval_hit_rate={evaluation.summary['retrieval_hit_rate']:.4f}, "
        f"mean_token_f1={evaluation.summary['mean_token_f1']:.4f}"
    )
