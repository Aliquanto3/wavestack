"""The work copy of the corpus (V1.2 story 3, CAP-8): where « Ajouter », « Modifier » and
« Supprimer un document » act, so that an update can be measured without ever touching
`content/` of the repository.

The copy is a small JSON file in the workshop's data folder
(`config.rag_lab_dir()/work_corpus/{lang}.json`): the documents added, the paragraphs appended
to a document, the documents deleted. « Revenir à l'état livré » deletes it. The shipped
corpus is read as it is; `chunks()` gives the chunks of the corpus with the copy applied.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from wavestack import config
from wavestack.messages import Message
from wavestack.rag.corpus import _COMMENT, Chunk, DocText, RagContent, chunk_documents

OPERATIONS = ("add", "modify", "delete")
ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
TEXT_MAX = 20_000  # characters of a document or a paragraph given by the page
TITLE_MAX = 200

logger = logging.getLogger(__name__)


class WorkDoc(BaseModel):
    title_text: str
    text: str


class WorkCopy(BaseModel):
    """The changes made to the shipped corpus, nothing else."""

    added: dict[str, WorkDoc] = Field(default_factory=dict)
    appended: dict[str, list[str]] = Field(default_factory=dict)  # doc id -> paragraphs
    deleted: list[str] = Field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.appended or self.deleted)


class UpdateRefused(Exception):
    """An update the copy cannot take: `reason` is a `Message`."""

    def __init__(self, reason: Message) -> None:
        super().__init__(str(reason))
        self.reason = reason


def path(lang: str, folder: Path | None = None) -> Path:
    return (folder or config.rag_lab_dir()) / "work_corpus" / f"{lang}.json"


def load(lang: str, folder: Path | None = None) -> WorkCopy:
    """The copy kept for `lang`, or an empty one (absent or unreadable file)."""
    target = path(lang, folder)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return WorkCopy()
    try:
        return WorkCopy.model_validate_json(raw)
    except (ValueError, ValidationError) as exc:
        logger.warning("Copie de travail illisible, lue comme vide : %s (%s)", target, exc)
        return WorkCopy()


def save(copy: WorkCopy, lang: str, folder: Path | None = None) -> None:
    target = path(lang, folder)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(copy.model_dump_json(indent=1), encoding="utf-8")
    os.replace(tmp, target)


def reset(lang: str, folder: Path | None = None) -> bool:
    """Back to the shipped state: the copy is deleted. Returns whether there was one."""
    target = path(lang, folder)
    existed = target.is_file()
    target.unlink(missing_ok=True)
    return existed


def known_ids(content: RagContent, copy: WorkCopy) -> list[str]:
    """The documents that are in the corpus now: the active shipped ones minus the deleted,
    then the added."""
    shipped = [d.id for d in content.documents if d.active and d.id not in copy.deleted]
    return [*shipped, *copy.added]


def apply(
    content: RagContent,
    copy: WorkCopy,
    operation: str,
    doc_id: str,
    title_text: str = "",
    text: str = "",
) -> WorkCopy:
    """A new copy with one operation applied (the given one is left as it is):
    - `add`: a new document, its `doc_id`, title and text;
    - `modify`: `text` is appended to the document as a last paragraph;
    - `delete`: the document leaves the corpus.
    Raises `UpdateRefused`."""
    new = copy.model_copy(deep=True)
    text, title_text = text.strip(), title_text.strip()
    if len(text) > TEXT_MAX or len(title_text) > TITLE_MAX:
        raise UpdateRefused(Message("session.rag_lab.update_too_long", max=TEXT_MAX))
    present = known_ids(content, copy)
    if operation == "add":
        # A shipped document deleted from the copy may come back under its id, as added.
        taken = {d.id for d in content.documents if d.id not in new.deleted} | set(new.added)
        if not ID_PATTERN.match(doc_id):
            raise UpdateRefused(Message("session.rag_lab.update_bad_id"))
        if doc_id in taken:
            raise UpdateRefused(Message("session.rag_lab.update_id_taken", doc=doc_id))
        if not title_text or not text:
            raise UpdateRefused(Message("session.rag_lab.update_empty"))
        new.added[doc_id] = WorkDoc(title_text=title_text, text=text)
        return new
    if operation not in OPERATIONS:
        raise UpdateRefused(Message("session.rag_lab.update_unknown_operation", op=operation))
    if doc_id not in present:
        raise UpdateRefused(Message("session.rag_lab.update_unknown_doc", doc=doc_id))
    if operation == "modify":
        if not text:
            raise UpdateRefused(Message("session.rag_lab.update_empty"))
        if doc_id in new.added:
            added = new.added[doc_id]
            new.added[doc_id] = WorkDoc(title_text=added.title_text, text=f"{added.text}\n\n{text}")
        else:
            new.appended.setdefault(doc_id, []).append(text)
        return new
    if doc_id in new.added:
        del new.added[doc_id]
    else:
        new.deleted.append(doc_id)
    new.appended.pop(doc_id, None)
    return new


def documents(content: RagContent, lang: str, copy: WorkCopy | None = None) -> list[DocText]:
    """The documents of the corpus with the copy applied (their text as `chunks()` reads
    it), the added documents last: what the other chunkings (semantic, parent-child) read."""
    copy = copy or WorkCopy()
    out: list[DocText] = []
    for doc in content.documents:
        if not doc.active or doc.id in copy.deleted:
            continue
        raw = config.content_file(doc.file, lang).read_text(encoding="utf-8-sig")
        text = "\n\n".join([_COMMENT.sub("", raw), *copy.appended.get(doc.id, [])])
        out.append(DocText(doc.id, doc.title_text, text))
    for doc_id, added in copy.added.items():
        out.append(DocText(doc_id, added.title_text, added.text))
    return out


def chunks(
    content: RagContent, max_chars: int, lang: str, copy: WorkCopy | None = None
) -> list[Chunk]:
    """`chunk_corpus` of the corpus with the copy applied (the same text, the same splitting),
    the added documents last."""
    return chunk_documents(documents(content, lang, copy), max_chars)


def summary(content: RagContent, copy: WorkCopy) -> dict[str, object]:
    """What the page shows of the copy: where it lives and what it changes."""
    return {
        "empty": copy.empty,
        "added": list(copy.added),
        "appended": sorted(copy.appended),
        "deleted": list(copy.deleted),
        "documents": [
            {"id": d.id, "title_text": d.title_text}
            for d in content.documents
            if d.active and d.id not in copy.deleted
        ]
        + [{"id": i, "title_text": d.title_text} for i, d in copy.added.items()],
    }


def chunk_keys(items: Sequence[Chunk]) -> set[tuple[str, str, str]]:
    """What identifies a chunk for the delta of an update: its document, title and text."""
    return {(c.doc_id, c.title_text, c.text) for c in items}
