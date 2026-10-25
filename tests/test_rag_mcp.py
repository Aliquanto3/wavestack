"""V1.2 story 20 (CAP-18): the RAG workshop's chain exposed as a read-only MCP server.

A real MCP client of the SDK (`mcp.Client` on `streamable_http_client`) talks to the real
application through `httpx2.ASGITransport`: no port opened, no network, no model. The brick's
index is built in a temporary folder by the real code of `rag/` and `FakeEmbedder` (the
deterministic double at the model's boundary, `test_rag`); the reranker is `FakeReranker`,
the generative model `FakeEngine` (its calls counted: the server never generates).
"""

from __future__ import annotations

import asyncio
import string
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2
import pytest
import yaml
from fake_embedder import MODEL_ID, FakeEmbedder
from fake_engine import FakeEngine
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation
from test_rag import build
from test_rag_lab import ended, ready, wait_idle
from test_rag_lab import run as page_run
from test_rag_rerank import Rerankers

from wavestack import config
from wavestack.mcp import architecture_server, policy
from wavestack.rag import exposed, workcopy
from wavestack.rag import index as rag_index
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import load_rag_content, load_rag_questions
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

PORT = 8425
BASE = f"http://127.0.0.1:{PORT}"
URL = f"{BASE}{architecture_server.PATH}"
PAGE = {"Origin": BASE}
CLIENT = Implementation(name="client-de-test", version="1.0")
SEARCH = "workshop__search_documents"
DESCRIBE = "workshop__describe_architecture"
ACCEPT = {"Accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "brut", "version": "1"},
    },
}


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class App:
    """The application and its session, on the running loop (the ASGITransport plays no
    `lifespan`: `attach_loop` is called by `serve`)."""

    def __init__(self, session: AppSession) -> None:
        self.session = session
        self.app = create_app(
            DiagnosticSession(session.cfg, port=PORT), port=PORT, version="t", app_session=session
        )
        self.http = self.raw()

    def raw(self, headers: dict[str, str] | None = None) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=self.app),
            base_url=BASE,
            headers=headers or {},
            timeout=30,
        )

    async def start(self, pipeline: rag_lab.Pipeline | None = None) -> httpx2.Response:
        body = {"pipelines": [pipeline.model_dump()]} if pipeline is not None else {}
        return await self.http.post("/api/intentions/rag_mcp_start", json=body, headers=PAGE)

    async def stop(self) -> httpx2.Response:
        return await self.http.post("/api/intentions/rag_mcp_stop", json={}, headers=PAGE)

    async def state(self) -> dict[str, Any]:
        return (await self.http.get("/api/rag_lab/mcp")).json()

    @asynccontextmanager
    async def client(self, token: str | None = None) -> AsyncIterator[Client]:
        token = token or (await self.state())["token"]
        async with self.raw({"Authorization": f"Bearer {token}"}) as http:
            transport = streamable_http_client(URL, http_client=http)
            async with Client(transport, mode="legacy", cache=None, client_info=CLIENT) as client:
                yield client


def serve(session: AppSession, scenario) -> Any:  # noqa: ANN001
    """`scenario(app)` on a fresh loop, the session attached to it, the server closed after."""

    async def main() -> Any:
        app = App(session)
        session.attach_loop(asyncio.get_running_loop())
        try:
            return await scenario(app)
        finally:
            await session.aclose_mcp()
            await app.http.aclose()

    return asyncio.run(main())


def catalog_of(session: AppSession) -> rag_lab.Catalog:
    return session._rag_lab_catalog(rag_lab.load_lab_content())


def preset(session: AppSession, name: str) -> rag_lab.Pipeline:
    return catalog_of(session).preset_pipeline(name)


def lexical(session: AppSession) -> rag_lab.Pipeline:
    """The shipped head, BM25 alone, the shipped tail."""
    chain = preset(session, "dense")
    chain.stages = [
        rag_lab.Stage(id=s.id, kind="lexical_search", option="bm25", params={})
        if s.kind == "vector_search"
        else s
        for s in chain.stages
    ]
    return chain


def security_entries(session: AppSession, *names: str) -> list[dict[str, Any]]:
    names = names or (SEARCH, DESCRIBE)
    return [e for e in session.security_journal_entries() if e["name"] in names]


