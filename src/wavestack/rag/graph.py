"""GraphRAG's knowledge graph, simplified (V1.2 story 13, CAP-7).

GraphRAG (Microsoft, 2024) extracts the entities of a corpus and their relations, groups the
entities into communities and summarizes each community; a local question goes from the entities
it names to their neighbours, a global one reads the summaries. The workshop ships that graph
precomputed in `content/rag_graph.yaml` (+ `content/i18n/{en,de}/`), built by a deterministic
rule with no model (`method: heuristic`, reproducible byte for byte: no duration in it,
`tools/build_graph.py`); « Reconstruire » extracts it again with the active model into the
workshop's data folder (`rag_lab_dir()/graph/{lang}.yaml`, `method: llm`, read first, passage by
passage), « Rétablir » deletes that file.

The rule. Entities: per document its `TERMS_PER_DOC` best key terms (words and pairs of words,
tf × log(N / df), the vocabulary frozen at the construction), acronyms, codes (`ORN-7731-QZ`, kept
from one mention), proper names of two words or more, quoted terms; an entity other than a code
mentioned in a single passage is dropped. Relations: two entities in one sentence (weight: the
sentences), no label (« apparaît avec »). Each entity and relation keeps its evidence: the
passages of the paragraphs chunking (`doc_id#rank`), each with the sha256 of its text.
Communities: deterministic local moves of modularity (Louvain's first phase), home-made.

As PageIndex's tree (`rag/pageindex.py`): the structure always comes from the chain's documents
(the work copy included), never from the disk; a passage the rebuilt file knows at the same
sha256 takes the model's extraction, another one the rule's (« stale » when the rebuilt file had
it for another text). Everything here is pure: no model, no session; the workshop's calls (the
question's entities, the « map » of a global question, the rebuild) only wrap it.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from wavestack import config
from wavestack.rag.contexts import _replace, fingerprint
from wavestack.rag.corpus import DocText, chunk_documents, split_sentences

GRAPH_FILE = "rag_graph.yaml"
HEURISTIC = "heuristic"
TERMS_PER_DOC = 6  # the key terms a document brings to the vocabulary
MIN_WORD_CHARS = 4
COMMUNITY_ROUNDS = 20
MIN_COMMUNITY = 3
COMMUNITY_SUMMARY_MAX_CHARS = 400
LOCAL_MAX_ENTITIES = 4
LOCAL_MAX_NEIGHBORS = 8
LOCAL_MAX_PASSAGES = 6
GLOBAL_TOP_COMMUNITIES = 3
GLOBAL_KEY_PASSAGES = 2  # the passages a « map » call reads with a community's summary
NAME_MAX_CHARS = 80  # an entity's name a model may write
ELLIPSIS = "…"
_EPSILON = 1e-12

Audience = Literal["all", "hr"]

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[\w'’-]+")
_NUMBER = re.compile(r"[\d.,:/-]+")
_ELISION = re.compile(r"\b(?:[cdjlmnst]|qu)'")
_CODE = re.compile(r"\b[A-Z]{2,}[0-9]*(?:-[A-Za-z0-9]+)+\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,}[0-9]*\b")
_UPPER = "A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ"
_PROPER = re.compile(
    rf"(?<![\w])([{_UPPER}][\w'-]+(?:\s+(?:de|du|des|la|le|d'|of|the|der|die|das|und|et|&)?\s*"
    rf"[{_UPPER}][\w'-]+)+)"
)
_QUOTED = re.compile(r"«\s*([^»]{2,60}?)\s*»|„([^“]{2,60})“|\"([^\"]{2,60})\"")
_FIRST_WORD = re.compile(r"\s*[\w'-]+")
_ENTITIES = re.compile(r"^[\s>*_`-]*entities[\s*_`]*:[\s*_`]*(.*)$", re.I)
_POINTS = re.compile(r"^[\s>*_`-]*points[\s*_`]*:[\s*_`]*(.*)$", re.I)
_ENTITY = re.compile(r"^[\s>*_`-]*entity[\s*_`]*:[\s*_`]*(.*)$", re.I)
_RELATION = re.compile(r"^[\s>*_`-]*relation[\s*_`]*:[\s*_`]*(.*)$", re.I)
_NONE = re.compile(r"^\W*(none|aucune?|keine)\W*$", re.I)
_SPLIT = re.compile(r"[,;]")
_QUOTES = " \t\"'«»“”„`*"


# ---------- words ----------


def normalize(text: str) -> str:
    """Lower case, accents dropped, elision (« l' », « d' ») removed, spaces folded."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    flat = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_ELISION.sub("", flat).split())


def slug(key: str) -> str:
    """An entity's stable id: its normalized name, words joined by « - »."""
    return re.sub(r"\W+", "-", normalize(key)).strip("-") or "x"


def _stop_words(lang: str) -> frozenset[str]:
    from wavestack.rag.lab import STOP_WORDS_BY_LANG  # noqa: PLC0415 - lab imports this module

    return STOP_WORDS_BY_LANG.get(
        config.as_language(lang), STOP_WORDS_BY_LANG[config.DEFAULT_LANGUAGE]
    )


def _tokens(sentence: str) -> list[tuple[str, str]]:
    """`(surface, normalized)` of each word: the surface in lower case, the elision removed."""
    out = []
    for raw in _TOKEN.findall(sentence):
        surface = raw.lower().replace("’", "'").split("'")[-1].strip("-")
        if surface:
            out.append((surface, normalize(surface)))
    return out


