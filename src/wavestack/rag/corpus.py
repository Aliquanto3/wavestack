"""The demonstration corpus and its chunking (story 15, AD-19).

`content/rag.yaml` declares the documents and the brick's texts; one chunking function
serves the index script and the tests.
"""

from __future__ import annotations

import re
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
    and passages, for the demonstration corpus. No annotation yet (story 15 adds it)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    type: QuestionType
    history: list[str] = Field(default_factory=list)  # previous turns, for `follow_up`
    question_text: str = Field(min_length=1)
    expected_answer_text: str = Field(min_length=1)
    expected_passages: list[RagPassage] = Field(default_factory=list)
    trap_passages: list[RagPassage] = Field(default_factory=list)  # `temporal`: the old version
    audience: Literal["all", "hr"] | None = None  # when the question targets an HR document
    annotation: str | None = None  # facultative (story 15 fills it; left empty here)

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


def chunk_corpus(
    content: RagContent, max_chars: int, lang: str = config.DEFAULT_LANGUAGE
) -> list[Chunk]:
    """Every document of the corpus, read from `content/` and chunked, in declared order.
    Languages (4/5): each document in `lang`, its translation under
    `content/i18n/{lang}/corpus/` when it exists, else the French file; the titles are
    `content`'s (the caller reads `rag.yaml` in the same language)."""
    chunks: list[Chunk] = []
    for doc in content.documents:
        if not doc.active:  # story 1: the trapped and sentinel documents, by default
            continue
        path = config.content_file(doc.file, lang)
        text = _COMMENT.sub("", path.read_text(encoding="utf-8-sig"))
        for position, piece in enumerate(split_text(text, max_chars), start=1):
            chunks.append(Chunk(doc.id, doc.title_text, position, piece))
    return chunks