def tree(folder: Path) -> dict[str, tuple[int, int]]:
    return {
        p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


async def until(predicate, timeout: float = 10.0) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition never met"
        await asyncio.sleep(0.01)


# ---------- the rule of exposure (D12) ----------


def _all_available(catalog: rag_lab.Catalog) -> rag_lab.Catalog:
    """Every option chosen as available: the rule is tested on the chain's structure alone."""
    for state in catalog.options.values():
        state.available = True
    return catalog


def test_the_presets_are_classified_by_their_stages(index):
    session, _ = ready(index)
    catalog = _all_available(catalog_of(session))
    texts = exposed.load_texts("fr")
    shipped = session.cfg.rag_chunk_max_chars
    for name in rag_lab.PRESETS:  # walked, never enumerated: story 11's presets included
        chain = catalog.preset_pipeline(name)
        found = exposed.refusal(chain, catalog, shipped, texts)
        context = chain.find("context")
        assert context is not None
        if name in ("dense", "hybrid", "rerank"):
            assert found is None, (name, found)
        elif not rag_lab.PRESETS[name]:
            expected = (
                "whole_corpus" if context.option in rag_lab.CORPUS_OPTIONS else "searches_itself"
            )
            assert found is not None and found.reason == expected, (name, found)
        else:
            assert found is not None or set(dict(rag_lab.PRESETS[name])) <= set(
                exposed.EXPOSABLE_SEGMENT
            ), name
    for name in ("long_context", "cag"):
        found = exposed.refusal(catalog.preset_pipeline(name), catalog, shipped, texts)
        assert found is not None and found.reason == "whole_corpus"
    session.close()


def _forged(catalog: rag_lab.Catalog, kind: str, option: str) -> rag_lab.Pipeline:
    chain = catalog.preset_pipeline("dense")
    if kind == "query":
        at = next(i for i, s in enumerate(chain.stages) if s.kind == "vector_search")
        chain.stages.insert(at, rag_lab.Stage(id="q1", kind="query", option=option))
        return chain
    for stage in chain.stages:
        if stage.kind == kind:
            stage.option = option
            if kind == "vector_store" or option != "paragraphs":
                stage.params = {k: v for k, v in stage.params.items() if k == "chunk_max_chars"}
    return chain


@pytest.mark.parametrize(
    ("kind", "option", "reason"),
    [
        ("query", "rewrite", "model_stage"),
        ("query", "hyde", "model_stage"),
        ("chunking", "semantic", "head"),
        ("vector_store", "faiss", "head"),
        ("vector_store", "memory", "head"),
        ("embedding", "fastembed", "head"),
    ],
)
def test_a_forged_chain_is_refused_with_its_reason(index, kind, option, reason):
    session, _ = ready(index)
    catalog = _all_available(catalog_of(session))
    chain = _forged(catalog, kind, option)
    assert rag_lab.validate_pipeline(chain, catalog) is None
    for lang in config.LANGUAGES:
        found = exposed.refusal(
            chain, catalog, session.cfg.rag_chunk_max_chars, exposed.load_texts(lang)
        )
        assert found is not None and found.reason == reason, found
        assert found.text
        if reason == "model_stage":
            assert catalog.content.stages["query"].label_text in found.text
    session.close()


def test_another_chunk_size_is_not_the_bricks_head(index):
    session, _ = ready(index)
    catalog = _all_available(catalog_of(session))
    chain = catalog.preset_pipeline("hybrid")
    chunking = chain.find("chunking")
    assert chunking is not None
    chunking.params = {"chunk_max_chars": 500}
    found = exposed.refusal(chain, catalog, session.cfg.rag_chunk_max_chars, exposed.load_texts())
    assert found is not None and found.reason == "head"
    session.close()


def test_the_reasons_exist_in_every_language():
    french = exposed.load_texts("fr").reasons.model_dump()
    assert set(french) == set(exposed.REASONS)
    for lang in config.LANGUAGES:
        reasons = exposed.load_texts(lang).reasons.model_dump()
        assert set(reasons) == set(french)
        for key, text in reasons.items():
            assert exposed.placeholders(text) == exposed.placeholders(french[key]), (lang, key)
            if lang != "fr":
                assert text != french[key], (lang, key)


def test_a_refused_chain_does_not_start(index):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        refused = await app.start(preset(session, "cag"))
        assert refused.status_code == 409 and refused.json()["detail"]
        assert (await app.state())["running"] is False

    serve(session, scenario)
    session.close()


# ---------- the client of CAP-18 (criteria 1, 2, 3) ----------


def test_a_client_lists_the_tool_and_receives_cited_passages(index):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        started = await app.start(preset(session, "hybrid"))
        assert started.status_code == 200, started.text
        body = started.json()
        assert body["running"] is True and body["token"] is None  # the GET renders it alone
        assert body["url"] == URL
        async with app.client() as client:
            listed = await client.list_tools()
            assert sorted(t.name for t in listed.tools) == sorted(architecture_server.TOOLS)
            search = next(t for t in listed.tools if t.name == "search_documents")
            assert set(search.input_schema["properties"]) == {"question", "top_k"}
            for tool in listed.tools:
                hints = tool.annotations
                assert hints.read_only_hint and hints.idempotent_hint
                assert hints.destructive_hint is False and hints.open_world_hint is False
            found = await client.call_tool(
                "search_documents", {"question": "congés payés", "top_k": 3}
            )
            assert not found.is_error, found.content
            passages = found.structured_content["passages"]
            assert 1 <= len(passages) <= 3
            for p in passages:
                assert {"doc_id", "title_text", "position", "text", "score", "citation"} <= set(p)
                assert p["position"] >= 1 and p["doc_id"] in p["citation"]
            assert passages[0]["title_text"] in found.content[0].text
            described = await client.call_tool("describe_architecture", {})
            assert described.structured_content["architecture"] == "hybrid"

    serve(session, scenario)
    wait_idle(session)
    session.close()


@pytest.mark.parametrize("which", ["lexical", "hybrid"])
def test_the_passages_are_the_last_stage_s_list_without_hr(index, which):
    engine = FakeEngine(output="Jamais appelé.")
    session, _ = ready(index, engine=engine)
    chain = lexical(session) if which == "lexical" else preset(session, "hybrid")
    question = load_rag_questions()[0].question_text
    events = page_run(session, question, chain)
    last = exposed.segment_of(chain)[-1].kind
    items = ended(events, last)["items"]
    hr = exposed.hr_documents(load_rag_content())
    expected = [(i["doc_id"], i["chunk_id"], i["score"]) for i in items if i["doc_id"] not in hr]
    calls = len(engine.calls)

    async def scenario(app: App) -> None:
        assert (await app.start(chain)).status_code == 200
        mark = get_journal().last_seq()
        async with app.client() as client:
            found = await client.call_tool("search_documents", {"question": question, "top_k": 10})
        passages = found.structured_content["passages"]
        assert [(p["doc_id"], p["chunk_id"], p["score"]) for p in passages] == expected[:10]
        assert [p["rank"] for p in passages] == list(range(1, len(passages) + 1))
        emitted = [e.kind for e in get_journal().events_since(mark)]
        assert not [k for k in emitted if k.startswith("rag_lab")], emitted  # nothing to the page

    serve(session, scenario)
    wait_idle(session)
    assert len(engine.calls) == calls  # no generation
    generation = ended(events, "generation")
    assert generation["status"] in ("ok", "skipped")  # the page's own run, for reference
    session.close()


def test_the_chain_is_frozen_at_the_start(index):
    session, _ = ready(index)
    loop_chain = preset(session, "hybrid")

    async def scenario(app: App) -> None:
        session.rag_mcp_start(loop_chain)
        loop_chain.stages = preset(session, "dense").stages  # the page's chain changed
        async with app.client() as client:
            described = await client.call_tool("describe_architecture", {})
            assert described.structured_content["architecture"] == "hybrid"
            found = await client.call_tool("search_documents", {"question": "télétravail"})
            assert found.structured_content["architecture"] == "hybrid"
        assert (await app.state())["chain"]["architecture"] == "hybrid"
        await app.stop()
        session.rag_mcp_start(preset(session, "dense"))
        async with app.client() as client:
            described = await client.call_tool("describe_architecture", {})
            assert described.structured_content["architecture"] == "dense"

    serve(session, scenario)
    wait_idle(session)
    session.close()


# ---------- confinement (criteria 5, 6) ----------


def _hr_passage_text() -> str:
    content = load_rag_content()
    doc = next(d for d in content.documents if d.audience == "hr")
    text = config.content_file(doc.file).read_text(encoding="utf-8")
    return next(p for p in text.split("\n\n") if len(p) > 80)[:400]


def test_no_question_returns_an_hr_passage(index):
    session, _ = ready(index)
    chain = preset(session, "hybrid")
    hr = exposed.hr_documents(load_rag_content())
    global_rh = next(q for q in load_rag_questions() if q.id == "q_global_rh").question_text
    exact = _hr_passage_text()
    raw = ended(page_run(session, exact, chain), "fusion")["items"]
    assert any(i["doc_id"] in hr for i in raw)  # the filter is exercised

    async def scenario(app: App) -> None:
        assert (await app.start(chain)).status_code == 200
        async with app.client() as client:
            for question in (global_rh, exact):
                found = await client.call_tool(
                    "search_documents", {"question": question, "top_k": 10}
                )
                passages = found.structured_content["passages"]
                assert passages and not [p for p in passages if p["doc_id"] in hr]
            assert found.structured_content["removed_hr"] >= 1

    serve(session, scenario)
    wait_idle(session)
    session.close()


def test_the_work_copy_the_trap_and_the_sentinel_never_reach_the_client(index):
    session, _ = ready(index)
    content = load_rag_content()
    planted = {}
    for doc_id in ("faq_mots_de_passe", "projet_orion"):
        doc = next(d for d in content.documents if d.id == doc_id)
        text = config.content_file(doc.file).read_text(encoding="utf-8")
        planted[f"copie_{doc_id}"] = workcopy.WorkDoc(title_text=doc.title_text, text=text)
    sentinel = planted["copie_projet_orion"].text.split("\n\n")[-1][:300]

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "hybrid"))).status_code == 200
        workcopy.save(workcopy.WorkCopy(added=planted), session.language)  # after the start
        async with app.client() as client:
            found = await client.call_tool("search_documents", {"question": sentinel, "top_k": 10})
        ids = {p["doc_id"] for p in found.structured_content["passages"]}
        assert not ids & {"faq_mots_de_passe", "projet_orion", *planted}

    serve(session, scenario)
    wait_idle(session)
    session.close()