def _full(word: str, stop: frozenset[str]) -> bool:
    return len(word) >= MIN_WORD_CHARS and word not in stop and not _NUMBER.fullmatch(word)


def grams(sentence: str, stop: frozenset[str]) -> dict[str, str]:
    """The words and pairs of words of a sentence that may be key terms, normalized -> surface:
    full words (`MIN_WORD_CHARS` letters, not a stop word, not a number), and two full words
    side by side or separated by stop words only (« gestion de crise »)."""
    words = _tokens(sentence)
    out: dict[str, str] = {}
    for i, (surface, word) in enumerate(words):
        if not _full(word, stop):
            continue
        out.setdefault(word, surface)
        for j in (i + 1, i + 2):
            if j < len(words) and _full(words[j][1], stop):
                if all(words[k][1] in stop for k in range(i + 1, j)):
                    key = " ".join(w for _, w in words[i : j + 1])
                    out.setdefault(key, " ".join(s for s, _ in words[i : j + 1]))
    return out


def specials(sentence: str) -> dict[str, tuple[str, str]]:
    """The entities a sentence names by their form, normalized -> (surface, type): codes
    (`ORN-7731-QZ`), acronyms, proper names of two words or more (not at the sentence's start:
    its first word is dropped), quoted terms."""
    out: dict[str, tuple[str, str]] = {}

    def add(surface: str, kind: str) -> None:
        surface = " ".join(surface.split()).strip(_QUOTES)
        key = normalize(surface)
        if len(key) >= 2 and not _NUMBER.fullmatch(key):
            out.setdefault(key, (surface, kind))

    for found in _CODE.finditer(sentence):
        add(found.group(), "code")
    body = _CODE.sub(" ", sentence)
    first = _FIRST_WORD.match(body)
    for found in _PROPER.finditer(body):
        words = found.group(1).split()
        if first and found.start(1) == first.end() - len(first.group().lstrip()):
            if len(words) < 3:
                continue
            words = words[1:]
        add(" ".join(words), "name")
    for found in _ACRONYM.finditer(body):
        add(found.group(), "acronym")
    for found in _QUOTED.finditer(body):
        add(next(g for g in found.groups() if g), "quoted")
    return out


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + ELLIPSIS


