"""V1.5 story 1: the provided cases' loading and the session file (D4)."""

from __future__ import annotations

import json
import os

import pytest
from fake_engine import FakeEngine, booted_session

from wavestack import config
from wavestack.agent_eval import store
from wavestack.agent_eval.cases import AgentCase, load_provided_cases, new_case_id


def session_case(case_id: str | None = None, **fields) -> AgentCase:
    return AgentCase.model_validate(
        {
            "id": case_id or new_case_id(),
            "title_text": "T",
            "symptom_text": "S",
            "assertion_text": "A",
            "prompt": "Quelle heure est-il ?",
            "max_model_calls": 3,
            "checks": [{"kind": "tool_called", "tool": "get_datetime"}],
            "provenance": {
                "source": "séance",
                "date": "2026-10-25T10:00:00+02:00",
                "turn_id": "t7",
                "system_prompt_text": "Tu es…",
            },
        }
        | fields
    )


PROVIDED = """
cases:
  - id: heure_get_datetime
    title_text: L'heure
    brick: tools
    symptom_text: invente l'heure
    assertion_text: appelle get_datetime
    prompt: Quelle heure est-il ?
    max_model_calls: 3
    checks:
      - {kind: tool_called, tool: get_datetime}
    provenance: {source: fourni, date: "2026-10-25"}
"""


def _content(tmp_path, monkeypatch, fr: str | None, en: str | None = None):
    monkeypatch.setattr(config, "content_dir", lambda: tmp_path)
    if fr is not None:
        (tmp_path / "agent_cases.yaml").write_text(fr, encoding="utf-8")
    if en is not None:
        (tmp_path / "i18n" / "en").mkdir(parents=True)
        (tmp_path / "i18n" / "en" / "agent_cases.yaml").write_text(en, encoding="utf-8")


# ---------- provided cases ----------


def test_no_provided_file_gives_no_case(tmp_path, monkeypatch):
    _content(tmp_path, monkeypatch, None)
    assert load_provided_cases("fr") == []


def test_provided_cases_load_in_the_language(tmp_path, monkeypatch):
    _content(tmp_path, monkeypatch, PROVIDED, PROVIDED.replace("L'heure", "The time"))
    assert [c.title_text for c in load_provided_cases("fr")] == ["L'heure"]
    assert [c.title_text for c in load_provided_cases("en")] == ["The time"]
    assert [c.title_text for c in load_provided_cases("de")] == ["L'heure"]  # French
    (case,) = load_provided_cases("fr")
    assert (case.id, case.brick, case.provenance.source, case.checks[0].kind) == (
        "heure_get_datetime",
        "tools",
        "fourni",
        "tool_called",
    )


@pytest.mark.parametrize(
    "change",
    [
        ("    brick: tools\n", ""),  # a provided case names its brick
        ("    prompt:", "    system_prompt: x\n    prompt:"),  # never a fixed system prompt
        ("source: fourni", "source: séance"),
        ("    max_model_calls: 3\n", ""),
        # Only checks an idle fake engine passes: no event present is required (SPEC).
        ("{kind: tool_called, tool: get_datetime}", "{kind: turn_completed}"),
        ('date: "2026-10-25"', 'date: "hier"'),  # provenance date in ISO
    ],
)
def test_an_invalid_provided_case_is_refused(tmp_path, monkeypatch, change):
    _content(tmp_path, monkeypatch, PROVIDED.replace(*change))
    with pytest.raises(ValueError):
        load_provided_cases("fr")


def test_provided_ids_are_unique_and_known(tmp_path, monkeypatch):
    twice = PROVIDED + PROVIDED.split("cases:\n", 1)[1]
    _content(tmp_path, monkeypatch, twice)
    with pytest.raises(ValueError, match="used twice"):
        load_provided_cases("fr")
    (tmp_path / "agent_cases.yaml").write_text(
        PROVIDED.replace("    prompt:", "    tools: [get_datetime, ghost]\n    prompt:"),
        encoding="utf-8",
    )
    assert load_provided_cases("fr", {"tools": {"get_datetime", "ghost"}})
    with pytest.raises(ValueError, match="ghost"):
        load_provided_cases("fr", {"tools": {"get_datetime"}})


# ---------- the session file ----------


def test_the_session_file_lives_in_the_data_dir():
    assert config.agent_cases_path() == config.data_dir() / "agent_cases.json"


def test_no_session_file_gives_no_case():
    assert store.read_session_cases() == []


def test_session_cases_round_trip_in_the_documented_format():
    first = session_case("u00000001")
    store.add_session_case(first)
    store.add_session_case(session_case("u00000002", window=4096))
    data = json.loads(config.agent_cases_path().read_text(encoding="utf-8"))
    assert data["version"] == 1 and [c["id"] for c in data["cases"]] == ["u00000001", "u00000002"]
    assert data["cases"][0]["provenance"]["source"] == "séance"
    assert store.read_session_cases() == [first, session_case("u00000002", window=4096)]
    assert not list(config.agent_cases_path().parent.glob("*.tmp"))