def test_a_changed_corpus_refuses_the_start(index):
    session, _ = ready(index)
    workcopy.save(workcopy.WorkCopy(deleted=["teletravail"]), session.language)

    async def scenario(app: App) -> None:
        refused = await app.start(preset(session, "dense"))
        assert refused.status_code == 409 and "copie de travail" in refused.json()["detail"]

    serve(session, scenario)
    session.close()


def test_a_call_writes_nothing(index):
    session, _ = ready(index)
    data = config.data_dir()

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "hybrid"))).status_code == 200
        before, brick = tree(data), tree(index.parent)
        async with app.client() as client:
            for question in ("congés payés", "mot de passe oublié"):
                found = await client.call_tool("search_documents", {"question": question})
                assert not found.is_error
        assert tree(data) == before
        assert tree(index.parent) == brick
        assert not config.rag_lab_dir().exists() or tree(config.rag_lab_dir()) == {
            k.removeprefix("rag_lab/"): v for k, v in before.items() if k.startswith("rag_lab/")
        }

    serve(session, scenario)
    wait_idle(session)
    session.close()


def test_without_the_index_nothing_starts_nor_is_built(index):
    session, _ = ready(index)
    hidden = index.with_name("ailleurs.sqlite")

    async def scenario(app: App) -> None:
        index.rename(hidden)
        refused = await app.start(preset(session, "dense"))
        assert refused.status_code == 409 and "construisez l'index" in refused.json()["detail"]
        hidden.rename(index)
        assert (await app.start(preset(session, "dense"))).status_code == 200
        index.rename(hidden)  # gone after the start
        before = tree(config.data_dir())
        async with app.client() as client:
            found = await client.call_tool("search_documents", {"question": "congés"})
        assert found.is_error and "construisez l'index" in found.content[0].text
        assert tree(config.data_dir()) == before
        assert not index.exists()
        assert [e["decision"] for e in security_entries(session, SEARCH)] == ["cancelled"]

    serve(session, scenario)
    wait_idle(session)
    session.close()


