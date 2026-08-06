from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from core.config import Settings
from core.utils import first_sentence, normalize_whitespace, write_json
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm


MIN_TEST_SET_SIZE = 30
TARGET_TEST_SET_SIZE = 42
QUESTION_PROMPT_VERSION = "retrieval-validated-english-scholar-v3"
_REQUIRED_COLUMNS = {"paper_id", "title", "summary"}
_QUESTION_TEMPLATES = {
    "authors": ["Who authored the study focused on {topic}?", "Who authored research about {topic}?"],
    "publication_date": [
        "When was the study about {topic} published?",
        "What is the publication date of the work on {topic}?",
    ],
    "categories": ["What categories apply to research on {topic}?", "Which subjects are listed for the work on {topic}?"],
    "publisher": ["Which publisher is listed for the work on {topic}?", "Who published the study about {topic}?"],
    "doi": ["What DOI identifies the research on {topic}?", "Give the DOI for the study about {topic}."],
    "landing_page": [
        "What is the DOI landing-page URL for research on {topic}?",
        "Where can the DOI record for the study about {topic} be found?",
    ],
    "pdf_url": ["Where is the PDF URL for the work on {topic}?", "What PDF link is recorded for research about {topic}?"],
    "summary": ["What is the main point of research on {topic}?", "According to its abstract, what does the study about {topic} describe?"],
}
_GENERIC_TOPIC_WORDS = {
    "a", "an", "and", "application", "applications", "based", "data", "for", "in", "learning", "machine",
    "of", "on", "paper", "research", "study", "system", "the", "to", "using", "with",
}


class _GeneratedQuestion(BaseModel):
    question: str = Field(description="One natural-language factual question.")


def _text(value: object) -> str:
    return normalize_whitespace(value) if isinstance(value, str) else ""