def _has(norm_text: str, key: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", norm_text) is not None


# ---------- the passages and the frozen vocabulary ----------


@dataclass(frozen=True)
class Passage:
    """A passage of the paragraphs chunking: `doc_id#rank`, its document, its text."""

    id: str
    doc_id: str
    rank: int
    title_text: str
    text: str
    sha256: str
    audience: str = "all"


def passages_of(
    documents: Sequence[DocText], chunk_max_chars: int, audiences: Mapping[str, str] | None = None
) -> list[Passage]:
    audiences = audiences or {}
    return [
        Passage(
            f"{c.doc_id}#{c.position}",
            c.doc_id,
            c.position,
            c.title_text,
            c.text,
            fingerprint(c.text),
            audiences.get(c.doc_id, "all"),
        )
        for c in chunk_documents(documents, chunk_max_chars)
    ]


@dataclass(frozen=True)
class Vocabulary:
    """The vocabulary of a construction: its documents' number, each word's document frequency,
    the key terms kept, and the text each document had (its sha256)."""

    documents: int
    df: Mapping[str, int]
    terms: frozenset[str]
    known: Mapping[str, str]


def _tf(passages: Sequence[Passage], stop: frozenset[str]) -> dict[str, Counter[str]]:
    tf: dict[str, Counter[str]] = defaultdict(Counter)
    for p in passages:
        for sentence in split_sentences(p.text):
            for key in grams(sentence, stop):
                tf[p.doc_id][key] += 1
    return tf


def _best(counts: Counter[str], df: Mapping[str, int], n: int, extra: int = 0) -> list[str]:
    scored = []
    for key, tf in counts.items():
        freq = max(1, df.get(key, 0) + extra)
        if tf >= 2 and 2 <= freq and 3 * freq <= n:
            scored.append((-tf * math.log(n / freq), key))
    return [key for _, key in sorted(scored)[:TERMS_PER_DOC]]


def vocabulary(documents: Sequence[DocText], lang: str, chunk_max_chars: int) -> Vocabulary:
    """The key terms of `documents`: for each, its `TERMS_PER_DOC` best words or pairs by tf ×
    log(N / df) (tf: its sentences that hold it, at least 2; df: the documents, 2 to N / 3),
    ties by term."""
    stop = _stop_words(lang)
    tf = _tf(passages_of(documents, chunk_max_chars), stop)
    df: Counter[str] = Counter()
    for counts in tf.values():
        df.update(counts.keys())
    n = len(documents)
    terms: set[str] = set()
    for counts in tf.values():
        terms.update(_best(counts, df, n))
    known = {d.doc_id: fingerprint(d.text) for d in documents}
    return Vocabulary(n, dict(df), frozenset(terms), known)


def terms_for(
    documents: Sequence[DocText], vocab: Vocabulary, lang: str, chunk_max_chars: int
) -> frozenset[str]:
    """The frozen vocabulary, plus the key terms of each document it did not know with this
    text (added or modified), computed against its frozen frequencies: the other documents'
    key terms do not change."""
    stop = _stop_words(lang)
    extra: set[str] = set()
    for doc in documents:
        if vocab.known.get(doc.doc_id) == fingerprint(doc.text):
            continue
        counts = _tf(passages_of([doc], chunk_max_chars), stop).get(doc.doc_id, Counter())
        added = 0 if doc.doc_id in vocab.known else 1
        extra.update(_best(counts, vocab.df, vocab.documents, added))
    return vocab.terms | extra


# ---------- one passage's extraction ----------


@dataclass
class Extraction:
    """What one passage brings: its entities (id -> name, type) and its relations ((a, b) ->
    weight, label), by the rule or by a model (`by_model`)."""

    entities: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    relations: dict[tuple[str, str], tuple[int, str]] = field(default_factory=dict)
    by_model: bool = False


def extract(text: str, terms: frozenset[str], lang: str) -> Extraction:
    """The rule on one passage: in each sentence, its key terms and its entities by form; a
    relation for each pair of them (its weight: the sentences)."""
    stop = _stop_words(lang)
    out = Extraction()
    for sentence in split_sentences(text):
        found: dict[str, tuple[str, str | None]] = {}
        for key, (surface, kind) in specials(sentence).items():
            found.setdefault(slug(key), (surface, kind))
        for key, surface in grams(sentence, stop).items():
            if key in terms:
                found.setdefault(slug(key), (surface, "term"))
        for eid, value in found.items():
            out.entities.setdefault(eid, value)
        ids = sorted(found)
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                weight, label = out.relations.get((a, b), (0, ""))
                out.relations[(a, b)] = (weight + 1, label)
    return out


def _name(text: str) -> str:
    return _cut(text.strip(_QUOTES), NAME_MAX_CHARS)


def parse_extraction(answer: str) -> Extraction | None:
    """A model's extraction of a passage: its `ENTITY: name | type` and `RELATION: a | b | verb`
    lines (a relation's ends are entities too); `None` when it has neither (unreadable). Only
    these lines of the model are read, never the passage."""
    out = Extraction(by_model=True)
    seen = False
    for line in answer.splitlines():
        line = line.strip()
        if found := _ENTITY.match(line):
            seen = True
            parts = [p.strip() for p in found.group(1).split("|")]
            name = _name(parts[0]) if parts else ""
            if name and normalize(name):
                kind = _name(parts[1]) if len(parts) > 1 and parts[1].strip() else None
                out.entities.setdefault(slug(name), (name, kind or None))
        elif found := _RELATION.match(line):
            seen = True
            parts = [p.strip() for p in found.group(1).split("|")]
            if len(parts) < 2:
                continue
            a, b = _name(parts[0]), _name(parts[1])
            if not (normalize(a) and normalize(b)) or slug(a) == slug(b):
                continue
            label = _name(parts[2]) if len(parts) > 2 else ""
            for name in (a, b):
                out.entities.setdefault(slug(name), (name, None))
            key = tuple(sorted((slug(a), slug(b))))
            weight, kept = out.relations.get(key, (0, ""))  # type: ignore[arg-type]
            out.relations[key] = (weight + 1, kept or label)  # type: ignore[index]
    return out if seen else None


# ---------- the graph in memory ----------


@dataclass
class Entity:
    id: str
    name: str
    type: str | None
    mentions: list[str]
    audience: str = "all"
    by_model: bool = False


@dataclass
class Relation:
    source: str
    target: str
    label: str
    weight: int
    evidence: list[str]
    audience: str = "all"


@dataclass
class Community:
    id: str
    entities: list[str]
    audience: str
    sources: list[str]
    summary_text: str
    sha256: str
    summary_source: str = HEURISTIC  # `rebuilt`, `shipped` or `heuristic`


def _restrictive(audiences: Sequence[str]) -> str:
    return "hr" if "hr" in audiences else "all"


@dataclass
class Graph:
    """The graph of a list of documents: its passages, entities, relations and communities (in
    id order), each passage's extraction, the files it read and what they said."""

    passages: dict[str, Passage] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)
    relations: dict[tuple[str, str], Relation] = field(default_factory=dict)
    communities: dict[str, Community] = field(default_factory=dict)
    extractions: dict[str, Extraction] = field(default_factory=dict)
    shipped: GraphFile | None = None
    rebuilt: GraphFile | None = None
    error: str | None = None
    stale: int = 0  # passages the rebuilt file had for another text
    chunk_max_chars: int = 0

    @property
    def header(self) -> GraphFile | None:
        return self.rebuilt or self.shipped

    @property
    def isolated(self) -> int:
        """Entities without any relation: outside every community."""
        linked = {e for pair in self.relations for e in pair}
        return sum(1 for e in self.entities if e not in linked)

    @property
    def by_model(self) -> int:
        return sum(1 for x in self.extractions.values() if x.by_model)

    def community_of(self) -> dict[str, str]:
        return {e: c.id for c in self.communities.values() for e in c.entities}

    def neighbours(self) -> dict[str, list[Relation]]:
        out: dict[str, list[Relation]] = defaultdict(list)
        for rel in self.relations.values():
            out[rel.source].append(rel)
            out[rel.target].append(rel)
        return out

    def of_document(self, doc_id: str) -> list[Passage]:
        return [p for p in self.passages.values() if p.doc_id == doc_id]