# ---------- the tool's bounds (criterion 7) ----------


@pytest.mark.parametrize(
    "arguments",
    [
        {"question": "congés", "top_k": 0},
        {"question": "congés", "top_k": 11},
        {"question": "congés", "top_k": 50},
        {"question": ""},
        {"question": "x" * (rag_lab.QUESTION_MAX + 1)},
    ],
)
def test_an_input_out_of_bounds_is_refused_before_any_computation(index, arguments):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "dense"))).status_code == 200
        async with app.client() as client:
            found = await client.call_tool("search_documents", arguments)
        assert found.is_error
        assert security_entries(session) == []  # the session's function never called
        assert session.state == "idle"

    serve(session, scenario)
    session.close()


# ---------- access (criterion 8) ----------


def test_the_guard_of_the_endpoint(index):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        stopped = await app.http.post(URL, json=INITIALIZE, headers=ACCEPT)
        assert stopped.status_code == 404
        assert (await app.start(preset(session, "dense"))).status_code == 200
        token = (await app.state())["token"]
        bearer = {"Authorization": f"Bearer {token}"} | ACCEPT
        assert (await app.http.post(URL, json=INITIALIZE, headers=ACCEPT)).status_code == 401
        wrong = {"Authorization": "Bearer faux"} | ACCEPT
        assert (await app.http.post(URL, json=INITIALIZE, headers=wrong)).status_code == 401
        evil = bearer | {"Origin": "http://evil.example"}
        assert (await app.http.post(URL, json=INITIALIZE, headers=evil)).status_code == 403
        host = bearer | {"Host": "evil.example"}
        assert (await app.http.post(URL, json=INITIALIZE, headers=host)).status_code == 400
        served = await app.http.post(URL, json=INITIALIZE, headers=bearer)  # no `Origin`
        assert served.status_code == 200, served.text
        assert served.json()["result"]["serverInfo"]["name"] == architecture_server.SERVER_NAME
        page = await app.http.post(URL, json=INITIALIZE, headers=bearer | PAGE)
        assert page.status_code == 200
        # The exception holds for the endpoint alone.
        other = await app.http.post("/api/intentions/rag_mcp_stop", json={})
        assert other.status_code == 403
        assert (await app.state())["running"] is True
        await app.stop()
        assert (await app.http.post(URL, json=INITIALIZE, headers=bearer)).status_code == 404
        assert (await app.start(preset(session, "dense"))).status_code == 200
        again = (await app.state())["token"]
        assert again != token
        old = {"Authorization": f"Bearer {token}"} | ACCEPT
        assert (await app.http.post(URL, json=INITIALIZE, headers=old)).status_code == 401
        return token, again

    tokens = serve(session, scenario)
    wait_idle(session)
    # Never written: neither the journal, nor the security journal, nor any file.
    events = [e.model_dump_json() for e in get_journal().events_since(0)]
    entries = repr(session.security_journal_entries())
    for token in tokens:
        assert not [e for e in events if token in e]
        assert token not in entries
        for root in (config.data_dir(), index.parent):
            for path in root.rglob("*"):
                if path.is_file():
                    assert token.encode() not in path.read_bytes(), path
    session.close()


