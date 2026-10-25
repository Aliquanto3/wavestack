"""PageIndex's tree of sections (V1.2 story 11, CAP-7): a search without vectors.

PageIndex (Vectify AI) builds, once, a tree of the corpus (the corpus, its documents, their
sections, each with a title and a short summary); at each question the model goes down it level by
level, reading the titles and summaries of the children, until the sections whose text becomes the
context. The workshop ships that tree precomputed, in `content/rag_pageindex.yaml` (+
`content/i18n/{en,de}/`), built by a deterministic rule with no model (`method: heuristic`,
reproducible byte for byte: no duration in it, `tools/build_pageindex.py`); « Reconstruire »
rewrites the summaries with the active model into the workshop's data folder
(`rag_lab_dir()/pageindex/{lang}.yaml`, `method: llm`, read first, entry by entry), « Rétablir »
deletes that file. As the contexts of story 6 (`rag/contexts.py`): the structure always comes from
the chain's documents (the work copy included); each summary comes from the rebuilt file, else
the shipped file, at equal fingerprint, else from the rule (a node « stale » when it had a rebuilt
summary for another text).

The tree has two levels on the shipped corpus (documents, then sections = the blocks between blank
lines, the `# title` line left out); a `## subtitle` block opens an intermediate level whose
sections are the blocks after it.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from wavestack import config
from wavestack.rag.contexts import _replace, fingerprint
from wavestack.rag.corpus import _BLANK_LINE, DocText, split_sentences

PAGEINDEX_FILE = "rag_pageindex.yaml"
HEURISTIC = "heuristic"
ROOT_ID = "corpus"
TREE_SUMMARY_MAX_CHARS = 120  # a summary's characters (the rule's first sentence, a model's)
TITLE_WORDS = 8  # a section's title: its first words
PAGEINDEX_BREADTH = 2  # the nodes the model may keep at each level
ELLIPSIS = "…"
_CHOICE = re.compile(r"^[\s>*_`-]*choice[\s*_`]*:[\s*_`]*(.*)$", re.I)
_NONE = re.compile(r"^\W*none\b", re.I)

logger = logging.getLogger(__name__)

Kind = Literal["root", "document", "heading", "section"]


class TreeNode(BaseModel):
    """A node of the tree: its stable id (`corpus`, `<doc_id>`, `<doc_id>#<rank>`), its parent,
    its kind, its title, its summary and the sha256 of its own text."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    parent: str | None = None
    kind: Kind
    title_text: str = Field(min_length=1)
    summary_text: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TreeFile(BaseModel):
    """`rag_pageindex.yaml`: who wrote it (`shipped` or `rebuilt`), how (`heuristic` or `llm`),
    with which model, and for the rebuilt file only what the rebuild measured (its tokens and
    its duration: the shipped file carries no duration, it is reproducible)."""

    model_config = ConfigDict(extra="forbid")

    author: Literal["shipped", "rebuilt"]
    method: Literal["heuristic", "llm"]
    model: str = Field(min_length=1)
    tokens: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    nodes: list[TreeNode]

    @model_validator(mode="after")
    def _measured_only_when_rebuilt(self) -> TreeFile:
        rebuilt = self.author == "rebuilt"
        if rebuilt != (self.method == "llm"):
            raise ValueError("a shipped tree is heuristic, a rebuilt one written by a model")
        if rebuilt and (self.tokens is None or self.duration_ms is None):
            raise ValueError("a rebuilt tree says its tokens and its duration")
        if not rebuilt and (self.tokens is not None or self.duration_ms is not None):
            raise ValueError("the shipped tree carries no measure (it is reproducible)")
        return self


