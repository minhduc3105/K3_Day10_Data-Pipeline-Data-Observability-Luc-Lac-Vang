from __future__ import annotations

from dataclasses import asdict
import json

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def _dataframe_records(df):
    return json.loads(df.to_json(orient="records", force_ascii=True))


def main() -> None:
    """Xay dung baseline pipeline end-to-end."""
    settings = load_settings()

    records = []
    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        records = load_raw_records(settings.paths.raw_records_json)
    if not records:
        records = fetch_source_records(settings)

    run_date = now_utc()
    clean_df = build_clean_dataframe(records, run_date=run_date)
    if clean_df.empty:
        raise RuntimeError("Cleaning produced an empty dataframe.")

    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))

    index = LocalEmbeddingIndex.build(clean_df, settings=settings, embeddings_output_path=settings.paths.embeddings_json)

    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set = read_json(settings.paths.eval_testset)
    else:
        test_set = build_test_set(clean_df, settings.paths.eval_testset)

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    quality = run_data_quality_checks(clean_df, settings=settings, report_name="baseline_quality")
    freshness = build_freshness_report(clean_df, settings=settings, report_path=settings.paths.freshness_report)

    demo_answers = []
    for sample in test_set[: min(3, len(test_set))]:
        result = answer_question(sample["question"], settings=settings, index=index)
        demo_answers.append(asdict(result))
    write_json(settings.paths.demo_answers, demo_answers)

    source_summary = {
        "source_api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "max_results": settings.max_results,
        "raw_records": len(records),
        "clean_records": int(len(clean_df)),
        "raw_response_path": str(settings.paths.raw_api_response),
        "raw_records_path": str(settings.paths.raw_records_json),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )

    print(f"Baseline complete: {len(clean_df)} clean records, {len(test_set)} eval samples.")
    print(f"Metrics: {settings.paths.baseline_metrics}")
    print(f"Report: {settings.paths.baseline_report}")
