"""The demonstration corpus and its chunking (story 15, AD-19).

`content/rag.yaml` declares the documents and the brick's texts; one chunking function
serves the index script and the tests.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from typing import Literal, NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from wavestack import config

# A sentence ends with one of these, followed by a space (or the text's end).
_SENTENCE_END = re.compile(r"[.!?…»](?=\s)")
_BLANK_LINE = re.compile(r"\n\s*\n")
# An HTML comment of a document (its « texte fictif » notice) is never indexed.
_COMMENT = re.compile(r"<!--.*?-->", re.S)


class CorpusDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title_text: str = Field(min_length=1)
    file: str = Field(min_length=1)  # relative to `content/`
    audience: Literal["all", "hr"] = "all"
    active: bool = True
    # A monolingual document (story 1): its file sits under `content/corpus/` in this
    # language, with no copy under `content/i18n/{lang}/corpus/`; `config.content_file`'s
    # fallback indexes it as-is in every language, and the i18n mirror test exempts it.
    languages: list[str] | None = None


class RagContent(BaseModel):
    """`content/rag.yaml`: the corpus and every French text of the brick."""

    model_config = ConfigDict(extra="forbid")

    notice_text: str = Field(min_length=1)
    intro_text: str = Field(min_length=1)
    excerpt_format_text: str = Field(min_length=1)
    placement_text: str = Field(min_length=1)
    phase_label_text: str = Field(min_length=1)
    index_label_text: str = Field(min_length=1)
    download_label_text: str = Field(min_length=1)
    build_label_text: str = Field(min_length=1)
    # Story 16: the reranking sub-option's texts.
    rerank_label_text: str = Field(min_length=1)
    rerank_phase_label_text: str = Field(min_length=1)
    rerank_search_placement_text: str = Field(min_length=1)  # {candidates}, {keep}
    rerank_placement_text: str = Field(min_length=1)  # {keep}
    rerank_download_label_text: str = Field(min_length=1)  # {size_mb}
    documents: list[CorpusDocument] = Field(min_length=1)

    @field_validator("excerpt_format_text")
    @classmethod
    def _known_fields(cls, value: str) -> str:
        value.format(position=1, title_text="", text="")  # raises on an unknown field
        return value

    @field_validator("download_label_text", "rerank_download_label_text")
    @classmethod
    def _size_field(cls, value: str) -> str:
        value.format(size_mb=1)
        return value

    @field_validator("rerank_search_placement_text", "rerank_placement_text")
    @classmethod
    def _rerank_fields(cls, value: str) -> str:
        value.format(candidates=1, keep=1)  # raises on an unknown field
        return value

    def excerpt(self, position: int, title_text: str, text: str) -> str:
        return self.excerpt_format_text.format(position=position, title_text=title_text, text=text)


class Chunk(NamedTuple):
    """An excerpt of a document: its document, and its rank in it (from 1)."""

    doc_id: str
    title_text: str
    position: int
    text: str


def load_rag_content(lang: str | None = None) -> RagContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_file("rag.yaml", lang)
    return RagContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


QuestionType = Literal[
    "factual", "multi_hop", "global", "no_answer", "temporal", "cross_lingual", "follow_up"
]


class RagPassage(BaseModel):
    """A passage expected (or, for `trap_passages`, a decoy) in a document, by a sentence
    taken as-is from its text: `tests/test_rag_questions.py` checks it is really there."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1)
    anchor_text: str = Field(min_length=1)


