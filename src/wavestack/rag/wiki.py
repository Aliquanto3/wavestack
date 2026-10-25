"""The LLM Wiki (V1.2 story 14, CAP-7): a wiki of Markdown pages compiled from the sources.

Karpathy's pattern, home-made: instead of searching the raw documents at each question, a model
**compiles** them once into a wiki (a page per source, a page per concept that several sources
share, an index of every page, linked by `[[page]]`), **lints** it (broken links, orphan pages,
thin or missing concepts, stale pages), and each question is answered from the pages the model
picks in the index. An update recompiles the pages the touched document feeds, then lints.

The workshop ships the wiki precomputed, in `content/rag_wiki.yaml` (+ `content/i18n/{en,de}/`),
compiled by a deterministic rule with no model (`method: heuristic`, reproducible byte for byte:
no duration in it, `tools/build_wiki.py`); « Reconstruire » makes the active model write each
page's synthesis into the workshop's data folder (`rag_lab_dir()/wiki/{lang}.yaml`, `method:
llm`), « Rétablir » deletes that file. As PageIndex's tree (story 11): the pages always come from
the chain's documents (the work copy included); the **vocabulary** (the concepts that have a
page) is the file's, frozen between two full compilations (so an update touches a few pages, and
the lint says which concepts the corpus now calls for); each synthesis comes from the rebuilt
file, else the shipped one, at equal fingerprint, else from the rule (a page « stale » when it
had a rebuilt synthesis for another text).

The rule: a concept is a word (five letters or more, accents folded, no digit, not a stop word)
among the `TERMS_PER_DOC` best of a document by tf × log(N / df) (tf: its sentences in the
document, at least two; df: the documents that have it, from 2 to max(2, N // 3)). A source
page: the document's two first sentences (its synthesis), its sentences with a figure (key
facts), its concepts; a concept page: the first sentence of each document that names it, with
the link to the document's page. Every page keeps its sources and its audience (the most
restrictive of its sources': `hr` when one is); nothing here filters on it (the workshop's rule,
story 11's review).
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from wavestack import config
from wavestack.messages import msg
from wavestack.rag.contexts import _replace, fingerprint
from wavestack.rag.corpus import DocText, split_sentences
from wavestack.rag.pageindex import blocks

WIKI_FILE = "rag_wiki.yaml"
HEURISTIC = "heuristic"
INDEX_ID = "index"
SOURCE_PREFIX = "source/"
CONCEPT_PREFIX = "concept/"
TERMS_PER_DOC = 2  # the concepts each document brings, at most
TERM_MIN_LETTERS = 5
TERM_MIN_SENTENCES = 2  # a document's term: in two of its sentences at least
SYNTHESIS_SENTENCES = 2  # the rule's synthesis of a source page: its first sentences
SYNTHESIS_MAX_CHARS = 300  # a synthesis's characters (the rule's, a model's)
FACTS_PER_PAGE = 4  # the key facts of a source page (its sentences with a figure)
LINE_MAX_CHARS = 240  # a key fact's, a quote's characters
INDEX_SUMMARY_MAX_CHARS = 120  # what the index shows of a page's synthesis
WIKI_BREADTH = 3  # the pages the model may pick in the index
ELLIPSIS = "…"
LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
_WORD = re.compile(r"\w+")
_PAGES = re.compile(r"^[\s>*_`-]*pages?[\s*_`]*:[\s*_`]*(.*)$", re.I)
_NONE = re.compile(r"^\W*none\b", re.I)
_DIGIT = re.compile(r"\d")

logger = logging.getLogger(__name__)

Kind = Literal["index", "source", "concept"]
Audience = Literal["all", "hr"]
LINT_CODES = (
    "broken_link",
    "orphan_page",
    "thin_concept",
    "empty_concept",
    "missing_concept",
    "stale_synthesis",
)


class WikiEntry(BaseModel):
    """A page of the file: its stable id (`index`, `source/<doc_id>`, `concept/<term>`), its
    kind, its title, its synthesis, its sources (documents), its audience, the sha256 of what it
    is compiled from, and its whole Markdown text (what the wiki copies of the documents)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Kind
    title_text: str = Field(min_length=1)
    synthesis_text: str
    sources: list[str]
    audience: Audience = "all"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str = Field(min_length=1)


