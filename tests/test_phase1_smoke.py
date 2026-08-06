from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import pipelines.phase1 as phase1
from evaluation.metrics import EvaluationBundle


def test_phase1_wires_existing_artifacts_without_network(monkeypatch, tmp_path) -> None:
    paths = SimpleNamespace(
        raw_records_json=tmp_path / "raw.json",
        clean_csv=tmp_path / "clean.csv",
        clean_json=tmp_path / "clean.json",
        chroma_dir=tmp_path / "chroma",
        eval_testset=tmp_path / "test_set.json",
        eval_testset_provenance=tmp_path / "test_set_provenance.json",
        embeddings_json=tmp_path / "embeddings.json",
        baseline_metrics=tmp_path / "metrics.json",
        baseline_answers=tmp_path / "answers.json",
        quality_dir=tmp_path / "quality",
        freshness_report=tmp_path / "freshness.json",
        baseline_report=tmp_path / "phase1.md",
    )
    paths.raw_records_json.write_text("[]")
    paths.eval_testset.write_text("[]")
    paths.eval_testset_provenance.write_text("{}")
    settings = SimpleNamespace(
        paths=paths,
        refresh_source=False,
        refresh_test_set=False,
        source_api="Crossref",
        source_query="machine learning",
        source_filter="has-abstract:true",
    )
    dataframe = pd.DataFrame([{"paper_id": "10.1/a", "title": "Paper", "summary": "Long enough"}])
    summary = {"samples": 1, "retrieval_hit_rate": 1.0, "mean_token_f1": 1.0, "judge_accuracy": 1.0, "mean_judge_score": 5.0}

    monkeypatch.setattr(phase1, "load_settings", lambda: settings)
    monkeypatch.setattr(phase1, "load_raw_records", lambda _: ["raw"])
    monkeypatch.setattr(phase1, "build_clean_dataframe", lambda *_: dataframe)
    monkeypatch.setattr(phase1, "save_clean_artifacts", lambda *_: None)
    monkeypatch.setattr(phase1.LocalEmbeddingIndex, "build", lambda *_: object())
    monkeypatch.setattr(phase1, "evaluate_pipeline", lambda *args, **kwargs: EvaluationBundle(summary=summary, answers=[]))
    monkeypatch.setattr(phase1, "run_data_quality_checks", lambda *args, **kwargs: {"is_valid": True, "total_rows": 1})
    monkeypatch.setattr(phase1, "build_freshness_report", lambda *args, **kwargs: {"latest_published": None, "oldest_published": None, "stale_rows": 0, "missing_published": 0, "is_fresh": True})
    monkeypatch.setattr(phase1, "generate_phase1_report", lambda path, **_: Path(path).write_text("ok"))

    phase1.main(skip_judge=True)
    assert paths.baseline_report.read_text() == "ok"
