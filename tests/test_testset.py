from __future__ import annotations

import json

import pandas as pd

from evaluation.testset import MIN_TEST_SET_SIZE, _generate_question, _is_retrievable, build_test_set, frozen_set_hash


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
            for index in range(10)
        ]
    )
    output_path = tmp_path / "test_set.json"

    samples = build_test_set(dataframe.sample(frac=1, random_state=7), output_path)

    assert len(samples) >= MIN_TEST_SET_SIZE
    assert [sample["id"] for sample in samples] == [f"q{index}" for index in range(1, len(samples) + 1)]
    assert all(sample["question_type"] == "factual" for sample in samples)
    assert all(len(sample["ground_truth_doc_ids"]) == 1 for sample in samples)
    assert samples[0]["question"].startswith("Who authored")
    assert samples[1]["question"].startswith("When was")
    assert "Paper 0" not in samples[0]["question"]
    assert json.loads(output_path.read_text(encoding="utf-8")) == samples


def test_build_test_set_requires_thirty_answerable_questions(tmp_path) -> None:
    dataframe = pd.DataFrame(
        [{"paper_id": "10.1/one", "title": "One", "summary": "Only one factual sentence."}]
    )

    try:
        build_test_set(dataframe, tmp_path / "test_set.json")
    except ValueError as error:
        assert "at least 10" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Expected a ValueError for an undersized dataset.")


def test_llm_question_validation_rejects_title_or_answer_leakage() -> None:
    class FakeLLM:
        def __init__(self, question):
            self.question = question

        def with_structured_output(self, _):
            return self

        def invoke(self, _):
            return type("Result", (), {"question": self.question})()

    safe_question = _generate_question(
        FakeLLM("Which research challenge is addressed by integrating data-driven models with development workflows?"),
        "summary",
        "Secret Paper Title",
        "Abstract text",
        "Secret answer",
    )
    assert safe_question.startswith("Which research")
    assert _generate_question(
        FakeLLM("What does Secret Paper Title say about its stated research problem?"),
        "summary",
        "Secret Paper Title",
        "Abstract",
        "Secret answer",
    ).startswith("What does Secret")
    with __import__("pytest").raises(ValueError):
        _generate_question(FakeLLM("Does the study conclude Secret answer?"), "summary", "Title", "Abstract", "Secret answer")
    assert len(frozen_set_hash([{"id": "q1"}])) == 64


def test_retrieval_validation_requires_ground_truth_document() -> None:
    class FakeIndex:
        settings = type("Settings", (), {"top_k": 4})()

        def search(self, *_args, **_kwargs):
            return [type("Result", (), {"paper_id": "10.1/right"})()]

    assert _is_retrievable("A grounded query", "10.1/right", FakeIndex())
    assert not _is_retrievable("A grounded query", "10.1/wrong", FakeIndex())
