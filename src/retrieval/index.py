from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import chromadb
import pandas as pd

from core.config import Settings
from core.utils import normalize_whitespace, read_json, safe_slug, write_json
from retrieval.embeddings import MiniLMEmbeddings


_CHUNK_CHARS = 720
_SEMANTIC_WEIGHT = 0.84
_LEXICAL_WEIGHT = 1.0 - _SEMANTIC_WEIGHT


@dataclass(frozen=True)
class SearchResult:
    paper_id: str
    title: str
    score: float
    content: str
    metadata: dict[str, Any]


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return normalize_whitespace(str(value))


def _split_summary(summary: str, max_chars: int = _CHUNK_CHARS) -> list[str]:
    """Split a long abstract on sentence boundaries without losing a sentence."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", summary) if part.strip()]
    if not sentences:
        return []
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w-]+", value.casefold()) if len(token) > 2}


def _lexical_score(query: str, content: str) -> float:
    """A small BM25-like overlap feature to stabilize precise scientific terms."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    matched = len(query_tokens & _tokens(content))
    return matched / len(query_tokens)


class LocalEmbeddingIndex:
    def __init__(
        self,
        settings: Settings,
        collection_name: str,
        documents: list[dict[str, Any]],
        persist_path: Path,
    ):
        self.settings = settings
        self.collection_name = collection_name
        self.documents = documents
        self.persist_path = persist_path
        self.embedding_backend = "chroma"
        self.embedding_model = MiniLMEmbeddings(settings.embedding_model)
        self.client = chromadb.PersistentClient(path=str(persist_path))
        self.collection = self.client.get_collection(name=collection_name)
        self.documents_by_paper_id: dict[str, dict[str, Any]] = {}
        self.documents_by_title: dict[str, dict[str, Any]] = {}
        for document in documents:
            if document["metadata"].get("chunk_type") != "paper":
                continue
            self.documents_by_paper_id.setdefault(document["paper_id"].lower(), document)
            self.documents_by_title.setdefault(document["title"].lower(), document)

    @staticmethod
    def _build_documents(df: pd.DataFrame) -> list[dict[str, Any]]:
        """Index paper, abstract, and metadata chunks while preserving one paper ID.

        A metadata question (author/date/publisher) should not compete with a
        full abstract, and a long abstract should not hide a relevant sentence.
        Every chunk therefore repeats the title and retains the same paper_id.
        """
        documents: list[dict[str, Any]] = []
        for row_index, row in enumerate(df.to_dict(orient="records")):
            paper_id = _text(row.get("paper_id"))
            title = _text(row.get("title"))
            summary = _text(row.get("summary"))
            # The clean-data contract requires both title and summary. If a
            # corrupted record loses its summary, it must not enter retrieval
            # with title-only metadata pretending to be valid evidence.
            if not paper_id or not title or not summary:
                continue
            metadata = {
                "paper_id": paper_id,
                "title": title,
                "published": _text(row.get("published")),
                "authors_joined": _text(row.get("authors_joined")),
                "categories_joined": _text(row.get("categories_joined")),
                "summary": summary,
                "publisher": _text(row.get("comment")),
                "abs_url": _text(row.get("abs_url")),
                "pdf_url": _text(row.get("pdf_url")),
            }
            # ``paper_id`` intentionally stays unchanged for quality/corruption
            # checks. Chroma's internal IDs must still be unique for duplicate
            # rows, so the physical row index is added only to record_id.
            record_key = f"{paper_id}::row::{row_index}"

            def add_chunk(chunk_type: str, chunk_index: int, content: str) -> None:
                documents.append(
                    {
                        "record_id": f"{record_key}::{chunk_type}::{chunk_index}",
                        "paper_id": paper_id,
                        "title": title,
                        "content": content,
                        "metadata": {**metadata, "chunk_type": chunk_type, "chunk_index": chunk_index},
                    }
                )

            paper_text = (
                f"Title: {title}\n"
                f"Authors: {metadata['authors_joined']}\n"
                f"Publisher: {metadata['publisher']}\n"
                f"Published: {metadata['published']}\n"
                f"Categories: {metadata['categories_joined']}\n"
                f"DOI: {paper_id}\n"
                f"Abstract: {summary}"
            )
            add_chunk("paper", 0, paper_text)
            add_chunk(
                "metadata",
                0,
                f"Title: {title}. Authors: {metadata['authors_joined']}. Publisher: {metadata['publisher']}. "
                f"Published: {metadata['published']}. Categories: {metadata['categories_joined']}. DOI: {paper_id}.",
            )
            for chunk_index, abstract_chunk in enumerate(_split_summary(summary)):
                add_chunk("abstract", chunk_index, f"Title: {title}\nAbstract: {abstract_chunk}")
        return documents

    @staticmethod
    def _derive_collection_name(settings: Settings, embeddings_output_path: Path | None) -> str:
        if embeddings_output_path is None:
            return settings.baseline_collection_name
        name_map = {
            settings.paths.embeddings_json.resolve(): settings.baseline_collection_name,
            settings.paths.corrupted_embeddings_json.resolve(): settings.corrupted_collection_name,
            settings.paths.repaired_embeddings_json.resolve(): settings.repaired_collection_name,
        }
        return name_map.get(embeddings_output_path.resolve(), safe_slug(embeddings_output_path.stem))

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        settings: Settings,
        embeddings_output_path: Path | None = None,
    ) -> "LocalEmbeddingIndex":
        collection_name = cls._derive_collection_name(settings, embeddings_output_path)
        documents = cls._build_documents(df)
        if not documents:
            raise ValueError("Cannot build an index without valid paper documents.")
        persist_path = settings.paths.chroma_dir
        persist_path.mkdir(parents=True, exist_ok=True)
        embedding_model = MiniLMEmbeddings(settings.embedding_model)
        client = chromadb.PersistentClient(path=str(persist_path))
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass
        collection = client.create_collection(name=collection_name, configuration={"hnsw": {"space": "cosine"}})
        collection.add(
            ids=[document["record_id"] for document in documents],
            embeddings=embedding_model.embed_documents([document["content"] for document in documents]),
            documents=[document["content"] for document in documents],
            metadatas=[document["metadata"] for document in documents],
        )
        manifest_path = embeddings_output_path or settings.paths.embeddings_json
        write_json(
            manifest_path,
            {
                "backend": "chroma",
                "embedding_model": settings.embedding_model,
                "index_strategy": "paper_metadata_and_sentence_chunks_hybrid_rerank_v2",
                "persist_path": str(persist_path),
                "collection_name": collection_name,
                "paper_count": int(df["paper_id"].nunique()),
                "chunk_count": len(documents),
                "documents": documents,
            },
        )
        return cls(settings, collection_name, documents, persist_path)

    @classmethod
    def load(cls, settings: Settings, embeddings_path: Path | None = None) -> "LocalEmbeddingIndex":
        payload = read_json(embeddings_path or settings.paths.embeddings_json)
        return cls(settings, payload["collection_name"], payload["documents"], Path(payload["persist_path"]))

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        requested_k = top_k or self.settings.top_k
        # Fetch a wider chunk pool, then collapse chunks to unique papers.
        candidate_count = min(len(self.documents), max(requested_k * 12, 32))
        results = self.collection.query(
            query_embeddings=[self.embedding_model.embed_query(query)],
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )
        by_paper_id: dict[str, SearchResult] = {}
        for content, metadata, distance in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0],
            strict=False,
        ):
            if not metadata or not content:
                continue
            semantic_score = max(0.0, 1.0 - float(distance or 0.0))
            hybrid_score = _SEMANTIC_WEIGHT * semantic_score + _LEXICAL_WEIGHT * _lexical_score(
                query, f"{metadata.get('title', '')} {content}"
            )
            result = SearchResult(
                paper_id=str(metadata["paper_id"]),
                title=str(metadata["title"]),
                score=hybrid_score,
                content=str(content),
                metadata=dict(metadata),
            )
            existing = by_paper_id.get(result.paper_id)
            if existing is None or result.score > existing.score:
                by_paper_id[result.paper_id] = result
        return sorted(by_paper_id.values(), key=lambda item: item.score, reverse=True)[:requested_k]

    def lookup(self, value: str) -> dict[str, Any] | None:
        needle = value.strip().lower()
        return self.documents_by_paper_id.get(needle) or self.documents_by_title.get(needle)
