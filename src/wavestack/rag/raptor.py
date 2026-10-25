"""RAPTOR's tree of summaries (V1.2 story 12, CAP-7): a search on every level of a tree.

RAPTOR (Sarthi et al., 2024, arXiv 2401.18059) clusters the chunks of a corpus, summarizes each
cluster, then clusters and summarizes the summaries, up to a few roots; at each question it
searches every node of the tree at once (the « collapsed tree »), chunks and summaries together.
The workshop ships that tree precomputed in `content/rag_raptor.yaml` (+ `content/i18n/{en,de}/`),
built by a deterministic rule with no model (`method: heuristic`, reproducible byte for byte: no
duration in it, `tools/build_raptor.py`); « Reconstruire » rebuilds it with the active model into
the workshop's data folder (`rag_lab_dir()/raptor/{lang}.yaml`, `method: llm`: the structure of
the rule, each summary written by the model), « Rétablir » deletes that file.

The rule. Leaves: the passages of the paragraphs chunking (`doc_id#rank`, the sha256 of their
text). Each passage is a vector of its words (tf × idf, accents folded, stop words left out); a
summary node's vector is the sum of its leaves'. Clustering: an agglomerative one by average
linkage on the cosine, deterministic (the closest pair first, ties by order), at most
`MAX_CLUSTER` children, never under `MIN_SIMILARITY`; a cluster of one gets no parent. A level
is built on the summary nodes of the level below, up to `MAX_LEVELS`. A summary by the rule:
the sentence of each child closest to the node's vector, the closest first while they hold in
`SUMMARY_MAX_CHARS`, in the corpus's order (an extractive summary; a model writes an
abstractive one). The original embeds the chunks (SBERT) and clusters them by Gaussian mixtures
on UMAP; here the words stand for the embedding, so that the shipped tree needs no model and is
reproducible (story 12, D2).

As PageIndex's tree (`rag/pageindex.py`), the tree read always comes from the chain's documents
(the work copy included): the structure of the file read (rebuilt, else shipped) is kept, a
passage that left the corpus leaves its node, a new passage joins the closest summary node of the
first level, and only the nodes whose children changed get a summary again (by the rule; the
model at an update). Everything here is pure: no model, no session.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from wavestack import config
from wavestack.rag.contexts import _replace
from wavestack.rag.corpus import DocText, split_sentences
from wavestack.rag.graph import _CODE, Passage, _stop_words, _tokens, passages_of

RAPTOR_FILE = "rag_raptor.yaml"
HEURISTIC = "heuristic"
MAX_CLUSTER = 4  # the children of a summary node, at most
MIN_SIMILARITY = 0.08  # two clusters join only when their average cosine is at least this
MAX_LEVELS = 3  # the levels of summaries above the passages
SUMMARY_MAX_CHARS = 400  # a summary's characters (the rule's sentences, a model's)
TOP_NODES = 5  # the nodes the collapsed-tree search keeps for the context
MIN_WORD_CHARS = 3
CODE_BONUS = 1.0  # a sentence citing a code (`TLV-7731-QZ`) first: the fact a question asks
DIGITS = 9  # the similarities are rounded: equal on every system, ties broken by order
ELLIPSIS = "…"

logger = logging.getLogger(__name__)

Vector = dict[str, float]


# ---------- vectors ----------


def words(text: str, stop: frozenset[str]) -> list[str]:
    """The words of a text that carry its subject: folded, at least `MIN_WORD_CHARS` letters,
    neither a stop word nor a number."""
    out = []
    for _, word in _tokens(text):
        if len(word) >= MIN_WORD_CHARS and word not in stop and not word.isdigit():
            out.append(word)
    return out


def idf_of(texts: Sequence[str], stop: frozenset[str]) -> dict[str, float]:
    n = len(texts)
    df: Counter[str] = Counter()
    for text in texts:
        df.update(set(words(text, stop)))
    return {w: math.log((1 + n) / (1 + d)) + 1.0 for w, d in sorted(df.items())}


def vector(text: str, idf: Mapping[str, float], stop: frozenset[str]) -> Vector:
    counts = Counter(words(text, stop))
    return _unit({w: c * idf.get(w, 1.0) for w, c in sorted(counts.items())})


def _unit(vec: Mapping[str, float]) -> Vector:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {w: v / norm for w, v in vec.items()} if norm else {}


def cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return round(sum(v * b.get(w, 0.0) for w, v in a.items()), DIGITS)


def centroid(vectors: Sequence[Mapping[str, float]]) -> Vector:
    total: dict[str, float] = {}
    for vec in vectors:
        for w, v in vec.items():
            total[w] = total.get(w, 0.0) + v
    return _unit(dict(sorted(total.items())))


def cluster(vectors: Sequence[Mapping[str, float]]) -> list[list[int]]:
    """The groups of `vectors` (their indexes, each group in order, the groups by their first):
    agglomerative, average linkage on the cosine (Lance-Williams), the closest pair first (ties:
    the first in order), at most `MAX_CLUSTER` members, never under `MIN_SIMILARITY`."""
    n = len(vectors)
    sim = [[cosine(vectors[i], vectors[j]) if i != j else 0.0 for j in range(n)] for i in range(n)]
    members = {i: [i] for i in range(n)}
    while True:
        best: tuple[float, int, int] | None = None
        active = sorted(members)
        for x, a in enumerate(active):
            row = sim[a]
            for b in active[x + 1 :]:
                s = row[b]
                if s < MIN_SIMILARITY or (best is not None and s <= best[0]):
                    continue
                if len(members[a]) + len(members[b]) <= MAX_CLUSTER:
                    best = (s, a, b)
        if best is None:
            break
        _, a, b = best
        na, nb = len(members[a]), len(members[b])
        for k in active:
            if k not in (a, b):
                s = round((na * sim[a][k] + nb * sim[b][k]) / (na + nb), DIGITS)
                sim[a][k] = sim[k][a] = s
        members[a] = sorted(members[a] + members.pop(b))
    return sorted(members.values(), key=lambda m: m[0])


# ---------- the tree in memory ----------


@dataclass
class Node:
    """A summary node: its stable id (`L{level}-{first passage}`), its level (1 above the
    passages), its children (passages or nodes of the level below), the documents and audience
    of its passages, its summary and where it comes from (`rule`, `shipped`, `rebuilt`), the
    sha256 of its children's, and whether a rebuilt summary was for other children (stale)."""

    id: str
    level: int
    children: list[str]
    sources: list[str] = field(default_factory=list)
    audience: str = "all"
    summary_text: str = ""
    sha256: str = ""
    source: str = "rule"
    stale: bool = False


