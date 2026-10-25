"""V1.5 story 4 (CAP-4): the routes of « Évaluer l'agent » and their HTTP guard."""

from __future__ import annotations

import json
import threading
import time

import pytest
from fake_engine import FakeEngine, booted_session
from starlette.testclient import TestClient
from test_agent_eval_runner import case
from test_tools import QWEN, call

from wavestack import config
from wavestack.agent_eval import store
from wavestack.agent_eval.cases import load_provided_cases
from wavestack.messages import msg
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.web.app import create_app

HEADERS = {"origin": "http://127.0.0.1:8421"}
GD = call("get_datetime")
API = "/api/agent_eval"


def fr(key: str) -> str:
    return msg(f"agent_eval.refused.{key}", "fr")


@pytest.fixture
def make():
    made = []

    def build(cases=(), outputs=(GD, "Il est 10 h."), gate=None):
        store.write_session_cases(list(cases))
        engine = FakeEngine(
            outputs=list(outputs), template=QWEN.decode("utf-8"), architecture="qwen35", gate=gate
        )
        session = booted_session(engine, window=16384)
        app = create_app(
            DiagnosticSession(config.load_config(), port=8421),
            port=8421,
            version="test",
            app_session=session,
        )
        made.append(session)
        return session, TestClient(app, base_url="http://127.0.0.1:8421")

    yield build
    for session in made:
        session.close()