def merge(passages: Sequence[Passage], extractions: Mapping[str, Extraction]) -> Graph:
    """The entities and relations of the passages' extractions, merged by id: an entity other
    than a code, mentioned in one passage only and by the rule only, is dropped; a relation
    keeps its ends. Sorted by id: the same input gives the same graph."""
    graph = Graph(passages={p.id: p for p in passages}, extractions=dict(extractions))
    found: dict[str, Entity] = {}
    links: dict[tuple[str, str], Relation] = {}
    for p in passages:
        x = extractions.get(p.id)
        if x is None:
            continue
        for eid, (name, kind) in x.entities.items():
            entity = found.get(eid)
            if entity is None:
                entity = found[eid] = Entity(eid, name, kind, [])
            entity.type = entity.type or kind
            if entity.mentions[-1:] != [p.id]:
                entity.mentions.append(p.id)
            entity.by_model = entity.by_model or x.by_model
        for (a, b), (weight, label) in x.relations.items():
            rel = links.get((a, b))
            if rel is None:
                rel = links[(a, b)] = Relation(a, b, label, 0, [])
            rel.weight += weight
            rel.label = rel.label or label
            rel.evidence.append(p.id)
    kept = {
        eid: e for eid, e in found.items() if e.type == "code" or e.by_model or len(e.mentions) >= 2
    }
    for eid in sorted(kept):
        e = kept[eid]
        e.audience = _restrictive([graph.passages[m].audience for m in e.mentions])
        graph.entities[eid] = e
    for key in sorted(links):
        rel = links[key]
        if rel.source in kept and rel.target in kept:
            rel.audience = _restrictive([graph.passages[m].audience for m in rel.evidence])
            graph.relations[key] = rel
    return graph


# ---------- the communities: local moves of modularity (Louvain's first phase) ----------


def _adjacency(graph: Graph) -> dict[str, dict[str, int]]:
    adj: dict[str, dict[str, int]] = defaultdict(dict)
    for rel in graph.relations.values():
        if rel.source == rel.target:
            continue
        adj[rel.source][rel.target] = adj[rel.source].get(rel.target, 0) + rel.weight
        adj[rel.target][rel.source] = adj[rel.target].get(rel.source, 0) + rel.weight
    return adj


def communities(graph: Graph, previous: Sequence[Sequence[str]] | None = None) -> list[list[str]]:
    """The communities of the entities that have a relation, by deterministic local moves of
    modularity: nodes in id order, each joins the neighbouring community of strictly greatest
    gain (ties: the smallest id), `COMMUNITY_ROUNDS` rounds at most or until no node moves;
    then a community smaller than `MIN_COMMUNITY` joins its most linked neighbour (ties: the
    smallest id). `previous` (an update): the existing entities start in their previous
    community, the new ones alone, so that the untouched communities stay. Each community's
    entities sorted, the communities by their smallest id."""
    adj = _adjacency(graph)
    nodes = sorted(adj)
    if not nodes:
        return []
    start: list[list[str]] = []
    placed: set[str] = set()
    for group in previous or ():
        members = sorted(e for e in group if e in adj and e not in placed)
        if members:
            start.append(members)
            placed.update(members)
    start += [[e] for e in nodes if e not in placed]
    start.sort(key=lambda g: g[0])
    label = {e: n for n, group in enumerate(start) for e in group}
    degree = {e: sum(adj[e].values()) for e in nodes}
    m2 = sum(degree.values())
    total: Counter[int] = Counter()
    for e in nodes:
        total[label[e]] += degree[e]
    for _ in range(COMMUNITY_ROUNDS):
        moved = False
        for e in nodes:
            here = label[e]
            total[here] -= degree[e]
            links: Counter[int] = Counter()
            for other, weight in adj[e].items():
                links[label[other]] += weight
            best, gain = here, links[here] - total[here] * degree[e] / m2
            for c in sorted(links):
                g = links[c] - total[c] * degree[e] / m2
                if g > gain + _EPSILON:
                    best, gain = c, g
            label[e] = best
            total[best] += degree[e]
            moved = moved or best != here
        if not moved:
            break
    groups: dict[int, list[str]] = defaultdict(list)
    for e in nodes:
        groups[label[e]].append(e)
    merged = [sorted(g) for g in groups.values()]
    while True:
        small = sorted((g for g in merged if len(g) < MIN_COMMUNITY), key=lambda g: (len(g), g[0]))
        target = None
        for group in small:
            inside = set(group)
            weights: Counter[int] = Counter()
            for n, other in enumerate(merged):
                if other is group:
                    continue
                weights[n] = sum(adj[e].get(o, 0) for e in inside for o in other)
            linked = [(w, merged[n][0], n) for n, w in weights.items() if w > 0]
            if linked:
                best = min(linked, key=lambda x: (-x[0], x[1]))
                target = (group, merged[best[2]])
                break
        if target is None:
            break
        group, into = target
        merged = [g for g in merged if g is not group and g is not into] + [sorted(group + into)]
    return sorted(merged, key=lambda g: g[0])


def community_sha(graph: Graph, members: Sequence[str]) -> str:
    """A community's fingerprint: its entities and the sha256 of their evidence."""
    shas = sorted({graph.passages[m].sha256 for e in members for m in graph.entities[e].mentions})
    return hashlib.sha256(
        ("\n".join(sorted(members)) + "\n\n" + "\n".join(shas)).encode()
    ).hexdigest()


def _sources(graph: Graph, members: Sequence[str]) -> list[str]:
    counts: Counter[str] = Counter()
    for e in members:
        for m in graph.entities[e].mentions:
            counts[graph.passages[m].doc_id] += 1
    return [d for d, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]


def internal_relations(graph: Graph, members: Sequence[str]) -> list[Relation]:
    inside = set(members)
    rels = [r for r in graph.relations.values() if r.source in inside and r.target in inside]
    return sorted(rels, key=lambda r: (-r.weight, r.source, r.target))


