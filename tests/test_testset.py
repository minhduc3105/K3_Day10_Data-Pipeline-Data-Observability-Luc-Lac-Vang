from __future__ import annotations

import json

import pandas as pd

from evaluation.testset import MIN_TEST_SET_SIZE, build_test_set


def test_build_test_set_is_factual_deterministic_and_persisted(tmp_path) -> None:
    dataframe = pd.DataFrame(
        [
            {
                "paper_id": f"10.1000/{index:02d}",
                "title": f"Paper {index}",
                "summary": f"Paper {index} explains a factual result. A second sentence adds context.",
                "authors_joined": f"Author {index}",
                "published": "2026-08-01",
                "categories_joined": "Machine Learning",
                "comment": f"Publisher {index}",
            }
            for index in range(8)
        ]
    )
    output_path = tmp_path / "test_set.json"

    samples = build_test_set(dataframe.sample(frac=1, random_state=7), output_path)

    assert len(samples) >= MIN_TEST_SET_SIZE
    assert [sample["id"] for sample in samples] == [f"q{index}" for index in range(1, len(samples) + 1)]
    assert all(sample["question_type"] == "factual" for sample in samples)
    assert all(len(sample["ground_truth_doc_ids"]) == 1 for sample in samples)
    assert samples[0]["question"] == "Who authored 'Paper 0'?"
    assert samples[1]["question"] == "When was 'Paper 0' published?"
    assert samples[2]["question"] == "What categories does 'Paper 0' belong to?"
    assert json.loads(output_path.read_text(encoding="utf-8")) == samples


def test_build_test_set_requires_thirty_answerable_questions(tmp_path) -> None:
    dataframe = pd.DataFrame(
        [{"paper_id": "10.1/one", "title": "One", "summary": "Only one factual sentence."}]
    )

    try:
        build_test_set(dataframe, tmp_path / "test_set.json")
    except ValueError as error:
        assert "at least 30" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Expected a ValueError for an undersized dataset.")