def test_two_starts_give_the_same_state_and_token(index):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "dense"))).status_code == 200
        first = await app.state()
        again = await app.start(preset(session, "hybrid"))
        assert again.status_code == 200
        second = await app.state()
        assert second["token"] == first["token"] and second["chain"] == first["chain"]
        assert (await app.stop()).json()["running"] is False
        assert (await app.stop()).json()["running"] is False

    serve(session, scenario)
    session.close()


# ---------- policy and journal (criteria 9, 10) ----------


def test_the_tools_are_low_risk_allowed_and_the_matrix_unchanged():
    for name in (SEARCH, DESCRIBE):
        assert policy.ToolPolicy.risk_of(name) == "low"
        assert policy.ToolPolicy.default_rule(name) == "allow"
    assert not [t for _, tools, _ in policy.MATRIX_ROWS for t in tools if t.startswith("workshop")]


@pytest.mark.parametrize("rule", ["deny", "ask"])
def test_a_tool_not_allowed_is_hidden_and_refused(index, rule):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "dense"))).status_code == 200
        state = await app.state()
        assert [(t["risk"], t["rule"]) for t in state["tools"]] == [("low", "allow")] * 2
        session.set_mcp_tool_rule(SEARCH, rule)
        async with app.client() as client:
            listed = await client.list_tools()
            assert [t.name for t in listed.tools] == ["describe_architecture"]
            found = await client.call_tool("search_documents", {"question": "congés"})
            assert found.is_error
        entries = security_entries(session, SEARCH)
        assert [e["decision"] for e in entries] == ["deny"]
        assert "client-de-test" in entries[0]["reason_text"]
        assert session.state == "idle"
        tools = {t["name"]: t for t in (await app.state())["tools"]}
        assert tools["search_documents"]["announced"] is False

    serve(session, scenario)
    session.close()