@dataclass
class Node:
    """A node of the tree in memory: its fields, its own text (a section's whole text, the
    document's for a document), its children's ids, where its summary comes from (`rebuilt`,
    `shipped` or `heuristic`) and whether it is stale (a rebuilt summary of another text)."""

    id: str
    parent: str | None
    kind: str
    title_text: str
    summary_text: str
    sha256: str
    text: str
    doc_id: str | None = None
    rank: int = 0
    children: list[str] = field(default_factory=list)
    source: str = HEURISTIC
    stale: bool = False

    def entry(self) -> TreeNode:
        return TreeNode(
            id=self.id,
            parent=self.parent,
            kind=self.kind,  # type: ignore[arg-type]
            title_text=self.title_text,
            summary_text=self.summary_text,
            sha256=self.sha256,
        )


@dataclass
class Tree:
    """The tree of a list of documents: its nodes by id (in order), and the files it read."""

    nodes: dict[str, Node]
    shipped: TreeFile | None = None
    rebuilt: TreeFile | None = None
    error: str | None = None

    @property
    def root(self) -> Node:
        return self.nodes[ROOT_ID]

    def children(self, node_id: str) -> list[Node]:
        return [self.nodes[c] for c in self.nodes[node_id].children]

    @property
    def header(self) -> TreeFile | None:
        """The file whose header is shown: the rebuilt one, else the shipped one."""
        return self.rebuilt or self.shipped

    @property
    def stale(self) -> int:
        return sum(1 for n in self.nodes.values() if n.stale)

    def depth(self) -> int:
        def down(node_id: str) -> int:
            kids = self.nodes[node_id].children
            return 1 + max((down(k) for k in kids), default=0)

        return down(ROOT_ID) - 1

    def of_document(self, doc_id: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.doc_id == doc_id]


# ---------- the deterministic builder (the shipped tree) ----------