def key_passages(graph: Graph, members: Sequence[str], limit: int) -> list[Passage]:
    """A community's passages, those of its heaviest relations first."""
    out: list[str] = []
    for rel in internal_relations(graph, members):
        for m in rel.evidence:
            if m not in out:
                out.append(m)
            if len(out) == limit:
                return [graph.passages[x] for x in out]
    for e in members:
        for m in graph.entities[e].mentions:
            if m not in out and len(out) < limit:
                out.append(m)
    return [graph.passages[x] for x in out]


def rule_summary(graph: Graph, members: Sequence[str]) -> str:
    """The rule's summary of a community: its main documents' titles, then the first sentence
    of its heaviest relations' evidence that names both ends, cut at
    `COMMUNITY_SUMMARY_MAX_CHARS`."""
    titles: list[str] = []
    for doc in _sources(graph, members)[:3]:
        title = next(p.title_text for p in graph.passages.values() if p.doc_id == doc)
        titles.append(title)
    keys = {e: normalize(graph.entities[e].name) for e in members}
    said: list[str] = []
    for rel in internal_relations(graph, members):
        for m in rel.evidence:
            for sentence in split_sentences(graph.passages[m].text):
                if sentence.startswith("#"):
                    continue
                norm = normalize(sentence)
                if _has(norm, keys[rel.source]) and _has(norm, keys[rel.target]):
                    if sentence not in said:
                        said.append(sentence)
                    break
        if sum(len(s) + 1 for s in said) > COMMUNITY_SUMMARY_MAX_CHARS:
            break
    head = " ; ".join(titles)
    return _cut(f"{head} : {' '.join(said)}" if said else head, COMMUNITY_SUMMARY_MAX_CHARS)


def form_communities(
    graph: Graph,
    previous: Sequence[Sequence[str]] | None = None,
    summaries: Sequence[GraphFile | None] = (),
    *,
    summarize: bool = True,
) -> None:
    """The graph's communities set: their entities (`communities`), audience, sources and
    fingerprint; each summary from the first file (rebuilt, then shipped) that has one at the
    same fingerprint, else the rule's (left empty when not `summarize`: the caller writes it)."""
    known: list[tuple[str, dict[str, str]]] = []
    for file in summaries:
        if file is not None:
            known.append((file.author, {c.sha256: c.summary_text for c in file.communities}))
    graph.communities = {}
    for members in communities(graph, previous):
        sha = community_sha(graph, members)
        summary, source = None, HEURISTIC
        for author, by_sha in known:
            if sha in by_sha:
                summary, source = by_sha[sha], author
                break
        audience = _restrictive([graph.entities[e].audience for e in members])
        graph.communities[members[0]] = Community(
            members[0],
            list(members),
            audience,
            _sources(graph, members),
            summary if summary is not None else (rule_summary(graph, members) if summarize else ""),
            sha,
            source,
        )


# ---------- the file ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


_ID = r"^[\w-]+$"
_PASSAGE = r"^[a-z0-9_]+#\d+$"


class EntityEntry(_Strict):
    id: str = Field(pattern=_ID)
    name: str = Field(min_length=1)
    type: str | None = None
    audience: Audience = "all"
    mentions: list[str] = Field(min_length=1)


class RelationEntry(_Strict):
    source: str = Field(pattern=_ID)
    target: str = Field(pattern=_ID)
    label: str = ""
    weight: int = Field(ge=1)
    audience: Audience = "all"
    evidence: list[str] = Field(min_length=1)


class CommunityEntry(_Strict):
    id: str = Field(pattern=_ID)
    entities: list[str] = Field(min_length=1)
    audience: Audience = "all"
    sources: list[str]
    summary_text: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GraphFile(_Strict):
    """`rag_graph.yaml`: who wrote it (`shipped` or `rebuilt`), how (`heuristic` or `llm`), with
    which model, its numbers, and for the rebuilt file only what the rebuild measured (the
    shipped file carries no duration: it is reproducible); then the passages cited (their
    sha256, once each), the entities, the relations and the communities."""

    author: Literal["shipped", "rebuilt"]
    method: Literal["heuristic", "llm"]
    model: str = Field(min_length=1)
    chunk_max_chars: int = Field(ge=1)
    entities_total: int = Field(ge=0)
    relations_total: int = Field(ge=0)
    communities_total: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    calls: int | None = Field(default=None, ge=0)
    passages: dict[str, str]
    entities: list[EntityEntry]
    relations: list[RelationEntry]
    communities: list[CommunityEntry]

    @model_validator(mode="after")
    def _shape(self) -> GraphFile:
        rebuilt = self.author == "rebuilt"
        if rebuilt != (self.method == "llm"):
            raise ValueError("a shipped graph is heuristic, a rebuilt one extracted by a model")
        measure = (self.duration_ms, self.input_tokens, self.output_tokens, self.calls)
        if rebuilt and any(m is None for m in measure):
            raise ValueError("a rebuilt graph says its duration, tokens and calls")
        if not rebuilt and any(m is not None for m in measure):
            raise ValueError("the shipped graph carries no measure (it is reproducible)")
        cited = [m for e in self.entities for m in e.mentions]
        cited += [m for r in self.relations for m in r.evidence]
        if missing := sorted(set(cited) - set(self.passages)):
            raise ValueError(f"evidence without a passage: {', '.join(missing[:3])}")
        return self

    @property
    def tokens(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)


