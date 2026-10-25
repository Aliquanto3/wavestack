"""V1.2 story 9 (CAP-10): the rank of the expected passage at each stage, the stage at fault,
and the three recorded failure cases of « Où naît l'erreur ».

Pure and read only (AD-1: the figures are the session's, the page draws them): a question of
`content/rag_questions.yaml` names its expected passages by an anchor sentence; a stage's list
holds the passage when one of its items is of the passage's document and contains the anchor.
Nothing is averaged: one question, one run, one verdict (the means are the Evaluate tab's).

The rules, in the order of the chain:

- Chunking: the anchor must be whole in a chunk, else the passage is not in the index
  (`not_indexed`).
- Search (dense and BM25 are one step: the best rank of either counts): absent from every list
  (`missing`), or ranked beyond the context's budget (`ranked_low`).
- Fusion and reranking: absent (`missing`), or fallen by more than `tolerance` ranks from the
  step before (`fell`).
- Context: the passage reached the last list beyond the budget, so the context cut it (`cut`).

The first step at fault is the one designated; a later step that brings the passage back
inside the budget is `rescued_by`. A passage in the middle of three excerpts or more is only
noted (`middle`): models read the ends better, but it is no fault of the chain.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.rag.corpus import (
    Chunk,
    RagPassage,
    RagQuestion,
    chunk_corpus,
    load_rag_content,
    load_rag_questions,
)

FILE = "rag_diagnosis.yaml"
SEARCHES = ("vector_search", "lexical_search")
RANKED = (*SEARCHES, "fusion", "rerank", "context")  # the stages that order passages
DEFAULT_TOLERANCE = 2  # N: the ranks a step may drop the passage before it is at fault
DEFAULT_BUDGET = 3  # k: the excerpts the context keeps
MAX_ITEMS = 50  # per stage, for a list sent by the page
REASONS = ("not_indexed", "missing", "ranked_low", "fell", "cut")


def folded(text: str) -> str:
    """Whitespace collapsed and case dropped: how an anchor is looked for in a chunk."""
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class Listed:
    """One item of a stage's ranked list: its document and its text. `placed`: the position
    in the context (V1.2 story 7: the order may differ from the ranking), when it has one."""

    doc_id: str
    text: str
    placed: int | None = None


@dataclass(frozen=True)
class StageList:
    kind: str
    items: Sequence[Listed]


def holds(item: Listed, passage: RagPassage) -> bool:
    return item.doc_id == passage.doc_id and folded(passage.anchor_text) in folded(item.text)


def rank_in(items: Sequence[Listed], passage: RagPassage) -> int | None:
    """The rank (from 1) of the first item that holds the passage, else `None`."""
    return next((n for n, item in enumerate(items, start=1) if holds(item, passage)), None)


def intact_in(chunks: Sequence[Chunk], passage: RagPassage) -> bool:
    return any(holds(Listed(c.doc_id, c.text), passage) for c in chunks)


def diagnose_passage(
    passage: RagPassage,
    chunks: Sequence[Chunk],
    stages: Sequence[StageList],
    *,
    budget: int = DEFAULT_BUDGET,
    tolerance: int = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """The steps (chunking, then each stage that ordered passages) and the verdict."""
    fault: dict[str, str] | None = None
    steps: list[dict[str, Any]] = []

    def blame(kind: str, reason: str) -> None:
        nonlocal fault
        if fault is None:
            fault = {"kind": kind, "reason": reason}

    by_kind = {s.kind: s for s in stages if s.kind in RANKED}
    ranks: dict[str, int | None] = {}
    ranked_steps: list[dict[str, Any]] = []
    for kind in RANKED:
        stage = by_kind.get(kind)
        if stage is None:
            continue
        rank = rank_in(stage.items, passage)
        ranks[kind] = rank
        ranked_steps.append({"kind": kind, "rank": rank, "of": len(stage.items)})

    # A list item is a chunk the chain did index: the passage found whole in one is whole in
    # the index, whatever the shipped corpus' cut (a working copy, another chunk size).
    intact = any(r is not None for r in ranks.values()) or intact_in(chunks, passage)
    steps.append({"kind": "chunking", "intact": intact, "rank": None, "of": None})
    steps.extend(ranked_steps)
    if not intact:
        blame("chunking", "not_indexed")
    if not ranks:
        # No stage ordered passages (nothing retrieved, nothing in the context): not found.
        blame("context", "missing")

    searched = [k for k in SEARCHES if k in ranks]
    best_search = min((r for k in searched if (r := ranks[k]) is not None), default=None)
    if searched:
        if best_search is None:
            blame(searched[0], "missing")
        elif best_search > budget:
            blame(next(k for k in searched if ranks[k] == best_search), "ranked_low")
    before = best_search
    for kind in ("fusion", "rerank"):
        if kind not in ranks:
            continue
        rank = ranks[kind]
        if rank is None:
            blame(kind, "missing")
        elif before is not None and rank - before > tolerance:
            blame(kind, "fell")
        before = rank if rank is not None else before
    last = next((ranks[k] for k in ("rerank", "fusion") if k in ranks), best_search)
    if "context" in ranks:
        if ranks["context"] is None and last is not None:
            # V1.2 story 7: present in the last ranked list, absent from the context, whatever
            # its rank: past `top_k`, left out by the budget, or cut off with its anchor.
            blame("context", "cut")
        elif ranks["context"] is None and last is None:
            blame("context", "missing")

    rescued_by = None
    if fault is not None and fault["reason"] in ("ranked_low", "fell"):
        later = list(RANKED[RANKED.index(fault["kind"]) + 1 :]) if fault["kind"] in RANKED else []
        rescued_by = next(
            (k for k in later if k != "context" and ranks.get(k) and ranks[k] <= budget), None
        )
    size = len(by_kind["context"].items) if "context" in by_kind else 0
    at = ranks.get("context")
    if at is not None:  # the position in the context, which the order may have changed
        at = by_kind["context"].items[at - 1].placed or at
    middle = size >= 3 and at is not None and 1 < at < size
    return {
        "doc_id": passage.doc_id,
        "anchor_text": passage.anchor_text,
        "steps": steps,
        "fault": fault,
        "rescued_by": rescued_by,
        "note": "middle" if middle else None,
    }


def diagnose(
    question: RagQuestion,
    chunks: Sequence[Chunk],
    stages: Sequence[StageList],
    *,
    budget: int = DEFAULT_BUDGET,
    tolerance: int = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """One diagnosis per expected passage; a question with none (`no_answer`) has no verdict."""
    return {
        "question_id": question.id,
        "question_text": question.question_text,
        "budget": budget,
        "tolerance": tolerance,
        "passages": [
            diagnose_passage(p, chunks, stages, budget=budget, tolerance=tolerance)
            for p in question.expected_passages
        ],
    }


# ---------- the recorded failure cases (« Où naît l'erreur ») ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordedItem(_Strict):
    """An item of a recorded list, by reference to the corpus: the chunk of `doc_id` that
    holds the question's `passage`-th expected passage, or its `other`-th chunk that holds
    none of them (so the same recording reads in every language)."""

    doc_id: str = Field(min_length=1)
    passage: int | None = Field(default=None, ge=0)
    other: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_reference(self) -> RecordedItem:
        if (self.passage is None) == (self.other is None):
            raise ValueError("an item names either `passage` or `other`")
        return self


class RecordedStage(_Strict):
    kind: str
    items: list[RecordedItem]

    @model_validator(mode="after")
    def _ranks_passages(self) -> RecordedStage:
        if self.kind not in RANKED:
            raise ValueError(f"unknown stage kind {self.kind!r}")
        return self


class FailureCase(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    question_id: str
    chunk_max_chars: int = Field(ge=200, le=1500)
    top_k: int = Field(ge=1, le=20)
    expected_fault: str  # `kind:reason`, held by the tests, never shown
    title_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)
    stages: list[RecordedStage]


class StageNames(_Strict):
    chunking_text: str
    vector_search_text: str
    lexical_search_text: str
    fusion_text: str
    rerank_text: str
    context_text: str


class ReasonTexts(_Strict):
    not_indexed_text: str
    missing_text: str
    ranked_low_text: str
    fell_text: str
    cut_text: str


class DiagnosisTexts(_Strict):
    """Placeholders: `{rank}`, `{of}`, `{stage}`, `{budget}`, `{tolerance}`, `{doc}`."""

    title_text: str
    hint_text: str
    free_question_text: str  # a typed question: no expected passage, no diagnosis
    no_expected_text: str  # a question without a passage to find
    wait_text: str  # no finished run for the question
    passage_text: str  # `{doc}`
    rank_text: str  # `{rank}`, `{of}`
    absent_text: str
    whole_text: str  # chunking: the passage is whole in a chunk
    cut_chunk_text: str  # chunking: the passage is cut across chunks
    fault_text: str  # `{stage}`
    no_fault_text: str
    rescued_text: str  # `{stage}`
    middle_text: str
    budget_text: str  # `{budget}`, `{tolerance}`
    stages: StageNames
    reasons: ReasonTexts
    cases_title_text: str
    cases_hint_text: str
    replay_badge_text: str
    replay_failed_text: str
    run_unavailable_text: str  # the page could not reach the diagnosis


class DiagnosisContent(_Strict):
    texts: DiagnosisTexts
    cases: list[FailureCase] = Field(min_length=3)


def load_diagnosis(lang: str | None = None) -> DiagnosisContent:
    """Raises on a missing or invalid file: the content's own test is what fails."""
    path = config.content_file(FILE, lang)
    return DiagnosisContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def resolve(case: FailureCase, question: RagQuestion, chunks: Sequence[Chunk]) -> list[StageList]:
    """The case's recorded lists as real chunks of the corpus."""
    anchors = question.expected_passages
    stages: list[StageList] = []
    for stage in case.stages:
        listed: list[Listed] = []
        for ref in stage.items:
            of_doc = [c for c in chunks if c.doc_id == ref.doc_id]
            if ref.passage is not None:
                pool = [c for c in of_doc if holds(Listed(c.doc_id, c.text), anchors[ref.passage])]
                at = 0
            else:
                pool = [
                    c
                    for c in of_doc
                    if not any(holds(Listed(c.doc_id, c.text), p) for p in anchors)
                ]
                at = ref.other or 0
            if at >= len(pool):
                raise ValueError(f"{case.id}: no chunk for {ref!r}")
            listed.append(Listed(pool[at].doc_id, pool[at].text))
        stages.append(StageList(stage.kind, listed))
    return stages