def finished(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 30
    while client.get(f"{API}/state").json()["current"] is not None:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    body = client.get(f"{API}/runs/{run_id}").json()
    assert body["status"] != "running"
    return body


def provided_ids() -> list[str]:
    return [c.id for c in load_provided_cases("fr")]


# ---------- the cases ----------


def test_cases_lists_the_provided_and_the_session_cases(make):
    _, client = make([case("u1")])

    body = client.get(f"{API}/cases").json()

    assert [c["id"] for c in body["provided"]] == provided_ids()
    assert [c["id"] for c in body["session"]] == ["u1"]
    assert body["session_error"] is None
    mine = body["session"][0]
    assert (mine["source"], mine["brick"], mine["max_model_calls"]) == ("séance", "tools", 3)
    assert mine["brick_label_text"] and mine["origin_turn_id"] is None


def test_an_unreadable_session_file_is_said_and_the_provided_cases_stay(make):
    _, client = make()
    config.agent_cases_path().write_text("{pas du json", encoding="utf-8")

    body = client.get(f"{API}/cases").json()

    assert body["session_error"] == "unreadable" and body["session"] == []
    assert [c["id"] for c in body["provided"]] == provided_ids()
    deleted = client.delete(f"{API}/cases/u1")
    assert (deleted.status_code, deleted.json()["detail"]) == (409, fr("unreadable"))


def test_delete_a_case(make):
    _, client = make([case("u1"), case("u2")])

    assert client.delete(f"{API}/cases/u1").json() == {"deleted": True}
    assert [c.id for c in store.read_session_cases()] == ["u2"]
    provided = client.delete(f"{API}/cases/heure_get_datetime")
    assert (provided.status_code, provided.json()["detail"]) == (409, fr("provided_case"))
    unknown = client.delete(f"{API}/cases/u9")
    assert (unknown.status_code, unknown.json()["detail"]) == (404, fr("unknown_case"))


def test_clear_the_session_cases(make):
    _, client = make([case("u1"), case("u2")])

    assert client.delete(f"{API}/cases").json() == {"cleared": 2}
    body = client.get(f"{API}/cases").json()
    assert body["session"] == [] and len(body["provided"]) == len(provided_ids())
    config.agent_cases_path().write_text("illisible", encoding="utf-8")
    assert client.delete(f"{API}/cases").json() == {"cleared": 0}
    written = json.loads(config.agent_cases_path().read_text(encoding="utf-8"))
    assert written == {"version": 1, "cases": []}


# ---------- a run ----------


def test_a_run_from_its_launch_to_its_result(make):
    _, client = make([case("u1")])

    started = client.post(f"{API}/runs", json={"case_id": "u1", "k": 1}, headers=HEADERS)

    assert started.status_code == 202
    run_id = started.json()["run_id"]
    body = finished(client, run_id)
    assert body["run_id"] == run_id and body["scope"] == "case" and body["k"] == 1
    assert body["status"] == "done" and (body["passed"], body["ran"], body["not_run"]) == (1, 1, 0)
    (result,) = body["cases"]
    assert result["status"] == "passed" and result["trials"][0]["model_calls"] == 2
    assert "stop_requested" not in body and "case_tag" not in body
    state = client.get(f"{API}/state").json()
    assert [r["run_id"] for r in state["runs"]] == [run_id]
    assert state["header"]["system_prompt"]["is_default"] is True
    assert len(state["header"]["system_prompt"]["start_text"]) <= 60


@pytest.mark.parametrize(
    ("body", "status", "detail"),
    [
        ({"case_id": None, "k": 3}, 422, fr("k_suite")),
        ({"case_id": "u1", "k": 2}, 422, None),
        ({"case_id": "u9", "k": 1}, 404, fr("unknown_case")),
        ({"case_id": "u1", "k": 1, "check_window": False}, 422, None),
    ],
)
def test_a_run_refused(make, body, status, detail):
    _, client = make([case("u1")])

    answer = client.post(f"{API}/runs", json=body, headers=HEADERS)

    assert answer.status_code == status
    if detail is not None:
        assert answer.json()["detail"] == detail
    assert client.get(f"{API}/state").json()["runs"] == []


def test_the_guard_refuses_every_change_during_a_run_but_stop(make):
    gate = threading.Event()
    session, client = make([case("u1"), case("u2")], gate=gate)
    try:
        run_id = client.post(f"{API}/runs", json={"case_id": "u1", "k": 1}, headers=HEADERS).json()[
            "run_id"
        ]
        deadline = time.monotonic() + 10
        while session.state != "turn":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        for method, path, body in (
            ("post", "/api/intentions/send", {"message": "Bonjour"}),
            ("post", "/api/intentions/brick", {"brick": "hooks", "wanted": True}),
            ("delete", f"{API}/cases", None),
            ("post", f"{API}/runs", {"case_id": "u2", "k": 1}),
        ):
            kwargs = {"json": body, "headers": HEADERS} if body is not None else {}
            answer = getattr(client, method)(path, **kwargs)
            assert (answer.status_code, answer.json()["detail"]) == (409, fr("running")), path
        assert client.get(f"{API}/state").status_code == 200
        assert "hooks" not in session._wanted  # nothing slipped in
        stopped = client.post("/api/intentions/stop", json={}, headers=HEADERS)
        assert stopped.status_code == 200 and stopped.json() == {"stopping": True}
    finally:
        gate.set()
    body = finished(client, run_id)
    assert body["status"] == "cancelled"
    assert body["cases"][0]["not_run_reason"] == "cancelled"
    assert client.delete(f"{API}/cases").status_code == 200  # the guard is gone


def test_the_guard_speaks_the_session_language(make):
    gate = threading.Event()
    session, client = make([case("u1")], gate=gate)
    session.set_language("en")
    try:
        client.post(f"{API}/runs", json={"case_id": "u1", "k": 1}, headers=HEADERS)
        answer = client.delete(f"{API}/cases")
        assert answer.json()["detail"] == msg("agent_eval.refused.running", "en")
    finally:
        gate.set()
        session.agent_eval.join(10)


# ---------- trace and comparison ----------


def test_the_trace_of_a_failed_try_marks_its_fault(make):
    failing = case("uf", tools=[], checks=[{"kind": "tool_called", "tool": "get_datetime"}])
    _, client = make([failing], outputs=["Je ne sais pas."])
    run_id = client.post(f"{API}/runs", json={"case_id": "uf", "k": 1}, headers=HEADERS).json()[
        "run_id"
    ]
    finished(client, run_id)

    trace = client.get(f"{API}/runs/{run_id}/trace", params={"case_id": "uf", "trial": 1})

    assert trace.status_code == 200
    items = trace.json()["items"]
    faults = [i for i in items if i["fault"]]
    assert len(faults) == 1 and faults[0]["text"] == "Fin du tour : completed"
    assert trace.json()["failing"]["kind"] == "tool_called"
    missing = client.get(f"{API}/runs/{run_id}/trace", params={"case_id": "uf", "trial": 2})
    assert (missing.status_code, missing.json()["detail"]) == (404, fr("unknown_trial"))
    gone = client.get(f"{API}/runs/r999999/trace", params={"case_id": "uf"})
    assert (gone.status_code, gone.json()["detail"]) == (404, fr("unknown_run"))
    assert client.get(f"{API}/runs/r999999").status_code == 404


def test_compare_two_runs(make):
    session, client = make([case("u1")], outputs=[GD, "Il est 10 h.", "Je ne sais pas."])
    first = client.post(f"{API}/runs", json={"case_id": "u1"}, headers=HEADERS).json()["run_id"]
    finished(client, first)
    session.save_system_prompt("Un autre prompt.")
    second = client.post(f"{API}/runs", json={"case_id": "u1"}, headers=HEADERS).json()["run_id"]
    finished(client, second)

    body = client.get(f"{API}/compare", params={"a": first, "b": second}).json()

    assert body["differs"] == ["system_prompt"] and body["control"] is False
    assert body["rows"] == [
        {
            "case_id": "u1",
            "title_text": "Cas u1",
            "a": "passed",
            "b": "failed",
            "change": "regressed",
            "absent_from": None,
        }
    ]
    unknown = client.get(f"{API}/compare", params={"a": first, "b": "r999999"})
    assert (unknown.status_code, unknown.json()["detail"]) == (404, fr("unknown_run"))
    same = client.get(f"{API}/compare", params={"a": first, "b": first})
    assert (same.status_code, same.json()["detail"]) == (422, fr("same_run"))