@dataclass
class Tree:
    """The tree of a list of documents: its passages (the leaves, in order) and its summary
    nodes (by level, then in order), and the files it was read from."""

    leaves: list[Passage]
    nodes: dict[str, Node]
    chunk_max_chars: int = 0
    shipped: RaptorFile | None = None
    rebuilt: RaptorFile | None = None
    error: str | None = None
    placed: int = 0  # the passages a reading placed in the structure of its file

    @property
    def header(self) -> RaptorFile | None:
        return self.rebuilt or self.shipped

    @property
    def levels(self) -> int:
        return max((n.level for n in self.nodes.values()), default=0)

    @property
    def stale(self) -> int:
        return sum(1 for n in self.nodes.values() if n.stale)

    @property
    def by_model(self) -> int:
        return sum(1 for n in self.nodes.values() if n.source == "rebuilt")

    def leaf(self, pid: str) -> Passage | None:
        return next((p for p in self.leaves if p.id == pid), None)

    def unparented(self) -> int:
        """The passages no summary node holds (a cluster of one)."""
        held = {c for n in self.nodes.values() if n.level == 1 for c in n.children}
        return sum(1 for p in self.leaves if p.id not in held)

    def by_level(self) -> dict[int, int]:
        return dict(sorted(Counter(n.level for n in self.nodes.values()).items()))

    def leaves_under(self, node_id: str) -> list[str]:
        node = self.nodes[node_id]
        if node.level == 1:
            return list(node.children)
        return [p for c in node.children for p in self.leaves_under(c)]


def _restrictive(audiences: Sequence[str]) -> str:
    return "hr" if "hr" in audiences else "all"


def _sha(children: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(children).encode()).hexdigest()