def replay(case_id: str, lang: str | None = None) -> dict[str, Any] | None:
    """A recorded case, diagnosed again with the shipped rules and the language's corpus:
    no model, no index, nothing run. `None`: unknown case."""
    lang = lang or config.DEFAULT_LANGUAGE
    content = load_diagnosis(lang)
    case = next((c for c in content.cases if c.id == case_id), None)
    if case is None:
        return None
    question = next(q for q in load_rag_questions(lang) if q.id == case.question_id)
    chunks = chunk_corpus(load_rag_content(lang), case.chunk_max_chars, lang)
    resolved = resolve(case, question, chunks)
    result = diagnose(question, chunks, resolved, budget=case.top_k)
    return result | {
        "case_id": case.id,
        "recorded": True,
        "stages": [
            {
                "kind": stage.kind,
                "items": [{"doc_id": i.doc_id, "text": i.text} for i in listed.items],
            }
            for stage, listed in zip(case.stages, resolved, strict=True)
        ],
    }


def listing(lang: str | None = None) -> dict[str, Any]:
    """`GET /api/rag_lab/diagnosis`: the texts and the cases (without their recordings)."""
    lang = lang or config.DEFAULT_LANGUAGE
    content = load_diagnosis(lang)
    asked = {q.id: q.question_text for q in load_rag_questions(lang)}
    return {
        "texts": content.texts.model_dump(),
        "cases": [
            {
                "id": c.id,
                "question_id": c.question_id,
                "question_text": asked[c.question_id],
                "title_text": c.title_text,
                "explain_text": c.explain_text,
            }
            for c in content.cases
        ],
    }


