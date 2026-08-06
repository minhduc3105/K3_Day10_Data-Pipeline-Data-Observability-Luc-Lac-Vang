from __future__ import annotations

from dataclasses import dataclass
import re

from core.config import Settings
from core.utils import first_sentence
from retrieval.index import LocalEmbeddingIndex, SearchResult


@dataclass(frozen=True)
class AnswerResult:
    question: str
    answer: str
    retrieved_doc_ids: list[str]
    retrieved_contexts: list[str]
    retrieved_titles: list[str]


def _extract_answer(question: str, top_result: SearchResult) -> str:
    lowered = question.casefold()
    metadata = top_result.metadata
    if any(phrase in lowered for phrase in ("who authored", "list the authors", "who conducted", "tác giả", "ai là những người")):
        return metadata["authors_joined"]
    if any(phrase in lowered for phrase in ("when was", "publication date", "published on", "ngày xuất bản", "xuất bản vào ngày")):
        return metadata["published"]
    if any(phrase in lowered for phrase in ("what categories", "which subjects", "danh mục", "chủ đề")):
        return metadata["categories_joined"]
    if "publisher" in lowered or "nhà xuất bản" in lowered:
        return str(metadata.get("publisher", ""))
    return first_sentence(metadata["summary"])


def answer_question(question: str, settings: Settings, index: LocalEmbeddingIndex, top_k: int | None = None) -> AnswerResult:
    title_match = re.search(r"'([^']+)'", question)
    exact = index.lookup(title_match.group(1)) if title_match else None
    retrieved = index.search(question, top_k=top_k)
    if exact:
        exact_result = SearchResult(
            paper_id=exact["paper_id"], title=exact["title"], score=1.0,
            content=exact["content"], metadata=exact["metadata"],
        )
        retrieved = [exact_result] + [item for item in retrieved if item.paper_id != exact_result.paper_id]
        retrieved = retrieved[: (top_k or settings.top_k)]
    answer = _extract_answer(question, retrieved[0]) if retrieved else "I don't know from the indexed corpus."
    return AnswerResult(
        question=question,
        answer=answer,
        retrieved_doc_ids=[item.paper_id for item in retrieved],
        retrieved_contexts=[item.content for item in retrieved],
        retrieved_titles=[item.title for item in retrieved],
    )