def to_file(
    graph: Graph,
    *,
    author: str = "shipped",
    model: str = HEURISTIC,
    only_model: bool = False,
    summaries: Sequence[str] | None = None,
    measure: Mapping[str, int] | None = None,
) -> GraphFile:
    """The file of a graph. `only_model` (a rebuild): only the passages a model extracted, their
    entities and relations, and the communities of `summaries` (those a model summarized)."""
    keep = {pid for pid, x in graph.extractions.items() if x.by_model or not only_model} & set(
        graph.passages
    )

    def cited(ids: Sequence[str]) -> list[str]:
        return [m for m in ids if m in keep]

    entities = [
        EntityEntry(
            id=e.id, name=e.name, type=e.type, audience=e.audience, mentions=cited(e.mentions)
        )
        for e in graph.entities.values()
        if cited(e.mentions)
    ]
    relations = [
        RelationEntry(
            source=r.source,
            target=r.target,
            label=r.label,
            weight=r.weight if not only_model else max(1, len(cited(r.evidence))),
            audience=r.audience,
            evidence=cited(r.evidence),
        )
        for r in graph.relations.values()
        if cited(r.evidence)
    ]
    chosen = set(summaries) if summaries is not None else None
    comms = [
        CommunityEntry(
            id=c.id,
            entities=c.entities,
            audience=c.audience,
            sources=c.sources,
            summary_text=c.summary_text,
            sha256=c.sha256,
        )
        for c in graph.communities.values()
        if chosen is None or c.id in chosen
    ]
    used = sorted(
        {m for e in entities for m in e.mentions} | {m for r in relations for m in r.evidence},
        key=_order(graph),
    )
    rebuilt = author == "rebuilt"
    return GraphFile(
        author=author,  # type: ignore[arg-type]
        method="llm" if rebuilt else HEURISTIC,  # type: ignore[arg-type]
        model=model,
        chunk_max_chars=graph.chunk_max_chars,
        entities_total=len(graph.entities),
        relations_total=len(graph.relations),
        communities_total=len(graph.communities),
        passages={m: graph.passages[m].sha256 for m in used},
        entities=entities,
        relations=relations,
        communities=comms,
        **(dict(measure) if rebuilt and measure else {}),
    )


def _order(graph: Graph):  # noqa: ANN202
    rank = {pid: n for n, pid in enumerate(graph.passages)}
    return lambda pid: rank.get(pid, len(rank))


def dump(file: GraphFile, comment: str = "") -> str:
    """The file's YAML text, stable (keys in order, no wrapping)."""
    data = file.model_dump(exclude_none=file.author == "shipped")
    lists = {k: data.pop(k) for k in ("entities", "relations", "communities")}
    # The header and the passages one per line; the lists of ids on one line each.
    head, tail = (
        yaml.safe_dump(
            part,
            allow_unicode=True,
            sort_keys=False,
            width=1_000_000,
            default_flow_style=style,
        )
        for part, style in ((data, False), (lists, None))
    )
    return f"{comment}{head}{tail}"


# ---------- building and reading ----------


def build_graph(
    documents: Sequence[DocText],
    lang: str,
    chunk_max_chars: int,
    audiences: Mapping[str, str] | None = None,
) -> Graph:
    """The graph of `documents` by the rule alone: their vocabulary, each passage extracted,
    merged, then the communities and their summaries by the rule. Deterministic."""
    vocab = vocabulary(documents, lang, chunk_max_chars)
    passages = passages_of(documents, chunk_max_chars, audiences)
    extractions = {p.id: extract(p.text, vocab.terms, lang) for p in passages}
    graph = merge(passages, extractions)
    graph.chunk_max_chars = chunk_max_chars
    form_communities(graph)
    return graph


def shipped_file(graph: Graph) -> GraphFile:
    return to_file(graph)


def rebuilt_path(lang: str, folder: Path | None = None) -> Path:
    """Where the rebuilt graph of `lang` is kept: the workshop's data folder."""
    return (folder or config.rag_lab_dir()) / "graph" / f"{lang}.yaml"