def _cut(text: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + ELLIPSIS


def _sentences(text: str) -> list[str]:
    return [
        " ".join(s.split())
        for s in split_sentences(text)
        if s.strip() and not s.lstrip().startswith(("#", "<!--"))
    ]


class _Space:
    """The vectors of a tree's passages, and the rule's summaries."""

    def __init__(self, leaves: Sequence[Passage], lang: str) -> None:
        self.stop = _stop_words(lang)
        self.idf = idf_of([p.text for p in leaves], self.stop)
        self.leaves = {p.id: p for p in leaves}
        self.vectors = {p.id: vector(p.text, self.idf, self.stop) for p in leaves}
        self.order = {p.id: n for n, p in enumerate(leaves)}

    def of(self, leaf_ids: Sequence[str]) -> Vector:
        return centroid([self.vectors[p] for p in leaf_ids if p in self.vectors])

    def summary(self, groups: Sequence[Sequence[str]]) -> str:
        """The rule's summary of a node whose children hold `groups` of passages: the sentence
        of each child closest to the node's vector (one citing a code first, as the graph keeps
        codes), the closest first while they hold in `SUMMARY_MAX_CHARS`, then in the corpus's
        order."""
        target = self.of([p for g in groups for p in g])
        picks = []
        for group in groups:
            best = None
            for pid in sorted(group, key=lambda p: self.order.get(p, 0)):
                if pid not in self.leaves:
                    continue
                for n, sentence in enumerate(_sentences(self.leaves[pid].text)):
                    score = cosine(vector(sentence, self.idf, self.stop), target)
                    score += CODE_BONUS if _CODE.search(sentence) else 0.0
                    key = (-score, self.order[pid], n)
                    if best is None or key < best[0]:
                        best = (key, sentence)
            if best is not None:
                picks.append(best)
        picks.sort(key=lambda b: b[0])
        chosen, used = [], 0
        for key, sentence in picks:
            if used + len(sentence) + (1 if chosen else 0) <= SUMMARY_MAX_CHARS:
                chosen.append((key[1], key[2], sentence))
                used += len(sentence) + (1 if len(chosen) > 1 else 0)
        if not chosen and picks:
            return _cut(picks[0][1])
        return " ".join(s for _, _, s in sorted(chosen))


def _finish(
    tree: Tree, space: _Space, known: Mapping[str, Mapping[str, tuple[str, str]]] | None = None
) -> None:
    """Each node's sources, audience and sha256, bottom-up; its summary from the files `known`
    (`rebuilt` first, then `shipped`: by id, `(sha256, text)`) at equal sha256 and not empty,
    else the rule's (stale when the rebuilt file had one for other children)."""
    known = known or {}
    leaves = {p.id: p for p in tree.leaves}
    first_of = {}
    for n, p in enumerate(tree.leaves):
        first_of.setdefault(p.doc_id, n)
    for node in sorted(tree.nodes.values(), key=lambda n: n.level):
        held = tree.leaves_under(node.id)
        node.sources = sorted({leaves[p].doc_id for p in held}, key=lambda d: first_of[d])
        node.audience = _restrictive([leaves[p].audience for p in held])
        kids = [leaves[c].sha256 if c in leaves else tree.nodes[c].sha256 for c in node.children]
        node.sha256 = _sha(kids)
        for name in ("rebuilt", "shipped"):
            sha, text = known.get(name, {}).get(node.id, ("", ""))
            if text and sha == node.sha256:
                node.summary_text, node.source = text, name
                break
        else:
            node.stale = bool(known.get("rebuilt", {}).get(node.id, ("", ""))[1])
            # one sentence per child: a passage, or the passages a lower node holds
            groups = [[c] if c in leaves else tree.leaves_under(c) for c in node.children]
            node.summary_text, node.source = space.summary(groups), "rule"


def build_tree(
    documents: Sequence[DocText],
    lang: str,
    chunk_max_chars: int,
    audiences: Mapping[str, str] | None = None,
) -> Tree:
    """The tree of `documents` by the rule alone: their passages clustered level by level, each
    node summarized by the rule. Deterministic."""
    leaves = passages_of(documents, chunk_max_chars, audiences)
    tree = Tree(leaves, {}, chunk_max_chars)
    space = _Space(leaves, lang)
    level_ids = [p.id for p in leaves]
    level_vectors = [space.vectors[p] for p in level_ids]
    for level in range(1, MAX_LEVELS + 1):
        groups = [g for g in cluster(level_vectors) if len(g) >= 2]
        if not groups:
            break
        made = []
        for group in groups:
            children = [level_ids[i] for i in group]
            first = children[0] if level == 1 else tree.leaves_under(children[0])[0]
            node = Node(f"L{level}-{first}", level, children)
            tree.nodes[node.id] = node
            made.append(node.id)
        if len(made) < 2:
            break
        level_ids = made
        level_vectors = [space.of(tree.leaves_under(i)) for i in made]
    _finish(tree, space, {})
    return tree


# ---------- the file ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NodeEntry(_Strict):
    id: str = Field(pattern=r"^L\d+-[a-z0-9_]+#\d+$")
    level: int = Field(ge=1)
    children: list[str] = Field(min_length=1)
    sources: list[str]
    audience: Literal["all", "hr"] = "all"
    summary_text: str  # empty: no summary by this file's author (the rule's at the reading)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RaptorFile(_Strict):
    """`rag_raptor.yaml`: who wrote it (`shipped` or `rebuilt`), how (`heuristic` or `llm`),
    with which model, its numbers, and for the rebuilt file only what the rebuild measured (the
    shipped file carries no duration: it is reproducible); then the passages (their sha256) and
    the summary nodes, by level."""

    author: Literal["shipped", "rebuilt"]
    method: Literal["heuristic", "llm"]
    model: str = Field(min_length=1)
    chunk_max_chars: int = Field(ge=1)
    leaves_total: int = Field(ge=0)
    nodes_total: int = Field(ge=0)
    levels: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    calls: int | None = Field(default=None, ge=0)
    leaves: dict[str, str]
    nodes: list[NodeEntry]

    @model_validator(mode="after")
    def _shape(self) -> RaptorFile:
        rebuilt = self.author == "rebuilt"
        if rebuilt != (self.method == "llm"):
            raise ValueError("a shipped tree is heuristic, a rebuilt one summarized by a model")
        measure = (self.duration_ms, self.input_tokens, self.output_tokens, self.calls)
        if rebuilt and any(m is None for m in measure):
            raise ValueError("a rebuilt tree says its duration, tokens and calls")
        if not rebuilt and any(m is not None for m in measure):
            raise ValueError("the shipped tree carries no measure (it is reproducible)")
        known = set(self.leaves)
        for node in self.nodes:
            if missing := [c for c in node.children if c not in known]:
                raise ValueError(f"{node.id}: a child unknown below it: {missing[0]}")
            known.add(node.id)
        return self

    @property
    def tokens(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)


def to_file(
    tree: Tree,
    *,
    author: str = "shipped",
    model: str = HEURISTIC,
    only_model: bool = False,
    measure: Mapping[str, int] | None = None,
) -> RaptorFile:
    """The file of a tree. `only_model` (a rebuild, an update): the summaries a model wrote
    only, the others left empty (the rule's at the reading)."""
    rebuilt = author == "rebuilt"
    return RaptorFile(
        author=author,  # type: ignore[arg-type]
        method="llm" if rebuilt else HEURISTIC,  # type: ignore[arg-type]
        model=model,
        chunk_max_chars=tree.chunk_max_chars,
        leaves_total=len(tree.leaves),
        nodes_total=len(tree.nodes),
        levels=tree.levels,
        leaves={p.id: p.sha256 for p in tree.leaves},
        nodes=[
            NodeEntry(
                id=n.id,
                level=n.level,
                children=n.children,
                sources=n.sources,
                audience=n.audience,  # type: ignore[arg-type]
                summary_text=n.summary_text if not only_model or n.source == "rebuilt" else "",
                sha256=n.sha256,
            )
            for n in sorted(tree.nodes.values(), key=lambda n: n.level)
        ],
        **(dict(measure) if rebuilt and measure else {}),
    )


def dump(file: RaptorFile, comment: str = "") -> str:
    """The file's YAML text, stable (keys in order, no wrapping, the lists of ids inline)."""
    data = file.model_dump(exclude_none=file.author == "shipped")
    nodes = data.pop("nodes")
    head = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1_000_000)
    tail = yaml.safe_dump(
        {"nodes": nodes},
        allow_unicode=True,
        sort_keys=False,
        width=1_000_000,
        default_flow_style=None,
    )
    return f"{comment}{head}{tail}"


