from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from core.utils import read_json, write_json


def _frozen_doc_ids(test_set_path: Path | str | None, available_ids: set[str]) -> list[str]:
    if test_set_path is None:
        return sorted(available_ids)
    test_set = read_json(Path(test_set_path))
    frozen_ids = [
        str(doc_id)
        for item in test_set
        if isinstance(item, dict)
        for doc_id in item.get("ground_truth_doc_ids", [])
        if str(doc_id) in available_ids
    ]
    return list(dict.fromkeys(frozen_ids))


def _rebuild_embedding_text(df: pd.DataFrame) -> pd.Series:
    title = df["title"].fillna("").astype(str)
    authors = df["authors_joined"].fillna("").astype(str)
    summary = df["summary"].fillna("").astype(str)
    return "Title: " + title + " | Authors: " + authors + " | Summary: " + summary


def corrupt_clean_dataframe(
    df: pd.DataFrame,
    output_log_path: Path | str,
    test_set_path: Path | str | None = None,
) -> pd.DataFrame:
    """Apply deterministic corruption that always overlaps frozen evaluation docs.

    The four scenarios make changes visible to content, freshness, and quality
    checks while preserving the original dataframe supplied by the caller.
    """
    required_columns = {"paper_id", "title", "summary", "authors_joined", "published"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing columns: {', '.join(sorted(missing_columns))}.")

    corrupted = df.copy(deep=True)
    corrupted["paper_id"] = corrupted["paper_id"].fillna("").astype(str)
    available_ids = set(corrupted.loc[corrupted["paper_id"] != "", "paper_id"])
    target_ids = _frozen_doc_ids(test_set_path, available_ids)
    if not target_ids:
        raise ValueError("No frozen-test document IDs were found in the clean dataframe.")

    # Blank several frozen documents, not just one. A document with no summary
    # has no usable retrieval context and is intentionally excluded by the
    # indexer; this makes the downstream retrieval impact measurable.
    blank_ids = target_ids[: min(4, len(target_ids))]
    stale_id = target_ids[4 % len(target_ids)]
    duplicate_id = target_ids[5 % len(target_ids)]
    noise_id = target_ids[6 % len(target_ids)]

    blank_mask = corrupted["paper_id"].isin(blank_ids)
    corrupted.loc[blank_mask, "summary"] = ""

    stale_mask = corrupted["paper_id"] == stale_id
    corrupted.loc[stale_mask, "published"] = "2000-01-01"
    corrupted.loc[stale_mask, "age_days"] = (datetime.now(UTC).date() - datetime(2000, 1, 1).date()).days

    duplicate_rows = corrupted.loc[corrupted["paper_id"] == duplicate_id].copy()
    corrupted = pd.concat([corrupted, duplicate_rows], ignore_index=True)
    corrupted["text_for_embedding"] = _rebuild_embedding_text(corrupted)

    noise_mask = corrupted["paper_id"] == noise_id
    noise = " [CORRUPTION_NOISE] lorem-ipsum ### unrelated-token-98765"
    corrupted.loc[noise_mask, "text_for_embedding"] += noise

    log = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_rows": len(df),
        "corrupted_rows": len(corrupted),
        "frozen_test_set": str(test_set_path) if test_set_path else None,
        "frozen_doc_ids_available": target_ids,
        "scenarios": [
            {
                "name": "blank_summary",
                "paper_ids": blank_ids,
                "rows_affected": int(blank_mask.sum()),
                "retrieval_expectation": "Documents without a summary are excluded from the retrieval index.",
            },
            {
                "name": "stale_date",
                "paper_ids": [stale_id],
                "new_published": "2000-01-01",
                "rows_affected": int(stale_mask.sum()),
            },
            {"name": "duplicate_id", "paper_ids": [duplicate_id], "rows_added": len(duplicate_rows)},
            {"name": "embedding_noise", "paper_ids": [noise_id], "rows_affected": int(noise_mask.sum())},
        ],
    }
    write_json(Path(output_log_path), log)
    return corrupted