def _read(path: Path) -> GraphFile:
    return GraphFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_files(
    lang: str, folder: Path | None = None
) -> tuple[GraphFile | None, GraphFile | None, str | None]:
    """The shipped graph of `lang` and the rebuilt one when the data folder has it; an
    unreadable rebuilt file is ignored, an unreadable shipped one said."""
    shipped = rebuilt = None
    error = None
    try:
        shipped = _read(config.content_file(GRAPH_FILE, lang))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        error = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]
    path = rebuilt_path(lang, folder)
    if path.is_file():
        try:
            rebuilt = _read(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            logger.warning("rebuilt graph unreadable, ignored: %s", path)
    return shipped, rebuilt, error


def model_extractions(file: GraphFile) -> dict[tuple[str, str], Extraction]:
    """A rebuilt file's extraction of each passage, by `(passage id, sha256)`."""
    out: dict[tuple[str, str], Extraction] = {
        (pid, sha): Extraction(by_model=True) for pid, sha in file.passages.items()
    }
    keys = {pid: (pid, sha) for pid, sha in file.passages.items()}
    for e in file.entities:
        for m in e.mentions:
            out[keys[m]].entities.setdefault(e.id, (e.name, e.type))
    for r in file.relations:
        for m in r.evidence:
            out[keys[m]].relations[(r.source, r.target)] = (1, r.label)
    return out


def assemble(
    documents: Sequence[DocText],
    lang: str,
    chunk_max_chars: int,
    *,
    audiences: Mapping[str, str] | None = None,
    construction: Sequence[DocText] | None = None,
    shipped: GraphFile | None = None,
    rebuilt: GraphFile | None = None,
) -> Graph:
    """The graph of `documents` (the chain's, the work copy included): each passage extracted
    by the rebuilt file's model at equal sha256, else by the rule with the vocabulary of
    `construction` (the shipped corpus: frozen) plus the touched documents' own key terms; the
    communities start from the file's (rebuilt, else shipped), each summary by fingerprint."""
    vocab = vocabulary(
        construction if construction is not None else documents, lang, chunk_max_chars
    )
    terms = terms_for(documents, vocab, lang, chunk_max_chars)
    passages = passages_of(documents, chunk_max_chars, audiences)
    by_model = model_extractions(rebuilt) if rebuilt is not None else {}
    known = set(rebuilt.passages) if rebuilt is not None else set()
    extractions: dict[str, Extraction] = {}
    stale = 0
    for p in passages:
        found = by_model.get((p.id, p.sha256))
        if found is None:
            stale += p.id in known
            found = extract(p.text, terms, lang)
        extractions[p.id] = found
    graph = merge(passages, extractions)
    graph.chunk_max_chars = chunk_max_chars
    graph.shipped, graph.rebuilt, graph.stale = shipped, rebuilt, stale
    start = rebuilt or shipped
    previous = [c.entities for c in start.communities] if start is not None else None
    form_communities(graph, previous, (rebuilt, shipped))
    return graph


def load_graph(
    documents: Sequence[DocText],
    lang: str,
    chunk_max_chars: int,
    *,
    audiences: Mapping[str, str] | None = None,
    construction: Sequence[DocText] | None = None,
    folder: Path | None = None,
) -> Graph:
    shipped, rebuilt, error = load_files(lang, folder)
    graph = assemble(
        documents,
        lang,
        chunk_max_chars,
        audiences=audiences,
        construction=construction,
        shipped=shipped,
        rebuilt=rebuilt,
    )
    graph.error = error
    return graph


def write_rebuilt(lang: str, file: GraphFile, folder: Path | None = None) -> Path:
    """The rebuilt file written whole or not at all (`_replace`), in the data folder only."""
    path = rebuilt_path(lang, folder)
    _replace(path, dump(file))
    return path


def forget(lang: str, doc_ids: Sequence[str], folder: Path | None = None) -> int:
    """The evidence the rebuilt file keeps from `doc_ids` removed, and the entities, relations
    and community summaries left without evidence (a summary that read them too): a deleted
    document leaves none of its text on disk. Written whole (`_replace`), only when there was
    something to remove; the number of passages removed."""
    path = rebuilt_path(lang, folder)
    if not doc_ids or not path.is_file():
        return 0
    try:
        file = _read(path)
    except (OSError, ValueError, yaml.YAMLError, ValidationError):
        return 0
    gone = set(doc_ids)

    def kept(ids: Sequence[str]) -> list[str]:
        return [m for m in ids if m.split("#", 1)[0] not in gone]

    passages = {pid: sha for pid, sha in file.passages.items() if pid.split("#", 1)[0] not in gone}
    removed = len(file.passages) - len(passages)
    comms = [c for c in file.communities if not gone & set(c.sources)]
    if not removed and len(comms) == len(file.communities):
        return 0
    entities = [e.model_copy(update={"mentions": kept(e.mentions)}) for e in file.entities]
    relations = [r.model_copy(update={"evidence": kept(r.evidence)}) for r in file.relations]
    _replace(
        path,
        dump(
            file.model_copy(
                update={
                    "passages": passages,
                    "entities": [e for e in entities if e.mentions],
                    "relations": [r for r in relations if r.evidence],
                    "communities": comms,
                }
            )
        ),
    )
    return removed


def reset(lang: str, folder: Path | None = None) -> bool:
    """« Rétablir le graphe livré »: the rebuilt file deleted. Whether there was one."""
    path = rebuilt_path(lang, folder)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ---------- the queries, pure ----------


def parse_entities(answer: str) -> list[str] | None:
    """The names of the first `ENTITIES:` line of a model's answer, `LOCAL_MAX_ENTITIES` at
    most, each once; `[]` for `ENTITIES: NONE`; `None` without such a line (unreadable)."""
    for line in answer.splitlines():
        found = _ENTITIES.match(line.strip())
        if found is None:
            continue
        rest = found.group(1).strip()
        if not rest or _NONE.match(rest):
            return []
        names: list[str] = []
        for part in _SPLIT.split(rest):
            name = _name(part)
            if name and normalize(name) and normalize(name) not in {normalize(n) for n in names}:
                names.append(name)
        return names[:LOCAL_MAX_ENTITIES]
    return None


def parse_points(answer: str) -> str | None:
    """What a « map » call found: the text after the first `POINTS:` line (and the lines that
    follow it); `""` for `POINTS: NONE`; `None` without such a line (unreadable)."""
    lines = answer.splitlines()
    for n, line in enumerate(lines):
        found = _POINTS.match(line.strip())
        if found is None:
            continue
        first = found.group(1).strip()
        if _NONE.match(first or "none") and not any(x.strip() for x in lines[n + 1 :]):
            return ""
        if _NONE.match(first):
            return ""
        rest = [first, *(x.strip() for x in lines[n + 1 :])]
        return "\n".join(x for x in rest if x).strip()
    return None


def match_entities(graph: Graph, names_or_question: str | Sequence[str]) -> list[str]:
    """The graph's entities a question (a text) or a list of names designate: a name by equal
    normalized form, else by inclusion of whole words (its words in an entity's, or an
    entity's in it; two at most, the longest first); a question by the entities whose name it
    holds, in the order it says them. `LOCAL_MAX_ENTITIES` at most, each once."""
    keys = {eid: normalize(e.name) for eid, e in graph.entities.items()}
    out: list[str] = []
    if isinstance(names_or_question, str):
        text = normalize(names_or_question)
        found = []
        for eid, key in keys.items():
            at = re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text)
            if at is not None:
                found.append((at.start(), -len(key), eid))
        out = [eid for _, _, eid in sorted(found)]
        return out[:LOCAL_MAX_ENTITIES]
    for name in names_or_question:
        key = normalize(name)
        if not key:
            continue
        exact = [eid for eid, k in keys.items() if k == key]
        if exact:
            picked = exact[:1]
        else:
            near = [(-len(k), eid) for eid, k in keys.items() if _has(k, key) or _has(key, k)]
            picked = [eid for _, eid in sorted(near)[:2]]
        for eid in picked:
            if eid not in out:
                out.append(eid)
    return out[: 2 * LOCAL_MAX_ENTITIES]


