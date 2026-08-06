from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


MIN_TEST_SET_SIZE = 30
_REQUIRED_COLUMNS = {"paper_id", "title", "summary"}


def _text(value: object) -> str:
    return normalize_whitespace(value) if isinstance(value, str) else ""


def _question_candidates(row: pd.Series) -> list[tuple[str, str]]:
    """Create answerable factual questions for one cleaned paper."""
    title = _text(row["title"])
    candidates: list[tuple[str, str]] = []

    authors = _text(row.get("authors_joined", ""))
    if authors:
        candidates.append((f"Who authored '{title}'?", authors))

    published = _text(row.get("published", ""))
    if published:
        candidates.append((f"When was '{title}' published?", published))

    categories = _text(row.get("categories_joined", ""))
    if categories:
        candidates.append((f"What categories does '{title}' belong to?", categories))

    summary_answer = first_sentence(_text(row["summary"]))
    if summary_answer:
        candidates.append((f"What is the main point of '{title}'?", summary_answer))
    return candidates


def build_test_set(df: pd.DataFrame, output_path: Path | str) -> list[dict[str, Any]]:
    """Create and persist a deterministic 30-question factual evaluation set.

    The dataframe is sorted by ``paper_id`` before generation so identical clean
    inputs always produce the same frozen question set. Each ground truth is
    copied verbatim from a cleaned field (or the first summary sentence).
    """
    missing_columns = _REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing columns: {', '.join(sorted(missing_columns))}.")

    eligible = df.copy()
    for column in _REQUIRED_COLUMNS:
        eligible[column] = eligible[column].map(_text)
    eligible = eligible.loc[
        (eligible["paper_id"] != "") & (eligible["title"] != "") & (eligible["summary"] != "")
    ]
    eligible = eligible.drop_duplicates(subset="paper_id", keep="first").sort_values("paper_id", kind="stable")

    samples: list[dict[str, Any]] = []
    for _, row in eligible.iterrows():
        for question, ground_truth in _question_candidates(row):
            samples.append(
                {
                    "id": f"q{len(samples) + 1}",
                    "question_type": "factual",
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [row["paper_id"]],
                }
            )
            if len(samples) == MIN_TEST_SET_SIZE:
                write_json(Path(output_path), samples)
                return samples

    raise ValueError(
        f"Could only create {len(samples)} answerable questions; at least {MIN_TEST_SET_SIZE} are required."
    )
