"""V1.2 story 10: the architectures without an index, the long context and the CAG.

The long context (`full_corpus`) puts the whole corpus in the prompt at each question; the CAG
(`cached_corpus`) evaluates it once as the prompt's prefix, kept in the local model's memory.
The models are fakes: `FakeEngine` (one token per byte) for the in-process engine, a stateless
subclass for llama-server, a scripted provider for the cloud. One token per byte, the shipped
corpus is ~40 000 tokens: the runs read a small corpus of three documents (its other documents
inactive), the shipped one serves the estimate (criterion 3) and the prompt too long (14).
Nothing asserts a gain of time: tokens evaluated, read and rebuilt.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fake_engine import FakeEngine
from pydantic import SecretStr
from test_cloud import GROQ_TEXT, SENTINEL, Provider
from test_rag import Embedders, build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage, wait_idle
from test_rag_rerank import Rerankers, place_reranker, rerank_config
from test_turn import _run as chat

from wavestack import config
from wavestack.messages import number
from wavestack.models import probe
from wavestack.models.engine import CancelToken, common_prefix_len
from wavestack.rag import diagnosis, workcopy
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import RagPassage, load_rag_content
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.trace.journal import get_journal

SMALL = ("mots_de_passe", "teletravail", "classification")
OTHER_QUESTION = "Quelle longueur pour un mot de passe ?"
GIB = 1024**3
MIB = 1024**2


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class Rss:
    """WaveStack's memory as the registry reads it (an outside measure), set by the test."""

    def __init__(self, value: int = 100 * MIB) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class Counting(FakeEngine):
    """The in-process engine, its `clear_cache` counted; `snapshot_error`: the copy right
    after a `prefill` (the CAG's) raises it."""

    def __init__(self, *, snapshot_error: BaseException | None = None, **kwargs) -> None:
        super().__init__(output="Quatorze.", **kwargs)
        self.clears = 0
        self.snapshot_error = snapshot_error
        self.armed = False

    def clear_cache(self) -> bool:
        self.clears += 1
        return super().clear_cache()

    def prefill(self, ids, cancel):  # noqa: ANN001, ANN201
        self.armed = True
        return super().prefill(ids, cancel)

    def snapshot(self):  # noqa: ANN201
        if self.armed and self.snapshot_error is not None:
            self.armed = False
            raise self.snapshot_error
        self.armed = False
        return super().snapshot()


class Bounded(Counting):
    """A model whose native context bounds the window."""

    def metadata(self):  # noqa: ANN201
        return replace(super().metadata(), native_context=8192)


class Server(FakeEngine):
    """As llama-server: no state to copy, its cache reused on the common prefix of two calls.
    `reuse`: it says its `cache_n`; `silent`: it says nothing of what it evaluated either."""

    def __init__(self, *, reuse: bool = True, silent: bool = False) -> None:
        super().__init__(output="Quatorze.", stateful=False)
        self.reuse, self.silent = reuse, silent
        self.common: int | None = None

    def complete(self, prompt_ids, *args, **kwargs):  # noqa: ANN001, ANN201
        self.common = common_prefix_len(self.cache, prompt_ids)
        self.cache = list(prompt_ids[: self.common])
        return super().complete(prompt_ids, *args, **kwargs)

    @property
    def last_cache_reuse(self):  # noqa: ANN201
        return (self.common, None) if self.reuse and self.common is not None else None

    @property
    def last_evaluated(self) -> int | None:
        return None if self.silent else super().last_evaluated


def lab(
    index: Path,
    engine: FakeEngine | None = None,
    *,
    window: int = 16384,
    model: str | None = "fake.gguf",
    rss: Rss | None = None,
    small: bool = True,
) -> AppSession:
    """A booted session (the RAG brick off), its models' files in place; `small`: the corpus
    reduced to `SMALL`."""
    place_model()
    place_reranker()
    values = rerank_config(index)
    values["context"] = {"window": window, "near_limit_ratio": 0.8}
    engine = engine or Counting()
    session = AppSession(
        config.Config(values=values),
        engine_factory=lambda path, n_ctx: engine,
        embedder_factory=Embedders(),
        reranker_factory=Rerankers(),
        rss_fn=rss,
    )
    session.boot(model).result()
    session.join()
    if small:
        shrink(session)
    return session


def shrink(session: AppSession) -> None:
    """The corpus the session read, its documents other than `SMALL` made inactive."""
    content = session._rag_content
    docs = [d.model_copy(update={"active": d.id in SMALL}) for d in content.documents]
    session._rag_content = content.model_copy(update={"documents": docs})


def preset(session: AppSession, key: str) -> rag_lab.Pipeline:
    return session._rag_lab_catalog(rag_lab.load_lab_content()).preset_pipeline(key)


def presets(session: AppSession) -> dict:
    return {p["id"]: p for p in session.rag_lab_state()["catalog"]["presets"]}


def summary(events: list, phase: str) -> dict:
    found = next(e.payload["cost_summary"] for e in events if e.kind == "rag_lab_run_ended")
    return next(s for s in found if s["phase"] == phase)


