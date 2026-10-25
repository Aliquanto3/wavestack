"""V1.5 story 3: the routes of « En faire un cas » on a real turn played by the fake engine."""

from __future__ import annotations

import pytest
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_tools import QWEN, call

from wavestack import config
from wavestack.agent_eval import store
from wavestack.messages import msg
from wavestack.session.app_session import AppSession
from wavestack.trace import journal as journal_module
from wavestack.trace.journal import Journal, get_journal

NOT_CALLED = {"kind": "tool_not_called", "tool": "get_datetime"}
CALLED = {"kind": "tool_called", "tool": "get_datetime"}


@pytest.fixture(autouse=True)
def _fresh_journal(monkeypatch):
    """Turn ids restart with each session: the journal is the test's own."""
    monkeypatch.setattr(journal_module, "_journal", Journal())


def client_for(session: AppSession):
    client = _client(session)
    client.headers.update(HEADERS)  # a write route checks the origin
    return client


def tool_engine(outputs: list[str] | None = None) -> FakeEngine:
    return FakeEngine(
        outputs=outputs or [call("get_datetime"), "Il est midi."],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
    )


def played(session: AppSession, message: str = "Quelle heure est-il ?") -> str:
    """Sends a message and returns the turn's id."""
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    started = [e for e in get_journal().events_since(mark) if e.kind == "turn_started"]
    return started[-1].turn_id


def setup(outputs: list[str] | None = None, **kw):
    engine = tool_engine(outputs)
    session = booted_session(engine, **kw)
    session.set_brick("tools", True)
    session.join()
    return engine, session, client_for(session)


def form(turn_id: str, **kw) -> dict:
    return {
        "turn_id": turn_id,
        "title_text": "L'heure inventée",
        "symptom_text": "Le modèle n'appelle pas l'outil",
        "assertion_text": "Il doit appeler get_datetime",
        "prompt": "Quelle heure est-il ?",
        "include_history": True,
        "freeze_system_prompt": False,
        "approval": "refuse",
        "on_overflow": "none",
        "max_model_calls": 3,
        "checks": [NOT_CALLED],
    } | kw


def test_the_draft_of_a_real_turn():
    _, session, client = setup()
    turn = played(session)
    response = client.get("/api/agent_eval/draft", params={"turn_id": turn})
    assert response.status_code == 200
    draft = response.json()
    assert draft["prompt"] == "Quelle heure est-il ?"
    assert [(c["tool"], c["arguments"], c["status"]) for c in draft["tool_calls"]] == [
        ("get_datetime", {}, "ok")
    ]
    assert draft["answer_text"] == "Il est midi."
    assert draft["origin_status"] == "completed" and draft["verdict_turn_ids"] == [turn]
    assert "tools" in draft["bricks"] and "get_datetime" in draft["tools"]
    assert draft["model_calls"] == 2 and draft["suggested_max_model_calls"] == 2
    assert draft["history"] == [] and draft["history_available"]


def test_the_verdict_says_the_case_fails_on_the_turn_without_calling_the_model():
    engine, session, client = setup()
    turn = played(session)
    calls, last = len(engine.calls), get_journal().last_seq()
    response = client.post("/api/agent_eval/verdict", json=form(turn))
    assert response.status_code == 200
    verdict = response.json()
    assert verdict["passed"] is False and verdict["origin_complete"] is True
    assert verdict["failing"]["kind"] == "tool_not_called"
    assert verdict["failing"]["reason_text"] == "get_datetime appelé"
    assert verdict["model_calls"] == 2
    assert [c["kind"] for c in verdict["checks"]] == ["tool_not_called", "model_calls_max"]
    assert len(engine.calls) == calls and get_journal().last_seq() == last


def test_the_verdict_says_when_the_case_cannot_fail():
    _, session, client = setup()
    verdict = client.post(
        "/api/agent_eval/verdict", json=form(played(session), checks=[CALLED])
    ).json()
    assert verdict["passed"] is True and verdict["failing"] is None


def test_the_verdict_reasons_follow_the_sessions_language():
    _, session, client = setup()
    session.set_language("en")
    turn = played(session)
    reason = client.post("/api/agent_eval/verdict", json=form(turn)).json()["failing"][
        "reason_text"
    ]
    assert reason == msg("agent_eval.tool_not_called.failed", "en", tool="get_datetime")
    assert reason != "get_datetime appelé"


def test_a_cap_below_the_real_calls_fails_on_the_cap():
    _, session, client = setup()
    verdict = client.post(
        "/api/agent_eval/verdict", json=form(played(session), checks=[CALLED], max_model_calls=1)
    ).json()
    assert verdict["passed"] is False
    assert verdict["failing"]["kind"] == "model_calls_max"
    assert verdict["failing"]["params"] == {"max": 1}


