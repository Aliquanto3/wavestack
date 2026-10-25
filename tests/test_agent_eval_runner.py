"""V1.5 story 4 (CAP-4): the executor of agent cases, through the session and a fake engine.

The session cases are written by `store.write_session_cases` in the test's data directory
(a real file); the cases are started by `start([ids], k)` for an exact list.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest
from fake_engine import FakeEngine
from test_tools import QWEN, call

from wavestack import config
from wavestack.agent_eval import store
from wavestack.agent_eval.cases import AgentCase, Provenance, load_provided_cases
from wavestack.messages import msg
from wavestack.models.cloud_base import CallCost, record_spend
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.trace.journal import get_journal

ROOT = Path(__file__).resolve().parents[1]
RUNNING_FR = msg("agent_eval.refused.running", "fr")
BASE = ["short_memory", "system_prompt", "tools"]
GD = call("get_datetime")
NNBSP = " "  # French thousands separator


def case(cid: str, **kw) -> AgentCase:
    data = {
        "id": cid,
        "title_text": f"Cas {cid}",
        "brick": "tools",
        "symptom_text": "symptôme",
        "assertion_text": "attendu",
        "prompt": "Quelle heure est-il ?",
        "bricks": BASE,
        "tools": ["get_datetime"],
        "hooks": [],
        "skills": [],
        "mcp_servers": [],
        "max_model_calls": 3,
        "checks": [{"kind": "tool_called", "tool": "get_datetime"}],
        "provenance": {"source": "séance", "date": "2026-10-25"},
    }
    data.update(kw)
    return AgentCase.model_validate(data)


class Factory:
    """The engine factory, counted: a load after the boot would be a reload."""

    def __init__(self, engine: FakeEngine) -> None:
        self.engine, self.calls = engine, 0

    def __call__(self, path, n_ctx):  # noqa: ANN001, ANN204
        self.calls += 1
        return self.engine


def make(cases, outputs, *, window=4096, values=None, gate=None):
    store.write_session_cases(cases)
    engine = FakeEngine(
        outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35", gate=gate
    )
    factory = Factory(engine)
    context = {"context": {"window": window, "near_limit_ratio": 0.8}}
    session = AppSession(
        config.Config(values=config._deep_merge(context, values or {})), engine_factory=factory
    )
    session.boot("fake.gguf").result()
    return engine, session, factory


@pytest.fixture
def closing():
    sessions: list[AppSession] = []
    yield sessions.append
    for s in sessions:
        s.close()


def play(session, ids, k=1, **kw):
    run_id = session.agent_eval.start(ids, k, **kw)
    return session.agent_eval.wait(run_id, timeout=30)


def since(mark: int, kind: str | None = None):
    return [e for e in get_journal().events_since(mark) if kind is None or e.kind == kind]


def states(mark: int) -> list[str]:
    out: list[str] = []
    for e in since(mark, "session_state"):
        if not out or out[-1] != e.payload["state"]:
            out.append(e.payload["state"])
    return out


def wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


def config_of(session):
    s = session
    return (
        set(s._wanted),
        set(s._tools_enabled),
        set(s._hooks_enabled),
        set(s._skills_enabled),
        set(s._mcp_enabled),
        s._mcp_lazy,
        s._rag_rerank,
        s._custom_prompt,
        s._active_scenario,
    )


def last_bricks(mark: int = 0):
    return [e.payload for e in since(mark, "bricks_changed")][-1]


# ---------- 1. the suite, one case after the other ----------


def test_suite_runs_the_cases_in_order_without_reloading(closing):
    a = case("ua")
    b = case(
        "ub",
        tools=[],
        bricks=["short_memory", "system_prompt"],
        checks=[{"kind": "answer_contains", "text": "Pascal"}],
    )
    c = case("uc", window=8192)
    engine, session, factory = make([a, b, c], [GD, "Il est 10 h.", "Bonjour."])
    closing(session)
    configured = session._window_state()["configured"]
    mark = get_journal().last_seq()

    run = play(session, ["ua", "ub", "uc"])

    ra, rb, rc = run.cases
    assert (ra.status, rb.status, rc.status) == ("passed", "failed", "not_run")
    assert rb.trials[0].failing.kind == "answer_contains"
    assert rb.trials[0].failing.reason_text == "la réponse ne contient pas « Pascal »"
    assert rc.not_run_reason == "window" and rc.trials[0].not_run_reason == "window"
    assert rc.reason_text == (
        f"demande une fenêtre de 8{NNBSP}192 tokens (fenêtre courante : 4{NNBSP}096)"
    )
    assert (run.passed, run.ran, run.not_run, run.status) == (1, 2, 1, "done")
    # No reload: the factory was called at the boot only, no `model_load` since the mark.
    assert factory.calls == 1 and "model_load" not in states(mark)
    assert session._window_state()["configured"] == configured
    started = [e.payload.get("case_id") for e in since(mark, "turn_started")]
    assert started == ["ua", "ub"]
    assert states(mark) == ["agent_eval", "turn", "agent_eval", "turn", "agent_eval", "idle"]
    assert session.state == "idle" and not session.agent_eval.running
    assert len(engine.calls) == 3


# ---------- 2. and 3. « Arrêter » ----------


def test_stop_during_a_case_cancels_it_and_the_rest(closing):
    gate = threading.Event()
    gate.set()
    cases = [case("u1"), case("u2"), case("u3")]
    engine, session, _ = make(cases, [GD, "Il est 10 h.", GD], gate=gate)
    closing(session)
    before = config_of(session)

    def hold(env):  # the second case waits at its first model call
        if env.kind == "turn_ended" and env.turn_id and env.context_id in (None, "main"):
            gate.clear()

    get_journal().subscribe(hold)
    try:
        run_id = session.agent_eval.start(["u1", "u2", "u3"], 1)
        wait_until(lambda: len(engine.calls) == 3)
        assert session.stop() is True
    finally:
        get_journal().unsubscribe(hold)
        gate.set()
    run = session.agent_eval.wait(run_id, timeout=30)

    c1, c2, c3 = run.cases
    assert c1.status == "passed" and c1.trials[0].verdict is not None
    assert (c2.status, c2.not_run_reason, c2.reason_text) == ("not_run", "cancelled", "arrêté")
    assert c2.trials[0].has_trace and c2.trials[0].verdict is None
    assert (c3.status, c3.not_run_reason, c3.trials[0].has_trace) == (
        "not_run",
        "cancelled",
        False,
    )
    trace = session.agent_eval.trace(run_id, "u2", 1)
    assert "Fin du tour : cancelled" in [i.text for i in trace.items]
    assert run.status == "cancelled" and session.state == "idle"
    assert config_of(session) == before


def test_stop_between_two_cases_launches_no_other_case(closing):
    _, session, _ = make([case("u1"), case("u2")], [GD, "Il est 10 h."])
    closing(session)
    mark = get_journal().last_seq()
    seen: list[bool] = []

    def stop_at_rest(env):
        ended = [e for e in since(mark, "turn_ended") if e.context_id in (None, "main")]
        if env.kind == "session_state" and env.payload["state"] == "agent_eval" and ended:
            if not seen:
                seen.append(session.stop())

    get_journal().subscribe(stop_at_rest)
    try:
        run = play(session, ["u1", "u2"])
    finally:
        get_journal().unsubscribe(stop_at_rest)

    assert seen == [True]
    assert [e.payload.get("case_id") for e in since(mark, "turn_started")] == ["u1"]
    assert run.cases[0].status == "passed"
    assert (run.cases[1].status, run.cases[1].not_run_reason) == ("not_run", "cancelled")
    assert run.status == "cancelled" and session.state == "idle"


# ---------- 4. the spending cap ----------


def test_spending_cap_reached_during_the_first_case_stops_the_run(closing):
    gate = threading.Event()
    cases = [case("u1"), case("u2"), case("u3")]
    values = {"finops": {"max_session_usd": 0.01}}
    engine, session, _ = make(cases, [GD, "Il est 10 h."], values=values, gate=gate)
    closing(session)
    try:
        run_id = session.agent_eval.start(["u1", "u2", "u3"], 1)
        wait_until(lambda: len(engine.calls) == 1)
        record_spend(CallCost(input_usd=0.01, output_usd=0.01, source="api"), 1.0)
    finally:
        gate.set()
    run = session.agent_eval.wait(run_id, timeout=30)

    c1, c2, c3 = run.cases
    assert c1.status == "passed"
    for c in (c2, c3):
        assert (c.status, c.not_run_reason) == ("not_run", "budget")
        assert c.reason_text == "plafond de dépense atteint (0,01 $)"
    assert run.status == "budget" and len(engine.calls) == 2  # none after the first case


def test_spending_cap_already_reached_runs_no_case(closing):
    values = {"finops": {"max_session_usd": 0.01}}
    engine, session, _ = make([case("u1"), case("u2")], [GD], values=values)
    closing(session)
    record_spend(CallCost(input_usd=0.02, output_usd=0.0, source="api"), 1.0)

    run = play(session, ["u1", "u2"])

    assert [(c.status, c.not_run_reason) for c in run.cases] == [("not_run", "budget")] * 2
    assert run.status == "budget" and engine.calls == []


# ---------- 5. H5 refused by the harness ----------


def test_h5_is_refused_by_the_harness_without_any_answer_of_the_test(closing):
    h5 = case(
        "uh5",
        bricks=[*BASE, "hooks"],
        tools=["public_holidays"],
        hooks=["h5"],
        prompt="Quels sont les jours fériés en 2026 ?",
        max_model_calls=2,
        checks=[
            {"kind": "hook_decided", "hook": "h5", "decision": "ask_human"},
            {"kind": "tool_not_called", "tool": "public_holidays"},
        ],
    )
    outputs = [call("public_holidays", year="2026"), "Je n'ai pas pu vérifier."]
    _, session, _ = make([h5], outputs)
    closing(session)
    mark = get_journal().last_seq()

    run = play(session, ["uh5"])

    assert run.cases[0].status == "passed", run.cases[0].trials[0].failing
    resolved = since(mark, "approval_resolved")
    assert [e.payload["decision"] for e in resolved] == ["refused"]
    trace = session.agent_eval.trace(run.run_id, "uh5", 1)
    approval = "Validation : refusé par le harnais (exécution d'un cas)"
    assert approval in [i.text for i in trace.items]
    assert states(mark)[-4:] == ["awaiting_human", "turn", "agent_eval", "idle"]
    assert not [e for e in since(mark, "tool_started") if e.payload["tool"] == "public_holidays"]


# ---------- 6. on_overflow ----------


def _talvane(on_overflow: str) -> AgentCase:
    provided = {c.id: c for c in load_provided_cases("fr")}["code_talvane_apres_compaction"]
    return provided.model_copy(
        update={
            "id": f"u_{on_overflow}",
            "on_overflow": on_overflow,
            "provenance": Provenance(source="séance", date="2026-10-25"),
        }
    )


@pytest.mark.parametrize(
    ("strategy", "outputs", "turns", "status"),
    [
        (
            "compaction",
            ["Résumé : le code est TLV-7731-QZ.", "Le code est TLV-7731-QZ."],
            3,
            "passed",
        ),
        ("sliding_window", ["Le code est TLV-7731-QZ."], 2, None),
        ("none", ["Le code est TLV-7731-QZ."], 1, "failed"),
    ],
)
def test_on_overflow_applies_the_case_strategy(closing, strategy, outputs, turns, status):
    c = _talvane(strategy)
    engine, session, _ = make([c], outputs, window=16384)
    closing(session)
    mark = get_journal().last_seq()

    run = play(session, [c.id], check_window=False)

    trial = run.cases[0].trials[0]
    assert len(trial.turn_ids) == turns
    started = since(mark, "turn_started")
    assert [e.turn_id for e in started] == trial.turn_ids
    assert all((e.payload["case_id"], e.payload["run_id"]) == (c.id, run.run_id) for e in started)
    if status is not None:
        assert run.cases[0].status == status
    if strategy == "compaction":
        assert trial.model_calls == 2 == len(engine.calls)
    if strategy == "none":
        assert trial.failing.reason_text == "tour incomplet (fini en « overflow »)"


# ---------- 7. and 8. the configuration ----------


def test_configuration_is_restored_after_the_run(closing):
    remember = call("remember", text="Le formateur s'appelle Anaël.")
    outputs = [remember, "C'est noté.", "Deuxième réponse.", "Réponse du cas."]
    c = case(
        "ucfg",
        bricks=["short_memory", "system_prompt", "hooks", "global_memory"],
        tools=None,
        hooks=["h1"],
        checks=[{"kind": "turn_completed"}],
        max_model_calls=1,
    )
    engine, session, _ = make([c], outputs, window=16384)
    closing(session)
    session.launch_scenario("global_memory")
    for brick_id in ("short_memory", "system_prompt", "tools", "global_memory"):
        session.set_brick(brick_id, True)
    session.set_tool("get_datetime", False)
    session.set_hook("h5", True)
    session.save_system_prompt("Tu es un assistant de test.")
    session.join()
    session.send("Retiens mon prénom.")
    wait_until(lambda: session.state == "idle")
    session.send("Et ensuite ?")
    wait_until(lambda: session.state == "idle")
    session.join()
    memory = [(e.id, e.text) for e in session._memory]
    assert any("Anaël" in text for _, text in memory) and len(session._history) == 2
    before, bricks_before = config_of(session), last_bricks()
    mark = get_journal().last_seq()

    run = play(session, ["ucfg"])

    assert run.cases[0].status == "passed", run.cases[0].trials[0].failing
    assert config_of(session) == before
    assert last_bricks() == bricks_before
    assert session._history == [] and session._last is None
    assert [(e.id, e.text) for e in session._memory] == memory
    assert since(mark, "harness_reset") == []
    # The case ran with its own configuration: `hooks` wanted before its turn.
    (turn,) = since(mark, "turn_started")
    played = [e for e in since(mark, "bricks_changed") if e.seq < turn.seq][-1]
    wanted = {b["id"] for b in played.payload["bricks"] if b["wanted"]}
    assert wanted == {"short_memory", "system_prompt", "hooks", "global_memory"}


def test_the_system_prompt_is_the_session_one_unless_the_case_fixes_it(closing):
    free = case("ufree", tools=[], bricks=["system_prompt"], checks=[{"kind": "turn_completed"}])
    fixed = free.model_copy(update={"id": "ufixed", "system_prompt": "PROMPT-FIGE du cas."})
    engine, session, _ = make([free, fixed], ["Réponse."])
    closing(session)
    session.save_system_prompt("PROMPT-SESSION personnalisé.")

    run = play(session, ["ufree", "ufixed"])

    first, second = (bytes(ids).decode("utf-8", "replace") for ids in engine.calls)
    assert "PROMPT-SESSION" in first and "PROMPT-FIGE" not in first
    assert "PROMPT-FIGE" in second and "PROMPT-SESSION" not in second
    assert run.system_prompt.text == "PROMPT-SESSION personnalisé."
    assert run.system_prompt.is_default is False
    assert session._custom_prompt == "PROMPT-SESSION personnalisé."


# ---------- 9. to 11. what survives, what is refused, the labels ----------


def test_results_survive_a_reset(closing):
    _, session, _ = make([case("u1")], [GD, "Il est 10 h."])
    closing(session)
    file_bytes = config.agent_cases_path().read_bytes()
    run = play(session, ["u1"])
    before = session.agent_eval.state().runs

    session.reset()

    assert session.agent_eval.state().runs == before
    assert session.agent_eval.trace(run.run_id, "u1", 1).items
    assert config.agent_cases_path().read_bytes() == file_bytes


def test_intentions_are_refused_during_a_run(closing):
    gate = threading.Event()
    _, session, _ = make([case("u1")], [GD, "Il est 10 h."], gate=gate)
    closing(session)
    try:
        run_id = session.agent_eval.start(["u1"], 1)
        wait_until(lambda: session.state == "turn")
        for intention in (
            lambda: session.send("Bonjour"),
            lambda: session.launch_scenario("global_memory"),
            session.reset,
            lambda: session.set_context_window(8192),
            lambda: session.compact("sliding_window"),
            lambda: session.agent_eval.start(["u1"], 1),
            lambda: session.agent_eval.delete_case("u1"),
            session.agent_eval.clear_cases,
        ):
            with pytest.raises(SendRefused) as refused:
                intention()
            assert str(refused.value.reason_text) == RUNNING_FR
        with pytest.raises(ValueError):
            session.agent_eval.start(None, 3)
        assert session.agent_eval.state().current.case_id == "u1"
    finally:
        gate.set()
    run = session.agent_eval.wait(run_id, timeout=30)
    assert run.cases[0].status == "passed"


def test_turns_of_a_case_carry_its_labels_and_no_others(closing):
    _, session, _ = make([case("u1")], ["Avant.", GD, "Il est 10 h.", "Après."])
    closing(session)
    mark = get_journal().last_seq()
    session.send("Bonjour")
    wait_until(lambda: session.state == "idle")
    run = play(session, ["u1"])
    session.send("Encore")
    wait_until(lambda: session.state == "idle")

    payloads = [e.payload for e in since(mark, "turn_started")]
    assert len(payloads) == 3
    assert "case_id" not in payloads[0] and "run_id" not in payloads[0]
    assert (payloads[1]["case_id"], payloads[1]["run_id"]) == ("u1", run.run_id)
    assert "case_id" not in payloads[2] and "run_id" not in payloads[2]


# ---------- 12. and 13. three tries, loop bounds ----------


def test_three_tries_give_pass_at_k_and_pass_pow_k(closing):
    outputs = [GD, "Il est 10 h.", "Je ne sais pas.", GD, "Il est 11 h."]
    _, session, _ = make([case("u1")], outputs)
    closing(session)

    run = play(session, ["u1"], k=3)

    (result,) = run.cases
    assert [t.status for t in result.trials] == ["passed", "failed", "passed"]
    assert (result.successes, result.ran) == (2, 3)
    assert (result.pass_at_k, result.pass_pow_k, result.status) == (True, False, "passed")
    assert run.scope == "case" and run.k == 3


def test_a_loop_to_the_step_limit_fails_and_the_run_goes_on(closing):
    loop = case("uloop", checks=[{"kind": "turn_completed"}], max_model_calls=5)
    then = case(
        "uthen",
        tools=[],
        bricks=["short_memory", "system_prompt"],
        checks=[{"kind": "answer_contains", "text": "10 h"}],
    )
    values = {"tools": {"max_calls": 2}}
    _, session, _ = make([loop, then], [GD, GD, "Il est 10 h."], values=values)
    closing(session)

    run = play(session, ["uloop", "uthen"])

    first, second = run.cases
    assert first.status == "failed"
    assert first.trials[0].failing.reason_text == "tour incomplet (fini en « limit »)"
    assert second.status == "passed"


# ---------- 14. an exception in the executor ----------


def test_an_exception_ends_the_run_in_error_and_restores_the_configuration(closing, monkeypatch):
    _, session, _ = make([case("u1"), case("u2"), case("u3")], [GD, "Il est 10 h."])
    closing(session)
    before = config_of(session)
    mark = get_journal().last_seq()
    real = session.apply_case
    calls = []

    def failing(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("panne au deuxième cas")
        return real(*args, **kwargs)

    monkeypatch.setattr(session, "apply_case", failing)

    run = play(session, ["u1", "u2", "u3"])

    assert run.status == "error" and run.error_text == "RuntimeError: panne au deuxième cas"
    assert run.cases[0].status == "passed" and run.cases[0].trials[0].verdict is not None
    assert [(c.status, c.not_run_reason) for c in run.cases[1:]] == [("not_run", "cancelled")] * 2
    errors = since(mark, "harness_error")
    assert [e.payload["message_text"] for e in errors] == [
        "L'exécution des cas s'est arrêtée sur une erreur."
    ]
    assert session.state == "idle" and config_of(session) == before


# ---------- 15. to 17. guards ----------

PRIVATE = re.compile(
    r"session\._(bricks|tools_enabled|skills_enabled|hooks_enabled|mcp_enabled|history)"
)


def test_no_private_configuration_access_outside_the_session():
    sources = [
        *sorted((ROOT / "tools" / "eval").glob("*.py")),
        ROOT / "src" / "wavestack" / "session" / "agent_eval_runner.py",
        ROOT / "tests" / "test_agent_cases_provided.py",
    ]
    found = [str(p) for p in sources if PRIVATE.search(p.read_text(encoding="utf-8"))]
    assert found == []
    assert [p.name for p in sorted((ROOT / "tools" / "eval").glob("*.py"))] == ["measure_cases.py"]


def test_unknown_ids_of_a_session_case_are_ignored_and_shown(closing):
    c = case("uunk", skills=["competence_supprimee"], mcp_servers=["serveur_retire"])
    _, session, _ = make([c], [GD, "Il est 10 h."])
    closing(session)

    run = play(session, ["uunk"])

    assert run.cases[0].ignored_ids == ["competence_supprimee", "serveur_retire"]
    assert run.cases[0].status == "passed"


def test_the_window_option_is_for_the_tests_only(closing):
    for folder in ("src/wavestack/web", "tools"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix in (".py", ".js", ".html"):
                assert "check_window" not in path.read_text(encoding="utf-8"), path
    _, session, _ = make([case("u1")], [GD, "Il est 10 h."])
    closing(session)
    assert play(session, ["u1"]).window_checked is True
    assert play(session, ["u1"], check_window=False).window_checked is False


# ---------- 18. the global memory, frozen ----------


def test_the_global_memory_is_set_back_between_cases_and_at_the_end(closing):
    writer = case(
        "uwrite",
        bricks=["short_memory", "system_prompt", "global_memory"],
        tools=[],
        checks=[{"kind": "turn_completed"}],
    )
    reader = writer.model_copy(update={"id": "uread"})
    remember = call("remember", text="Entrée écrite par un cas.")
    engine, session, _ = make([writer, reader], [remember, "Noté.", "Lu."], window=16384)
    closing(session)
    before = [(e.id, e.text) for e in session._memory]
    mark = get_journal().last_seq()

    run = play(session, ["uwrite", "uread"])

    assert [c.status for c in run.cases] == ["passed", "passed"]
    writes = [e.payload for e in since(mark, "effect_applied") if e.payload["op"] == "add"]
    assert writes[0]["text"] == "Entrée écrite par un cas."  # the first case wrote it
    read = bytes(engine.calls[2]).decode("utf-8", "replace")
    assert "Entrée écrite par un cas." not in read  # the second reads the snapshot's
    assert before and [(e.id, e.text) for e in session._memory] == before
    assert since(mark, "harness_reset") == []


# ---------- review 4a: an engine deaf to « Arrêter », a thread that fails to start ----------


def test_a_turn_deaf_to_stop_keeps_the_run_until_it_ends_then_restores(closing):
    gate = threading.Event()  # the fake engine waits on it, whatever the cancellation
    c = case("udeaf", system_prompt="Prompt du cas.", checks=[{"kind": "turn_completed"}])
    engine, session, _ = make([c], [GD, "Il est 10 h."], gate=gate)
    closing(session)
    before = config_of(session)
    session.agent_eval._settle_s = 0.2  # the bound, short for the test
    try:
        run_id = session.agent_eval.start(["udeaf"], 1)
        wait_until(lambda: len(engine.calls) == 1)
        assert session.stop() is True
        run = session.agent_eval.wait(run_id, timeout=3)  # recorded over past the bound
        assert run.status == "cancelled"
        assert run.cases[0].not_run_reason == "cancelled"
        # Still in its run: never `idle` with the case's configuration.
        assert session.agent_eval.running and session.state != "idle"
        assert session._custom_prompt == "Prompt du cas."
        with pytest.raises(SendRefused) as refused:
            session.send("Bonjour")
        assert str(refused.value.reason_text) == RUNNING_FR
    finally:
        gate.set()
    wait_until(lambda: session.state == "idle")
    assert not session.agent_eval.running and config_of(session) == before


def test_a_thread_that_fails_to_start_leaves_the_session_idle(closing, monkeypatch):
    _, session, _ = make([case("u1")], [GD, "Il est 10 h."])
    closing(session)
    real, failed = threading.Thread.start, []

    def start(self):  # noqa: ANN001, ANN202 - the run's thread fails once
        if self.name == "wavestack-agent-eval" and not failed:
            failed.append(1)
            raise RuntimeError("can't start new thread")
        return real(self)

    monkeypatch.setattr(threading.Thread, "start", start)
    with pytest.raises(RuntimeError):
        session.agent_eval.start(["u1"], 1)

    assert session.state == "idle" and not session.agent_eval.running
    assert session.agent_eval.state().runs == []
    assert play(session, ["u1"]).cases[0].status == "passed"
