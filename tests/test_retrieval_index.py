from __future__ import annotations

import pandas as pd

from retrieval.index import LocalEmbeddingIndex


def test_index_builds_paper_metadata_and_abstract_chunks() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "paper_id": "10.1000/example",
                "title": "Coastal restoration with native plants",
                "summary": "Native grasses stabilize shoreline soil. Community monitoring measures biodiversity recovery.",
                "authors_joined": "A. Researcher",
                "categories_joined": "Ecology",
                "published": "2026-01-02",
                "comment": "Open Science Press",
                "abs_url": "https://doi.org/10.1000/example",
                "pdf_url": "",
            }
        ]
    )

    documents = LocalEmbeddingIndex._build_documents(dataframe)
    chunk_types = {document["metadata"]["chunk_type"] for document in documents}
    assert {"paper", "metadata", "abstract"} <= chunk_types
    assert all(document["paper_id"] == "10.1000/example" for document in documents)
    assert any("Publisher: Open Science Press" in document["content"] for document in documents)


def test_index_excludes_records_without_retrieval_context() -> None:
    dataframe = pd.DataFrame(
        [{"paper_id": "10.1000/blank", "title": "Lost summary", "summary": "", "authors_joined": "A", "categories_joined": "", "published": "", "comment": "", "abs_url": "", "pdf_url": ""}]
    )
    assert LocalEmbeddingIndex._build_documents(dataframe) == []