def rebuilt_path(lang: str, folder: Path | None = None) -> Path:
    """Where the rebuilt tree of `lang` is kept: the workshop's data folder."""
    return (folder or config.rag_lab_dir()) / "raptor" / f"{lang}.yaml"


def _read(path: Path) -> RaptorFile:
    return RaptorFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_files(
    lang: str, folder: Path | None = None
) -> tuple[RaptorFile | None, RaptorFile | None, str | None]:
    """The shipped tree of `lang` and the rebuilt one when the data folder has it; an
    unreadable rebuilt file is ignored, an unreadable shipped one said."""
    shipped = rebuilt = None
    error = None
    try:
        shipped = _read(config.content_file(RAPTOR_FILE, lang))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        error = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]
    path = rebuilt_path(lang, folder)
    if path.is_file():
        try:
            rebuilt = _read(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            logger.warning("rebuilt RAPTOR tree unreadable, ignored: %s", path)
    return shipped, rebuilt, error


def assemble(
    documents: Sequence[DocText],
    lang: str,
    chunk_max_chars: int,
    *,
    audiences: Mapping[str, str] | None = None,
    shipped: RaptorFile | None = None,
    rebuilt: RaptorFile | None = None,
) -> Tree:
    """The tree of `documents` (the chain's, the work copy included) in the structure of the
    file read (rebuilt, else shipped, at the same passages' size; none: the rule's tree): a
    passage gone leaves its node (a node left empty goes), a new one joins the closest node of
    the first level (or none under `MIN_SIMILARITY`); each summary from the rebuilt file, else
    the shipped one, at equal sha256 of its children, else the rule's."""
    start = next(
        (f for f in (rebuilt, shipped) if f is not None and f.chunk_max_chars == chunk_max_chars),
        None,
    )
    if start is None:
        tree = build_tree(documents, lang, chunk_max_chars, audiences)
        tree.shipped, tree.rebuilt = shipped, rebuilt
        return tree
    leaves = passages_of(documents, chunk_max_chars, audiences)
    current = {p.id for p in leaves}
    tree = Tree(leaves, {}, chunk_max_chars, shipped, rebuilt)
    for entry in sorted(start.nodes, key=lambda e: e.level):
        kids = [c for c in entry.children if c in current or c in tree.nodes]
        if kids:
            tree.nodes[entry.id] = Node(entry.id, entry.level, kids)
    space = _Space(leaves, lang)
    firsts = [n for n in tree.nodes.values() if n.level == 1]
    centres = {n.id: space.of(n.children) for n in firsts}
    order = {p.id: i for i, p in enumerate(leaves)}
    for p in leaves:
        if p.id in start.leaves:
            continue
        scored = [(cosine(space.vectors[p.id], centres[n.id]), -i) for i, n in enumerate(firsts)]
        best = max(scored, default=None)
        if best is not None and best[0] >= MIN_SIMILARITY:
            node = firsts[-best[1]]
            node.children = sorted([*node.children, p.id], key=lambda c: order[c])
            tree.placed += 1
    known = {
        name: {e.id: (e.sha256, e.summary_text) for e in file.nodes} if file else {}
        for name, file in (("shipped", shipped), ("rebuilt", rebuilt))
    }
    _finish(tree, space, known)
    return tree


def resummarize(tree: Tree, nodes: Sequence[Node], lang: str) -> None:
    """The rule's summaries of `nodes` computed again (an update by the rule: its own cost)."""
    space = _Space(tree.leaves, lang)
    leaves = {p.id for p in tree.leaves}
    for node in sorted(nodes, key=lambda n: n.level):
        if node.source == "rule":
            groups = [[c] if c in leaves else tree.leaves_under(c) for c in node.children]
            node.summary_text = space.summary(groups)


def load_tree(
    documents: Sequence[DocText],
    lang: str,
    chunk_max_chars: int,
    *,
    audiences: Mapping[str, str] | None = None,
    folder: Path | None = None,
) -> Tree:
    shipped, rebuilt, error = load_files(lang, folder)
    tree = assemble(
        documents, lang, chunk_max_chars, audiences=audiences, shipped=shipped, rebuilt=rebuilt
    )
    tree.error = error
    return tree


def write_rebuilt(lang: str, file: RaptorFile, folder: Path | None = None) -> Path:
    """The rebuilt file written whole or not at all (`_replace`), in the data folder only."""
    path = rebuilt_path(lang, folder)
    _replace(path, dump(file))
    return path


def forget(lang: str, doc_ids: Sequence[str], folder: Path | None = None) -> int:
    """The passages of `doc_ids` removed from the rebuilt file, and the summaries that read them
    emptied (a summary of several documents mixes their text): a deleted document leaves none
    of its text on disk. A node left without children goes. Written whole (`_replace`), only
    when there was something to remove; the number of passages removed."""
    path = rebuilt_path(lang, folder)
    if not doc_ids or not path.is_file():
        return 0
    try:
        file = _read(path)
    except (OSError, ValueError, yaml.YAMLError, ValidationError):
        return 0
    gone = set(doc_ids)
    leaves = {pid: sha for pid, sha in file.leaves.items() if pid.split("#", 1)[0] not in gone}
    removed = len(file.leaves) - len(leaves)
    known = set(leaves)
    nodes = []
    changed = False
    for entry in sorted(file.nodes, key=lambda e: e.level):
        kids = [c for c in entry.children if c in known]
        touched = bool(gone & set(entry.sources))
        changed = changed or touched or len(kids) != len(entry.children)
        if not kids:
            continue
        known.add(entry.id)
        nodes.append(
            entry.model_copy(
                update={
                    "children": kids,
                    "sources": [s for s in entry.sources if s not in gone],
                    "summary_text": "" if touched else entry.summary_text,
                }
            )
        )
    if not removed and not changed:
        return 0
    _replace(path, dump(file.model_copy(update={"leaves": leaves, "nodes": nodes})))
    return removed


def reset(lang: str, folder: Path | None = None) -> bool:
    """« Rétablir l'arbre livré »: the rebuilt file deleted. Whether there was one."""
    path = rebuilt_path(lang, folder)
    if not path.is_file():
        return False
    path.unlink()
    return True


def clean_summary(answer: str) -> str:
    """A model's answer kept as a summary: its text on one line, cut at `SUMMARY_MAX_CHARS`;
    empty when it wrote nothing."""
    return _cut(answer.strip())


# ---------- the search on every level (« collapsed tree »), pure ----------


@dataclass(frozen=True)
class Pick:
    """A node the search kept: a passage (level 0) or a summary, its documents, its text, its
    BM25 score and its audience (shown, never filtered in the workshop)."""

    node_id: str
    level: int
    doc_id: str
    title_text: str
    text: str
    score: float
    sources: tuple[str, ...]
    audience: str


def searchable(tree: Tree) -> list[tuple[str, int, str]]:
    """Every node of the tree as the search reads it, `(id, level, text)`: the passages, then
    the summaries by level."""
    out = [(p.id, 0, f"{p.title_text}\n{p.text}") for p in tree.leaves]
    out += [(n.id, n.level, n.summary_text) for n in tree.nodes.values()]
    return out


def select(
    tree: Tree,
    question: str,
    lang: str,
    k: int = TOP_NODES,
    scores: Callable[[str, Sequence[str], str], list[float]] | None = None,
) -> list[Pick]:
    """The `k` nodes of every level closest to the question by BM25 (`lab.bm25`), a positive
    score only, ties by order (passages first)."""
    if scores is None:
        from wavestack.rag.lab import bm25  # noqa: PLC0415 - lab imports this module

        scores = bm25
    nodes = searchable(tree)
    found = scores(question, [t for _, _, t in nodes], lang)
    ranked = sorted(
        (i for i, s in enumerate(found) if s > 0), key=lambda i: (-round(found[i], DIGITS), i)
    )[:k]
    leaves = {p.id: p for p in tree.leaves}
    picks = []
    for i in ranked:
        node_id, level, _ = nodes[i]
        if level == 0:
            p = leaves[node_id]
            picks.append(
                Pick(node_id, 0, p.doc_id, p.title_text, p.text, found[i], (p.doc_id,), p.audience)
            )
        else:
            n = tree.nodes[node_id]
            picks.append(
                Pick(
                    node_id,
                    n.level,
                    n.sources[0] if n.sources else "",
                    "",
                    n.summary_text,
                    found[i],
                    tuple(n.sources),
                    n.audience,
                )
            )
    return picks


def summary_source(tree: Tree, node: Node) -> str:
    """What a model reads to summarize `node`: its children's texts (the passages for the first
    level, the summaries below it for the others), one per paragraph."""
    leaves = {p.id: p for p in tree.leaves}
    parts = []
    for c in node.children:
        if c in leaves:
            parts.append(f"{leaves[c].title_text}\n{leaves[c].text}")
        else:
            parts.append(tree.nodes[c].summary_text)
    return "\n\n".join(parts)