def test_the_write_is_atomic(monkeypatch):
    store.write_session_cases([session_case("u1")])
    before = config.agent_cases_path().read_text(encoding="utf-8")

    def failing(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing)
    with pytest.raises(OSError):
        store.write_session_cases([session_case("u2")])
    assert config.agent_cases_path().read_text(encoding="utf-8") == before
    # The temporary file does not stay behind.
    assert not list(config.agent_cases_path().parent.glob("*.tmp"))


def test_a_provided_case_with_one_positive_check_loads(tmp_path, monkeypatch):
    _content(
        tmp_path,
        monkeypatch,
        PROVIDED.replace(
            "      - {kind: tool_called, tool: get_datetime}",
            "      - {kind: turn_completed}\n      - {kind: subagent_called}",
        ),
    )
    (case,) = load_provided_cases("fr")
    assert [c.kind for c in case.checks] == ["turn_completed", "subagent_called"]


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_another_version_is_unreadable(version):
    path = config.agent_cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "cases": []}), encoding="utf-8")
    with pytest.raises(store.SessionCasesUnreadable):
        store.read_session_cases()
    path.write_text(json.dumps({"version": 1, "cases": []}), encoding="utf-8")
    assert store.read_session_cases() == []


@pytest.mark.parametrize("date", ["2026-10-25", "2026-10-25T10:00:00+02:00", "2026-10-25T10:00"])
def test_an_iso_provenance_date_is_accepted(date):
    assert session_case("u1", provenance={"source": "séance", "date": date}).provenance.date == date


def test_an_id_already_used_is_refused():
    store.add_session_case(session_case("u1"))
    with pytest.raises(ValueError, match="u1"):
        store.add_session_case(session_case("u1"))
    provided = session_case("u2").model_copy(update={"id": "heure"})
    with pytest.raises(ValueError, match="heure"):
        store.add_session_case(session_case("heure_u"), provided=[provided])  # starts with u
    assert [c.id for c in store.read_session_cases()] == ["u1"]


def test_only_a_session_case_is_added():
    provided = AgentCase.model_validate(
        session_case("u1").model_dump() | {"provenance": {"source": "fourni", "date": "2026-10-25"}}
    )
    with pytest.raises(ValueError, match="séance"):
        store.add_session_case(provided)


def test_new_ids_start_with_u_and_differ():
    ids = {new_case_id() for _ in range(50)}
    assert len(ids) == 50 and all(i.startswith("u") and len(i) == 9 for i in ids)


def test_delete_and_clear():
    store.add_session_case(session_case("u1"))
    store.add_session_case(session_case("u2"))
    assert store.delete_session_case("u1") is True
    assert store.delete_session_case("heure_get_datetime") is False
    assert [c.id for c in store.read_session_cases()] == ["u2"]
    store.clear_session_cases()
    assert store.read_session_cases() == []
    assert json.loads(config.agent_cases_path().read_text(encoding="utf-8")) == {
        "version": 1,
        "cases": [],
    }


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        json.dumps({"version": 2, "cases": []}),
        json.dumps({"version": 1, "cases": [{"id": "u1"}]}),
        json.dumps({"version": 1, "cases": [], "more": 1}),
    ],
)
def test_an_unreadable_file_is_reported_and_clear_repairs_it(content):
    path = config.agent_cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(store.SessionCasesUnreadable, match="agent_cases.json"):
        store.read_session_cases()
    with pytest.raises(store.SessionCasesUnreadable):
        store.add_session_case(session_case("u1"))
    assert path.read_text(encoding="utf-8") == content  # never overwritten by an add
    store.clear_session_cases()
    assert store.read_session_cases() == []


def test_a_file_with_an_id_twice_or_another_provenance_is_unreadable():
    case = session_case("u1").model_dump(mode="json")
    path = config.agent_cases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "cases": [case, case]}), encoding="utf-8")
    with pytest.raises(store.SessionCasesUnreadable, match="twice"):
        store.read_session_cases()
    case["provenance"]["source"] = "recette"
    path.write_text(json.dumps({"version": 1, "cases": [case]}), encoding="utf-8")
    with pytest.raises(store.SessionCasesUnreadable, match="provenance"):
        store.read_session_cases()


def test_the_reset_never_touches_the_session_cases():
    store.add_session_case(session_case("u1"))
    before = config.agent_cases_path().read_bytes()
    session = booted_session(FakeEngine(output="ok"))
    session.reset()
    session.join()
    assert config.agent_cases_path().read_bytes() == before
    assert [c.id for c in store.read_session_cases()] == ["u1"]