class RagQuestion(BaseModel):
    """`content/rag_questions.yaml` (story 1): a prepared question with its expected answer
    and passages, for the demonstration corpus. The reference annotations are in
    `content/rag_evaluation.yaml` (V1.2 story 15)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    type: QuestionType
    history: list[str] = Field(default_factory=list)  # previous turns, for `follow_up`
    question_text: str = Field(min_length=1)
    expected_answer_text: str = Field(min_length=1)
    expected_passages: list[RagPassage] = Field(default_factory=list)
    trap_passages: list[RagPassage] = Field(default_factory=list)  # `temporal`: the old version
    audience: Literal["all", "hr"] | None = None  # when the question targets an HR document
    # Obsolète (V1.2 story 15) : les annotations de référence vivent dans `rag_evaluation.yaml`.
    annotation: str | None = None

    @model_validator(mode="after")
    def _no_answer_has_no_expected_passage(self) -> RagQuestion:
        if self.type == "no_answer" and self.expected_passages:
            raise ValueError(f"{self.id}: a no_answer question has no expected_passages")
        return self

    @model_validator(mode="after")
    def _known_doc_ids(self, info: ValidationInfo) -> RagQuestion:
        context = info.context or {}
        known: set[str] | None = context.get("doc_ids")
        if known is not None:
            for passage in (*self.expected_passages, *self.trap_passages):
                if passage.doc_id not in known:
                    raise ValueError(f"{self.id}: unknown doc_id {passage.doc_id!r}")
        return self


class RagQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[RagQuestion] = Field(min_length=1)


def load_rag_questions(lang: str | None = None) -> list[RagQuestion]:
    """`content/rag_questions.yaml` (story 1): raises on a missing or invalid file, or on a
    question whose `doc_id` is unknown in `rag.yaml` of the same language."""
    path = config.content_file("rag_questions.yaml", lang)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc_ids = {doc.id for doc in load_rag_content(lang).documents}
    return RagQuestionSet.model_validate(raw, context={"doc_ids": doc_ids}).questions


def _cut_long(paragraph: str, max_chars: int) -> list[str]:
    """A paragraph longer than `max_chars`, cut at a sentence's end, else at the limit."""
    pieces = []
    rest = paragraph
    while len(rest) > max_chars:
        ends = [m.end() for m in _SENTENCE_END.finditer(rest[: max_chars + 1])]
        cut = ends[-1] if ends else max_chars
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def split_text(text: str, max_chars: int) -> list[str]:
    """Paragraphs (separated by a blank line) merged while they fit in `max_chars`; a longer
    paragraph is cut at a sentence's end, else at the limit."""
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in _BLANK_LINE.split(text.replace("\r\n", "\n"))):
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks += _cut_long(paragraph, max_chars)
            continue
        merged = f"{current}\n\n{paragraph}" if current else paragraph
        if len(merged) <= max_chars:
            current = merged
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


class DocText(NamedTuple):
    """A document of the corpus, read: its id, its title and its text (comment removed)."""

    doc_id: str
    title_text: str
    text: str


def read_documents(content: RagContent, lang: str = config.DEFAULT_LANGUAGE) -> list[DocText]:
    """The active documents of the corpus, read in `lang` (its translation under
    `content/i18n/{lang}/corpus/` when it exists, else the French file), in declared order."""
    documents: list[DocText] = []
    for doc in content.documents:
        if not doc.active:  # story 1: the trapped and sentinel documents, by default
            continue
        path = config.content_file(doc.file, lang)
        text = _COMMENT.sub("", path.read_text(encoding="utf-8-sig"))
        documents.append(DocText(doc.id, doc.title_text, text))
    return documents


def chunk_documents(documents: Sequence[DocText], max_chars: int) -> list[Chunk]:
    """Each document chunked by `split_text`, its chunks ranked from 1."""
    chunks: list[Chunk] = []
    for doc in documents:
        for position, piece in enumerate(split_text(doc.text, max_chars), start=1):
            chunks.append(Chunk(doc.doc_id, doc.title_text, position, piece))
    return chunks


def chunk_corpus(
    content: RagContent, max_chars: int, lang: str = config.DEFAULT_LANGUAGE
) -> list[Chunk]:
    """Every document of the corpus, read from `content/` and chunked, in declared order.
    Languages (4/5): each document in `lang`, its translation under
    `content/i18n/{lang}/corpus/` when it exists, else the French file; the titles are
    `content`'s (the caller reads `rag.yaml` in the same language)."""
    return chunk_documents(read_documents(content, lang), max_chars)