def test_a_turn_stopped_by_the_limit_is_accepted_and_every_check_fails():
    engine = tool_engine([call("get_datetime")])
    session = booted_session(engine, values={"tools": {"max_calls": 2, "max_retries": 0}})
    session.set_brick("tools", True)
    session.join()
    client = client_for(session)
    turn = played(session)
    draft = client.get("/api/agent_eval/draft", params={"turn_id": turn}).json()
    assert draft["origin_status"] == "limit"
    verdict = client.post("/api/agent_eval/verdict", json=form(turn)).json()
    assert verdict["passed"] is False and verdict["origin_complete"] is False
    assert verdict["failing"]["reason_text"] == "tour incomplet (fini en « limit »)"


def test_an_incomplete_check_is_a_field_error_and_the_verdict_is_not_computed():
    _, session, client = setup()
    turn = played(session)
    response = client.post(
        "/api/agent_eval/verdict",
        json=form(turn, checks=[{"kind": "answer_contains", "text": ""}]),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "checks.0.text", "message_text": "Ce champ est obligatoire."}
    ]


def test_empty_texts_are_tolerated_by_the_verdict():
    _, session, client = setup()
    response = client.post(
        "/api/agent_eval/verdict",
        json=form(played(session), title_text="", symptom_text="", assertion_text="", prompt=""),
    )
    assert response.status_code == 200


def test_the_verdict_refuses_a_check_of_the_cap_or_an_unknown_kind_and_bad_counts():
    _, session, client = setup()
    turn = played(session)

    def errors(**kw):
        response = client.post("/api/agent_eval/verdict", json=form(turn, **kw))
        assert response.status_code == 422
        return response.json()["detail"]

    kind = "Ce type de vérification n'existe pas."
    assert errors(checks=[{"kind": "model_calls_max", "max": 3}]) == [
        {"field": "checks.0.kind", "message_text": kind}
    ]
    assert errors(checks=[{"kind": "nope"}]) == [{"field": "checks.0.kind", "message_text": kind}]
    assert errors(checks=[NOT_CALLED] * 3) == [
        {"field": "checks", "message_text": "Choisissez une ou deux vérifications."}
    ]
    assert errors(checks=[]) == [
        {"field": "checks", "message_text": "Choisissez une ou deux vérifications."}
    ]
    assert errors(max_model_calls=0) == [
        {"field": "max_model_calls", "message_text": "Le plafond doit être au moins 1."}
    ]


def test_an_optional_parameter_left_empty_is_dropped():
    _, session, client = setup()
    verdict = client.post(
        "/api/agent_eval/verdict",
        json=form(played(session), checks=[CALLED | {"before": ""}]),
    ).json()
    assert verdict["passed"] is True


# ---------- saving ----------


def test_saving_writes_a_session_case_with_the_provenance_of_the_journal():
    _, session, client = setup()
    turn = played(session)
    response = client.post("/api/agent_eval/cases", json=form(turn, freeze_system_prompt=True))
    assert response.status_code == 201
    saved = response.json()["case"]
    (stored,) = store.read_session_cases()
    assert stored.model_dump(mode="json") == saved
    assert saved["id"].startswith("u") and saved["title_text"] == "L'heure inventée"
    assert saved["checks"] == [NOT_CALLED] and saved["max_model_calls"] == 3
    assert saved["provenance"]["source"] == "séance" and saved["provenance"]["turn_id"] == turn
    started = next(e for e in get_journal().all_events() if e.kind == "turn_started")
    assert saved["provenance"]["date"] == started.ts.isoformat()
    assert saved["provenance"]["system_prompt_text"] == saved["system_prompt"]
    assert saved["tools"] and "get_datetime" in saved["tools"]


def test_a_second_case_is_added_to_the_first():
    _, session, client = setup()
    turn = played(session)
    ids = [client.post("/api/agent_eval/cases", json=form(turn)).json()["case"]["id"] for _ in "ab"]
    assert [c.id for c in store.read_session_cases()] == ids and len(set(ids)) == 2


def test_the_saved_case_survives_the_sessions_reset():
    _, session, client = setup()
    saved = client.post("/api/agent_eval/cases", json=form(played(session))).json()["case"]
    session.reset()
    session.join()
    assert [c.id for c in store.read_session_cases()] == [saved["id"]]


def test_a_body_with_a_provenance_is_refused_and_nothing_is_written():
    _, session, client = setup()
    response = client.post(
        "/api/agent_eval/cases",
        json=form(played(session)) | {"provenance": {"source": "fourni", "date": "2026-10-25"}},
    )
    assert response.status_code == 422
    assert not config.agent_cases_path().exists()