class WikiFile(BaseModel):
    """`rag_wiki.yaml`: who wrote it (`shipped` or `rebuilt`), how (`heuristic` or `llm`), with
    which model, the vocabulary it was compiled with (its concepts), and for the rebuilt file
    only what the rebuild measured (tokens, duration: the shipped file is reproducible)."""

    model_config = ConfigDict(extra="forbid")

    author: Literal["shipped", "rebuilt"]
    method: Literal["heuristic", "llm"]
    model: str = Field(min_length=1)
    tokens: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    concepts: list[str]
    pages: list[WikiEntry]

    @model_validator(mode="after")
    def _measured_only_when_rebuilt(self) -> WikiFile:
        rebuilt = self.author == "rebuilt"
        if rebuilt != (self.method == "llm"):
            raise ValueError("a shipped wiki is heuristic, a rebuilt one written by a model")
        if rebuilt and (self.tokens is None or self.duration_ms is None):
            raise ValueError("a rebuilt wiki says its tokens and its duration")
        if not rebuilt and (self.tokens is not None or self.duration_ms is not None):
            raise ValueError("the shipped wiki carries no measure (it is reproducible)")
        return self


@dataclass
class Page:
    """A page in memory: its fields, what it is compiled from (`material`: the document's text,
    or the quotes of a concept), the Markdown after its synthesis (`body`), where its synthesis
    comes from (`rebuilt`, `shipped` or `heuristic`) and whether it is stale."""

    id: str
    kind: str
    title_text: str
    synthesis_text: str
    sources: list[str]
    audience: str
    sha256: str
    material: str
    body: str = ""
    source: str = HEURISTIC
    stale: bool = False

    @property
    def text(self) -> str:
        parts = [f"# {self.title_text}"]
        if self.synthesis_text:
            parts.append(self.synthesis_text)
        if self.body:
            parts.append(self.body)
        return "\n\n".join(parts)

    @property
    def links(self) -> list[str]:
        return LINK.findall(self.text)

    def entry(self) -> WikiEntry:
        return WikiEntry(
            id=self.id,
            kind=self.kind,  # type: ignore[arg-type]
            title_text=self.title_text,
            synthesis_text=self.synthesis_text,
            sources=list(self.sources),
            audience=self.audience,  # type: ignore[arg-type]
            sha256=self.sha256,
            text=self.text,
        )


@dataclass
class Wiki:
    """The wiki of a list of documents: its pages by id (the index first), the vocabulary it
    was compiled with, and the files it read."""

    pages: dict[str, Page]
    concepts: list[str]
    shipped: WikiFile | None = None
    rebuilt: WikiFile | None = None
    error: str | None = None

    @property
    def header(self) -> WikiFile | None:
        """The file whose header is shown: the rebuilt one, else the shipped one."""
        return self.rebuilt or self.shipped

    @property
    def stale(self) -> int:
        return sum(1 for p in self.pages.values() if p.stale)

    def listed(self) -> list[Page]:
        """The pages the index lists (all but the index), in its order."""
        return [p for p in self.pages.values() if p.id != INDEX_ID]

    def count(self, kind: str) -> int:
        return sum(1 for p in self.pages.values() if p.kind == kind)

    def links(self) -> int:
        return sum(len(p.links) for p in self.pages.values())

    def size(self) -> int:
        """The characters of every page (what the wiki holds)."""
        return sum(len(p.text) for p in self.pages.values())


