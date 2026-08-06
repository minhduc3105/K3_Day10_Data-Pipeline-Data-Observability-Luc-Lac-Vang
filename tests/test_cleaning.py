from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from ingestion.cleaning import build_clean_dataframe, save_clean_artifacts
from ingestion.crossref import PaperRecord


LONG_SUMMARY = "<jats:p>" + ("A retrieval-ready summary sentence. " * 5) + "</jats:p>"


def _record(**overrides) -> PaperRecord:
    values = {
        "paper_id": "10.1000/valid",
        "title": "<b>Retrieval</b> Paper",
        "summary": LONG_SUMMARY,
        "authors": [{"given": "Ada", "family": "Lovelace"}, {"literal": "Research <i>Team</i>"}],
        "categories": [{"name": "<b>Artificial Intelligence</b>"}, "Machine Learning"],
        "primary_category": "",
        "published": "2026-08-01",
        "updated": "invalid-date",
        "abs_url": "https://doi.org/10.1000/valid",
        "pdf_url": "",
        "comment": "",
    }
    values.update(overrides)
    return PaperRecord(**values)


def test_build_clean_dataframe_normalizes_and_filters_records() -> None:
    cleaned = build_clean_dataframe(
        [
            _record(),
            _record(paper_id="10.1000/short", summary="Too short"),
            _record(paper_id="10.1000/no-title", title="<b> </b>"),
            _record(paper_id="10.1000/invalid-date", published="not-a-date"),
            _record(),
        ],
        datetime(2026, 8, 6),
    )

    assert cleaned["paper_id"].tolist() == ["10.1000/valid", "10.1000/invalid-date"]
    first = cleaned.iloc[0]
    assert first["title"] == "Retrieval Paper"
    assert "<" not in first["summary"]
    assert first["authors_joined"] == "Ada Lovelace, Research Team"
    assert first["categories_joined"] == "Artificial Intelligence, Machine Learning"
    assert first["primary_category"] == "Artificial Intelligence"
    assert first["published"] == "2026-08-01"
    assert first["age_days"] == 5
    assert first["text_for_embedding"] == (
        f"Title: Retrieval Paper | Authors: Ada Lovelace, Research Team | Summary: {first['summary']}"
    )
    assert cleaned.iloc[1]["published"] == ""
    assert pd.isna(cleaned.iloc[1]["age_days"])


def test_save_clean_artifacts_writes_csv_and_json(tmp_path) -> None:
    dataframe = build_clean_dataframe([_record()], datetime(2026, 8, 6))
    paths = SimpleNamespace(clean_csv=tmp_path / "papers_clean.csv", clean_json=tmp_path / "papers_clean.json")
    save_clean_artifacts(dataframe, SimpleNamespace(paths=paths))

    assert pd.read_csv(paths.clean_csv).shape[0] == 1
    saved_records = json.loads(paths.clean_json.read_text(encoding="utf-8"))
    assert saved_records[0]["paper_id"] == "10.1000/valid"
    assert saved_records[0]["age_days"] == 5