class LiveItem(_Strict):
    doc_id: str = Field(max_length=200)
    text: str = Field(max_length=20000)
    placed: int | None = Field(default=None, ge=1, le=MAX_ITEMS)


class LiveStage(_Strict):
    kind: str = Field(max_length=32)
    items: list[LiveItem] = Field(max_length=MAX_ITEMS)


class LiveRequest(_Strict):
    """What the page sends: its finished run's lists, as the journal gave them."""

    question_id: str = Field(max_length=100)
    chunk_max_chars: int = Field(ge=200, le=1500)
    top_k: int = Field(default=DEFAULT_BUDGET, ge=1, le=20)  # the lab's BOUNDS
    tolerance: int = Field(default=DEFAULT_TOLERANCE, ge=0, le=10)
    stages: list[LiveStage] = Field(max_length=12)


def live(request: LiveRequest, lang: str | None = None) -> dict[str, Any] | None:
    """A finished run read for the prepared question it answered. `None`: unknown question."""
    lang = lang or config.DEFAULT_LANGUAGE
    question = next((q for q in load_rag_questions(lang) if q.id == request.question_id), None)
    if question is None:
        return None
    chunks = chunk_corpus(load_rag_content(lang), request.chunk_max_chars, lang)
    stages = [
        StageList(s.kind, [Listed(i.doc_id, i.text, i.placed) for i in s.items])
        for s in request.stages
    ]
    return diagnose(question, chunks, stages, budget=request.top_k, tolerance=request.tolerance)


__all__ = [
    "DEFAULT_BUDGET",
    "DEFAULT_TOLERANCE",
    "REASONS",
    "DiagnosisContent",
    "FailureCase",
    "LiveRequest",
    "diagnose",
    "diagnose_passage",
    "listing",
    "live",
    "load_diagnosis",
    "replay",
]
