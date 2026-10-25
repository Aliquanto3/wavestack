"""V1.2 story 16 (CAP-12): the workshop's run as a tree of steps (step, sub-step, model call),
`parent_step` set by the chain's ids, and its OTLP export to the GenAI conventions behind the
`otel` extra, through the factory (AD-15). Nothing leaves without `[otel] endpoint`.

The collector is a fake OTLP/HTTP server on the loopback (a free port, no fixed one); the
model is `FakeEngine`. The export's tests need the extra (`uv sync --extra otel`): skipped
without it, the tree's and the refusals' run everywhere.
"""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_bricks import HEADERS
from test_rag import build
from test_rag_lab import QUESTION, _client, run, run_status, wait_idle
from test_rag_lab_generation import ANSWER, GENERATION, ready

from wavestack import config
from wavestack.rag import lab as rag_lab
from wavestack.session.app_session import SendRefused
from wavestack.trace import otel as trace_otel
from wavestack.trace import tree as trace_tree
from wavestack.trace.journal import get_journal

SECRET = "sk-or-v1-NE-DOIT-JAMAIS-SORTIR"
AUTH = "Basic dGVzdDp0ZXN0"


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


class Collector:
    """A fake OTLP/HTTP collector on 127.0.0.1, port chosen by the system: it keeps each
    request's path, headers and body and answers 200 (an empty `ExportTraceServiceResponse`)."""

    def __init__(self, status: int = 200) -> None:
        self.requests: list[tuple[str, dict[str, str], bytes]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server's name
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                owner.requests.append((self.path, dict(self.headers.items()), body))
                self.send_response(status)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> Collector:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()


def otel_needed() -> None:
    pytest.importorskip("opentelemetry.sdk.trace")
    pytest.importorskip("opentelemetry.exporter.otlp.proto.common")


def decoded(body: bytes) -> list:
    """The spans of an `ExportTraceServiceRequest`, with their attributes as a dict."""
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    request = ExportTraceServiceRequest()
    request.ParseFromString(body)
    spans = []
    for resource in request.resource_spans:
        for scope in resource.scope_spans:
            spans.extend(scope.spans)
    return spans


def attrs(span) -> dict:  # noqa: ANN001
    out = {}
    for kv in span.attributes:
        value = kv.value
        kind = value.WhichOneof("value")
        if kind == "array_value":
            out[kv.key] = [v.string_value for v in value.array_value.values]
        else:
            out[kv.key] = getattr(value, kind)
    return out


def nodes(tree: dict) -> int:
    return 1 + sum(nodes(c) for c in tree["children"])


def last_tree(events: list) -> dict:
    return next(e.payload for e in events if e.kind == "rag_lab_run_ended")["steps"]


# ---------- the tree and `parent_step` ----------


def test_parent_step_reads_the_chain_s_ids():
    assert rag_lab.parent_step("lab1.s3") == "lab1"
    assert rag_lab.parent_step("lab1.s3.index") == "lab1.s3"
    assert rag_lab.parent_step("upd2.s1.extra.deep") == "upd2.s1.extra"
    for outside in ("lab1", "rag_lab", "rag_lab.cag", "judge3", "", None):
        assert rag_lab.parent_step(outside) is None


def test_a_run_is_a_tree_of_stages_and_model_calls(index):
    session = ready(index)
    events = run(session)
    assert run_status(events) == "ok"
    # `parent_step`: a stage is the run's, a model call its stage's (traced on its step).
    stage_events = [e for e in events if e.kind.startswith("rag_lab_stage_")]
    assert all(e.parent_step == rag_lab.parent_step(e.step_id) for e in stage_events)
    assert {e.parent_step for e in stage_events if e.step_id == GENERATION} == {"lab1"}
    calls = [e for e in events if e.kind.startswith("model_call")]
    assert calls and {(e.step_id, e.parent_step) for e in calls} == {(GENERATION, GENERATION)}
    run_events = [e for e in events if e.kind in ("rag_lab_run_started", "rag_lab_run_ended")]
    assert {e.parent_step for e in run_events} == {None}
    tree = last_tree(events)
    assert (tree["id"], tree["kind"], tree["status"]) == ("lab1", "run", "ok")
    assert tree["duration_ms"] is not None and tree["ended_at"] is not None
    stages = [c for c in tree["children"] if c["kind"] == "stage"]
    started = next(e.payload for e in events if e.kind == "rag_lab_run_started")["stages"]
    assert [s["name"] for s in stages] == [s["label_text"] for s in started]
    generation = next(s for s in stages if s["id"] == GENERATION)
    (call,) = generation["children"]
    assert call["kind"] == "model_call" and call["id"] == f"{GENERATION}.c1"
    assert call["name"] == session.active_model()["label"] and call["provider"] == "llama_cpp"
    assert call["input_tokens"] > 0 and call["output_tokens"] == 20
    assert (generation["input_tokens"], generation["output_tokens"]) == (
        call["input_tokens"],
        call["output_tokens"],
    )
    # No text of the question nor of the answer in the tree.
    flat = str(tree)
    assert QUESTION not in flat and ANSWER not in flat


def test_the_tree_is_rebuilt_from_the_journal_with_its_part():
    """B2's part runs before its stage (BM25's index at the end of BUILD): it ends under it."""
    from datetime import UTC, datetime

    from wavestack.trace.envelope import Envelope

    now = datetime.now(UTC)
    seq = iter(range(1, 100))

    def env(kind: str, step: str, payload: dict) -> Envelope:
        return Envelope(
            seq=next(seq),
            ts=now,
            session_epoch=0,
            context_id="rag_lab",
            step_id=step,
            parent_step=rag_lab.parent_step(step),
            kind=kind,
            actor="harness",
            trigger="user",
            payload=payload,
        )

    base = {"run_id": "lab9", "kind": "lexical_search", "option": "bm25", "stage_id": "b"}
    ended = {"status": "ok", "duration_ms": 3}
    events = [
        env(
            "rag_lab_run_started",
            "lab9",
            {"run_id": "lab9", "stages": [], "question": "q", "phase_label": "p"},
        ),
        env("rag_lab_stage_ended", "lab9.s2.index", base | {"part": "index"} | ended),
        env("rag_lab_stage_ended", "lab9.s2", base | ended),
        env("rag_lab_run_ended", "lab9", {"run_id": "lab9", "status": "ok", "duration_ms": 9}),
    ]
    tree = trace_tree.build(trace_tree.run_events(events, "lab9"), "lab9")
    assert tree is not None and [c.id for c in tree.children] == ["lab9.s2"]
    (part,) = tree.children[0].children
    assert (part.id, part.kind, part.parent) == ("lab9.s2.index", "part", "lab9.s2")
    assert trace_tree.build(events, "lab8") is None


# ---------- nothing leaves without a URL ----------


def test_without_a_url_nothing_leaves(index):
    session = ready(index)
    assert config.Config(values={}).otel_endpoint is None
    events = run(session)
    status = session.rag_lab_otel()
    assert status["ready"] is False and status["endpoint"] is None
    assert session.rag_lab_state()["otel"]["ready"] is False
    with pytest.raises(SendRefused):
        session.export_rag_lab_otel("lab1")
    assert not [e for e in events if e.kind == "outbound_request"]


def test_without_the_extra_the_export_says_so(index, monkeypatch):
    """The extra absent (its modules unimportable): unavailable, said, nothing built."""
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", None)
    session = ready(index, otel={"endpoint": "http://127.0.0.1:9"})
    status = session.rag_lab_otel()
    assert status["available"] is False and status["ready"] is False
    assert status["reason_text"].key == "rag_lab.otel.missing"
    run(session)
    with pytest.raises(SendRefused):
        session.export_rag_lab_otel("lab1")


def test_the_collector_s_host_is_allowed_only_by_its_url():
    plain = config.Config(values={"net": {"allowed_hosts": ["a.example"]}})
    assert plain.allowed_hosts == ["a.example"]
    values = {"net": {"allowed_hosts": ["a.example"]}, "otel": {}}
    values["otel"]["endpoint"] = "https://otel.example.org/api/public/otel"
    assert config.Config(values=values).allowed_hosts == ["a.example", "otel.example.org"]
    for bad in ("ftp://x.example", "not a url", "http://", "https://u:p@x.example", 3):
        assert config.Config(values={"otel": {"endpoint": bad}}).otel_endpoint is None
    assert config.Config(values={"otel": {"capture_content": "yes"}}).otel_capture_content is False
    assert config.Config(values={"otel": {"auth_env": "1BAD"}}).otel_auth_env is None
    assert config.Config(values={"otel": {"auth_env": "OTEL_AUTH"}}).otel_auth_env == "OTEL_AUTH"
    assert trace_otel.traces_url("http://h:1/") == "http://h:1/v1/traces"
    assert trace_otel.traces_url("http://h:1/v1/traces") == "http://h:1/v1/traces"


# ---------- the export, to a fake collector ----------


def test_the_export_sends_genai_spans_and_no_text(index, monkeypatch):
    otel_needed()
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("WAVESTACK_TEST_OTEL_AUTH", AUTH)
    with Collector() as collector:
        otel = {"endpoint": collector.url, "auth_env": "WAVESTACK_TEST_OTEL_AUTH"}
        session = ready(index, otel=otel)
        events = run(session)
        assert session.rag_lab_otel()["ready"] is True
        mark = get_journal().last_seq()
        sent = session.export_rag_lab_otel("lab1")
    ((path, headers, body),) = collector.requests
    assert path == "/v1/traces" and headers["Content-Type"] == "application/x-protobuf"
    assert headers["Authorization"] == AUTH
    spans = decoded(body)
    assert sent["spans"] == len(spans)
    by_id = {s.span_id: s for s in spans}
    (root,) = [s for s in spans if not s.parent_span_id]
    assert root.name == "invoke_workflow wavestack.rag_lab"
    assert attrs(root)["gen_ai.operation.name"] == "invoke_workflow"
    assert len({s.trace_id for s in spans}) == 1
    (chat,) = [s for s in spans if attrs(s).get("gen_ai.operation.name") == "chat"]
    a = attrs(chat)
    assert a["gen_ai.provider.name"] == "llama_cpp" and a["gen_ai.usage.output_tokens"] == 20
    assert a["gen_ai.usage.input_tokens"] > 0 and a["gen_ai.response.finish_reasons"]
    assert chat.name == f"chat {a['gen_ai.request.model']}"
    stage = by_id[chat.parent_span_id]
    assert attrs(stage)["wavestack.rag_lab.stage.kind"] == "generation"
    assert by_id[stage.parent_span_id] is root
    assert chat.start_time_unix_nano <= chat.end_time_unix_nano
    searches = [s for s in spans if attrs(s).get("gen_ai.operation.name") == "retrieval"]
    assert searches and all(s.name.startswith("retrieval ") for s in searches)
    # The tree's every node is a span; no text, no key, no header's value leaves.
    assert len(spans) == nodes(last_tree(events))
    for secret in (QUESTION, ANSWER, SECRET):
        assert secret.encode("utf-8") not in body
    assert "gen_ai.input.messages" not in str([attrs(s) for s in spans])
    # Loopback: the factory sends it without an `outbound_request`.
    assert not [e for e in get_journal().events_since(mark) if e.kind == "outbound_request"]


def test_the_texts_leave_only_when_set(index):
    otel_needed()
    with Collector() as collector:
        session = ready(index, otel={"endpoint": collector.url, "capture_content": True})
        run(session)
        session.export_rag_lab_otel("lab1")
    spans = decoded(collector.requests[0][2])
    (root,) = [s for s in spans if not s.parent_span_id]
    assert QUESTION in attrs(root)["gen_ai.input.messages"]
    assert ANSWER in attrs(root)["gen_ai.output.messages"]
    (chat,) = [s for s in spans if attrs(s).get("gen_ai.operation.name") == "chat"]
    assert QUESTION in attrs(chat)["gen_ai.input.messages"]


def test_the_routes_say_the_state_and_a_refusal(index):
    otel_needed()
    with Collector(status=503) as collector:
        session = ready(index, otel={"endpoint": collector.url})
        client = _client(session)
        state = client.get("/api/rag_lab/otel").json()
        assert state["ready"] is True and state["endpoint"] == collector.url
        missing = client.post("/api/rag_lab/otel/export", json={"run_id": "nope"}, headers=HEADERS)
        assert missing.status_code == 409
        session.run_rag_lab(QUESTION, None)
        wait_idle(session)
        refused = client.post("/api/rag_lab/otel/export", json={"run_id": "lab1"}, headers=HEADERS)
    assert refused.status_code == 502 and "503" in refused.json()["detail"]


def test_the_page_panel_and_file_are_wired():
    static = Path(__file__).resolve().parents[1] / "src" / "wavestack" / "web" / "static"
    html = (static / "rag.html").read_text(encoding="utf-8")
    script = '<script type="module" src="/static/rag-tree.js"></script>'
    assert html.index(script) > html.index('src="/static/rag.js"')
    for element in ("rag-tree", "rag-tree-body", "rag-otel-note", "rag-otel-export"):
        assert f'id="{element}"' in html
    source = (static / "rag-tree.js").read_text(encoding="utf-8")
    assert 'registerTab("tree"' in source and "/api/rag_lab/otel/export" in source