def _short(text: str, limit: int = TREE_SUMMARY_MAX_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + ELLIPSIS


def _first_sentence(text: str) -> str:
    sentences = [s for s in split_sentences(text) if not s.startswith("#")]
    return _short(sentences[0]) if sentences else ""


def _title_of(block: str) -> str:
    words = block.split()
    if len(words) <= TITLE_WORDS:
        return " ".join(words)
    return " ".join(words[:TITLE_WORDS]) + ELLIPSIS


def blocks(text: str) -> list[str]:
    """A document's sections: its blocks between blank lines (the rule of the `paragraphs`
    chunking), the `# title` line left out, empty blocks dropped."""
    out = []
    for raw in _BLANK_LINE.split(text.replace("\r\n", "\n")):
        block = raw.strip()
        if not block:
            continue
        lines = block.splitlines()
        if lines[0].startswith("# "):
            block = "\n".join(lines[1:]).strip()
            if not block:
                continue
        out.append(block)
    return out


def build_tree(documents: Sequence[DocText]) -> dict[str, Node]:
    """The tree of `documents`, by the rule: the root, a node per document (its title, its first
    sentence), a node per section (its first `TITLE_WORDS` words, its first sentence), a
    `## subtitle` block heading the sections after it. Deterministic: the same documents give
    the same tree."""
    nodes: dict[str, Node] = {}
    root = Node(ROOT_ID, None, "root", ROOT_ID, "", "", "")
    nodes[ROOT_ID] = root
    for doc in documents:
        sections = blocks(doc.text)
        node = Node(
            doc.doc_id,
            ROOT_ID,
            "document",
            doc.title_text or doc.doc_id,
            _first_sentence(doc.text) or _short(doc.title_text),
            fingerprint(doc.text),
            doc.text,
            doc.doc_id,
        )
        nodes[node.id] = node
        root.children.append(node.id)
        parent = node
        for rank, block in enumerate(sections, start=1):
            node_id = f"{doc.doc_id}#{rank}"
            if block.startswith("## "):
                head, _, rest = block.partition("\n")
                title = head.lstrip("#").strip() or _title_of(block)
                summary = _first_sentence(rest) or _short(title)
                heading = Node(
                    node_id, doc.doc_id, "heading", title, summary, fingerprint(block), block
                )
                heading.doc_id, heading.rank = doc.doc_id, rank
                nodes[node_id] = heading
                node.children.append(node_id)
                parent = heading
                continue
            section = Node(
                node_id,
                parent.id,
                "section",
                _title_of(block),
                _first_sentence(block) or _short(block),
                fingerprint(block),
                block,
                doc.doc_id,
                rank,
            )
            nodes[node_id] = section
            parent.children.append(node_id)
    titles = [nodes[c].title_text for c in root.children]
    root.summary_text = _short("; ".join(titles))
    digest = hashlib.sha256("\n".join(nodes[c].sha256 for c in root.children).encode())
    root.sha256 = digest.hexdigest()
    return nodes


def shipped_file(nodes: dict[str, Node]) -> TreeFile:
    """The file of a tree built by the rule: no model, no measure."""
    return TreeFile(
        author="shipped",
        method=HEURISTIC,
        model=HEURISTIC,
        nodes=[n.entry() for n in nodes.values()],
    )


def dump(file: TreeFile, comment: str = "") -> str:
    """The file's YAML text, stable (keys in order, no wrapping)."""
    body = yaml.safe_dump(
        file.model_dump(exclude_none=file.author == "shipped"),
        allow_unicode=True,
        sort_keys=False,
        width=1_000_000,
    )
    return f"{comment}{body}"


# ---------- reading: the structure from the documents, the summaries from the files ----------


def rebuilt_path(lang: str, folder: Path | None = None) -> Path:
    """Where the rebuilt tree of `lang` is kept: the workshop's data folder."""
    return (folder or config.rag_lab_dir()) / "pageindex" / f"{lang}.yaml"


def _read(path: Path) -> TreeFile:
    return TreeFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_files(
    lang: str, folder: Path | None = None
) -> tuple[TreeFile | None, TreeFile | None, str | None]:
    """The shipped tree of `lang` (`config.content_file`) and the rebuilt one when the data
    folder has it; an unreadable rebuilt file is ignored, an unreadable shipped one said."""
    shipped = rebuilt = None
    error = None
    try:
        shipped = _read(config.content_file(PAGEINDEX_FILE, lang))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        error = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]
    path = rebuilt_path(lang, folder)
    if path.is_file():
        try:
            rebuilt = _read(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            logger.warning("rebuilt tree unreadable, ignored: %s", path)
    return shipped, rebuilt, error


def assemble(
    documents: Sequence[DocText], shipped: TreeFile | None, rebuilt: TreeFile | None
) -> Tree:
    """The tree of `documents` (the structure), each summary from the rebuilt file, else the
    shipped file, at equal (id, sha256), else the rule's; a node whose id has a rebuilt summary
    for another text is stale."""
    nodes = build_tree(documents)
    by_key = {
        name: {(e.id, e.sha256): e.summary_text for e in file.nodes} if file else {}
        for name, file in (("shipped", shipped), ("rebuilt", rebuilt))
    }
    rebuilt_ids = {e.id for e in rebuilt.nodes} if rebuilt else set()
    for node in nodes.values():
        key = (node.id, node.sha256)
        if key in by_key["rebuilt"]:
            node.summary_text, node.source = by_key["rebuilt"][key], "rebuilt"
        elif key in by_key["shipped"]:
            node.summary_text, node.source = by_key["shipped"][key], "shipped"
        elif node.id in rebuilt_ids:
            node.stale = True
    return Tree(nodes, shipped, rebuilt)


def load_tree(documents: Sequence[DocText], lang: str, folder: Path | None = None) -> Tree:
    shipped, rebuilt, error = load_files(lang, folder)
    tree = assemble(documents, shipped, rebuilt)
    tree.error = error
    return tree


def write_rebuilt(
    lang: str,
    entries: Sequence[TreeNode],
    *,
    model: str,
    tokens: int,
    duration_ms: int,
    folder: Path | None = None,
) -> Path:
    """Keep the summaries a rebuild (or an update) wrote over those an earlier one kept (by id
    and sha256), in the data folder, never `content/`; the header adds this one's measure to
    the earlier ones and names each model. Written whole or not at all (`_replace`)."""
    path = rebuilt_path(lang, folder)
    kept: dict[tuple[str, str], TreeNode] = {}
    if path.is_file():
        try:
            earlier: TreeFile | None = _read(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            earlier = None
        if earlier is not None:
            kept = {(e.id, e.sha256): e for e in earlier.nodes}
            models = [m for m in earlier.model.split(" + ") if m]
            if model not in models:
                models.append(model)
            model = " + ".join(models)
            tokens += earlier.tokens or 0
            duration_ms += earlier.duration_ms or 0
    for entry in entries:
        kept[(entry.id, entry.sha256)] = entry
    file = TreeFile(
        author="rebuilt",
        method="llm",
        model=model,
        tokens=tokens,
        duration_ms=duration_ms,
        nodes=list(kept.values()),
    )
    _replace(path, dump(file))
    return path


def forget(lang: str, doc_ids: Sequence[str], folder: Path | None = None) -> int:
    """The summaries the rebuilt file keeps for the nodes of `doc_ids` (the document and its
    sections), removed: a deleted document leaves none of its text on disk. Written whole
    (`_replace`), only when there was something to remove; the number removed."""
    path = rebuilt_path(lang, folder)
    if not doc_ids or not path.is_file():
        return 0
    try:
        file = _read(path)
    except (OSError, ValueError, yaml.YAMLError, ValidationError):
        return 0
    gone = set(doc_ids)
    kept = [n for n in file.nodes if n.id.split("#", 1)[0] not in gone]
    removed = len(file.nodes) - len(kept)
    if removed:
        _replace(path, dump(file.model_copy(update={"nodes": kept})))
    return removed


def reset(lang: str, folder: Path | None = None) -> bool:
    """« Rétablir l'arbre livré »: the rebuilt file deleted. Whether there was one."""
    path = rebuilt_path(lang, folder)
    if not path.is_file():
        return False
    path.unlink()
    return True


def clean_summary(answer: str) -> str:
    """A model's answer kept as a summary: its first non-empty paragraph, on one line, cut at
    `TREE_SUMMARY_MAX_CHARS`; empty when it wrote nothing."""
    for paragraph in answer.strip().split("\n\n"):
        text = " ".join(paragraph.split())
        if text:
            return _short(text)
    return ""


# ---------- the descent ----------


def parse_choice(answer: str, count: int) -> list[int] | None:
    """The numbers of the first `CHOICE:` line of a model's answer, in `1..count`, at most
    `PAGEINDEX_BREADTH`, each once (a number out of range ignored); `[]` for `CHOICE: NONE` or
    no valid number; `None` when the answer has no `CHOICE:` line (unreadable)."""
    for line in answer.splitlines():
        found = _CHOICE.match(line.strip())
        if found is None:
            continue
        rest = found.group(1)
        if _NONE.match(rest):
            return []
        picked: list[int] = []
        for number in re.findall(r"\d+", rest):
            n = int(number)
            if 1 <= n <= count and n not in picked:
                picked.append(n)
        return picked[:PAGEINDEX_BREADTH]
    return None


def level_list(nodes: Sequence[Node]) -> str:
    """The numbered list a level shows the model: each child's title and summary, nothing
    else."""
    lines = []
    for n, node in enumerate(nodes, start=1):
        summary = f" — {node.summary_text}" if node.summary_text else ""
        lines.append(f"{n}. {node.title_text}{summary}")
    return "\n".join(lines)


__all__ = [
    "PAGEINDEX_BREADTH",
    "PAGEINDEX_FILE",
    "ROOT_ID",
    "TREE_SUMMARY_MAX_CHARS",
    "Node",
    "Tree",
    "TreeFile",
    "TreeNode",
    "assemble",
    "blocks",
    "build_tree",
    "clean_summary",
    "dump",
    "level_list",
    "load_files",
    "load_tree",
    "parse_choice",
    "rebuilt_path",
    "reset",
    "shipped_file",
    "write_rebuilt",
]
