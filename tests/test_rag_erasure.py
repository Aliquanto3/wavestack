"""V1.2 story 18 (CAP-14): the « Effacement » card of the Attack tab.

No model, no index, no network (the guard of `conftest.py` stays on). The statuses and counts
are written by hand, measured at the spec's checkpoint on the real corpus; a difference is a
defect of the story, not a value to rewrite.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_bricks import HEADERS

from wavestack import config
from wavestack.rag import erasure, workcopy
from wavestack.rag import index as rag_index
from wavestack.rag.corpus import chunk_corpus, load_rag_content
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.web.app import create_app

LANGS = ("fr", "en", "de")
CONTENT = config.repo_root() / "content"
CODE = "ORN-7731-QZ"
AVERAGE = re.compile(r"\b(mean|average|avg|mrr|recall_at_k|aggregates?)\b", re.IGNORECASE)
STORY_OF = {
    "long_context": 10,
    "cag": 10,
    "raptor": 12,
    "crag": 12,
    "llm_wiki": 14,
}
# V1.2 story 10 brought long_context and cag into the workshop (`lab.PRESETS`); their places
# stay constructed, with the story 10 that will record the real cache.
IN_WORKSHOP = (
    "dense",
    "hybrid",
    "rerank",
    "long_context",
    "cag",
    "agentic",
    "pageindex",
    "graphrag",  # V1.2 story 13
)


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def make_session(lang: str = "fr") -> AppSession:
    return AppSession(config.Config(values={"language": lang}))


def ask(session: AppSession, **fields):
    return session.rag_lab_erasure(erasure.ErasureRequest(**fields))


def statuses(body: dict) -> dict[str, str]:
    return {p["id"]: p["status"] for p in body["places"]}


START = {
    "chunks": "present",
    "bm25": "present",
    "contexts": "present",
    "shipped_contexts": "absent",
    "raptor_summaries": "present",
    "pageindex_tree": "present",
    "graph_communities": "present",
    "graph_entities": "present",
    "wiki_pages": "present",
    "cag_cache": "present",
    "long_context_prefix": "present",
    "source": "no_copy",
}
ERASED = {
    **START,
    "chunks": "erased",
    "bm25": "erased",
    "contexts": "to_rebuild",
    "raptor_summaries": "to_rebuild",
    "pageindex_tree": "to_rebuild",
    "graph_communities": "to_rebuild",
    "graph_entities": "to_rebuild",
    "wiki_pages": "to_rebuild",
    "cag_cache": "to_reload",
    "long_context_prefix": "to_reload",
}


@pytest.mark.parametrize("lang", LANGS)
def test_start_the_measured_places_hold_the_code(lang):
    body = ask(make_session(lang), sentinel_active=True, step="start")
    assert statuses(body) == START
    hits = {p["id"]: p["hits"] for p in body["places"]}
    assert hits["chunks"] == 2 and hits["bm25"] == 2 and hits["contexts"] == 1
    assert hits["shipped_contexts"] == 0 and hits["source"] == 1
    assert hits["pageindex_tree"] >= 1  # V1.2 story 11: measured on the rule's tree
    # V1.2 story 13: measured on the rule's graph, the code kept as an entity from one mention
    assert hits["graph_entities"] >= 1 and hits["graph_communities"] >= 1
    assert body["corpus"]["sentinel_passages"] == 2
    assert [p["position"] for p in body["results"]["ranking"]] == [2, 1]
    assert [p["rank"] for p in body["results"]["ranking"]] == [1, 2]
    assert {r["doc_id"] for r in body["results"]["ranking"]} == {"projet_orion"}


@pytest.mark.parametrize("lang", LANGS)
def test_erase_chunks_and_bm25_are_erased_the_rest_stays(lang):
    body = ask(make_session(lang), sentinel_active=True, step="erase")
    assert statuses(body) == ERASED
    assert {p["id"]: p["hits"] for p in body["places"]}["source"] == 0
    assert body["results"]["ranking"] == []
    holding = {h["place"]: h for h in body["results"]["holding"]}
    assert set(holding) == {
        "contexts",
        "raptor_summaries",
        "pageindex_tree",
        "graph_communities",
        "graph_entities",
        "wiki_pages",
        "cag_cache",
        "long_context_prefix",
    }
    assert all(CODE in h["text"] for h in holding.values())


@pytest.mark.parametrize("lang", LANGS)
def test_rebuild_one_architecture_touches_only_its_places(lang):
    body = ask(make_session(lang), sentinel_active=True, step="rebuild", rebuilt=["graphrag"])
    # V1.2 story 13: the graph's places are measured, « erased » once the graph is rebuilt
    # without the sentinel (never « illustratif, non mesuré »)
    assert statuses(body) == {
        **ERASED,
        "graph_communities": "erased",
        "graph_entities": "erased",
    }
    rebuilt = next(p for p in body["places"] if p["id"] == "graph_communities")
    assert rebuilt["status_text"] == rebuilt_measured_text(lang) and rebuilt["hits"] == 0
    assert body["costs"] and body["costs"][0]["architecture"] == "graphrag"
    assert not re.search(r"\d+\s*(ms|s|tokens?|\$|€)", body["costs"][0]["text"])


@pytest.mark.parametrize("lang", LANGS)
def test_a_shared_copy_turns_erased_as_soon_as_one_architecture_rebuilds(lang):
    body = ask(make_session(lang), sentinel_active=True, step="rebuild", rebuilt=["dense"])
    found = statuses(body)
    assert found["contexts"] == "erased" and found["shipped_contexts"] == "absent"
    assert found["graph_communities"] == "to_rebuild" and found["cag_cache"] == "to_reload"
    contexts = next(p for p in body["places"] if p["id"] == "contexts")
    assert contexts["shared"] and contexts["shared_text"]


def test_a_cache_turns_erased_by_its_own_architecture_only():
    found = statuses(
        ask(make_session(), sentinel_active=True, step="rebuild", rebuilt=["cag", "pageindex"])
    )
    assert found["cag_cache"] == "erased_illustrative"
    assert found["pageindex_tree"] == "erased"  # V1.2 story 11: measured, never illustrative
    assert found["long_context_prefix"] == "to_reload"


def rebuilt_measured_text(lang: str) -> str:
    return erasure.load_erasure(lang).texts["status"]["erased"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_source_says_whether_the_code_is_still_read_in_it(lang):
    texts = erasure.load_erasure(lang).texts
    for step, key, hits in (("start", "source_found_text", 1), ("erase", "source_gone_text", 0)):
        body = ask(make_session(lang), sentinel_active=True, step=step)
        source = next(p for p in body["places"] if p["id"] == "source")
        assert source["status"] == "no_copy" and source["hits"] == hits
        assert source["status_text"] == f"{texts['status']['no_copy']} · {texts[key]}"


def test_rebuild_without_an_architecture_is_refused():
    with pytest.raises(ValidationError):
        erasure.ErasureRequest(sentinel_active=True, step="rebuild")


def test_the_guard_without_a_sentinel_gives_the_message_and_no_status():
    for step, rebuilt in (("erase", []), ("rebuild", ["graphrag"])):
        body = ask(make_session(), sentinel_active=False, step=step, rebuilt=rebuilt)
        assert body["guard_text"] == "Rien à effacer : construisez d'abord les copies."
        assert body["step"] == "idle" and body["results"] is None
        assert all(p["status"] is None for p in body["places"])
    started = ask(make_session(), sentinel_active=False, step="start")
    assert started["step"] == "idle" and started["guard_text"] is None


def test_erase_twice_gives_the_same_table_and_idle_has_no_status():
    session = make_session()
    one = ask(session, sentinel_active=True, step="erase")
    two = ask(session, sentinel_active=True, step="erase")
    assert one == two
    idle = ask(session, sentinel_active=True, step="idle")
    assert idle["step"] == "idle" and idle["corpus"]["sentinel_passages"] == 2
    assert ask(session, sentinel_active=False)["corpus"]["sentinel_passages"] == 0


def test_rebuilt_outside_rebuild_and_unknown_values_are_refused():
    for step in ("idle", "start", "erase"):
        with pytest.raises(ValidationError):
            erasure.ErasureRequest(sentinel_active=True, step=step, rebuilt=["graphrag"])
    with pytest.raises(ValidationError):
        erasure.ErasureRequest(step="rebuild", rebuilt=["nope"])
    with pytest.raises(ValidationError):
        erasure.ErasureRequest(step="explode")


def test_the_displayed_marks_illustrative_and_upcoming():
    body = ask(make_session(), sentinel_active=True, step="erase")
    places = {p["id"]: p for p in body["places"]}
    assert places["raptor_summaries"]["kind"] == "constructed"
    assert places["raptor_summaries"]["illustrative_text"].startswith("illustratif · cas construit")
    # V1.2 story 11: the tree; V1.2 story 13: the graph's entities and communities
    for pid in ("pageindex_tree", "graph_communities", "graph_entities"):
        assert places[pid]["kind"] == "measured"
        assert places[pid]["illustrative_text"] is None
    assert places["wiki_pages"]["illustrative_text"].endswith("story 14)")
    assert places["chunks"]["illustrative_text"] is None
    rows = {r["architecture"]: r for r in places["bm25"]["rows"]}
    assert rows["hybrid"]["upcoming_text"] is None
    assert "story 12" in rows["crag"]["upcoming_text"] and "BM25" in rows["crag"]["upcoming_text"]
    source = {r["architecture"]: r["upcoming_text"] for r in places["source"]["rows"]}
    assert source["agentic"] is None and source["long_context"] is None


def snapshot_bytes(*roots: Path) -> dict[str, str]:
    found = {}
    for root in roots:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in files:
            found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


@pytest.mark.parametrize("lang", LANGS)
def test_nothing_is_written_nor_changed(lang):
    session = make_session(lang)
    content = load_rag_content(lang)
    chunks = chunk_corpus(content, 700, lang)
    digest = rag_index.corpus_digest(chunks)
    work = workcopy.load(lang)

    def files() -> dict[str, str]:
        roots = [CONTENT / "rag.yaml", CONTENT / "rag_contexts.yaml", CONTENT / "corpus"]
        roots += [CONTENT / "i18n"]
        if config.data_dir().exists():
            roots.append(config.data_dir())
        return snapshot_bytes(*roots)

    before = files()
    assert next(d for d in content.documents if d.id == "projet_orion").active is False
    session.rag_lab_erasure_texts()
    for step, rebuilt in (
        ("start", []),
        ("erase", []),
        ("rebuild", ["graphrag", "dense", "cag"]),
    ):
        ask(session, sentinel_active=True, step=step, rebuilt=rebuilt)
    assert files() == before
    assert rag_index.corpus_digest(chunk_corpus(load_rag_content(lang), 700, lang)) == digest
    assert workcopy.load(lang) == work
    shipped = (CONTENT / "rag.yaml").read_text(encoding="utf-8")
    assert re.search(
        r"id: projet_orion[^\n]*\n[^\n]*\n[^\n]*\n\s+audience: all\n\s+active: false", shipped
    )


# ---------- the data ----------


def load(lang: str) -> dict:
    return yaml.safe_load(config.content_file(erasure.FILE, lang).read_text(encoding="utf-8"))


def holes(value):
    if isinstance(value, dict):
        return {k: holes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [holes(v) for v in value]
    return sorted(re.findall(r"\{(\w+)\}", str(value)))


@pytest.mark.parametrize("lang", ("en", "de"))
def test_the_three_languages_mirror_each_other(lang):
    fr, tr = erasure.load_erasure("fr"), erasure.load_erasure(lang)
    assert holes(tr.texts) == holes(fr.texts)
    texts = {"label_text", "update_text", "unit_text", "measured_on_text", "text", "rebuilt_text"}
    assert [a.model_dump(exclude=texts) for a in tr.architectures] == [
        a.model_dump(exclude=texts) for a in fr.architectures
    ]
    for f, t in zip(fr.places, tr.places, strict=True):
        assert f.model_dump(exclude=texts | {"provenance"}) == t.model_dump(
            exclude=texts | {"provenance"}
        )
        assert f.provenance == t.provenance or f.provenance.kind == t.provenance.kind  # type: ignore[union-attr]
        assert t.label_text != f.label_text
        if f.text:
            assert CODE in (t.text or "") and CODE not in (t.rebuilt_text or "")
    assert (tr.chunk_max_chars, tr.top_k, tr.doc_id, tr.code) == (700, 3, "projet_orion", CODE)


@pytest.mark.parametrize("lang", LANGS)
def test_constructed_places_cite_the_code_and_name_their_story(lang):
    content = erasure.load_erasure(lang)
    assert len(content.architectures) == 11
    constructed = [p for p in content.places if p.provenance]
    assert {p.id for p in constructed} == {
        "raptor_summaries",
        "wiki_pages",
        "cag_cache",
        "long_context_prefix",
    }
    for place in constructed:
        assert place.provenance.kind == "constructed"  # type: ignore[union-attr]
        assert CODE in (place.text or "") and CODE not in (place.rebuilt_text or "")
        assert place.story == STORY_OF[place.architectures[0]]
    for arch in content.architectures:
        assert arch.available == (arch.id in IN_WORKSHOP)
        assert arch.story == (None if arch.available else STORY_OF[arch.id])


def mutate(lang: str, fn) -> dict:
    data = load(lang)
    fn(data)
    return data


def test_invalid_data_is_refused_at_the_load():
    model = erasure.ErasureContent
    place = lambda d, pid: next(p for p in d["places"] if p["id"] == pid)  # noqa: E731
    cases = [
        lambda d: place(d, "raptor_summaries")["provenance"].pop("to_record_with"),
        lambda d: place(d, "raptor_summaries").update(provenance={"kind": "recorded"}),
        lambda d: place(d, "raptor_summaries").update(story=None),
        lambda d: place(d, "raptor_summaries").update(story=15),
        lambda d: place(d, "raptor_summaries").update(rebuilt_text=f"avec {CODE}"),
        lambda d: place(d, "raptor_summaries").update(text="sans le code"),
        lambda d: place(d, "chunks").update(erase_mode="rebuild"),
        lambda d: place(d, "chunks").update(text="x"),
        lambda d: d.update(unknown=1),
        lambda d: d["architectures"].pop(),
        lambda d: d["texts"].pop("guard_text"),
        lambda d: d["texts"]["status"].pop("erased_illustrative"),
        lambda d: d["texts"]["provenance"].pop("constructed_text"),
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            model.model_validate(mutate("fr", case))


# ---------- the code: no model, only the permitted imports ----------


def test_the_module_imports_only_the_permitted_names():
    tree = ast.parse((config.repo_root() / "src/wavestack/rag/erasure.py").read_text("utf-8"))
    found = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("wavestack")
        for alias in node.names
    }
    assert found == {
        ("wavestack", "config"),
        ("wavestack.messages", "msg"),
        ("wavestack.rag.attack", "Provenance"),
        ("wavestack.rag.attack", "provenance_text"),
        ("wavestack.rag.contexts", "heuristic_entries"),
        ("wavestack.rag.pageindex", "build_tree"),  # V1.2 story 11: the rule's tree, pure
        ("wavestack.rag.graph", "build_graph"),  # V1.2 story 13: the rule's graph, pure
        ("wavestack.rag.contexts", "load_book"),
        ("wavestack.rag.corpus", "Chunk"),
        ("wavestack.rag.corpus", "DocText"),
        ("wavestack.rag.corpus", "RagContent"),
        ("wavestack.rag.corpus", "chunk_documents"),
        ("wavestack.rag.corpus", "load_rag_content"),
        ("wavestack.rag.corpus", "read_documents"),
        ("wavestack.rag.index", "passage_text"),
        ("wavestack.rag.lab", "bm25"),
        ("wavestack.rag.lab", "bm25_terms"),
        ("wavestack.rag.lab", "lexical_index"),
    }


def test_no_model_factory_is_called():
    def boom(*args, **kwargs):
        raise AssertionError("a model was opened")

    session = make_session()
    session._engine_factory = boom  # type: ignore[assignment]
    session._embedder_factory = boom  # type: ignore[assignment]
    session._reranker_factory = boom  # type: ignore[assignment]
    session.rag_lab_erasure_texts()
    body = ask(session, sentinel_active=True, step="rebuild", rebuilt=["raptor"])
    assert body["step"] == "rebuild"


# ---------- the endpoints ----------


def client_for(session: AppSession) -> TestClient:
    app = create_app(
        DiagnosticSession(session.cfg, port=8421), port=8421, version="t", app_session=session
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


def keys_of(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys_of(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys_of(v)}
    return set()


def test_endpoints_shapes_and_422():
    client = client_for(make_session())
    got = client.get("/api/rag_lab/erasure")
    assert got.status_code == 200
    body = got.json()
    assert body["defaults"] == {"sentinel_active": False, "step": "idle", "rebuilt": []}
    assert body["code"] == CODE and len(body["architectures"]) == 11
    assert "places" not in body  # no computation
    posted = client.post(
        "/api/rag_lab/erasure",
        headers=HEADERS,
        json={"sentinel_active": True, "step": "rebuild", "rebuilt": ["graphrag"]},
    )
    assert posted.status_code == 200
    answer = posted.json()
    assert answer["rebuilt"] == ["graphrag"]
    for wrong in (
        {"extra": 1},
        {"step": "explode"},
        {"sentinel_active": "maybe"},
        {"sentinel_active": True, "step": "rebuild", "rebuilt": ["nope"]},
        {"sentinel_active": True, "step": "erase", "rebuilt": ["graphrag"]},
        {"sentinel_active": True, "step": "start", "rebuilt": ["graphrag"]},
    ):
        assert (
            client.post("/api/rag_lab/erasure", json=wrong, headers=HEADERS).status_code == 422
        ), wrong
    for shown in (body, answer):
        assert not [k for k in keys_of(shown) if AVERAGE.search(k)]


def test_the_card_is_played_without_a_model_an_index_or_a_key():
    client = client_for(make_session())
    for step in ("idle", "start", "erase", "rebuild"):
        response = client.post(
            "/api/rag_lab/erasure",
            headers=HEADERS,
            json={
                "sentinel_active": True,
                "step": step,
                "rebuilt": ["graphrag"] if step == "rebuild" else [],
            },
        )
        assert response.status_code == 200


def test_the_page_script_has_no_colour_and_no_inner_html():
    code = (config.repo_root() / "src/wavestack/web/static/rag-attack-erasure.js").read_text(
        "utf-8"
    )
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    assert 'registerTab("attack_erasure"' in code and 'registerTab("attack"' not in code
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", code)
    css = (config.repo_root() / "src/wavestack/web/static/rag.css").read_text("utf-8")
    block = css.split("V1.2 story 18")[1]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(", block)
    html = (config.repo_root() / "src/wavestack/web/static/rag.html").read_text("utf-8")
    panel = html.split('id="rag-panel-attack"')[1].split('id="rag-panel-sheets"')[0]
    assert "rag-soon" in panel and "rag-atk-soon" not in panel
    assert "rag-attack-erasure.js" in html and "rag-attack-access.js" in html