@dataclass
class LocalPick:
    """A local query's selection: the entities recognized, their neighbours, the relations
    kept and the evidence passages (each with its audience)."""

    entities: list[str]
    neighbours: list[str]
    relations: list[Relation]
    passages: list[Passage]


def select_local(graph: Graph, entity_ids: Sequence[str]) -> LocalPick:
    """The neighbours at one hop of the entities, by weight, `LOCAL_MAX_NEIGHBORS` at most; the
    evidence passages of the relations kept, each once, `LOCAL_MAX_PASSAGES` at most (an
    entity without relation: its own mentions). No audience filter (D7): each passage says
    its own."""
    chosen = [e for e in entity_ids if e in graph.entities]
    inside = set(chosen)
    incident = [r for r in graph.relations.values() if r.source in inside or r.target in inside]
    incident.sort(key=lambda r: (-r.weight, r.source, r.target))
    neighbours: list[str] = []
    for rel in incident:
        other = rel.target if rel.source in inside else rel.source
        if (
            other not in inside
            and other not in neighbours
            and len(neighbours) < LOCAL_MAX_NEIGHBORS
        ):
            neighbours.append(other)
    near = inside | set(neighbours)
    kept = [r for r in incident if r.source in near and r.target in near]
    ids: list[str] = []
    for rel in kept:
        for m in rel.evidence:
            if m not in ids and len(ids) < LOCAL_MAX_PASSAGES:
                ids.append(m)
    if not kept:
        for e in chosen:
            for m in graph.entities[e].mentions:
                if m not in ids and len(ids) < LOCAL_MAX_PASSAGES:
                    ids.append(m)
    return LocalPick(chosen, neighbours, kept, [graph.passages[m] for m in ids])


def _words(text: str, stop: frozenset[str]) -> set[str]:
    out = set()
    for word in re.findall(r"\w+", normalize(text)):
        if len(word) >= 3 and word not in stop and not word.isdigit():
            out.add(word[:-1] if len(word) > 4 and word.endswith(("s", "x")) else word)
    return out


@dataclass
class GlobalPick:
    community: Community
    score: int
    names: list[str]
    passages: list[Passage]

    @property
    def audience(self) -> str:
        return self.community.audience


def select_global(
    graph: Graph, question: str, lang: str = config.DEFAULT_LANGUAGE
) -> list[GlobalPick]:
    """The communities closest to a question: the words they share with it (stop words left
    out, accents folded) in their summary and their entities' names; ties by size, then id;
    `GLOBAL_TOP_COMMUNITIES` at most, none that shares no word. Each with its entities' names
    and its key passages."""
    stop = _stop_words(lang)
    asked = _words(question, stop)
    ranked = []
    for c in graph.communities.values():
        names = [graph.entities[e].name for e in c.entities]
        score = len(asked & _words(" ".join([c.summary_text, *names]), stop))
        if score:
            ranked.append((-score, -len(c.entities), c.id, names))
    ranked.sort(key=lambda x: (x[0], x[1], x[2]))
    return [
        GlobalPick(
            graph.communities[cid],
            -score,
            names,
            key_passages(graph, graph.communities[cid].entities, GLOBAL_KEY_PASSAGES),
        )
        for score, _, cid, names in ranked[:GLOBAL_TOP_COMMUNITIES]
    ]


def clean_summary(answer: str) -> str:
    """A model's answer kept as a community's summary: its text on one line, cut."""
    return _cut(answer.strip(), COMMUNITY_SUMMARY_MAX_CHARS) if answer.strip() else ""


__all__ = [
    "COMMUNITY_ROUNDS",
    "COMMUNITY_SUMMARY_MAX_CHARS",
    "GLOBAL_TOP_COMMUNITIES",
    "GRAPH_FILE",
    "LOCAL_MAX_ENTITIES",
    "LOCAL_MAX_NEIGHBORS",
    "LOCAL_MAX_PASSAGES",
    "MIN_COMMUNITY",
    "TERMS_PER_DOC",
    "Community",
    "Entity",
    "Extraction",
    "Graph",
    "GraphFile",
    "Passage",
    "Relation",
    "assemble",
    "build_graph",
    "communities",
    "dump",
    "extract",
    "forget",
    "load_graph",
    "match_entities",
    "merge",
    "parse_entities",
    "parse_extraction",
    "parse_points",
    "rebuilt_path",
    "reset",
    "select_global",
    "select_local",
    "shipped_file",
    "to_file",
    "write_rebuilt",
]