def test_each_call_is_journaled_without_its_texts(index):
    gate = threading.Event()
    session, _ = ready(index, rerankers=Rerankers(gate=gate))
    question = "Combien de jours de congés payés ?"

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "dense"))).status_code == 200
        async with app.client() as client:
            found = await client.call_tool("search_documents", {"question": question})
            assert not found.is_error
            excerpt = found.structured_content["passages"][0]["text"][:40]
            await client.call_tool("describe_architecture", {})
            session.run_rag_lab(question, preset(session, "rerank"))  # the page busy
            await until(lambda: session.state == "rag_lab")
            busy = await client.call_tool("search_documents", {"question": question})
            assert busy.is_error and "occupé" in busy.content[0].text
            gate.set()
            await until(lambda: session.state == "idle")
            session.set_mcp_tool_rule(DESCRIBE, "deny")
            await client.call_tool("describe_architecture", {})
        token = (await app.state())["token"]
        return excerpt, token

    excerpt, token = serve(session, scenario)
    wait_idle(session)
    entries = security_entries(session)
    assert [(e["name"], e["decision"]) for e in entries] == [
        (SEARCH, "allow"),
        (DESCRIBE, "allow"),
        (SEARCH, "cancelled"),
        (DESCRIBE, "deny"),
    ]
    for entry in entries:
        assert entry["source"] == "mcp_tool"
        assert "client-de-test" in entry["reason_text"]
        for secret in (question, excerpt, token):
            assert secret not in entry["reason_text"]
    assert " ms" in entries[0]["reason_text"] and "passage" in entries[0]["reason_text"]
    session.close()


# ---------- concurrency (criterion 11) ----------


def test_a_call_holds_the_workshop_and_a_second_one_is_refused(index):
    gate = threading.Event()
    session, _ = ready(index, rerankers=Rerankers(gate=gate))

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "rerank"))).status_code == 200
        async with app.client() as first, app.client() as second:
            call = asyncio.create_task(
                first.call_tool("search_documents", {"question": "télétravail"})
            )
            await until(lambda: session.state == "rag_lab")
            with pytest.raises(SendRefused) as refused:
                session.run_rag_lab("télétravail", preset(session, "dense"))
            assert "client MCP" in str(refused.value.reason_text)
            started = time.monotonic()
            other = await second.call_tool("search_documents", {"question": "congés"})
            assert other.is_error and time.monotonic() - started < 3  # no queue
            gate.set()
            found = await call
            assert not found.is_error, found.content
        await until(lambda: session.state == "idle")

    serve(session, scenario)
    session.close()


def test_a_call_past_its_delay_is_cancelled(index):
    gate = threading.Event()
    session, _ = ready(index, rerankers=Rerankers(gate=gate))
    session.RAG_MCP_TIMEOUT_S = 0.3  # injected: 30 s in production

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "rerank"))).status_code == 200
        async with app.client() as client:
            found = await client.call_tool("search_documents", {"question": "télétravail"})
            assert found.is_error and "0,3" in found.content[0].text
            assert session.state == "rag_lab"  # until the run meets its checkpoint
            gate.set()
            await until(lambda: session.state == "idle")
        assert [e["decision"] for e in security_entries(session, SEARCH)] == ["cancelled"]

    serve(session, scenario)
    session.close()


# ---------- cohabitation (criterion 12) ----------


def test_the_exposed_server_is_none_of_the_managed_ones(index):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        before = (
            sorted(session._mcp_servers),
            (await app.http.get("/api/mcp_lab")).json(),
            (await app.http.get("/api/state")).json().get("bricks"),
        )
        assert (await app.start(preset(session, "dense"))).status_code == 200
        after = (
            sorted(session._mcp_servers),
            (await app.http.get("/api/mcp_lab")).json(),
            (await app.http.get("/api/state")).json().get("bricks"),
        )
        assert after == before
        assert URL not in session.cfg.mcp_urls.values()
        assert not [u for u in session.cfg.mcp_urls.values() if architecture_server.PATH in u]

    serve(session, scenario)
    session.close()


# ---------- languages and life cycle (criterion 13) ----------