@pytest.mark.parametrize("field", ["title_text", "symptom_text", "assertion_text", "prompt"])
def test_an_empty_text_is_a_field_error(field):
    _, session, client = setup()
    response = client.post("/api/agent_eval/cases", json=form(played(session), **{field: "  "}))
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": field, "message_text": "Ce champ est obligatoire."}
    ]
    assert not config.agent_cases_path().exists()


def test_three_checks_are_refused():
    _, session, client = setup()
    response = client.post(
        "/api/agent_eval/cases", json=form(played(session), checks=[NOT_CALLED, CALLED, NOT_CALLED])
    )
    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"field": "checks", "message_text": "Choisissez une ou deux vérifications."}
    ]
    assert not config.agent_cases_path().exists()


def test_an_unreadable_file_is_a_409_and_stays_as_it_was():
    _, session, client = setup()
    turn = played(session)
    path = config.agent_cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    response = client.post("/api/agent_eval/cases", json=form(turn))
    assert response.status_code == 409
    assert response.json()["detail"] == msg("agent_case.error.unreadable", "fr")
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_a_case_with_only_a_negative_check_is_saved():
    _, session, client = setup()
    response = client.post("/api/agent_eval/cases", json=form(played(session), checks=[NOT_CALLED]))
    assert response.status_code == 201


# ---------- refusals ----------


def test_an_unknown_turn_is_a_404_in_the_sessions_language():
    _, _, client = setup()
    for response in (
        client.get("/api/agent_eval/draft", params={"turn_id": "t99"}),
        client.post("/api/agent_eval/verdict", json=form("t99")),
        client.post("/api/agent_eval/cases", json=form("t99")),
    ):
        assert response.status_code == 404
        assert response.json()["detail"] == msg("agent_case.refused.unknown_turn", "fr")


def test_a_compaction_turn_is_a_409():
    engine = FakeEngine(outputs=["ok"])
    session = booted_session(engine, window=2048, values={"context": {"compaction_max_tokens": 64}})
    session.set_brick("short_memory", True)
    session.join()
    for i in range(3):
        played(session, f"{i}" + "a" * 100)
    mark = get_journal().last_seq()
    session.compact("compaction", None)
    session.join()
    session.join()
    compaction = next(
        e
        for e in get_journal().events_since(mark)
        if e.kind == "turn_started" and e.payload.get("kind") == "compaction"
    )
    response = client_for(session).get(
        "/api/agent_eval/draft", params={"turn_id": compaction.turn_id}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == msg("agent_case.refused.not_a_message", "fr")


# ---------- the texts of the form ----------

STATIC = config.repo_root() / "src" / "wavestack" / "web" / "static"


def _ui(lang: str) -> dict:
    import yaml

    path = config.content_file("ui.yaml", lang)
    return yaml.safe_load(path.read_text(encoding="utf-8"))["main"]["agent_case"]


def _node(tree: dict, dotted: str):
    for part in dotted.split("."):
        tree = tree[part]
    return tree


def test_every_text_the_form_asks_for_exists_in_the_three_languages():
    import re

    script = (STATIC / "agent-case-form.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'\btc\("([a-z0-9_.]+)"', script))
    kinds = ["tool_called", "tool_not_called", "argument_never", "answer_contains"]
    kinds += ["hook_decided", "subagent_called", "turn_completed"]
    keys |= {f"form.checks.kind.{k}" for k in kinds}
    keys |= {
        f"form.checks.param.{p}" for p in "tool before argument contains text hook decision".split()
    }
    keys |= {f"form.checks.decision.{d}" for d in ("block", "ask_human")}
    keys |= {f"form.overflow.{o}" for o in ("none", "compaction", "sliding_window")}
    keys |= {f"form.config.option.{o}" for o in ("mcp_lazy", "rag_rerank")}
    assert "form.save" in keys and len(keys) > 40
    for lang in ("fr", "en", "de"):
        tree = _ui(lang)
        for key in sorted(keys - {"form.history.include"}):
            assert isinstance(_node(tree, key), str), (lang, key)
        # The count picks `one` or `other`.
        assert set(tree["form"]["history"]["include"]) == {"one", "other"}, lang


def test_the_form_only_exports_its_interface():
    import re

    script = (STATIC / "agent-case-form.js").read_text(encoding="utf-8")
    exported = re.findall(r"^export (?:async )?function (\w+)", script, re.M)
    assert sorted(exported) == [
        "canMakeCase",
        "closeCaseForm",
        "onCaseSaved",
        "openCaseForm",
        "registerOpenView",
    ]
    assert "window.agentEval" not in script and "./agent-eval.js" not in script