# ---------- V1.2 story 6 (CAP-4): sentences, semantic and parent-child chunking ----------


def split_sentences(text: str) -> list[str]:
    """The sentences of a text, in order: each paragraph (blank line) cut after a sentence's
    end (`_SENTENCE_END`); a title line without a full stop is a sentence of its own."""
    sentences: list[str] = []
    for paragraph in (p.strip() for p in _BLANK_LINE.split(text.replace("\r\n", "\n"))):
        start = 0
        for match in _SENTENCE_END.finditer(paragraph):
            piece = paragraph[start : match.end()].strip()
            if piece:
                sentences.append(piece)
            start = match.end()
        rest = paragraph[start:].strip()
        if rest:
            sentences.append(rest)
    return sentences


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    """The cosine distance of two vectors (1 for a null one)."""
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 1.0
    return 1.0 - sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


def percentile(values: Sequence[float], q: float) -> float:
    """The `q`-th percentile (0 to 100) of `values`, linearly interpolated."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q / 100
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _pack(sentences: Sequence[str], max_chars: int) -> list[str]:
    """Sentences joined by a space while they fit in `max_chars`; a longer sentence is cut
    at its last sentence end, else at the limit."""
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces += _cut_long(sentence, max_chars)
            continue
        merged = f"{current} {sentence}" if current else sentence
        if len(merged) <= max_chars:
            current = merged
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_semantic(
    documents: Sequence[DocText],
    embed: Callable[[list[str]], list[list[float]]],
    max_chars: int,
    cut_percentile: float,
) -> tuple[list[Chunk], int]:
    """Semantic chunking: the sentences of each document are embedded (`embed`: one vector
    per sentence), and a chunk ends where the distance between two neighbouring sentences is
    at or above the `cut_percentile`-th percentile (and above the smallest) of every such
    distance in the corpus; no chunk passes `max_chars`. Deterministic for a given
    embedding. Returns the chunks and how many sentences were embedded."""
    per_doc = [split_sentences(doc.text) for doc in documents]
    flat = [s for sentences in per_doc for s in sentences]
    vectors = embed(flat) if flat else []
    distances: list[list[float]] = []
    at = 0
    for sentences in per_doc:
        mine = vectors[at : at + len(sentences)]
        at += len(sentences)
        distances.append([_distance(a, b) for a, b in zip(mine, mine[1:], strict=False)])
    every = [d for ds in distances for d in ds]
    threshold, floor = percentile(every, cut_percentile), min(every, default=0.0)
    chunks: list[Chunk] = []
    for doc, sentences, gaps in zip(documents, per_doc, distances, strict=True):
        groups: list[list[str]] = [[]]
        for i, sentence in enumerate(sentences):
            groups[-1].append(sentence)
            if i < len(gaps) and gaps[i] >= threshold and gaps[i] > floor:
                groups.append([])
        position = 0
        for group in groups:
            for piece in _pack(group, max_chars):
                position += 1
                chunks.append(Chunk(doc.doc_id, doc.title_text, position, piece))
    return chunks, len(flat)


def chunk_parent_child(
    parents: Sequence[Chunk], child_max_chars: int
) -> tuple[list[Chunk], list[int]]:
    """Parent-child chunking: each parent chunk cut into children of `child_max_chars` at
    most (sentences grouped; a longer sentence cut at the limit), ranked from 1 in their
    document. Returns the children and, for each, the index of its parent in `parents`."""
    children: list[Chunk] = []
    parent_of: list[int] = []
    ranks: dict[str, int] = {}
    for index, parent in enumerate(parents):
        for piece in _pack(split_sentences(parent.text), child_max_chars):
            ranks[parent.doc_id] = ranks.get(parent.doc_id, 0) + 1
            children.append(Chunk(parent.doc_id, parent.title_text, ranks[parent.doc_id], piece))
            parent_of.append(index)
    return children, parent_of