def _leaves(node: Any, path: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        return {
            k: v for key, value in node.items() for k, v in _leaves(value, f"{path}{key}.").items()
        }
    if isinstance(node, list):
        return {f"{path}#{len(node)}": None} | {
            k: v for i, value in enumerate(node) for k, v in _leaves(value, f"{path}{i}.").items()
        }
    return {path.rstrip("."): node}


def _fields(text: Any) -> set[str]:
    if not isinstance(text, str):
        return set()
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_the_texts_have_the_same_keys_bounds_and_placeholders_in_every_language():
    def read(lang: str) -> dict[str, Any]:
        path = config.content_dir() / (
            exposed.FILE if lang == "fr" else f"i18n/{lang}/{exposed.FILE}"
        )
        assert path.is_file(), path  # never a silent fallback on French
        return _leaves(yaml.safe_load(path.read_text(encoding="utf-8")))

    french = read("fr")
    for lang in config.LANGUAGES:
        exposed.load_texts(lang)  # valid
        leaves = read(lang)
        assert set(leaves) == set(french), lang
        for key, value in leaves.items():
            assert _fields(value) == _fields(french[key]), (lang, key)
            words = string.Formatter().parse(value) if isinstance(value, str) else ()
            literal = "".join(text for text, *_ in words)
            if lang != "fr" and sum(c.isalpha() for c in literal) > 12:
                assert value != french[key], (lang, key)


def test_the_tools_speak_the_language_of_the_start_and_a_change_stops_the_server(index):
    session, _ = ready(index)

    english_index = session.cfg.rag_index_path("en")
    rag_index.build_index(
        load_rag_content("en"),
        FakeEmbedder(model_id=MODEL_ID),
        english_index,
        chunk_max_chars=700,
        lang="en",
    )

    async def scenario(app: App) -> None:
        session.set_language("en")
        started = await app.start(preset(session, "dense"))
        assert started.status_code == 200, started.text
        english = exposed.load_texts("en").tools.search_documents.description_text
        async with app.client() as client:
            listed = await client.list_tools()
        search = next(t for t in listed.tools if t.name == "search_documents")
        assert search.description == english
        session.set_language("de")
        state = await app.state()
        assert state["running"] is False and state["note_text"]
        assert state["texts"]["state_off_text"] == exposed.load_texts("de").card.state_off_text
        token = {"Authorization": "Bearer x"} | ACCEPT
        assert (await app.http.post(URL, json=INITIALIZE, headers=token)).status_code == 404

    serve(session, scenario)
    session.close()


def test_closing_the_session_stops_the_server(index):
    session, _ = ready(index)

    async def scenario(app: App) -> None:
        assert (await app.start(preset(session, "dense"))).status_code == 200
        token = (await app.state())["token"]
        await asyncio.to_thread(session.close)
        bearer = {"Authorization": f"Bearer {token}"} | ACCEPT
        assert (await app.http.post(URL, json=INITIALIZE, headers=bearer)).status_code == 404

    serve(session, scenario)


def test_without_a_loop_the_start_is_refused(index):
    session, _ = ready(index)
    App(session)  # the endpoint mounted, no loop attached
    with pytest.raises(SendRefused):
        session.rag_mcp_start(preset(session, "dense"))
    session.close()


# ---------- the card (criterion 14) ----------

STATIC = Path(__file__).resolve().parents[1] / "src" / "wavestack" / "web" / "static"


def test_the_card_is_in_the_build_tab_and_draws_text_only():
    html = (STATIC / "rag.html").read_text(encoding="utf-8")
    build_tab = html.split('id="rag-panel-build"')[1].split('id="rag-panel-compare"')[0]
    assert 'id="rag-mcp-card"' in build_tab
    assert '<script type="module" src="/static/rag-mcp.js"></script>' in html
    code = (STATIC / "rag-mcp.js").read_text(encoding="utf-8")
    assert "innerHTML" not in code and "insertAdjacentHTML" not in code
    assert "mcp.policy.risk." in code and "status-chip" in code
    assert "/api/rag_lab/mcp" in code
    css = (STATIC / "rag.css").read_text(encoding="utf-8")
    block = css.split("/* V1.2 story 20")[1]
    assert block.count("{") == block.count("}")
    assert "#" not in block.split("*/", 1)[1].replace("#rag-mcp", "")  # tokens, no colour
