from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


MIN_TEST_SET_SIZE = 30
TARGET_TEST_SET_SIZE = 42
_REQUIRED_COLUMNS = {"paper_id", "title", "summary"}
_QUESTION_TEMPLATES = {
    "authors": ["Who authored '{title}'?", "Name the author(s) of '{title}'."],
    "publication_date": ["When was '{title}' published?", "What is the publication date of '{title}'?"],
    "categories": ["What categories does '{title}' belong to?", "Which subjects are listed for '{title}'?"],
    "publisher": ["Which publisher is listed for '{title}'?", "Who published '{title}'?"],
    "doi": ["What DOI identifies '{title}'?", "Give the DOI for '{title}'."],
    "landing_page": [
        "What is the DOI landing-page URL for '{title}'?",
        "Where can the DOI record for '{title}' be found?",
    ],
    "pdf_url": ["Where is the PDF URL for '{title}'?", "What PDF link is recorded for '{title}'?"],
    "summary": ["What is the main point of '{title}'?", "According to its abstract, what does '{title}' describe?"],
}


def _text(value: object) -> str:
    return normalize_whitespace(value) if isinstance(value, str) else ""


def _question_candidates(row: pd.Series) -> dict[str, str]:
    """Create varied, answerable factual questions for one cleaned paper."""
    title = _text(row["title"])
    candidates: dict[str, str] = {}

    authors = _text(row.get("authors_joined", ""))
    if authors:
        candidates["authors"] = authors

    published = _text(row.get("published", ""))
    if published:
        candidates["publication_date"] = published

    categories = _text(row.get("categories_joined", ""))
    if categories:
        candidates["categories"] = categories

    publisher = _text(row.get("comment", ""))
    if publisher:
        candidates["publisher"] = publisher

    paper_id = _text(row["paper_id"])
    if paper_id:
        candidates["doi"] = paper_id

    landing_page = _text(row.get("abs_url", ""))
    if landing_page:
        candidates["landing_page"] = landing_page

    pdf_url = _text(row.get("pdf_url", ""))
    if pdf_url:
        candidates["pdf_url"] = pdf_url

    summary_answer = first_sentence(_text(row["summary"]))
    if summary_answer:
        candidates["summary"] = summary_answer
    return candidates


def build_test_set(df: pd.DataFrame, output_path: Path | str) -> list[dict[str, Any]]:
    """Create and persist a deterministic, varied factual evaluation set.

    The dataframe is sorted by ``paper_id`` before generation so identical clean
    inputs always produce the same frozen question set. Candidates are selected
    round-robin by information type to avoid filling the set with only author
    and date questions. Each ground truth is copied from cleaned data.
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

    candidates_by_kind: dict[str, list[tuple[str, str, str]]] = {
        "authors": [],
        "publication_date": [],
        "categories": [],
        "publisher": [],
        "doi": [],
        "landing_page": [],
        "pdf_url": [],
        "summary": [],
    }
    for _, row in eligible.iterrows():
        for kind, ground_truth in _question_candidates(row).items():
            template = _QUESTION_TEMPLATES[kind][len(candidates_by_kind[kind]) % len(_QUESTION_TEMPLATES[kind])]
            candidates_by_kind[kind].append((template.format(title=row["title"]), ground_truth, row["paper_id"]))

    available_candidates = sum(len(candidates) for candidates in candidates_by_kind.values())
    target_size = min(TARGET_TEST_SET_SIZE, available_candidates)
    if target_size < MIN_TEST_SET_SIZE:
        raise ValueError(
            f"Could only create {target_size} answerable questions; at least {MIN_TEST_SET_SIZE} are required."
        )

    samples: list[dict[str, Any]] = []
    candidate_offsets = {kind: 0 for kind in candidates_by_kind}
    while len(samples) < target_size:
        added_in_round = False
        for kind, candidates in candidates_by_kind.items():
            offset = candidate_offsets[kind]
            if offset >= len(candidates):
                continue
            question, ground_truth, paper_id = candidates[offset]
            samples.append(
                {
                    "id": f"q{len(samples) + 1}",
                    "question_type": "factual",
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper_id],
                }
            )
            candidate_offsets[kind] += 1
            added_in_round = True
            if len(samples) == target_size:
                write_json(Path(output_path), samples)
                return samples
        if not added_in_round:  # pragma: no cover - guarded by available_candidates above
            break
    raise RuntimeError("Evaluation-set generation stopped before reaching its target size.")
