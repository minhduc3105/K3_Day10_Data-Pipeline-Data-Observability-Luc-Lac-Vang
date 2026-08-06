from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

MIN_DOCUMENTS = 5
PAPERS_PER_TYPE = 3

# Question templates are worded to match the extractors in `retrieval.qa._extract_answer`.
# The title is wrapped in single quotes so `answer_question` can do an exact lookup.
QUESTION_TYPES = (
    ("factual", "authors", "Who authored '{title}'?"),
    ("factual", "date", "When was '{title}' published?"),
    ("factual", "summary", "What is the main contribution reported in '{title}'?"),
    ("factual", "categories", "What categories are assigned to '{title}'?"),
)


def _ground_truth(row: pd.Series, kind: str) -> str:
    """Return the answer `retrieval.qa` should produce for this question kind."""
    if kind == "authors":
        return str(row["authors_joined"])
    if kind == "date":
        return str(row["published"])
    if kind == "categories":
        return str(row["categories_joined"])
    return first_sentence(str(row["summary"]))


def _select_indices(total: int, count: int, offset: int = 0) -> list[int]:
    """Pick evenly spaced row positions so the frozen set stays deterministic.

    `offset` rotates the selection so each question type lands on different
    papers, widening document coverage across the eval set.
    """
    if count >= total:
        return list(range(total))
    step = total / count
    return [(int(position * step) + offset) % total for position in range(count)]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a frozen evaluation set from the cleaned dataframe."""
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} documents to build a test set, got {len(df)}.")

    # An ASCII apostrophe in the title would break the '...' exact-lookup regex in qa.py.
    usable = df[~df["title"].str.contains("'", regex=False)].reset_index(drop=True)
    if len(usable) < MIN_DOCUMENTS:
        raise ValueError(f"Only {len(usable)} documents have quote-safe titles; need {MIN_DOCUMENTS}.")

    samples: list[dict[str, Any]] = []
    for type_index, (question_type, kind, template) in enumerate(QUESTION_TYPES):
        for position in _select_indices(len(usable), PAPERS_PER_TYPE, offset=type_index):
            row = usable.iloc[position]
            ground_truth = _ground_truth(row, kind)
            # Skip questions the corpus cannot answer (e.g. Crossref omits `subject`).
            if not ground_truth:
                continue
            samples.append(
                {
                    "id": f"q{len(samples) + 1}",
                    "question_type": question_type,
                    "question": template.format(title=row["title"]),
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [str(row["paper_id"])],
                }
            )

    if len(samples) < MIN_DOCUMENTS:
        raise ValueError(f"Built only {len(samples)} samples; need at least {MIN_DOCUMENTS}.")

    write_json(output_path, samples)
    return samples