@dataclass(frozen=True)
class Finding:
    """A finding of the lint: its code (`LINT_CODES`), the page it is about, a detail (the
    link broken, the concept missing)."""

    code: str
    page_id: str
    detail: str = ""


# ---------- words and concepts ----------


def fold(text: str) -> str:
    """Lower case, accents dropped (the rule of `lab.fold`)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _stop(lang: str) -> frozenset[str]:
    from wavestack.rag import lab  # lazily: `lab` imports this module

    return lab.STOP_WORDS_BY_LANG.get(
        config.as_language(lang), lab.STOP_WORDS_BY_LANG[config.DEFAULT_LANGUAGE]
    )


def _words(sentence: str, stop: frozenset[str]) -> list[tuple[str, str]]:
    """`(term, surface)` for each word of a sentence that may be a concept."""
    out = []
    for word in _WORD.findall(sentence):
        term = fold(word)
        if len(term) < TERM_MIN_LETTERS or _DIGIT.search(term) or term in stop:
            continue
        out.append((term, word.lower()))
    return out


def sentences_of(doc: DocText) -> list[str]:
    """A document's sentences, its `# title` line left out (the blocks of PageIndex)."""
    return [s for block in blocks(doc.text) for s in split_sentences(block)]


@dataclass
class _Read:
    """What the rule reads of the documents: each one's sentences and their terms."""

    sentences: dict[str, list[str]]
    terms: dict[str, list[set[str]]]
    surfaces: dict[str, Counter[str]] = field(default_factory=dict)


def _read(documents: Sequence[DocText], lang: str) -> _Read:
    stop = _stop(lang)
    read = _Read({}, {})
    for doc in documents:
        sentences = sentences_of(doc)
        read.sentences[doc.doc_id] = sentences
        sets = []
        for sentence in sentences:
            words = _words(sentence, stop)
            sets.append({t for t, _ in words})
            for term, surface in words:
                read.surfaces.setdefault(term, Counter())[surface] += 1
        read.terms[doc.doc_id] = sets
    return read


def select_concepts(documents: Sequence[DocText], lang: str) -> list[str]:
    """The vocabulary a full compilation gives: the `TERMS_PER_DOC` best terms of each document
    by tf × log(N / df), among those in `TERM_MIN_SENTENCES` of its sentences and in 2 to
    max(2, N // 3) documents; ties by term. Sorted."""
    return _select(_read(documents, lang))


