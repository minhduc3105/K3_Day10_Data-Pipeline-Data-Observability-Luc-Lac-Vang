from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.utils import normalize_whitespace, write_json


def _rebuild_text_for_embedding(row: pd.Series) -> str:
    return normalize_whitespace(
        "\n".join(
            [
                f"Title: {row.get('title', '')}",
                f"Authors: {row.get('authors_joined', '')}",
                f"Categories: {row.get('categories_joined', '')}",
                f"Published: {row.get('published', '')}",
                f"Summary: {row.get('summary', '')}",
            ]
        )
    )


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate nhieu dang data corruption tren clean dataframe."""
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")

    corrupted = df.copy().reset_index(drop=True)
    log: dict[str, object] = {
        "input_rows": int(len(df)),
        "operations": [],
    }

    sort_cols = [col for col in ["published", "paper_id"] if col in corrupted.columns]
    if sort_cols:
        corrupted = corrupted.sort_values(sort_cols, ascending=[False] * len(sort_cols)).reset_index(drop=True)

    drop_count = max(1, min(3, len(corrupted) // 6))
    dropped_ids = corrupted.head(drop_count)["paper_id"].astype(str).tolist()
    corrupted = corrupted.iloc[drop_count:].reset_index(drop=True)
    log["operations"].append({"type": "drop_latest_records", "count": drop_count, "paper_ids": dropped_ids})

    blank_count = max(1, min(3, len(corrupted) // 5))
    blank_indices = list(range(0, min(blank_count, len(corrupted))))
    for idx in blank_indices:
        corrupted.at[idx, "summary"] = ""
        corrupted.at[idx, "summary_chars"] = 0
    log["operations"].append(
        {
            "type": "blank_summary",
            "count": len(blank_indices),
            "paper_ids": corrupted.loc[blank_indices, "paper_id"].astype(str).tolist() if blank_indices else [],
        }
    )

    noise_indices = list(range(blank_count, min(blank_count + 3, len(corrupted))))
    noise = " DATA_QUALITY_NOISE repeated irrelevant tokens 9999"
    for idx in noise_indices:
        corrupted.at[idx, "summary"] = normalize_whitespace(f"{corrupted.at[idx, 'summary']} {noise}")
        corrupted.at[idx, "summary_chars"] = len(str(corrupted.at[idx, "summary"]))
    log["operations"].append(
        {
            "type": "inject_noise",
            "count": len(noise_indices),
            "paper_ids": corrupted.loc[noise_indices, "paper_id"].astype(str).tolist() if noise_indices else [],
        }
    )

    truncate_indices = list(range(blank_count + len(noise_indices), min(blank_count + len(noise_indices) + 3, len(corrupted))))
    for idx in truncate_indices:
        corrupted.at[idx, "title"] = str(corrupted.at[idx, "title"])[:18].rstrip()
    log["operations"].append(
        {
            "type": "truncate_title",
            "count": len(truncate_indices),
            "paper_ids": corrupted.loc[truncate_indices, "paper_id"].astype(str).tolist() if truncate_indices else [],
        }
    )

    stale_indices = list(range(max(0, len(corrupted) - 3), len(corrupted)))
    for idx in stale_indices:
        corrupted.at[idx, "published"] = "2000-01-01"
        corrupted.at[idx, "age_days"] = 9999
    log["operations"].append(
        {
            "type": "make_stale_publication_date",
            "count": len(stale_indices),
            "paper_ids": corrupted.loc[stale_indices, "paper_id"].astype(str).tolist() if stale_indices else [],
        }
    )

    duplicate_count = max(1, min(2, len(corrupted) // 8))
    duplicates = corrupted.tail(duplicate_count).copy()
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    log["operations"].append(
        {
            "type": "add_duplicate_rows",
            "count": int(len(duplicates)),
            "paper_ids": duplicates["paper_id"].astype(str).tolist(),
        }
    )

    corrupted["summary_chars"] = corrupted["summary"].fillna("").astype(str).str.len()
    corrupted["text_for_embedding"] = corrupted.apply(_rebuild_text_for_embedding, axis=1)
    log["output_rows"] = int(len(corrupted))
    write_json(Path(output_log_path), log)
    return corrupted.reset_index(drop=True)
