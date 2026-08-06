from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import ensure_parent, first_sentence, write_json


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao evaluation set tu cleaned dataframe."""
    required = {"paper_id", "title", "summary", "authors_joined", "categories_joined", "published"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("Cannot build test set from an empty dataframe.")

    candidates = df.copy()
    candidates = candidates[candidates["summary"].astype(str).str.len() >= 40]
    if candidates.empty:
        raise ValueError("Cannot build test set without usable summaries.")

    selected = candidates.head(min(6, len(candidates)))
    samples: list[dict[str, Any]] = []

    def add_sample(row: pd.Series, question_type: str, question: str, ground_truth: str) -> None:
        if not ground_truth:
            return
        samples.append(
            {
                "id": f"{question_type}-{len(samples) + 1:03d}",
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )

    for _, row in selected.iterrows():
        title = str(row["title"])
        add_sample(
            row,
            "summary",
            f"What is the main point of '{title}'?",
            first_sentence(str(row["summary"])),
        )
        add_sample(
            row,
            "authors",
            f"Who authored '{title}'?",
            str(row["authors_joined"]),
        )
        add_sample(
            row,
            "date",
            f"When was '{title}' published?",
            str(row["published"]),
        )
        add_sample(
            row,
            "categories",
            f"What categories are listed for '{title}'?",
            str(row["categories_joined"]),
        )

    ensure_parent(output_path)
    write_json(output_path, samples)
    return samples
