"""V1.2 story 18 (CAP-14): the « Effacement » card of the Attack tab.

Pure and read only (AD-1: the figures are the session's, the page draws them). The sentinel
document of the shipped corpus (`projet_orion`, inactive in `rag.yaml`, code `ORN-7731-QZ`) is
activated in the request's state only: the corpus in memory is the active shipped documents plus
the sentinel, chunked as the workshop chunks them. The shipped corpus, `rag.yaml`, the shipped
contexts, the index and the work copy are never read for writing.

What is measured, without any model: the text of the chunks, BM25's inverted index, the
heuristic contexts recomputed in memory, the shipped contexts file (read as it is), the source.
What a model would produce (summaries, tree, graph, wiki, prompt cache) is a *constructed* case,
shown as illustrative with the story that will replace it. The status of every place is
computed, never declared: it is the search of the code in the place's current content. Nothing
is generated, loaded, downloaded or sent.
"""

from __future__ import annotations

from typing import Any, Literal, NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.messages import msg
from wavestack.rag.attack import Provenance, provenance_text
from wavestack.rag.contexts import heuristic_entries, load_book
from wavestack.rag.corpus import (
    Chunk,
    DocText,
    RagContent,
    chunk_documents,
    load_rag_content,
    read_documents,
)
from wavestack.rag.index import passage_text
from wavestack.rag.lab import bm25, bm25_terms, lexical_index

FILE = "rag_erasure.yaml"
ARCHITECTURES = (
    "dense",
    "hybrid",
    "rerank",
    "long_context",
    "cag",
    "agentic",
    "pageindex",
    "raptor",
    "graphrag",
    "llm_wiki",
    "crag",
)
Architecture = Literal[
    "dense",
    "hybrid",
    "rerank",
    "long_context",
    "cag",
    "agentic",
    "pageindex",
    "raptor",
    "graphrag",
    "llm_wiki",
    "crag",
]
STEPS = ("idle", "start", "erase", "rebuild")
MEASURED = ("chunks", "bm25", "contexts", "shipped_contexts", "source")
MODE_OF_MEASURED = {
    "chunks": "delete",
    "bm25": "delete",
    "contexts": "rebuild",
    "shipped_contexts": "rebuild",
    "source": "none",
}
STORIES = range(10, 15)
STATUSES = (
    "present",
    "erased",
    "erased_illustrative",
    "to_rebuild",
    "to_reload",
    "absent",
    "no_copy",
)
# The texts the session reads: a missing one is refused at the load, not a 500 when drawn.
REQUIRED_TEXTS = (
    "guard_text",
    "hits_text",
    "shared_text",
    "illustrative_text",
    "erased_illustrative_text",
    "upcoming_text",
    "cost_text",
    "source_found_text",
    "source_gone_text",
    *(f"status.{s}" for s in STATUSES),
    *(f"step_text.{s}" for s in ("idle", "start", "erase", "rebuild")),
    "provenance.constructed_text",
    "provenance.recorded_text",
)
SCORE_DIGITS = 2
EXCERPT_CONTEXT = 120


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- the shipped content ----------


class ArchitectureInfo(_Strict):
    id: Architecture
    available: bool  # in the workshop's `lab.PRESETS` (dense, hybrid, rerank)
    story: int | None = None  # the story that brings it
    label_text: str = Field(min_length=1)
    update_text: str = Field(min_length=1)  # what putting it back in order costs, in words

    @model_validator(mode="after")
    def _story_iff_missing(self) -> ArchitectureInfo:
        if self.available == (self.story is not None):
            raise ValueError("an architecture of the workshop has no story; the others have one")
        if self.story is not None and self.story not in STORIES:
            raise ValueError("a story between 10 and 14")
        return self


