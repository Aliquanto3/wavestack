"""V1.2 story 6 (CAP-4, CAP-17): the chunking options of the document search workshop.

`semantic`, `parent_child` and `contextual` are run by the real workshop with the suite's fakes
(`FakeEmbedder`, `FakeEngine`): nothing touches the network and no real model is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_embedder import vector
from fake_engine import FakeEngine
from test_rag import Embedders, build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage, wait_idle
from test_rag_lab_generation import own_chain
from test_rag_rerank import Rerankers, place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.rag import contexts
from wavestack.rag import index as rag_index
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import chunk_documents, load_rag_content, read_documents
from wavestack.session.app_session import AppSession
from wavestack.trace.journal import get_journal


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def ready(index: Path, *outputs: str, embedding_ok: bool = True):
    place_reranker()
    if embedding_ok:
        place_model()
    engine = FakeEngine(outputs=list(outputs) or ["Un contexte réécrit."], output="Réponse.")
    session, _ = session_for(rerank_config(index), rerank=False, bricks=(), engine=engine)
    return session


def chain_with(session, option: str, size: int = 700, *, hybrid: bool = False):
    chain = own_chain(session)
    chunking = stage(chain, "chunking")
    chunking.option = option
    chunking.params["chunk_max_chars"] = size
    if hybrid:
        position = next(i for i, s in enumerate(chain.stages) if s.kind == "vector_search")
        chain.stages[position + 1 : position + 1] = [
            rag_lab.Stage(id="b1", kind="lexical_search", option="bm25"),
            rag_lab.Stage(id="f1", kind="fusion", option="rrf"),
        ]
    return chain


def facts(payload: dict) -> dict[str, str]:
    return {f["label_text"]: f["value_text"] for f in payload["facts"]}


# ---------- criterion 1: paragraphs as before ----------


def test_the_options_and_the_paragraphs_sequence_are_those_of_before():
    assert rag_lab.OPTIONS["chunking"] == ("paragraphs", "semantic", "parent_child", "contextual")
    assert list(rag_lab.STEPS)[:2] == ["documents", "chunking"]
    chunking = rag_lab.STEPS["chunking"]
    assert (chunking.reads, chunking.writes, chunking.calls) == (("documents",), ("chunks",), ())


def test_paragraphs_lists_its_chunks_and_adds_nothing_else(index):
    session = ready(index)
    events = run(session, QUESTION, chain_with(session, "paragraphs", 300))
    chunking = ended(events, "chunking")
    assert chunking["status"] == "ok" and chunking["warning_text"] is None
    assert chunking["chunks_total"] > len(chunking["chunks"])
    assert len(chunking["chunks"]) == rag_lab.FOCUS_CHUNKS_MAX
    assert all("parent_text" not in c or c["parent_text"] is None for c in chunking["chunks"])
    assert all(c["context_text"] is None for c in chunking["chunks"])


# ---------- semantic ----------


def test_semantic_cuts_by_sentences_and_says_what_it_embedded(index):
    session = ready(index)
    events = run(session, QUESTION, chain_with(session, "semantic", 400))
    assert run_status(events) == "ok"
    chunking = ended(events, "chunking")
    assert chunking["status"] == "ok", chunking["error_text"]
    assert int(facts(chunking)["Phrases embeddées"].replace(" ", "").replace(" ", "")) > 100
    assert "Durée de l'embedding des phrases" in facts(chunking)
    documents = read_documents(load_rag_content(), "fr")
    longest = max(len(c.text) for c in chunk_documents(documents, 400))
    assert longest <= 400
    assert chunking["costs"][0]["kind"] == "chunking" and chunking["costs"][0]["tokens"]
    assert ended(events, "embedding")["status"] == "ok"


def test_semantic_without_an_embedding_falls_back_on_paragraphs_with_a_warning(index):
    session = ready(index, embedding_ok=False)
    chain = chain_with(session, "semantic", 400)
    events = run(session, QUESTION, chain)
    chunking = ended(events, "chunking")
    assert chunking["status"] == "ok"
    assert "paragraphes" in chunking["warning_text"]
    assert chunking["chunks_total"] == len(
        chunk_documents(read_documents(load_rag_content(), "fr"), 400)
    )


# ---------- parent-child ----------


def test_parent_child_searches_children_and_returns_distinct_parents(index):
    session = ready(index)
    events = run(session, QUESTION, chain_with(session, "parent_child", 700))
    assert run_status(events) == "ok"
    chunking = ended(events, "chunking")
    parents = int(facts(chunking)["Parents"].replace(" ", "").replace(" ", ""))
    total = chunking["chunks_total"]
    assert total > parents
    assert all(len(c["text"]) <= rag_lab.CHILD_MAX_CHARS for c in chunking["chunks"])
    assert all(c["parent_text"] for c in chunking["chunks"])
    search = ended(events, "vector_search")
    assert all(len(i["text"]) <= rag_lab.CHILD_MAX_CHARS for i in search["items"])
    context = ended(events, "context")
    texts = [i["text"] for i in context["items"]]
    assert 1 <= len(texts) <= 3 and len(set(texts)) == len(texts)
    assert any(len(t) > rag_lab.CHILD_MAX_CHARS for t in texts)
    assert "Enfants lus" in facts(context)


# ---------- contextual ----------


def test_contextual_marks_every_chunk_and_embeds_the_context_first(index):
    session = ready(index)
    chain = chain_with(session, "contextual", 700, hybrid=True)
    events = run(session, QUESTION, chain)
    assert run_status(events) == "ok"
    chunking = ended(events, "chunking")
    assert chunking["warning_text"] is None, chunking["warning_text"]
    assert len(chunking["chunks"]) == rag_lab.FOCUS_CHUNKS_MAX
    for chunk in chunking["chunks"]:
        assert chunk["context_label"] == "précalculé · heuristique, sans LLM"
        assert chunk["context_text"]
    assert chunking["costs"][0]["measured_at_build"] is True

    # the embedded text begins with the context: the cached vectors are those of that text
    book = contexts.load_book("fr", config.rag_lab_dir())
    chunks = chunk_documents(read_documents(load_rag_content(), "fr"), 700)
    matched = contexts.match(chunks, book)
    folders = [p for p in config.rag_lab_dir().iterdir() if (p / rag_lab.CHUNKS_FILE).is_file()]
    assert len(folders) == 1
    stored = rag_lab.read_vectors(folders[0], chunks, len(vector("x")))
    assert stored[0] == pytest.approx(
        vector(rag_index.passage_text(chunks[0], matched.contexts[0]))
    )
    assert matched.contexts[0] and stored[0] != pytest.approx(
        vector(rag_index.passage_text(chunks[0]))
    )
    # and BM25 indexes it too: more occurrences than the same chain without contexts
    plain = run(session, QUESTION, chain_with(session, "paragraphs", 700, hybrid=True))
    lexical = [
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_ended" and e.payload["kind"] == "lexical_index"
    ][0]
    baseline = [
        e.payload
        for e in plain
        if e.kind == "rag_lab_stage_ended" and e.payload["kind"] == "lexical_index"
    ][0]
    assert facts(lexical)["Occurrences"] != facts(baseline)["Occurrences"]


def test_contextual_at_another_size_indexes_without_context_and_counts_them(index):
    session = ready(index)
    events = run(session, QUESTION, chain_with(session, "contextual", 300))
    chunking = ended(events, "chunking")
    assert run_status(events) == "ok"
    assert "ignorés" in chunking["warning_text"]
    assert facts(chunking)["Contextes ignorés"] != "0"
    assert facts(chunking)["Extraits sans contexte"] != "0"


# ---------- rebuild ----------


def _events_since(mark: int) -> list:
    return [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]


def _key_of(events: list) -> str:
    return ended(events, "embedding")["output_text"].split("dossier ")[1].split(")")[0]


def test_rebuild_writes_llm_contexts_apart_and_changes_the_cache_key(index):
    session = ready(index, "Un contexte réécrit par le modèle.")
    chain = chain_with(session, "contextual", 700)
    shipped = config.content_file(contexts.CONTEXTS_FILE, "fr")
    before_bytes = shipped.read_bytes()
    first_key = _key_of(run(session, QUESTION, chain))

    mark = get_journal().last_seq()
    run_id = session.rebuild_rag_lab_contexts(chain)
    assert run_id.startswith(rag_lab.REBUILD_RUN_PREFIX)
    wait_idle(session)
    events = _events_since(mark)
    assert next(e.payload["status"] for e in events if e.kind == "rag_lab_run_ended") == "ok"
    assert shipped.read_bytes() == before_bytes
    book = contexts.load_book("fr", config.rag_lab_dir())
    assert book.rebuilt is not None and (book.rebuilt.author, book.rebuilt.method) == (
        "rebuilt",
        "llm",
    )
    assert book.rebuilt.chunks == 73 and book.rebuilt.tokens > 0

    after = run(session, QUESTION, chain)
    labels = {c["context_label"] for c in ended(after, "chunking")["chunks"]}
    assert len(labels) == 1 and next(iter(labels)).startswith("reconstruit · par le modèle")
    assert _key_of(after) != first_key
    assert "reconstruit" in session.rag_lab_state()["contexts"]["summary_text"]
    # the last run of the page is the chain's run, not the rebuild
    assert session.rag_lab_state()["last_run"][0]["payload"]["run_id"].startswith("lab")


def test_rebuild_keeps_the_old_context_of_a_failed_chunk_and_goes_on(index):
    session = ready(index, "Un contexte.")
    real = session._rag_lab_generate
    calls = []

    def generate(ask, cancel):  # the model's boundary: one call in three comes back empty
        calls.append(ask)
        got = real(ask, cancel)
        if len(calls) % 3 == 0:
            got.answer_text = "  "
        return got

    session._rag_lab_generate = generate  # type: ignore[method-assign]
    chain = chain_with(session, "contextual", 700)
    session.rebuild_rag_lab_contexts(chain)
    wait_idle(session)
    book = contexts.load_book("fr", config.rag_lab_dir())
    assert len(calls) == 73 and book.rebuilt.chunks == 73 - 24
    assert "Tu situes" in calls[0].instruction and calls[0].reserve == rag_lab.CONTEXT_MAX_TOKENS
    matched = contexts.match(chunk_documents(read_documents(load_rag_content(), "fr"), 700), book)
    assert matched.missing == 0
    assert {a.author for a in matched.applied} == {"rebuilt", "shipped"}


def test_stop_keeps_the_contexts_already_rewritten(index):
    session = ready(index, "Un contexte.")
    real = session._rag_lab_generate
    calls = []

    def generate(ask, cancel):  # noqa: ANN001, ANN202
        calls.append(ask)
        if len(calls) == 4:
            session.stop()
        return real(ask, cancel)

    session._rag_lab_generate = generate  # type: ignore[method-assign]
    session.rebuild_rag_lab_contexts(chain_with(session, "contextual", 700))
    wait_idle(session)
    book = contexts.load_book("fr", config.rag_lab_dir())
    assert len(calls) == 4 and book.rebuilt is not None and book.rebuilt.chunks <= 4


def test_rebuild_without_a_model_is_refused_with_its_reason(index):
    place_model()
    place_reranker()
    session = AppSession(
        config.Config(values=rerank_config(index)),
        embedder_factory=Embedders(),
        reranker_factory=Rerankers(),
    )
    session.boot(None).result()
    session.join()
    state = session.rag_lab_state()["contexts"]
    assert state["rebuild_blocked_text"]
    with pytest.raises(Exception, match="modèle"):
        session.rebuild_rag_lab_contexts(chain_with(session, "contextual", 700))


def test_reset_deletes_the_rebuilt_file_and_the_shipped_contexts_are_read_again(index):
    session = ready(index, "Un contexte.")
    chain = chain_with(session, "contextual", 700)
    session.rebuild_rag_lab_contexts(chain)
    wait_idle(session)
    path = contexts.rebuilt_path("fr", config.rag_lab_dir())
    assert path.is_file() and session.rag_lab_state()["contexts"]["rebuilt"] is True
    state = session.reset_rag_lab_contexts()
    assert not path.exists() and state["rebuilt"] is False and state["author"] == "shipped"
    labels = {
        c["context_label"] for c in ended(run(session, QUESTION, chain), "chunking")["chunks"]
    }
    assert labels == {"précalculé · heuristique, sans LLM"}


# ---------- brick index, update, sheets ----------


def test_the_bricks_index_serves_only_paragraphs(index):
    session = ready(index)
    plain = own_chain(session)
    stage(plain, "vector_store").option = "sqlite_vec"
    stage(plain, "chunking").params["chunk_max_chars"] = 700
    events = run(session, QUESTION, plain)
    assert "index de la brique" in ended(events, "chunking")["output_text"]
    other = chain_with(session, "contextual", 700)
    stage(other, "vector_store").option = "sqlite_vec"
    events = run(session, QUESTION, other)
    assert "index de la brique" not in ended(events, "chunking")["output_text"]
    assert "lu seulement" not in ended(events, "vector_store")["output_text"]


@pytest.mark.parametrize("option", ["semantic", "parent_child", "contextual"])
def test_an_update_is_refused_outside_paragraphs(index, option):
    session = ready(index)
    with pytest.raises(Exception, match="paragraphes"):
        session.update_rag_lab("delete", "teletravail", pipeline=chain_with(session, option))
    assert session.state == "idle"


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_every_chunking_option_has_a_sheet_with_a_source(lang):
    content = rag_lab.load_lab_content(lang)
    for option in rag_lab.OPTIONS["chunking"]:
        sheet = content.sheets[f"chunking.{option}"]
        assert sheet.sources and sheet.bench_text == ""
    heuristic = {"fr": "heuristique", "en": "heuristic", "de": "heuristisch"}[lang]
    assert heuristic in content.sheets["chunking.contextual"].when_text


def test_late_chunking_is_deferred_with_its_reason_and_candidate_model():
    text = (
        Path(__file__).resolve().parents[1]
        / "_bmad-output/implementation-artifacts/deferred-work.md"
    ).read_text(encoding="utf-8")
    assert "late chunking" in text.lower() and "jina-embeddings-v2-small-en" in text