def _select(read: _Read) -> list[str]:
    n = len(read.terms)
    tf = {doc: Counter(t for s in sets for t in s) for doc, sets in read.terms.items()}
    df: Counter[str] = Counter()
    for counts in tf.values():
        df.update(counts.keys())
    high = max(2, n // 3)
    chosen: set[str] = set()
    for counts in tf.values():
        scored = sorted(
            (-(k * math.log(n / df[t])), t)
            for t, k in counts.items()
            if k >= TERM_MIN_SENTENCES and 2 <= df[t] <= high
        )
        chosen.update(t for _, t in scored[:TERMS_PER_DOC])
    return sorted(chosen)


def _surface(read: _Read, term: str) -> str:
    counts = read.surfaces.get(term)
    if not counts:
        return term
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


# ---------- the deterministic compiler (the shipped wiki) ----------


def short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + ELLIPSIS


def _say(key: str, lang: str, **kw: object) -> str:
    return msg(f"rag_lab.wiki.{key}", lang, **kw)


def _audience(sources: Sequence[str], audiences: Mapping[str, str] | None) -> str:
    found = [(audiences or {}).get(s, "all") for s in sources]
    return "hr" if "hr" in found else "all"


def source_id(doc_id: str) -> str:
    return f"{SOURCE_PREFIX}{doc_id}"


def concept_id(term: str) -> str:
    return f"{CONCEPT_PREFIX}{term}"


def build_wiki(
    documents: Sequence[DocText],
    lang: str,
    concepts: Sequence[str] | None = None,
    audiences: Mapping[str, str] | None = None,
    only: set[str] | None = None,
) -> dict[str, Page]:
    """The wiki of `documents` by the rule: the index, a page per document, a page per concept
    of `concepts` (the vocabulary: `select_concepts` when `None`) that one document at least
    names. `only`: the ids of the pages to compile (an update), the index left out.
    Deterministic: the same documents give the same pages."""
    read = _read(documents, lang)
    vocabulary = _select(read) if concepts is None else sorted(concepts)
    titles = {d.doc_id: d.title_text or d.doc_id for d in documents}
    named = {
        t: [d.doc_id for d in documents if any(t in s for s in read.terms[d.doc_id])]
        for t in vocabulary
    }
    pages: dict[str, Page] = {}
    for doc in documents:
        page_id = source_id(doc.doc_id)
        if only is not None and page_id not in only:
            continue
        sentences = read.sentences[doc.doc_id]
        synthesis = short(" ".join(sentences[:SYNTHESIS_SENTENCES]), SYNTHESIS_MAX_CHARS)
        facts = [
            f"- {short(s, LINE_MAX_CHARS)}"
            for s in sentences[SYNTHESIS_SENTENCES:]
            if _DIGIT.search(s)
        ][:FACTS_PER_PAGE]
        links = [f"[[{concept_id(t)}]]" for t in vocabulary if doc.doc_id in named[t]]
        body = []
        if facts:
            body.append(f"## {_say('heading_facts', lang)}\n" + "\n".join(facts))
        if links:
            body.append(f"## {_say('heading_concepts', lang)}\n" + " · ".join(links))
        body.append(_say("sources_line", lang, sources=f"corpus/{doc.doc_id}.md"))
        pages[page_id] = Page(
            page_id,
            "source",
            titles[doc.doc_id],
            synthesis,
            [doc.doc_id],
            _audience([doc.doc_id], audiences),
            fingerprint(doc.text),
            doc.text,
            "\n\n".join(body),
        )
    for term in vocabulary:
        page_id = concept_id(term)
        if not named[term] or (only is not None and page_id not in only):
            continue
        quotes = []
        for doc_id in named[term]:
            sets = read.terms[doc_id]
            first = next(i for i, s in enumerate(sets) if term in s)
            sentence = short(read.sentences[doc_id][first], LINE_MAX_CHARS)
            quotes.append((doc_id, sentence))
        lines = [f"- {s} ([[{source_id(d)}]])" for d, s in quotes]
        body = f"## {_say('heading_quotes', lang)}\n" + "\n".join(lines)
        material = "\n".join([term, *(f"{d}: {s}" for d, s in quotes)])
        pages[page_id] = Page(
            page_id,
            "concept",
            _surface(read, term),
            short(quotes[0][1], SYNTHESIS_MAX_CHARS),
            [d for d, _ in quotes],
            _audience([d for d, _ in quotes], audiences),
            fingerprint(material),
            material,
            body,
        )
    if only is not None:
        return pages
    return with_index(pages, lang)


def with_index(pages: Mapping[str, Page], lang: str) -> dict[str, Page]:
    """`pages` behind the index, which lists them by kind (title and synthesis cut); its own
    fingerprint is that of the pages' ids and fingerprints."""
    listed = [p for p in pages.values() if p.id != INDEX_ID]
    sections = []
    for kind, heading in (("source", "heading_sources"), ("concept", "heading_concept_pages")):
        lines = [
            f"- [[{p.id}]] {p.title_text}"
            + (f" — {short(p.synthesis_text, INDEX_SUMMARY_MAX_CHARS)}" if p.synthesis_text else "")
            for p in listed
            if p.kind == kind
        ]
        if lines:
            sections.append(f"## {_say(heading, lang)}\n" + "\n".join(lines))
    digest = fingerprint("\n".join(f"{p.id} {p.sha256}" for p in listed))
    index = Page(
        INDEX_ID,
        "index",
        _say("index_title", lang),
        _say("index_synthesis", lang, pages=len(listed)),
        sorted({s for p in listed for s in p.sources}),
        "hr" if any(p.audience == "hr" for p in listed) else "all",
        digest,
        "",
        "\n\n".join(sections),
    )
    return {INDEX_ID: index, **{p.id: p for p in listed}}


def shipped_file(pages: Mapping[str, Page], concepts: Sequence[str]) -> WikiFile:
    """The file of a wiki compiled by the rule: no model, no measure."""
    return WikiFile(
        author="shipped",
        method=HEURISTIC,
        model=HEURISTIC,
        concepts=list(concepts),
        pages=[p.entry() for p in pages.values()],
    )


def dump(file: WikiFile, comment: str = "") -> str:
    """The file's YAML text, stable (keys in order, no wrapping)."""
    body = yaml.safe_dump(
        file.model_dump(exclude_none=file.author == "shipped"),
        allow_unicode=True,
        sort_keys=False,
        width=1_000_000,
    )
    return f"{comment}{body}"


# ---------- reading: the pages from the documents, the syntheses from the files ----------


def rebuilt_path(lang: str, folder: Path | None = None) -> Path:
    """Where the rebuilt wiki of `lang` is kept: the workshop's data folder."""
    return (folder or config.rag_lab_dir()) / "wiki" / f"{lang}.yaml"


def _read_file(path: Path) -> WikiFile:
    return WikiFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_files(
    lang: str, folder: Path | None = None
) -> tuple[WikiFile | None, WikiFile | None, str | None]:
    """The shipped wiki of `lang` (`config.content_file`) and the rebuilt one when the data
    folder has it; an unreadable rebuilt file is ignored, an unreadable shipped one said."""
    shipped = rebuilt = None
    error = None
    try:
        shipped = _read_file(config.content_file(WIKI_FILE, lang))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        error = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]
    path = rebuilt_path(lang, folder)
    if path.is_file():
        try:
            rebuilt = _read_file(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            logger.warning("rebuilt wiki unreadable, ignored: %s", path)
    return shipped, rebuilt, error


def vocabulary(
    documents: Sequence[DocText], lang: str, shipped: WikiFile | None, rebuilt: WikiFile | None
) -> list[str]:
    """The concepts that have a page: the rebuilt file's, else the shipped one's (frozen
    between two full compilations), else the rule's on `documents`."""
    file = rebuilt or shipped
    return list(file.concepts) if file is not None else select_concepts(documents, lang)


def assemble(
    documents: Sequence[DocText],
    lang: str,
    shipped: WikiFile | None,
    rebuilt: WikiFile | None,
    audiences: Mapping[str, str] | None = None,
) -> Wiki:
    """The wiki of `documents` (its pages, with the files' vocabulary), each synthesis from the
    rebuilt file, else the shipped file, at equal (id, sha256), else the rule's; a page whose id
    has a rebuilt synthesis for another text is stale. The index is drawn last."""
    concepts = vocabulary(documents, lang, shipped, rebuilt)
    pages = build_wiki(documents, lang, concepts, audiences)
    by_key = {
        name: {(e.id, e.sha256): e.synthesis_text for e in file.pages} if file else {}
        for name, file in (("shipped", shipped), ("rebuilt", rebuilt))
    }
    rebuilt_ids = {e.id for e in rebuilt.pages} if rebuilt else set()
    for page in pages.values():
        if page.id == INDEX_ID:
            continue
        key = (page.id, page.sha256)
        if key in by_key["rebuilt"]:
            page.synthesis_text, page.source = by_key["rebuilt"][key], "rebuilt"
        elif key in by_key["shipped"]:
            page.synthesis_text, page.source = by_key["shipped"][key], "shipped"
        elif page.id in rebuilt_ids:
            page.stale = True
    return Wiki(with_index(pages, lang), concepts, shipped, rebuilt)


def load_wiki(
    documents: Sequence[DocText],
    lang: str,
    folder: Path | None = None,
    audiences: Mapping[str, str] | None = None,
) -> Wiki:
    shipped, rebuilt, error = load_files(lang, folder)
    wiki = assemble(documents, lang, shipped, rebuilt, audiences)
    wiki.error = error
    return wiki


def touched_pages(
    before: Sequence[DocText], after: Sequence[DocText], lang: str, concepts: Sequence[str]
) -> tuple[set[str], set[str]]:
    """What an update recompiles: the pages of the documents added, modified or deleted, and
    the concept pages whose word one of them names (before or after); and the pages it removes
    (a deleted document's, a concept no document names any more). The index is not counted."""
    old = {d.doc_id: d for d in before}
    new = {d.doc_id: d for d in after}
    changed = [i for i, d in new.items() if i not in old or old[i].text != d.text]
    removed = [i for i in old if i not in new]
    docs = [new[i] for i in changed] + [old[i] for i in changed if i in old]
    docs += [old[i] for i in removed]
    read = _read(docs, lang)
    words = {t for sets in read.terms.values() for s in sets for t in s}
    touched = {source_id(i) for i in changed}
    touched |= {concept_id(t) for t in concepts if t in words}
    after_ids = set(build_wiki(after, lang, concepts, only=touched)) if touched else set()
    gone = {source_id(i) for i in removed} | (touched - after_ids)
    return touched & after_ids, gone


# ---------- the lint ----------


def lint(wiki: Wiki, documents: Sequence[DocText], lang: str) -> list[Finding]:
    """The wiki's health check, by rule: a link to no page, a page no other page links to (the
    index aside), a concept page with fewer than two sources, a concept of the vocabulary no
    document names any more, a concept a full compilation would give that has no page, a page
    whose rebuilt synthesis was for another text. In that order, each by page id."""
    ids = set(wiki.pages)
    found: list[Finding] = []
    inbound: Counter[str] = Counter()
    for page in wiki.listed():
        for link in page.links:
            inbound[link] += 1
            if link not in ids:
                found.append(Finding("broken_link", page.id, link))
    found += [Finding("orphan_page", p.id) for p in wiki.listed() if not inbound[p.id]]
    found += [
        Finding("thin_concept", p.id, str(len(p.sources)))
        for p in wiki.listed()
        if p.kind == "concept" and len(p.sources) < 2
    ]
    found += [
        Finding("empty_concept", concept_id(t)) for t in wiki.concepts if concept_id(t) not in ids
    ]
    have = set(wiki.concepts)
    found += [
        Finding("missing_concept", concept_id(t), t)
        for t in select_concepts(documents, lang)
        if t not in have
    ]
    found += [Finding("stale_synthesis", p.id) for p in wiki.listed() if p.stale]
    return found


# ---------- « Reconstruire », « Rétablir », a deleted document ----------


def write_rebuilt(
    lang: str,
    entries: Sequence[WikiEntry],
    *,
    concepts: Sequence[str],
    model: str,
    tokens: int,
    duration_ms: int,
    merge: bool,
    folder: Path | None = None,
) -> Path:
    """The pages a rebuild wrote (`merge=False`: the whole file, its vocabulary new) or an update
    rewrote (`merge=True`: over those an earlier rebuild kept, by id and sha256, its measure
    added, its vocabulary kept), in the data folder, never `content/`. Written whole or not at
    all (`_replace`)."""
    path = rebuilt_path(lang, folder)
    kept: dict[tuple[str, str], WikiEntry] = {}
    words = list(concepts)
    if merge and path.is_file():
        try:
            earlier: WikiFile | None = _read_file(path)
        except (OSError, ValueError, yaml.YAMLError, ValidationError):
            earlier = None
        if earlier is not None:
            kept = {(e.id, e.sha256): e for e in earlier.pages}
            models = [m for m in earlier.model.split(" + ") if m]
            if model not in models:
                models.append(model)
            model = " + ".join(models)
            tokens += earlier.tokens or 0
            duration_ms += earlier.duration_ms or 0
            words = list(earlier.concepts)
    for entry in entries:
        kept[(entry.id, entry.sha256)] = entry
    file = WikiFile(
        author="rebuilt",
        method="llm",
        model=model,
        tokens=tokens,
        duration_ms=duration_ms,
        concepts=words,
        pages=list(kept.values()),
    )
    _replace(path, dump(file))
    return path


def forget(lang: str, doc_ids: Sequence[str], folder: Path | None = None) -> int:
    """The pages the rebuilt file keeps that quote one of `doc_ids` (the document's page, the
    concept pages citing it), removed: a deleted document leaves none of its text on disk.
    Written whole (`_replace`), only when there was something to remove; the number removed."""
    path = rebuilt_path(lang, folder)
    if not doc_ids or not path.is_file():
        return 0
    try:
        file = _read_file(path)
    except (OSError, ValueError, yaml.YAMLError, ValidationError):
        return 0
    gone = set(doc_ids)
    kept = [p for p in file.pages if not gone & set(p.sources)]
    removed = len(file.pages) - len(kept)
    if removed:
        _replace(path, dump(file.model_copy(update={"pages": kept})))
    return removed


def reset(lang: str, folder: Path | None = None) -> bool:
    """« Rétablir le wiki livré »: the rebuilt file deleted. Whether there was one."""
    path = rebuilt_path(lang, folder)
    if not path.is_file():
        return False
    path.unlink()
    return True


def clean_synthesis(answer: str) -> str:
    """A model's answer kept as a synthesis: its first non-empty paragraph, on one line, cut at
    `SYNTHESIS_MAX_CHARS`, its `[[links]]` left as written (the lint checks them); empty when
    it wrote nothing."""
    for paragraph in answer.strip().split("\n\n"):
        text = " ".join(paragraph.split())
        if text:
            return short(text, SYNTHESIS_MAX_CHARS)
    return ""


# ---------- the query: the model picks pages in the index ----------


def index_list(pages: Sequence[Page]) -> str:
    """The numbered list the query shows the model: each source page's title and synthesis cut,
    each concept page's title alone (its subject; its synthesis would double the list), nothing
    else."""
    lines = []
    for n, page in enumerate(pages, start=1):
        summary = (
            "" if page.kind == "concept" else short(page.synthesis_text, INDEX_SUMMARY_MAX_CHARS)
        )
        lines.append(f"{n}. {page.title_text}" + (f" — {summary}" if summary else ""))
    return "\n".join(lines)


def parse_pages(answer: str, count: int) -> list[int] | None:
    """The numbers of the first `PAGES:` line of a model's answer, in `1..count`, at most
    `WIKI_BREADTH`, each once (a number out of range ignored); `[]` for `PAGES: NONE` or no
    valid number; `None` when the answer has no `PAGES:` line (unreadable)."""
    for line in answer.splitlines():
        found = _PAGES.match(line.strip())
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
        return picked[:WIKI_BREADTH]
    return None


__all__ = [
    "INDEX_ID",
    "LINT_CODES",
    "WIKI_BREADTH",
    "WIKI_FILE",
    "Finding",
    "Page",
    "Wiki",
    "WikiEntry",
    "WikiFile",
    "assemble",
    "build_wiki",
    "clean_synthesis",
    "dump",
    "forget",
    "index_list",
    "lint",
    "load_files",
    "load_wiki",
    "parse_pages",
    "rebuilt_path",
    "reset",
    "select_concepts",
    "shipped_file",
    "touched_pages",
    "with_index",
    "write_rebuilt",
]
