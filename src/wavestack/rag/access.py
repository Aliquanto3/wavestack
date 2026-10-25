"""V1.2 story 18 (CAP-15): the « Droits d'accès » card of the Attack tab.

Pure and read only (AD-1). Two profiles (`all` sees the passages of `audience: all`, `hr` sees
everything) and two modes, on one question of the question set (`q_global_rh`):

- `after`: the top-k of BM25 over the whole corpus, then the forbidden passages are removed.
  The card shows what the pipeline read *before* the filter: that is the leak, and the number
  of results shorter than k betrays the document.
- `before`: BM25 over the index of the authorized documents only (the idf too is computed
  without the others), so nothing forbidden is ever read.

Deterministic, no model, no network, nothing written. The audience of a passage is its
document's, in `rag.yaml`.
"""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.rag.attack import Provenance, provenance_text
from wavestack.rag.corpus import (
    Chunk,
    chunk_corpus,
    load_rag_content,
    load_rag_questions,
)
from wavestack.rag.index import passage_text
from wavestack.rag.lab import bm25

FILE = "rag_access.yaml"
PROFILES = ("all", "hr")
MODES = ("after", "before")
SCORE_DIGITS = 2
# The texts the session and the card read (a missing one is refused at the load, not a 500).
REQUIRED_TEXTS = (
    *(f"notes.{n}" for n in ("leak_text", "authorized_text", "safe_before_text", "no_leak_text")),
    "notes.shortfall_text",
    *(f"profile.{p}" for p in PROFILES),
    *(f"mode.{m}" for m in MODES),
    *(f"audience.{a}" for a in PROFILES),
    "provenance.constructed_text",
    "provenance.recorded_text",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rewrite(_Strict):
    """The query rewriting step that « read » the passage in mode `after`: a constructed text,
    not a call. It cites the title of `doc_id`, a document of the measured leak."""

    provenance: Provenance
    doc_id: str
    text: str = Field(min_length=1)  # {title}


def _text_at(texts: dict[str, Any], path: str) -> object:
    node: object = texts
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    return node


class AccessContent(_Strict):
    chunk_max_chars: int = Field(ge=100, le=4000)
    top_k: int = Field(ge=1, le=10)
    question_id: str
    rewrite: Rewrite
    texts: dict[str, Any]

    @model_validator(mode="after")
    def _title_placeholder(self) -> AccessContent:
        if "{title}" not in self.rewrite.text:
            raise ValueError("the rewriting cites a title")
        missing = [k for k in REQUIRED_TEXTS if not isinstance(_text_at(self.texts, k), str)]
        if missing:
            raise ValueError(f"missing texts: {', '.join(missing)}")
        return self


def load_access(lang: str | None = None) -> AccessContent:
    """Raises on a missing or invalid file, or on a question the language does not have."""
    path = config.content_file(FILE, lang)
    content = AccessContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if all(q.id != content.question_id for q in load_rag_questions(lang)):
        raise ValueError(f"unknown question {content.question_id!r}")
    return content


class AccessRequest(_Strict):
    profile: Literal["all", "hr"] = "all"
    mode: Literal["after", "before"] = "after"


def _question_text(content: AccessContent, lang: str) -> str:
    found = next(q for q in load_rag_questions(lang) if q.id == content.question_id)
    return found.question_text


def _rank(question: str, chunks: list[Chunk], lang: str) -> list[tuple[Chunk, float]]:
    """Every chunk ranked by BM25 against the question (best first, ties by corpus order)."""
    scores = bm25(question, [passage_text(c) for c in chunks], lang)
    order = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    return [(chunks[i], scores[i]) for i in order]


def _passage(
    rank: int, chunk: Chunk, score: float, audience: str, *, kept: bool | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "rank": rank,
        "doc_id": chunk.doc_id,
        "title_text": chunk.title_text,
        "position": chunk.position,
        "text": chunk.text,
        "score": round(score, SCORE_DIGITS),
        "audience": audience,
    }
    if kept is not None:
        out["kept"] = kept
    return out


def run(request: AccessRequest, lang: str) -> dict[str, Any]:
    content = load_access(lang)
    texts = content.texts
    shipped = load_rag_content(lang)  # the shipped file: the trap and the sentinel stay inactive
    audience = {d.id: d.audience for d in shipped.documents}
    chunks = chunk_corpus(shipped, content.chunk_max_chars, lang)
    question = _question_text(content, lang)
    allowed = {"all"} if request.profile == "all" else {"all", "hr"}
    k = content.top_k
    if request.mode == "after":
        top = _rank(question, chunks, lang)[:k]
        seen = [_passage(i, c, s, audience[c.doc_id]) for i, (c, s) in enumerate(top, start=1)]
        returned = [p for p in seen if p["audience"] in allowed]
    else:
        authorized = [c for c in chunks if audience[c.doc_id] in allowed]
        top = _rank(question, authorized, lang)[:k]
        seen = [_passage(i, c, s, audience[c.doc_id]) for i, (c, s) in enumerate(top, start=1)]
        returned = list(seen)
    for p in seen:
        p["kept"] = p in returned
    leaked = [p for p in seen if p["audience"] not in allowed]
    returned_view = [{**p, "rank": n} for n, p in enumerate(returned, start=1)]
    shortfall = len(returned) < k
    rewrite = None
    if leaked and any(p["doc_id"] == content.rewrite.doc_id for p in leaked):
        title = next(d.title_text for d in shipped.documents if d.id == content.rewrite.doc_id)
        rewrite = {
            "text": content.rewrite.text.format(title=title),
            "provenance": {
                "kind": content.rewrite.provenance.kind,
                "text": provenance_text(content.rewrite.provenance, texts),
            },
        }
    if leaked:
        note = texts["notes"]["leak_text"].format(count=len(leaked))
    elif request.profile == "hr":
        note = texts["notes"]["authorized_text"]
    elif request.mode == "before":
        note = texts["notes"]["safe_before_text"]
    else:
        note = texts["notes"]["no_leak_text"]
    return {
        "profile": request.profile,
        "mode": request.mode,
        "question": {"id": content.question_id, "text": question},
        "k": k,
        "corpus": {
            "documents": len({c.doc_id for c in chunks}),
            "passages": len(chunks),
            "hr_documents": sum(1 for d in {c.doc_id for c in chunks} if audience[d] == "hr"),
            "max_chars": content.chunk_max_chars,
        },
        "seen_before_filter": seen,
        "returned": returned_view,
        "leaked": leaked,
        "returned_count": len(returned),
        "shortfall": shortfall,
        "shortfall_text": (
            texts["notes"]["shortfall_text"].format(count=len(returned), k=k) if shortfall else None
        ),
        "note_text": note,
        "rewrite": rewrite,
    }


def listing(lang: str) -> dict[str, Any]:
    """`GET /api/rag_lab/access`: the texts and the default state, no computation."""
    content = load_access(lang)
    return {
        "lang": config.as_language(lang),
        "texts": content.texts,
        "question": {"id": content.question_id, "text": _question_text(content, lang)},
        "chunk_max_chars": content.chunk_max_chars,
        "top_k": content.top_k,
        "defaults": AccessRequest().model_dump(),
        "profiles": list(PROFILES),
        "modes": list(MODES),
    }