def frozen_set_hash(samples: list[dict[str, Any]]) -> str:
    serialized = json.dumps(samples, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _topic_anchor(row: pd.Series) -> str:
    """Create a short semantic topic without exposing the full paper title."""
    def meaningful_words(value: str) -> list[str]:
        return [
            word
            for word in re.findall(r"[\w-]+", value.lower())
            if len(word) > 2 and not word.isdigit() and word not in _GENERIC_TOPIC_WORDS
        ]

    title_words = meaningful_words(_text(row["title"]))
    if len(title_words) >= 2:
        return " ".join(title_words[:5])
    summary_words = meaningful_words(first_sentence(_text(row["summary"])))
    return " ".join(summary_words[:5]) or "the paper's research problem"


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
        topic = _topic_anchor(row)
        for kind, ground_truth in _question_candidates(row).items():
            template = _QUESTION_TEMPLATES[kind][len(candidates_by_kind[kind]) % len(_QUESTION_TEMPLATES[kind])]
            candidates_by_kind[kind].append((template.format(topic=topic), ground_truth, row["paper_id"]))

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


def _hard_question_tasks(df: pd.DataFrame, count: int) -> list[tuple[str, str, str, str, str]]:
    """Choose one varied, answerable fact per paper before revisiting any paper."""
    eligible = df.copy()
    for column in _REQUIRED_COLUMNS:
        eligible[column] = eligible[column].map(_text)
    eligible = eligible.loc[
        (eligible["paper_id"] != "") & (eligible["title"] != "") & (eligible["summary"] != "")
    ].drop_duplicates(subset="paper_id", keep="first")
    eligible = eligible.sort_values("paper_id", kind="stable").reset_index(drop=True)

    field_options = (
        ("summary", ""),
        ("authors", "authors_joined"),
        ("publication_date", "published"),
        ("publisher", "comment"),
    )
    tasks: list[tuple[str, str, str, str, str]] = []
    for row_number, (_, row) in enumerate(eligible.iterrows()):
        preferred = row_number % len(field_options)
        for shift in range(len(field_options)):
            kind, field = field_options[(preferred + shift) % len(field_options)]
            answer = first_sentence(_text(row["summary"])) if kind == "summary" else _text(row.get(field, ""))
            if answer:
                tasks.append((kind, row["paper_id"], row["title"], row["summary"], answer))
                break
        if len(tasks) == count:
            return tasks
    return tasks


def _generate_question(
    llm,
    kind: str,
    title: str,
    summary: str,
    answer: str,
    retry_feedback: str = "",
) -> str:
    task_instruction = {
        "summary": "Ask about the central problem, method, finding, or application described in the abstract.",
        "authors": "Ask who conducted the work, using research details from the abstract as the clue.",
        "publication_date": "Ask when the work was published, using research details from the abstract as the clue.",
        "publisher": "Ask which publisher issued the work, using research details from the abstract as the clue.",
    }[kind]
    prompt = f"""
Create one difficult but answerable factual question for an English scholarly RAG benchmark.

Paper title (context only; never reveal it): {title}
Abstract: {summary}
Reference answer (context only; never reveal it): {answer}
Requested answer type: {kind}

{task_instruction}
Rules:
- Do not mention the title, DOI, URL, author names, publisher name, date, or reference answer.
- Do not repeat the complete title as a phrase. Individual scientific terms are allowed
  only when they are also explained by the abstract.
- Paraphrase the abstract; do not copy a phrase of more than six consecutive words.
- Use concrete details from the abstract so semantic retrieval can find the document.
- Ask exactly one fluent question in English. The source corpus and embedding model
  are English, so retain two to four distinctive scientific terms from the abstract
  while still paraphrasing the wording.
- Return only the question.
{retry_feedback}
""".strip()
    result = llm.with_structured_output(_GeneratedQuestion).invoke(prompt)
    question = _text(result.question)
    lowered = question.casefold()
    if len(question) < 20 or _text(title).casefold() in lowered or _text(answer).casefold() in lowered:
        raise ValueError("Generated question leaked a title/reference answer or was too short.")
    return question


def _is_retrievable(question: str, paper_id: str, index: LocalEmbeddingIndex | None) -> bool:
    if index is None:
        return True
    return paper_id in {result.paper_id for result in index.search(question, top_k=index.settings.top_k)}


def build_llm_generated_test_set(
    df: pd.DataFrame,
    output_path: Path | str,
    settings: Settings,
    question_count: int = TARGET_TEST_SET_SIZE,
    provenance_path: Path | str | None = None,
    retrieval_index: LocalEmbeddingIndex | None = None,
) -> list[dict[str, Any]]:
    """Freeze hard, non-template questions generated by the configured LLM.

    The LLM only writes questions. Ground truths and document IDs are copied
    from the clean dataframe, preventing any model-generated answer drift.
    """
    tasks = _hard_question_tasks(df, question_count)
    if len(tasks) < MIN_TEST_SET_SIZE:
        raise ValueError(f"Only {len(tasks)} LLM-generation tasks are available; at least {MIN_TEST_SET_SIZE} are required.")

    llm = build_llm(settings=settings, temperature=0.0)
    samples: list[dict[str, Any]] = []
    for number, (kind, paper_id, title, summary, ground_truth) in enumerate(tasks, start=1):
        question: str | None = None
        last_error: Exception | None = None
        retry_feedback = ""
        for _ in range(5):
            try:
                candidate = _generate_question(llm, kind, title, summary, ground_truth, retry_feedback)
                if not _is_retrievable(candidate, paper_id, retrieval_index):
                    raise ValueError("Generated question did not retrieve its ground-truth paper in top-k.")
                question = candidate
                break
            except Exception as error:  # pragma: no cover - provider-dependent
                last_error = error
                retry_feedback = (
                    "Previous candidate was rejected. Rephrase it now: do not repeat the full title or answer, "
                    "and use different, concrete clues from the abstract."
                )
        if question is None:
            raise RuntimeError(f"Could not generate a valid hard question for {paper_id}.") from last_error
        samples.append(
            {
                "id": f"q{number}",
                "question_type": "factual",
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [paper_id],
            }
        )
    write_json(Path(output_path), samples)
    if provenance_path is not None:
        clean_payload = df.to_dict(orient="records")
        clean_hash = hashlib.sha256(
            json.dumps(clean_payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        write_json(
            Path(provenance_path),
            {
                "generator_provider": settings.llm_provider,
                "generator_model": settings.model_name,
                "prompt_version": QUESTION_PROMPT_VERSION,
                "question_count": len(samples),
                "retrieval_validation": {
                    "enabled": retrieval_index is not None,
                    "top_k": settings.top_k if retrieval_index is not None else None,
                    "all_ground_truth_docs_retrievable": retrieval_index is not None,
                },
                "clean_data_sha256": clean_hash,
                "test_set_sha256": frozen_set_hash(samples),
            },
        )
    return samples