def calls_ended(events: list) -> list[dict]:
    return [e.payload for e in events if e.kind == "model_call_ended"]


def facts(payload: dict) -> dict:
    return {f["label_text"]: f["value_text"] for f in payload["facts"]}


def update(session: AppSession, *args, **kwargs) -> list:  # noqa: ANN002, ANN003
    mark = get_journal().last_seq()
    session.update_rag_lab(*args, **kwargs)
    wait_idle(session)
    return [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]


# ---------- criteria 1, 15, 16, 19: presets, families, chain rules, views, texts ----------


def test_the_two_presets_join_their_own_family_with_an_empty_segment(index):
    # V1.2 story 11: the agentic search and PageIndex follow, PageIndex in « Structure »;
    # V1.2 story 13: GraphRAG last, after PageIndex in « Structure ».
    assert list(rag_lab.PRESETS) == [
        "dense",
        "hybrid",
        "rerank",
        "long_context",
        "cag",
        "agentic",
        "pageindex",
        "graphrag",
        "llm_wiki",  # V1.2 story 14
    ]
    assert rag_lab.PRESETS["long_context"] == rag_lab.PRESETS["cag"] == ()
    assert rag_lab.PRESET_FAMILIES == {
        "search": ("dense", "hybrid", "rerank"),
        "structure": ("pageindex", "graphrag", "llm_wiki"),
        "no_index": ("long_context", "cag", "agentic"),
    }
    session = lab(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    for key, option in (("long_context", "full_corpus"), ("cag", "cached_corpus")):
        chain = catalog.preset_pipeline(key)
        assert [s.kind for s in chain.stages] == [*rag_lab.FIXED_HEAD, *rag_lab.FIXED_TAIL]
        assert stage(chain, "context").option == option and stage(chain, "context").params == {}
    shown = presets(session)
    assert shown["long_context"]["family"] == shown["cag"]["family"] == "no_index"
    assert shown["cag"]["segment"] == [] and shown["cag"]["replaces_context"] is True
    assert shown["cag"]["context"] == {"option": "cached_corpus", "params": {}}
    state = session.rag_lab_state()["catalog"]
    assert state["preset_families"] == [
        {"id": "search", "label_text": "Recherche"},
        {"id": "structure", "label_text": "Structure"},
        {"id": "no_index", "label_text": "Sans index"},
    ]
    assert state["corpus_options"] == ["full_corpus", "cached_corpus"]
    session.close()


@pytest.mark.parametrize(
    "families",
    [
        {"search": ("dense", "hybrid", "rerank"), "no_index": ("long_context",)},
        {"search": ("dense", "hybrid", "rerank", "cag"), "no_index": ("long_context", "cag")},
    ],
)
def test_a_preset_outside_a_family_or_in_two_fails_the_content(monkeypatch, families):
    path = config.content_file("rag_lab.yaml", "fr")
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    rag_lab.RagLabContent.model_validate(raw)
    monkeypatch.setattr(rag_lab, "PRESET_FAMILIES", families)
    with pytest.raises(ValueError, match="preset_families"):
        rag_lab.RagLabContent.model_validate(raw)


@pytest.mark.parametrize(
    ("kind", "option"),
    [("vector_search", "cosine"), ("query", "rewrite"), ("fusion", "rrf"), ("rerank", "declared")],
)
def test_a_corpus_context_refuses_any_step_of_the_segment(index, kind, option):
    session = lab(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    chain = catalog.preset_pipeline("long_context")
    chain.stages.insert(3, rag_lab.Stage(id="x1", kind=kind, option=option))
    reason, at = rag_lab.check_pipeline(chain, catalog)
    assert at == "x1"
    assert "lit le corpus entier, sans recherche" in reason
    assert "Corpus entier dans le prompt" in reason
    session.close()


def test_without_search_another_context_keeps_its_refusal_and_the_head_is_unchecked(index):
    session = lab(index)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    chain = catalog.preset_pipeline("long_context")
    stage(chain, "context").option = "excerpts"
    reason, at = rag_lab.check_pipeline(chain, catalog)
    assert at == stage(chain, "context").id and "aucune recherche" in reason
    # FAISS absent in the head: the long context does not use it, the chain is accepted.
    chain = catalog.preset_pipeline("long_context")
    stage(chain, "vector_store").option = "faiss"
    catalog.options[("vector_store", "faiss")].available = False
    catalog.options[("vector_store", "faiss")].reason_text = "FAISS absent"
    assert rag_lab.check_pipeline(chain, catalog) is None
    stage(chain, "context").option = "excerpts"
    stage(chain, "context").params = {"top_k": 3}
    chain.stages.insert(3, rag_lab.Stage(id="x1", kind="vector_search", option="cosine"))
    assert "FAISS absent" in rag_lab.check_pipeline(chain, catalog)[0]
    session.close()


def test_the_sequence_draws_the_prefix_for_the_cag_only_and_no_question_embedding(index):
    session = lab(index)
    steps = {s["key"]: s for s in session.rag_lab_state()["catalog"]["steps"]}
    assert steps["cache_prefix"] | {"explain_text": ""} == steps["cache_prefix"] | {
        "phase": "build",
        "stage": "context",
        "own": False,
        "part": "prefix",
        "options": ["cached_corpus"],
        "hidden_with": [],
        "explain_text": "",
    }
    assert steps["embed_query"]["hidden_with"] == [
        "full_corpus",
        "cached_corpus",
        "agent_loop",  # V1.2 story 11
        "section_tree",
        "graph_search",  # V1.2 story 13
        "wiki_pages",  # V1.2 story 14
    ]
    assert [u["component"] for u in steps["cache_prefix"]["uses"]] == [
        "documents",
        "model_cache",
        "llm",
    ]
    context = rag_lab.STEPS["context"]
    assert (context.reads, context.writes, context.options) == (
        ("chunks", "question"),
        ("augmented_prompt",),
        (),
    )
    assert rag_lab.COMPONENTS["model_cache"] == ("models", "🗃️", None)
    session.close()


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_sheets_presets_families_and_component_in_each_language(lang):
    texts = rag_lab.load_lab_content(lang)
    long_sheet, cag_sheet = (
        texts.sheets["context.full_corpus"],
        texts.sheets["context.cached_corpus"],
    )
    assert any("Lost in the Middle" in s.label_text for s in long_sheet.sources)
    assert any(s.label_text.startswith("Chan et al.") for s in cag_sheet.sources)
    assert "2024" in cag_sheet.sources[0].label_text
    assert long_sheet.bench_text == cag_sheet.bench_text == ""
    reload_word = {"fr": "recharge", "en": "reloads", "de": "neu"}[lang]
    assert reload_word in cag_sheet.when_text and reload_word in cag_sheet.cost_text
    for key in ("long_context", "cag"):
        assert texts.presets[key].label_text and texts.presets[key].explain_text
    assert set(texts.preset_families) == {"search", "structure", "no_index"}
    assert texts.components["model_cache"].note_text
    assert texts.steps["cache_prefix"].explain_text
    assert texts.options["context"]["cached_corpus"].label_text


# ---------- criterion 3: the shipped corpus fits in 16 384 tokens, estimated ----------


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_the_shipped_corpus_fits_the_window_with_the_largest_reserve(lang):
    content = load_rag_content(lang)
    documents = workcopy.documents(content, lang)
    excerpts = [content.excerpt(n, d.title_text, d.text) for n, d in enumerate(documents, 1)]
    prompt = "\n\n".join([content.intro_text, *excerpts, QUESTION])
    tokens = config.estimate_tokens(prompt, config.Config().chars_per_token)
    assert tokens + config.MAX_RESERVE <= rag_lab.NO_INDEX_WINDOW, tokens


# ---------- criteria 4, 5: availability ----------


def no_index(session: AppSession) -> tuple[dict, dict]:
    shown = presets(session)
    return shown["long_context"], shown["cag"]


@pytest.mark.parametrize("window", [4096, 8192])
def test_a_small_window_greys_both_and_the_api_refuses_them(index, window):
    session = lab(index, window=window)
    for shown in no_index(session):
        assert shown["available"] is False
        reason = shown["reason_text"]
        assert number(16384, "fr") in reason and number(window, "fr") in reason
        assert "sélecteur « Fenêtre »" in reason and "page Conversation" in reason
    mark = get_journal().last_seq()
    with pytest.raises(SendRefused):
        session.run_rag_lab(QUESTION, preset(session, "long_context"))
    assert not [e for e in get_journal().events_since(mark) if e.context_id == "rag_lab"]
    # The window raised: both available, read afresh (no other action).
    _, done = session.set_context_window(16384)
    if done is not None:
        done.result()
    session.join()
    assert all(p["available"] for p in no_index(session))
    session.close()


def test_the_validation_reads_the_window_again_once_it_changes(index):
    """The validation's catalog (kept a few seconds) is read again for another window."""
    session = lab(index, window=4096)
    chain = preset(session, "long_context")
    assert session.validate_rag_lab(chain)["valid"] is False
    _, done = session.set_context_window(16384)
    if done is not None:
        done.result()
    session.join()
    assert session.validate_rag_lab(chain)["valid"] is True
    session.close()


@pytest.mark.parametrize(
    ("lang", "needed", "where"),
    [("en", "16,384", "“Window” selector"), ("de", "16.384", "Auswahl „Fenster“")],
)
def test_the_reason_in_english_and_german(index, lang, needed, where):
    session = lab(index, window=4096)
    session.set_language(lang)
    for shown in no_index(session):
        assert needed in shown["reason_text"] and where in shown["reason_text"]
    session.close()


def test_a_window_bound_by_the_model_says_the_bound(index):
    session = lab(index, Bounded())
    long_context, cag = no_index(session)
    assert not long_context["available"] and not cag["available"]
    assert number(8192, "fr") in long_context["reason_text"]
    assert f"déjà de {number(16384, 'fr')}" in long_context["reason_text"]
    assert "contexte natif du modèle" in long_context["reason_text"]
    assert "sélecteur" not in long_context["reason_text"]
    session.close()


def test_without_a_model_the_cag_is_local_only_and_the_long_context_skips_its_generation(index):
    session = lab(index, model=None)
    long_context, cag = no_index(session)
    assert cag["available"] is False and "modèle local" in cag["reason_text"]
    assert long_context["available"] is True
    events = run(session, pipeline=preset(session, "long_context"))
    assert ended(events, "generation")["status"] == "skipped"
    assert run_status(events) == "ok"
    session.close()


def cloud(index: Path, *, tpm: bool) -> tuple[AppSession, Provider]:
    place_model()
    place_reranker()
    shipped = config.load_config()
    values = rerank_config(index)
    values["context"] = {"window": 16384, "near_limit_ratio": 0.8}
    cfg = config.Config(values=config._deep_merge(shipped.values, values))
    entry = cfg.cloud_model("groq")
    if not tpm:  # declared at 32 768, its quota not bounding
        entry = entry.model_copy(update={"tpm": None, "window": 32768})
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    provider = Provider(GROQ_TEXT)
    session = AppSession(
        cfg,
        cloud_factory=provider.factory,
        embedder_factory=Embedders(),
        reranker_factory=Rerankers(),
    )
    session.boot_cloud(entry).result()
    session.join()
    return session, provider


def test_in_the_cloud_the_long_context_runs_and_the_cag_is_refused(index):
    session, provider = cloud(index, tpm=False)
    long_context, cag = no_index(session)
    assert long_context["available"] and not cag["available"]
    assert "modèle local" in cag["reason_text"]
    events = run(session, pipeline=preset(session, "long_context"))
    generation = ended(events, "generation")
    assert generation["status"] == "ok" and len(provider.requests) == 1
    body = provider.requests[0].content.decode("utf-8")
    assert "Mots de passe" in body or "mot de passe" in body
    assert summary(events, "query")["usd"] is not None
    session.close()


def test_in_the_cloud_a_declaration_that_bounds_lower_says_it(index):
    session, _ = cloud(index, tpm=True)
    long_context, _ = no_index(session)
    assert not long_context["available"] and "quota du fournisseur" in long_context["reason_text"]
    session.close()


# ---------- criteria 2, 12, 18: the long context ----------


def test_the_long_context_puts_every_document_whole_in_the_prompt(index):
    engine = Counting()
    session = lab(index, engine)
    events = run(session, pipeline=preset(session, "long_context"))
    assert run_status(events) == "ok"
    for kind in rag_lab.FIXED_HEAD:
        head = ended(events, kind)
        assert head["status"] == "skipped" and "Non utilisée" in head["error_text"]
        assert [(c["phase"], c["tokens"], c["duration_ms"], c["usd"]) for c in head["costs"]] == [
            ("build", 0, 0, 0.0)
        ]
    context = ended(events, "context")
    content = session._rag_content
    documents = workcopy.documents(content, "fr")
    assert [d.doc_id for d in documents] == list(SMALL)
    assert [
        (i["doc_id"], i["chunk_id"], i["rank"], i["placed"], i["state"]) for i in context["items"]
    ] == [(d, n, n, n, "whole") for n, d in enumerate(SMALL, 1)]
    assert [i["text"] for i in context["items"]] == [d.text for d in documents]
    assert context["output_text"].startswith(content.intro_text)
    assert context["budget"] is None and context["window"] == 16384
    assert facts(context)["Source"].startswith("le corpus")
    prompt = bytes(engine.calls[-1]).decode("utf-8")
    assert context["output_text"] in prompt and QUESTION in prompt
    assert prompt.index(context["output_text"]) < prompt.rindex(QUESTION)
    # The three times: nothing to build, the whole prompt at each question.
    build = summary(events, "build")
    assert build["tokens"] == 0 and build["duration_ms"] == 0 and build["usd"] == 0.0
    generation = ended(events, "generation")
    query = summary(events, "query")
    assert query["tokens"] == len(engine.calls[-1]) + len("Quatorze.")
    assert generation["cache"] is None
    session.close()


def test_the_long_context_reads_the_work_copy_once_it_differs(index):
    engine = Counting()
    session = lab(index, engine)
    copy = workcopy.apply(
        session._rag_content, workcopy.WorkCopy(), "add", "nouveau", "Neuf", "Un texte neuf."
    )
    workcopy.save(copy, "fr")
    events = run(session, pipeline=preset(session, "long_context"))
    context = ended(events, "context")
    assert [i["doc_id"] for i in context["items"]] == [*SMALL, "nouveau"]
    assert "copie de travail" in facts(context)["Source"]
    assert "Un texte neuf." in bytes(engine.calls[-1]).decode("utf-8")
    session.close()


def test_the_diagnosis_finds_the_anchor_in_a_whole_document_and_notes_the_middle(index):
    session = lab(index)
    events = run(session, pipeline=preset(session, "long_context"))
    items = ended(events, "context")["items"]
    listed = [diagnosis.Listed(i["doc_id"], i["text"], i["placed"]) for i in items]
    stages = [diagnosis.StageList("context", listed)]
    text = items[1]["text"]
    anchor = next(line for line in text.splitlines() if len(line) > 40)[:40]
    middle = diagnosis.diagnose_passage(RagPassage(doc_id=SMALL[1], anchor_text=anchor), [], stages)
    assert middle["fault"] is None and middle["note"] == "middle"
    first_anchor = next(line for line in items[0]["text"].splitlines() if len(line) > 40)[:40]
    first = RagPassage(doc_id=SMALL[0], anchor_text=first_anchor)
    found = diagnosis.diagnose_passage(first, [], stages)
    assert found["fault"] is None and found["note"] is None
    session.close()


# ---------- criteria 6, 7, 12, 17: the CAG on an engine with a state ----------


def test_the_cag_builds_its_prefix_cold_then_reads_it_warm(index):
    engine = Counting()
    session = lab(index, engine)
    chain = preset(session, "cag")
    cold = run(session, pipeline=chain)
    assert run_status(cold) == "ok"
    prefix_ids = engine.prefills[-1]
    n = len(prefix_ids)
    assert engine.clears == 1 and len(engine.prefills) == 1 and engine.prefilled == [n]
    part = ended(cold, "cache_prefix")
    assert part["status"] == "ok" and part["part"] == "prefix"
    assert part["cache"]["state"] == "cold" and part["cache"]["prefix_tokens"] == n
    assert part["cache"]["state_bytes"] == n * 4  # the fake's snapshot size
    assert [(c["phase"], c["tokens"]) for c in part["costs"]] == [("build", n)]
    assert isinstance(part["costs"][0]["duration_ms"], int)
    generation = ended(cold, "generation")
    sent = len(engine.calls[-1])
    assert generation["cache"] == {
        "state": "cold",
        "prefix_tokens": n,
        "read_tokens": n,
        "evaluated_tokens": sent - n,
        "state_bytes": n * 4,
        "build_ms": part["cache"]["build_ms"],
    }
    assert summary(cold, "build")["tokens"] == n
    assert summary(cold, "query")["tokens"] == sent - n + len("Quatorze.")
    assert "lus du cache" in generation["costs"][0]["note_text"]
    snapshots, restores = engine.snapshots, engine.restores
    entry = session._cag_cache
    assert entry is not None and entry.prefix_tokens == n

    warm = run(session, OTHER_QUESTION, chain)
    assert len(engine.prefills) == 1 and engine.clears == 1  # nothing built again
    assert engine.restores == restores + 2  # the CAG's state, then the main context's
    assert engine.snapshots == snapshots + 1  # the main context's copy only
    generation = ended(warm, "generation")
    sent = len(engine.calls[-1])
    assert generation["cache"]["state"] == "warm"
    assert generation["cache"]["read_tokens"] == n
    assert generation["cache"]["evaluated_tokens"] == sent - n
    (call,) = calls_ended(get_journal().events_since(0)[-200:])[-1:]
    assert call["cache_read_tokens"] == n and call["cache_write_tokens"] == sent - n
    assert summary(warm, "query")["tokens"] == sent - n + len("Quatorze.")
    part = ended(warm, "cache_prefix")
    assert part["status"] == "ok" and part["costs"][0]["measured_at_build"] is True
    assert facts(generation)["État du cache"].startswith("chaud")
    session.close()


def test_the_prefix_is_an_exact_token_prefix_cut_at_a_line_before_the_question(index):
    engine = Counting()
    session = lab(index, engine)
    chain = preset(session, "cag")
    first = run(session, pipeline=chain)
    run(session, OTHER_QUESTION, chain)
    prefix = engine.prefills[0]
    sent = [c for c in engine.calls if c[: len(prefix)] == prefix]
    assert len(sent) == 2  # each question's prompt starts with the same prefix
    text = bytes(prefix).decode("utf-8")
    assert text.endswith("\n") and QUESTION not in text and OTHER_QUESTION not in text
    # The focus's parts are the generation's messages (the same function, story 7).
    context = ended(first, "context")
    prompt = bytes(sent[0]).decode("utf-8")
    assert all(part["text"] in prompt for part in context["prompt_parts"])
    session.close()


def test_the_journal_keeps_the_cache_and_never_the_state(index):
    engine = Counting()
    session = lab(index, engine)
    events = run(session, pipeline=preset(session, "cag"))
    kept = [e for e in get_journal().events_since(0) if e.kind == "rag_lab_stage_ended"]
    cached = [e.payload for e in kept if e.payload.get("cache")]
    assert {p["kind"] for p in cached} == {"cache_prefix", "generation"}
    assert set(cached[-1]["cache"]) == {
        "state",
        "prefix_tokens",
        "read_tokens",
        "evaluated_tokens",
        "state_bytes",
        "build_ms",
    }
    dumped = json.dumps([e.payload for e in events], default=str)
    assert "EngineSnapshot" not in dumped and "snapshot" not in dumped
    session.close()


# ---------- criteria 8, 9: invalidation and memory ----------


@pytest.mark.parametrize("change", ["window", "language", "clear", "close", "model"])
def test_each_change_drops_the_entry_and_the_next_run_is_cold(index, change):
    engine = Counting()
    session = lab(index, engine)
    chain = preset(session, "cag")
    run(session, pipeline=chain)
    assert session._cag_cache is not None
    if change == "window":
        _, done = session.set_context_window(8192)
        if done is not None:
            done.result()
        session.join()
        assert session._cag_cache is None
        _, done = session.set_context_window(16384)
        if done is not None:
            done.result()
        session.join()
    elif change == "language":
        session.set_language("en")
        shrink(session)  # the corpus is read again in English
    elif change == "clear":
        session.clear_cache()
    elif change == "close":
        session.close()
        assert session._cag_cache is None
        return
    else:
        session._release()
        assert session._cag_cache is None
        return
    assert session._cag_cache is None
    prefills = len(engine.prefills)
    again = run(session, OTHER_QUESTION, preset(session, "cag"))
    assert run_status(again) == "ok", [e.payload.get("error_text") for e in again][-3:]
    assert len(engine.prefills) == prefills + 1
    assert ended(again, "generation")["cache"]["state"] == "cold"
    session.close()


def test_a_snapshot_that_raises_memory_error_keeps_no_state(index):
    engine = Counting(snapshot_error=MemoryError())
    session = lab(index, engine)
    events = run(session, pipeline=preset(session, "cag"))
    assert run_status(events) == "ok"
    part = ended(events, "cache_prefix")
    assert part["cache"]["state"] == "none" and "MemoryError" in part["warning_text"]
    generation = ended(events, "generation")
    assert (
        generation["cache"]["state"] == "none"
        and "Cache CAG non gardé" in generation["warning_text"]
    )
    assert session._cag_cache is None
    session.close()


def test_an_estimate_over_the_budget_builds_nothing(index, tmp_path):
    path = tmp_path / "Probed.gguf"
    path.write_bytes(b"placeholder")
    stat = path.stat()
    probe.record_success(
        probe.ProbeResult(
            ok=True,
            path=str(path),
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            rss_bytes=GIB,
            kv_bytes_per_token=100_000,
            probe_version=probe.PROBE_VERSION,
            probe_window=4096,
            rss_eval_tokens=0,
        )
    )
    rss = Rss()
    engine = Counting()
    session = lab(index, engine, model=str(path), rss=rss)
    assert session.active_model() is not None
    rss.value = 3900 * MIB  # WaveStack now near its 4 096 Mo budget
    events = run(session, pipeline=preset(session, "cag"))
    assert run_status(events) == "ok"
    assert engine.prefills == [] and engine.clears == 0
    part = ended(events, "cache_prefix")
    assert part["status"] == "skipped" and "Mémoire insuffisante" in part["error_text"]
    assert "Mo" in part["error_text"]
    generation = ended(events, "generation")
    assert generation["status"] == "ok" and generation["cache"]["state"] == "none"
    assert "Cache CAG non gardé" in generation["warning_text"]
    assert session._cag_cache is None
    session.close()


def test_a_memory_over_the_budget_after_the_snapshot_drops_the_state(index):
    rss = Rss()
    engine = Counting()
    session = lab(index, engine, rss=rss)
    rss.value = 5 * GIB
    events = run(session, pipeline=preset(session, "cag"))
    part = ended(events, "cache_prefix")
    assert part["cache"]["state"] == "none" and "au-delà du budget" in part["warning_text"]
    assert session._cag_cache is None
    session.close()


# ---------- criterion 10: the chat's context comes back ----------


def test_a_conversation_keeps_its_context_around_the_cag(index):
    engine = Counting()
    session = lab(index, engine)
    chat(session, "Bonjour")
    main = list(session._main_cache or [])
    assert main
    chain = preset(session, "cag")
    run(session, pipeline=chain)
    assert engine.cache == main and session._main_cache == main
    run(session, OTHER_QUESTION, chain)
    assert engine.cache == main and session._main_cache == main
    after = chat(session, "Encore")
    assert "rag_lab" not in [p["cause"] for p in after.get("prefix_not_reused", [])]
    session.close()


def test_the_chat_gauge_ignores_the_workshops_calls():
    source = (Path(__file__).parents[1] / "src/wavestack/web/static/app.js").read_text(
        encoding="utf-8"
    )
    case = source[source.index('case "model_call_ended":') :]
    case = case[: case.index("break;")]
    assert 'if (envelope.context_id !== "rag_lab")' in case
    assert case.index("context_id") < case.index("store.cacheGauge =")


# ---------- criterion 11: a server without state ----------


@pytest.mark.parametrize("reuse", [True, False])
def test_a_server_is_warmed_with_one_token_then_reads_its_cache(index, reuse):
    engine = Server(reuse=reuse)
    session = lab(index, engine)
    chain = preset(session, "cag")
    cold = run(session, pipeline=chain)
    assert run_status(cold) == "ok"
    warm_up, sent = engine.calls[-2], engine.calls[-1]
    n = len(warm_up)
    assert sent[:n] == warm_up and bytes(warm_up).decode("utf-8").endswith("\n")
    part = ended(cold, "cache_prefix")
    assert [(c["phase"], c["tokens"]) for c in part["costs"]] == [("build", n)]
    assert ended(cold, "generation")["cache"]["state"] == "cold"
    calls = len(engine.calls)
    warm = run(session, OTHER_QUESTION, chain)
    assert len(engine.calls) == calls + 1  # no warm-up
    generation = ended(warm, "generation")
    assert generation["cache"]["state"] == "warm" and generation["cache"]["read_tokens"] >= n
    # The chat's call evicts the prefix: lost, said, counted for what was evaluated.
    chat(session, "Bonjour")
    lost = run(session, QUESTION, chain)
    generation = ended(lost, "generation")
    sent = len(engine.calls[-1])
    assert generation["cache"]["state"] == "lost" and "Préfixe perdu" in generation["warning_text"]
    read = generation["cache"]["read_tokens"]
    assert read < n and summary(lost, "query")["tokens"] == sent - read + len("Quatorze.")
    assert session._cag_cache is not None  # kept: the server holds the prefix again
    session.close()


def test_a_server_that_says_nothing_is_unknown_without_figures(index):
    engine = Server(reuse=False, silent=True)
    session = lab(index, engine)
    events = run(session, pipeline=preset(session, "cag"))
    generation = ended(events, "generation")
    assert generation["cache"]["state"] == "unknown"
    assert generation["cache"]["read_tokens"] is None
    assert generation["cache"]["evaluated_tokens"] is None
    part = ended(events, "cache_prefix")
    assert part["costs"][0]["note_text"]  # the warm-up's tokens estimated
    session.close()


# ---------- criterion 12: the three times compared ----------


def test_the_cag_queries_fewer_tokens_than_the_long_context(index):
    session = lab(index, Counting())
    long_context = run(session, pipeline=preset(session, "long_context"))
    cag = run(session, pipeline=preset(session, "cag"))
    assert summary(long_context, "build")["tokens"] == 0
    assert summary(long_context, "query")["tokens"] > 0
    assert summary(cag, "build")["tokens"] > 0
    assert summary(cag, "query")["tokens"] < summary(long_context, "query")["tokens"]
    session.close()


# ---------- criterion 13: the updates ----------


def test_an_update_of_the_long_context_redoes_nothing(index):
    session = lab(index)
    events = update(
        session, "add", "nouveau", "Neuf", "Un texte neuf.", preset(session, "long_context")
    )
    assert run_status(events) == "ok"
    started = next(e.payload for e in events if e.kind == "rag_lab_run_started")
    assert started["stages"] == []
    assert summary(events, "update") | {"note_text": None} == {
        "phase": "update",
        "parts": 0,
        "tokens": 0,
        "duration_ms": 0,
        "usd": 0.0,
        "energy_wh_min": None,
        "energy_wh_max": None,
        "gco2e_min": None,
        "gco2e_max": None,
        "partial": False,
        "measured_at_build": False,
        "note_text": None,
    }
    assert "relu à chaque requête" in summary(events, "update")["note_text"]
    assert not workcopy.load("fr").empty  # the copy kept
    session.close()


@pytest.mark.parametrize(
    ("operation", "more"), [("add", True), ("modify", True), ("delete", False)]
)
def test_an_update_of_the_cag_reloads_its_whole_prefix(index, operation, more):
    engine = Counting()
    session = lab(index, engine)
    chain = preset(session, "cag")
    cold = run(session, pipeline=chain)
    built = summary(cold, "build")["tokens"]
    args = {
        "add": ("add", "nouveau", "Neuf", "Un texte neuf."),
        "modify": ("modify", "teletravail", "", "Un paragraphe de plus."),
        "delete": ("delete", "classification"),
    }[operation]
    clears = engine.clears
    events = update(session, *args, pipeline=chain)
    assert run_status(events) == "ok"
    part = ended(events, "cache_prefix")
    assert part["status"] == "ok"
    tokens = summary(events, "update")["tokens"]
    assert engine.clears == clears + 1 and engine.prefilled[-1] == tokens
    assert (tokens > built) if more else (tokens < built)
    assert session._cag_cache is not None and session._cag_cache.prefix_tokens == tokens
    prefills = len(engine.prefills)
    after = run(session, OTHER_QUESTION, chain)
    assert len(engine.prefills) == prefills
    assert ended(after, "generation")["cache"]["state"] == "warm"
    session.close()


def test_an_update_of_the_cag_without_a_local_model_is_estimated(index):
    session = lab(index)
    texts = rag_lab.load_lab_content()
    catalog = session._rag_lab_catalog(texts)
    seen: list[tuple[str, dict]] = []
    deps = replace(
        session._rag_lab_deps(texts, catalog, CancelToken(), rag_lab.Loans(session._load_registry)),
        cag=None,
        emit=lambda kind, payload, step_id, component: seen.append((kind, payload)),
    )
    before = workcopy.WorkCopy()
    after = workcopy.apply(session._rag_content, before, "add", "nouveau", "Neuf", "Un texte neuf.")
    status = rag_lab.UpdateRun("upd9", "Ajout", preset(session, "cag"), deps, before, after).run()
    assert status == "ok"
    part = next(p for k, p in seen if k == "rag_lab_stage_ended")
    assert part["status"] == "skipped" and part["costs"][0]["tokens"] > 0
    assert "estimé" in part["costs"][0]["note_text"]
    assert part["costs"][0]["duration_ms"] is None
    session.close()


# ---------- criterion 14: too long ----------


def test_a_prompt_over_the_window_is_never_sent_nor_cached(index):
    engine = Counting()
    session = lab(index, engine, small=False)  # ~40 000 tokens at one byte a token
    calls = len(engine.calls)
    events = run(session, pipeline=preset(session, "cag"))
    generation = ended(events, "generation")
    assert generation["status"] == "error" and "Prompt trop long" in generation["error_text"]
    assert number(16384, "fr") in generation["error_text"]
    assert len(engine.calls) == calls and engine.prefills == [] and engine.clears == 0
    assert ended(events, "cache_prefix")["status"] == "skipped"
    assert session._cag_cache is None
    session.close()


# ---------- review: errors around the prefix, a merging tokenizer, the budget's slot ----------


class Merging(FakeEngine):
    """A tokenizer that merges an end of line with the byte after it (as BPE merges across a
    line): the text up to a cut tokenized alone ends otherwise than the whole prompt."""

    def tokenize(self, text: str) -> list[int]:
        raw, out, i = list(text.encode("utf-8")), [], 0
        while i < len(raw):
            if raw[i] == 10 and i + 1 < len(raw):
                out.append(1000 + raw[i + 1])
                i += 2
            else:
                out.append(raw[i])
                i += 1
        return out


def test_the_prefix_stays_an_exact_prefix_with_a_merging_tokenizer():
    from wavestack.context.render import RenderedContext

    engine = Merging()
    prompt = "Consigne\nCorpus entier\nQuestion ?"
    rendered = RenderedContext(prompt, engine.tokenize(prompt), [])
    ids = AppSession._cag_prefix_ids(engine, rendered, "Question ?")
    alone = engine.tokenize(prompt[: prompt.rfind("\n") + 1])
    assert ids and ids == rendered.ids[: len(ids)]
    assert len(ids) == len(alone) - 1  # the merged « \nQ » is never in the prefix
    assert ids == alone[:-1]


def test_a_model_call_that_raises_after_the_prefix_restores_the_main_context(index, monkeypatch):
    engine = Counting()
    session = lab(index, engine)
    chat(session, "Bonjour")
    main = list(session._main_cache or [])
    assert main

    def broken(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("panne")

    monkeypatch.setattr(session, "_call_model", broken)
    events = run(session, pipeline=preset(session, "cag"))
    assert ended(events, "generation")["status"] == "error"
    assert ended(events, "cache_prefix")["status"] == "ok"  # built before the call
    assert engine.cache == main and session._main_cache == main
    session.close()


def test_a_preparation_that_raises_is_not_said_local_only(index, monkeypatch):
    engine = Counting()
    session = lab(index, engine)

    def broken(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("panne")

    monkeypatch.setattr(session, "_cag_prepare", broken)
    events = run(session, pipeline=preset(session, "cag"))
    part = ended(events, "cache_prefix")
    assert part["status"] == "error" and "RuntimeError" in part["error_text"]
    assert "local" not in part["error_text"]
    session.close()


def test_a_failed_prefill_sends_no_generation(index):
    class Failing(Counting):
        def prefill(self, ids, cancel):  # noqa: ANN001, ANN201
            raise RuntimeError("prefill en panne")

    engine = Failing()
    session = lab(index, engine)
    calls = len(engine.calls)
    events = run(session, pipeline=preset(session, "cag"))
    assert ended(events, "cache_prefix")["status"] == "error"
    generation = ended(events, "generation")
    assert generation["status"] == "error" and "RuntimeError" in generation["error_text"]
    assert len(engine.calls) == calls  # nothing generated behind a failed prefix
    assert session._cag_cache is None
    session.close()


def test_the_kept_state_is_held_by_the_budget_until_it_is_dropped(index):
    engine = Counting()
    session = lab(index, engine)
    run(session, pipeline=preset(session, "cag"))
    assert session._load_registry.holder("rag_lab.cag") is not None
    session.clear_cache()
    assert session._cag_cache is None
    assert session._load_registry.holder("rag_lab.cag") is None
    session.close()
