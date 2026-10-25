"""The contexts of the contextual chunking (V1.2 story 6, CAP-4).

Contextual retrieval (Anthropic, 2024) adds to each chunk a short context that situates it in
its document, before the embedding and the lexical index. The workshop ships those contexts
precomputed, in `content/rag_contexts.yaml` (+ `content/i18n/{en,de}/`): one entry per chunk
(its document, its rank, the sha256 of its text, its context) under a header that says who
wrote them (`author`: `shipped` or `rebuilt`), how (`method`: `heuristic`, a deterministic
rule with no model, or `llm`), with which model, at which chunk size and what the build
measured. « Reconstruire » rewrites them with the active model into the workshop's data folder
(`rag_lab_dir()/contexts/{lang}.yaml`, read first, entry by entry); « rétablir » deletes that
file. A context belongs to a chunk by (document, sha256 of its text): a chunk that changed
(another size, a work copy) has none, and the entries left over are counted.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wavestack import config
from wavestack.rag.corpus import Chunk, DocText, split_sentences

CONTEXTS_FILE = "rag_contexts.yaml"
HEURISTIC = "heuristic"
CONTEXT_MAX_CHARS = 400  # a context kept: cut here (the model is asked for far less)
FIRST_SENTENCE_MAX_CHARS = 200  # the heuristic's quotation of the document's opening

logger = logging.getLogger(__name__)


class ContextEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1)
    position: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_text: str = Field(min_length=1)


class ContextsFile(BaseModel):
    """`rag_contexts.yaml`: the header (who, how, with what, at which size, what it cost) and
    the entries."""

    model_config = ConfigDict(extra="forbid")

    author: Literal["shipped", "rebuilt"]
    method: Literal["heuristic", "llm"]
    model: str = Field(min_length=1)  # « heuristic » for the heuristic method
    chunk_max_chars: int = Field(ge=1)
    chunks: int = Field(ge=0)  # chunks written by the build
    tokens: int = Field(ge=0)  # tokens written (an estimate)
    duration_ms: int = Field(ge=0)
    entries: list[ContextEntry]


def fingerprint(text: str) -> str:
    """The sha256 of a chunk's text: what a context is tied to."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def key_of(chunk: Chunk) -> tuple[str, str]:
    return (chunk.doc_id, fingerprint(chunk.text))


@dataclass(frozen=True)
class Applied:
    """A context a chunk got, and where it comes from."""

    context_text: str
    author: str  # `shipped` or `rebuilt`
    method: str  # `heuristic` or `llm`
    model: str


@dataclass
class Book:
    """The contexts available: the shipped file and the rebuilt one (each `None` when absent
    or invalid; `error` says why the shipped one is unusable)."""

    shipped: ContextsFile | None = None
    rebuilt: ContextsFile | None = None
    error: str | None = None

    def entries(self) -> dict[tuple[str, str], Applied]:
        """Every context by (document, sha256): the shipped ones, then the rebuilt ones over
        them (entry by entry)."""
        out: dict[tuple[str, str], Applied] = {}
        for file in (self.shipped, self.rebuilt):
            if file is None:
                continue
            for entry in file.entries:
                out[(entry.doc_id, entry.sha256)] = Applied(
                    entry.context_text, file.author, file.method, file.model
                )
        return out

    @property
    def header(self) -> ContextsFile | None:
        """The file whose header is shown: the rebuilt one, else the shipped one."""
        return self.rebuilt or self.shipped


@dataclass
class Matched:
    """What `match` found for a list of chunks: a context (or `None`) for each, how many
    entries no chunk matches, and a fingerprint of the contexts applied."""

    applied: list[Applied | None]
    ignored: int
    fingerprint: str

    @property
    def contexts(self) -> list[str]:
        return [a.context_text if a else "" for a in self.applied]

    @property
    def missing(self) -> int:
        return sum(1 for a in self.applied if a is None)


def rebuilt_path(lang: str, folder: Path | None = None) -> Path:
    """Where the rebuilt contexts of `lang` are kept: the workshop's data folder."""
    return (folder or config.rag_lab_dir()) / "contexts" / f"{lang}.yaml"


