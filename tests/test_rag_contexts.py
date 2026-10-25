"""V1.2 story 6 (CAP-4): the contexts of the contextual chunking, the semantic and the
parent-child chunking functions, and the shipped files' coherence. No model, no network."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from wavestack import config
from wavestack.rag import contexts, lab
from wavestack.rag.corpus import (
    Chunk,
    DocText,
    chunk_documents,
    chunk_parent_child,
    chunk_semantic,
    load_rag_content,
    read_documents,
    split_sentences,
)

ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SIZE = 700


def _tool():
    spec = importlib.util.spec_from_file_location(
        "build_rag_contexts", ROOT / "tools" / "build_rag_contexts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chunks(lang: str, size: int = SHIPPED_SIZE) -> list[Chunk]:
    return chunk_documents(read_documents(load_rag_content(lang), lang), size)


def test_the_paragraphs_cache_key_is_the_one_before_the_story():
    identity = {"id": "m", "dims": 8, "size": 1, "sha256": "ab"}
    assert lab.cache_key(identity, 700, "cafe") == "49e29042c4a3be6518d4"
    assert lab.cache_key(identity, 700, "cafe", {"option": "semantic"}) != "49e29042c4a3be6518d4"


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_the_shipped_contexts_cover_exactly_the_active_corpus(lang):
    path = config.content_file(contexts.CONTEXTS_FILE, lang)
    file = contexts.ContextsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert (file.author, file.method, file.model) == ("shipped", "heuristic", "heuristic")
    assert file.chunk_max_chars == SHIPPED_SIZE and file.tokens > 0
    chunks = _chunks(lang, file.chunk_max_chars)
    assert file.chunks == len(file.entries) == len(chunks)
    by_key = {(e.doc_id, e.sha256): e for e in file.entries}
    for chunk in chunks:
        entry = by_key[contexts.key_of(chunk)]
        assert entry.position == chunk.position
        assert entry.context_text != chunk.title_text
        assert not chunk.text.startswith(entry.context_text)
        assert chunk.title_text in entry.context_text


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_the_builder_gives_the_same_file_again(lang):
    tool = _tool()
    shipped = tool.target(lang).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert tool.build(lang, SHIPPED_SIZE) == shipped


def test_a_context_of_another_size_is_ignored_and_counted():
    book = contexts.load_book("fr")
    at_shipped = contexts.match(_chunks("fr"), book)
    assert at_shipped.missing == 0 and at_shipped.ignored == 0
    other = contexts.match(_chunks("fr", 300), book)
    assert other.missing > 0 and other.ignored > 0
    assert other.fingerprint != at_shipped.fingerprint


def test_rebuilt_contexts_win_entry_by_entry_and_reset_restores_the_shipped(tmp_path):
    chunks = _chunks("fr")
    first = chunks[0]
    entry = contexts.ContextEntry(
        doc_id=first.doc_id,
        position=first.position,
        sha256=contexts.fingerprint(first.text),
        context_text="Contexte réécrit.",
    )
    shipped_bytes = config.content_file(contexts.CONTEXTS_FILE, "fr").read_bytes()
    contexts.write_rebuilt(
        "fr", [entry], model="m", chunk_max_chars=700, tokens=3, duration_ms=5, folder=tmp_path
    )
    book = contexts.load_book("fr", tmp_path)
    matched = contexts.match(chunks, book)
    assert matched.applied[0].author == "rebuilt" and matched.applied[0].method == "llm"
    assert matched.applied[1].author == "shipped"
    assert book.header.author == "rebuilt"
    assert config.content_file(contexts.CONTEXTS_FILE, "fr").read_bytes() == shipped_bytes
    assert contexts.reset("fr", tmp_path) is True
    assert contexts.reset("fr", tmp_path) is False
    assert contexts.match(chunks, contexts.load_book("fr", tmp_path)).applied[0].author == "shipped"


def test_an_unreadable_rebuilt_file_is_ignored(tmp_path):
    path = contexts.rebuilt_path("fr", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("author: [broken", encoding="utf-8")
    book = contexts.load_book("fr", tmp_path)
    assert book.rebuilt is None and book.shipped is not None


def test_a_models_answer_is_kept_as_one_short_context():
    assert contexts.clean_context("  Premier\nparagraphe.\n\nSecond.") == "Premier paragraphe."
    assert contexts.clean_context("  \n ") == ""
    assert len(contexts.clean_context("mot " * 500)) <= contexts.CONTEXT_MAX_CHARS


def test_sentences_are_cut_after_their_end_and_a_title_stands_alone():
    assert split_sentences("# Titre\n\nUne phrase. Une autre ! Reste") == [
        "# Titre",
        "Une phrase.",
        "Une autre !",
        "Reste",
    ]


def _topic_embed(sentences: list[str]) -> list[list[float]]:
    return [[1.0, 0.0] if "alpha" in s else [0.0, 1.0] for s in sentences]


def test_semantic_chunks_cut_where_the_topic_changes_and_stay_bounded():
    text = " ".join(["alpha un.", "alpha deux.", "beta un.", "beta deux.", "alpha trois."])
    documents = [DocText("d", "Titre", text)]
    chunks, sentences = chunk_semantic(documents, _topic_embed, 1000, 70)
    assert sentences == 5
    assert [c.text for c in chunks] == [
        "alpha un. alpha deux.",
        "beta un. beta deux.",
        "alpha trois.",
    ]
    assert [c.position for c in chunks] == [1, 2, 3]
    small, _ = chunk_semantic(documents, _topic_embed, 12, 70)
    assert all(len(c.text) <= 12 for c in small)


def test_parent_child_children_are_small_and_each_names_its_parent():
    parents = _chunks("fr")
    children, parent_of = chunk_parent_child(parents, lab.CHILD_MAX_CHARS)
    assert len(children) > len(parents) and len(children) == len(parent_of)
    assert max(len(c.text) for c in children) <= lab.CHILD_MAX_CHARS
    for child, index in zip(children, parent_of, strict=True):
        assert child.doc_id == parents[index].doc_id
        assert child.text.split(" ")[0] in parents[index].text


def test_a_rebuilt_header_covers_every_entry_kept(tmp_path):
    # Review V1.2-6: a second rebuild merges its entries with the first's; the header counts
    # them all and adds up what each rebuild wrote, instead of describing the last one only.
    chunks = _chunks("fr")

    def entry(chunk):
        return contexts.ContextEntry(
            doc_id=chunk.doc_id,
            position=chunk.position,
            sha256=contexts.fingerprint(chunk.text),
            context_text="Contexte réécrit.",
        )

    contexts.write_rebuilt(
        "fr",
        [entry(c) for c in chunks[:3]],
        model="a",
        chunk_max_chars=700,
        tokens=30,
        duration_ms=50,
        folder=tmp_path,
    )
    contexts.write_rebuilt(
        "fr",
        [entry(c) for c in chunks[2:5]],
        model="b",
        chunk_max_chars=700,
        tokens=20,
        duration_ms=40,
        folder=tmp_path,
    )
    header = contexts.load_book("fr", tmp_path).rebuilt
    assert (header.chunks, len(header.entries)) == (5, 5)
    assert (header.tokens, header.duration_ms, header.model) == (50, 90, "a + b")
    contexts.write_rebuilt(
        "fr",
        [entry(chunks[0])],
        model="b",
        chunk_max_chars=300,
        tokens=7,
        duration_ms=9,
        folder=tmp_path,
    )
    header = contexts.load_book("fr", tmp_path).rebuilt
    assert (header.chunks, header.tokens, header.duration_ms, header.model) == (1, 7, 9, "b")