class Place(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    erase_mode: Literal["delete", "rebuild", "reload", "none"]
    measured: Literal["chunks", "bm25", "contexts", "shipped_contexts", "source"] | None = None
    provenance: Provenance | None = None
    story: int | None = None
    architectures: list[Architecture] = Field(min_length=1)
    shared: bool = False
    label_text: str = Field(min_length=1)
    unit_text: str = Field(min_length=1)
    measured_on_text: str | None = None
    text: str | None = None  # a constructed place: what it holds (it cites the code)
    rebuilt_text: str | None = None  # ... and what it holds once rebuilt (it does not)

    @model_validator(mode="after")
    def _shape(self) -> Place:
        if (self.measured is None) == (self.provenance is None):
            raise ValueError("a place is measured, or constructed with a provenance")
        if self.measured is not None:
            if self.erase_mode != MODE_OF_MEASURED[self.measured]:
                raise ValueError(f"{self.id}: erase_mode of a {self.measured} place")
            if self.text or self.rebuilt_text or self.story is not None:
                raise ValueError("a measured place holds no constructed content")
            if not self.measured_on_text:
                raise ValueError("a measured place says on what it is measured")
        else:
            if self.erase_mode not in ("rebuild", "reload"):
                raise ValueError("a constructed place is rebuilt or reloaded")
            if not (self.text and self.rebuilt_text):
                raise ValueError("a constructed place has a text and a rebuilt text")
            if self.story not in STORIES:
                raise ValueError("a constructed place names the story that replaces it (10 to 14)")
        return self


def _text_at(texts: dict[str, Any], path: str) -> object:
    node: object = texts
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    return node


class ErasureContent(_Strict):
    chunk_max_chars: int = Field(ge=100, le=4000)
    top_k: int = Field(ge=1, le=10)
    doc_id: str
    code: str = Field(min_length=3)
    architectures: list[ArchitectureInfo] = Field(min_length=11)
    places: list[Place] = Field(min_length=1)
    texts: dict[str, Any]

    @model_validator(mode="after")
    def _shape(self) -> ErasureContent:
        missing = [k for k in REQUIRED_TEXTS if not isinstance(_text_at(self.texts, k), str)]
        if missing:
            raise ValueError(f"missing texts: {', '.join(missing)}")
        if [a.id for a in self.architectures] != list(ARCHITECTURES):
            raise ValueError("the eleven architectures, in order")
        ids = [p.id for p in self.places]
        if len(set(ids)) != len(ids):
            raise ValueError("a place appears once")
        for place in self.places:
            if place.measured is None:
                if self.code not in (place.text or ""):
                    raise ValueError(f"{place.id}: the text cites the code")
                if self.code in (place.rebuilt_text or ""):
                    raise ValueError(f"{place.id}: the rebuilt text does not cite the code")
                if len(place.architectures) != 1:
                    raise ValueError(f"{place.id}: a constructed place belongs to one architecture")
                arch = self.architecture(place.architectures[0])
                if arch.story != place.story:
                    raise ValueError(f"{place.id}: the story of its architecture")
        return self

    def architecture(self, arch_id: str) -> ArchitectureInfo:
        return next(a for a in self.architectures if a.id == arch_id)


def load_erasure(lang: str | None = None) -> ErasureContent:
    """Raises on a missing or invalid file: the content's own test is what fails."""
    path = config.content_file(FILE, lang)
    return ErasureContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------- the request ----------


class ErasureRequest(_Strict):
    sentinel_active: bool = False
    step: Literal["idle", "start", "erase", "rebuild"] = "idle"
    rebuilt: list[Architecture] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rebuilt_only_when_rebuilding(self) -> ErasureRequest:
        if self.rebuilt and self.step != "rebuild":
            raise ValueError("`rebuilt` belongs to the step `rebuild`")
        if self.step == "rebuild" and not self.rebuilt:
            raise ValueError("the step `rebuild` names at least one architecture")
        return self


# ---------- the copies in memory ----------


def sentinel_content(content: ErasureContent, lang: str, active: bool) -> RagContent:
    """A copy of `RagContent` where only the sentinel turns active: the shipped file, the
    index and the work copy are not read for writing."""
    shipped = load_rag_content(lang)
    if not active:
        return shipped
    documents = [
        d.model_copy(update={"active": True}) if d.id == content.doc_id else d
        for d in shipped.documents
    ]
    return shipped.model_copy(update={"documents": documents})


class Copies(NamedTuple):
    """Everything the places are made of, with the sentinel (`with_`) and without it."""

    lang: str
    code: str
    doc_id: str
    docs_with: list[DocText]
    docs_without: list[DocText]
    chunks: list[Chunk]  # with the sentinel
    contexts_with: list[str]
    contexts_without: list[str]
    shipped_contexts: list[str]
    index_counts: list[dict[str, int]]  # BM25's inverted index, one document per chunk
    terms: list[str]


def build_copies(content: ErasureContent, lang: str) -> Copies:
    docs_with = read_documents(sentinel_content(content, lang, True), lang)
    docs_without = read_documents(sentinel_content(content, lang, False), lang)
    chunks = chunk_documents(docs_with, content.chunk_max_chars)

    def say(**kw: object) -> str:
        return msg("rag_lab.contexts.heuristic", lang, **kw)

    def contexts(documents: list[DocText]) -> list[str]:
        made = chunk_documents(documents, content.chunk_max_chars)
        return [e.context_text for e in heuristic_entries(documents, made, say)]

    shipped = load_book(lang).shipped  # the shipped file alone, never the rebuilt one
    index = lexical_index([passage_text(c) for c in chunks], lang)
    return Copies(
        lang=lang,
        code=content.code,
        doc_id=content.doc_id,
        docs_with=docs_with,
        docs_without=docs_without,
        chunks=chunks,
        contexts_with=contexts(docs_with),
        contexts_without=contexts(docs_without),
        shipped_contexts=[e.context_text for e in shipped.entries] if shipped else [],
        index_counts=index.counts,
        terms=bm25_terms(content.code, lang),
    )


def _items(place: Place, copies: Copies, erased: bool, rebuilt: set[str]) -> list[str]:
    """The current content of a place: one text per item (a chunk, an entry, a document, a
    constructed text). `erased`: the sentinel left the source; `rebuilt`: the architectures
    rebuilt from the source without it."""
    rebuilding = bool(rebuilt & set(place.architectures))
    if place.measured == "chunks" or place.measured == "bm25":
        # `delete`: filtered by `doc_id` (the vectors leave with their chunk)
        return [c.text for c in copies.chunks if not (erased and c.doc_id == copies.doc_id)]
    if place.measured == "contexts":
        return copies.contexts_without if rebuilding else copies.contexts_with
    if place.measured == "shipped_contexts":
        return copies.shipped_contexts
    if place.measured == "source":
        return [d.text for d in (copies.docs_without if erased else copies.docs_with)]
    assert place.text and place.rebuilt_text  # noqa: S101 - validated at the load
    return [place.rebuilt_text if rebuilding else place.text]


def _hit_items(place: Place, copies: Copies, erased: bool, rebuilt: set[str]) -> list[str]:
    """The items of a place that hold the code. BM25's index holds it when the three terms of
    the code are in the counts of one same document."""
    if place.measured == "bm25":
        kept = [
            (c, counts)
            for c, counts in zip(copies.chunks, copies.index_counts, strict=True)
            if not (erased and c.doc_id == copies.doc_id)
        ]
        return [c.text for c, counts in kept if all(t in counts for t in copies.terms)]
    return [t for t in _items(place, copies, erased, rebuilt) if copies.code in t]


def status_of(
    place: Place, copies: Copies, erased: bool, rebuilt: set[str]
) -> tuple[str, list[str]]:
    """`(status, items holding the code)`, computed from the content of the place now and at the
    start: never declared. A constructed place rebuilt is `erased_illustrative`, never the
    measured `erased`: its rebuilt content is written by hand, nothing was measured."""
    held = _hit_items(place, copies, erased, rebuilt)
    if place.erase_mode == "none":
        return "no_copy", held
    if held:
        if not erased:
            return "present", held
        return {"delete": "present", "rebuild": "to_rebuild", "reload": "to_reload"}[
            place.erase_mode
        ], held
    if not _hit_items(place, copies, False, set()):
        return "absent", held
    return ("erased_illustrative" if place.provenance is not None else "erased"), held


def _status_text(content: ErasureContent, place: Place, status: str, held: list[str]) -> str:
    """The status in words; the source (`none`) adds whether the code is still read in it."""
    words = content.texts["status"][status]
    if place.erase_mode == "none":
        key = "source_found_text" if held else "source_gone_text"
        words = f"{words} · {content.texts[key]}"
    return words


def _excerpt(text: str, code: str) -> str:
    at = text.find(code)
    if at < 0:
        return text[: 2 * EXCERPT_CONTEXT]
    start, end = max(0, at - EXCERPT_CONTEXT), at + len(code) + EXCERPT_CONTEXT
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


# ---------- the card ----------


def _place_rows(
    content: ErasureContent, copies: Copies | None, erased: bool, rebuilt: set[str]
) -> list[dict[str, Any]]:
    texts = content.texts
    out: list[dict[str, Any]] = []
    for place in content.places:
        status, held = ("", []) if copies is None else status_of(place, copies, erased, rebuilt)
        constructed = place.provenance is not None
        row_status = None if copies is None else status
        rows = []
        for arch_id in place.architectures:
            arch = content.architecture(arch_id)
            upcoming = (
                texts["upcoming_text"].format(story=arch.story, on=place.measured_on_text)
                if not arch.available and not constructed
                else None
            )
            rows.append(
                {
                    "architecture": arch.id,
                    "architecture_text": arch.label_text,
                    "available": arch.available,
                    "upcoming_text": upcoming,
                }
            )
        out.append(
            {
                "id": place.id,
                "label_text": place.label_text,
                "kind": "constructed" if constructed else "measured",
                "erase_mode": place.erase_mode,
                "shared": place.shared,
                "shared_text": texts["shared_text"] if place.shared else None,
                "illustrative_text": (
                    texts["illustrative_text"].format(
                        provenance=provenance_text(place.provenance, texts)
                    )
                    if place.provenance
                    else None
                ),
                "status": row_status,
                "status_text": (
                    None if row_status is None else _status_text(content, place, status, held)
                ),
                "status_note_text": (
                    texts["erased_illustrative_text"]
                    if row_status == "erased_illustrative"
                    else None
                ),
                "hits": None if copies is None else len(held),
                "hits_text": (
                    None
                    if copies is None
                    else texts["hits_text"].format(unit=place.unit_text, hits=len(held))
                ),
                "rows": rows,
            }
        )
    return out


def _results(
    content: ErasureContent, copies: Copies, erased: bool, rebuilt: set[str]
) -> dict[str, Any]:
    """The question on the code, asked now: BM25 of the code over the chunks still there, and
    the text of every place that still holds it. Nothing is generated."""
    chunks = [c for c in copies.chunks if not (erased and c.doc_id == copies.doc_id)]
    scores = bm25(copies.code, [passage_text(c) for c in chunks], copies.lang)
    order = [i for i in sorted(range(len(chunks)), key=lambda i: (-scores[i], i)) if scores[i] > 0]
    ranking = [
        {
            "rank": rank,
            "doc_id": chunks[i].doc_id,
            "title_text": chunks[i].title_text,
            "position": chunks[i].position,
            "score": round(scores[i], SCORE_DIGITS),
            "text": chunks[i].text,
        }
        for rank, i in enumerate(order[: content.top_k], start=1)
    ]
    still = []
    for place in content.places:
        status, held = status_of(place, copies, erased, rebuilt)
        if not held:
            continue
        still.append(
            {
                "place": place.id,
                "label_text": place.label_text,
                "status": status,
                "status_text": _status_text(content, place, status, held),
                "kind": "constructed" if place.provenance else "measured",
                "text": _excerpt(held[0], copies.code),
            }
        )
    return {"query": copies.code, "ranking": ranking, "holding": still}


def _corpus(content: ErasureContent, copies: Copies, active: bool) -> dict[str, Any]:
    docs = copies.docs_with if active else copies.docs_without
    chunks = chunk_documents(docs, content.chunk_max_chars)
    return {
        "documents": len(docs),
        "passages": len(chunks),
        "sentinel_passages": sum(1 for c in chunks if c.doc_id == content.doc_id),
        "max_chars": content.chunk_max_chars,
    }


def run(request: ErasureRequest, lang: str) -> dict[str, Any]:
    """The card for one request, recomputed: the table of places by architecture, and the
    question on the code once the copies are built."""
    content = load_erasure(lang)
    texts = content.texts
    building = request.sentinel_active and request.step != "idle"
    body: dict[str, Any] = {
        "sentinel_active": request.sentinel_active,
        "step": request.step if building else "idle",
        "rebuilt": [],
        "code": content.code,
        "guard_text": None,
        "places": [],
        "results": None,
        "costs": [],
    }
    guarded = request.step in ("erase", "rebuild") and not request.sentinel_active
    if guarded:
        body["guard_text"] = texts["guard_text"]
    copies = build_copies(content, lang)
    body["corpus"] = _corpus(content, copies, request.sentinel_active)
    if not building:
        body["places"] = _place_rows(content, None, False, set())
        return body
    erased = request.step in ("erase", "rebuild")
    rebuilt = set(request.rebuilt) if request.step == "rebuild" else set()
    body["rebuilt"] = [a for a in ARCHITECTURES if a in rebuilt]
    body["places"] = _place_rows(content, copies, erased, rebuilt)
    body["results"] = _results(content, copies, erased, rebuilt)
    body["costs"] = [
        {
            "architecture": a.id,
            "architecture_text": a.label_text,
            "text": texts["cost_text"].format(architecture=a.label_text, update=a.update_text),
        }
        for a in content.architectures
        if a.id in rebuilt
    ]
    return body


def listing(lang: str) -> dict[str, Any]:
    """`GET /api/rag_lab/erasure`: the texts and the default state, no computation."""
    content = load_erasure(lang)
    title = next(d.title_text for d in load_rag_content(lang).documents if d.id == content.doc_id)
    return {
        "lang": config.as_language(lang),
        "texts": content.texts,
        "doc": {"id": content.doc_id, "title_text": title},
        "code": content.code,
        "chunk_max_chars": content.chunk_max_chars,
        "architectures": [
            {"id": a.id, "label_text": a.label_text, "available": a.available, "story": a.story}
            for a in content.architectures
        ],
        "defaults": ErasureRequest().model_dump(),
        "steps": list(STEPS),
    }