def _read(path: Path) -> ContextsFile:
    return ContextsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_book(lang: str, folder: Path | None = None) -> Book:
    """The shipped contexts of `lang` (`config.content_file`), validated, and the rebuilt
    ones when the data folder has them. An unreadable rebuilt file is ignored (the shipped
    contexts serve); an unreadable shipped file is said in `error`."""
    book = Book()
    try:
        book.shipped = _read(config.content_file(CONTEXTS_FILE, lang))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        book.error = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]
    path = rebuilt_path(lang, folder)
    if path.is_file():
        try:
            book.rebuilt = _read(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            logger.warning("rebuilt contexts unreadable, ignored: %s", path)
    return book


def match(chunks: Sequence[Chunk], book: Book) -> Matched:
    """The context of each chunk (rebuilt before shipped), and the entries left over."""
    entries = book.entries()
    keys = [key_of(c) for c in chunks]
    applied = [entries.get(k) for k in keys]
    ignored = len(set(entries) - set(keys))
    digest = hashlib.sha256()
    for key, a in zip(keys, applied, strict=True):
        if a is not None:
            digest.update(f"{key[0]}\x1f{key[1]}\x1f{a.context_text}\x1e".encode())
    return Matched(applied, ignored, digest.hexdigest()[:16])


# ---------- the deterministic builder of the shipped contexts ----------


def _opening(document: DocText, position: int) -> str:
    """The sentence a heuristic context quotes: the document's first sentence outside its
    title (its second one for the first chunk, whose own text starts with the first)."""
    sentences = [s for s in split_sentences(document.text) if not s.startswith("#")]
    if not sentences:
        return document.title_text
    sentence = sentences[1] if position == 1 and len(sentences) > 1 else sentences[0]
    if len(sentence) > FIRST_SENTENCE_MAX_CHARS:
        sentence = sentence[: FIRST_SENTENCE_MAX_CHARS - 1].rstrip() + "…"
    return sentence


def heuristic_entries(
    documents: Sequence[DocText], chunks: Sequence[Chunk], say: Callable[..., str]
) -> list[ContextEntry]:
    """What the chunk does not say by itself: its rank among its document's chunks, its
    title, how the document opens. `say`: writes the sentence (keywords `position`, `total`,
    `title`, `first`) in the file's language.
    Deterministic: the same corpus gives the same entries."""
    by_id = {d.doc_id: d for d in documents}
    totals: dict[str, int] = {}
    for chunk in chunks:
        totals[chunk.doc_id] = totals.get(chunk.doc_id, 0) + 1
    entries = []
    for chunk in chunks:
        text = say(
            position=chunk.position,
            total=totals[chunk.doc_id],
            title=chunk.title_text,
            first=_opening(by_id[chunk.doc_id], chunk.position),
        )
        entries.append(
            ContextEntry(
                doc_id=chunk.doc_id,
                position=chunk.position,
                sha256=fingerprint(chunk.text),
                context_text=text,
            )
        )
    return entries


def shipped_file(
    entries: list[ContextEntry], chunk_max_chars: int, estimate_tokens
) -> ContextsFile:
    """The header of a file built by the heuristic: no model, no duration."""
    return ContextsFile(
        author="shipped",
        method=HEURISTIC,
        model=HEURISTIC,
        chunk_max_chars=chunk_max_chars,
        chunks=len(entries),
        tokens=sum(estimate_tokens(e.context_text) for e in entries),
        duration_ms=0,
        entries=entries,
    )


def dump(file: ContextsFile, comment: str = "") -> str:
    """The file's YAML text, stable (keys in order, no wrapping)."""
    body = yaml.safe_dump(file.model_dump(), allow_unicode=True, sort_keys=False, width=1_000_000)
    return f"{comment}{body}"


def _replace(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(data, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_rebuilt(
    lang: str,
    entries: Sequence[ContextEntry],
    *,
    model: str,
    chunk_max_chars: int,
    tokens: int,
    duration_ms: int,
    folder: Path | None = None,
) -> Path:
    """Keep the contexts a rebuild wrote, over those an earlier rebuild kept at the same chunk
    size (by document and sha256), in the data folder; never `content/`. The header covers
    every entry of the file: `chunks` counts them, `tokens` and `duration_ms` add this
    rebuild's to the earlier ones kept, `model` names each model that wrote some. An earlier
    file at another chunk size is replaced whole (its header could not describe both)."""
    path = rebuilt_path(lang, folder)
    kept: dict[tuple[str, str], ContextEntry] = {}
    earlier: ContextsFile | None = None
    if path.is_file():
        try:
            earlier = _read(path)
        except (OSError, ValueError, yaml.YAMLError):
            earlier = None
    if earlier is not None and earlier.chunk_max_chars == chunk_max_chars and earlier.entries:
        kept = {(e.doc_id, e.sha256): e for e in earlier.entries}
        models = [m for m in earlier.model.split(" + ") if m]
        if model not in models:
            models.append(model)
        model = " + ".join(models)
        tokens += earlier.tokens
        duration_ms += earlier.duration_ms
    for entry in entries:
        kept[(entry.doc_id, entry.sha256)] = entry
    file = ContextsFile(
        author="rebuilt",
        method="llm",
        model=model,
        chunk_max_chars=chunk_max_chars,
        chunks=len(kept),
        tokens=tokens,
        duration_ms=duration_ms,
        entries=list(kept.values()),
    )
    _replace(path, dump(file))
    return path


def reset(lang: str, folder: Path | None = None) -> bool:
    """« Rétablir les contextes livrés »: the rebuilt file deleted. Whether there was one."""
    path = rebuilt_path(lang, folder)
    if not path.is_file():
        return False
    path.unlink()
    return True


def clean_context(answer: str) -> str:
    """A model's answer kept as a context: its first non-empty paragraph, on one line, cut at
    `CONTEXT_MAX_CHARS`; empty when it wrote nothing."""
    for paragraph in answer.strip().split("\n\n"):
        text = " ".join(paragraph.split())
        if text:
            return text[:CONTEXT_MAX_CHARS].rstrip()
    return ""


__all__ = [
    "Applied",
    "Book",
    "ContextEntry",
    "ContextsFile",
    "Matched",
    "clean_context",
    "dump",
    "fingerprint",
    "heuristic_entries",
    "key_of",
    "load_book",
    "match",
    "rebuilt_path",
    "reset",
    "shipped_file",
    "write_rebuilt",
]
