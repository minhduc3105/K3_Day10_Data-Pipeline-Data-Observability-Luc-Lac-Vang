from __future__ import annotations

from datetime import datetime

import pandas as pd
from pandas.testing import assert_frame_equal

from core.utils import write_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import PaperRecord


def test_corruption_overlaps_frozen_documents_and_repair_is_clean(tmp_path) -> None:
    summary = "A sufficiently detailed summary for a reproducible cleaning and repair test. " * 2
    raw_records = [
        PaperRecord(f"10.1/{index}", f"Paper {index}", summary, ["Author"], [], "", "2026-08-01", "", "", "", "Publisher")
        for index in range(4)
    ]
    baseline = build_clean_dataframe(raw_records, datetime(2026, 8, 6))
    test_set_path = tmp_path / "test_set.json"
    write_json(
        test_set_path,
        [{"id": f"q{index}", "question_type": "factual", "question": "Question", "ground_truth": "Answer", "ground_truth_doc_ids": [f"10.1/{index}"]} for index in range(4)],
    )
    log_path = tmp_path / "corruption_log.json"
    corrupted = corrupt_clean_dataframe(baseline, log_path, test_set_path)

    scenario_ids = {paper_id for scenario in __import__("json").loads(log_path.read_text())["scenarios"] for paper_id in scenario["paper_ids"]}
    assert scenario_ids == {f"10.1/{index}" for index in range(4)}
    assert corrupted["paper_id"].duplicated().any()
    assert (corrupted["summary"] == "").any()
    repaired = build_clean_dataframe(raw_records, datetime(2026, 8, 6))
    assert_frame_equal(baseline, repaired)
