"""V1.5 story 4 (CAP-4): the pure part of the runs, on hand-built journals: the classification
of a try, a case's status at k = 3, pass@k and pass^k, the counts, the comparison, the trace."""

from __future__ import annotations

import pytest
from test_agent_eval_checks import TS, J, case

from wavestack.agent_eval import runs
from wavestack.agent_eval.runs import CaseResult, Run, SystemPrompt, TrialOutcome
from wavestack.trace.envelope import Envelope

GD = {"kind": "tool_called", "tool": "get_datetime"}


def passing_journal() -> J:
    j = J()
    j.start()
    j.call()
    j.tool("get_datetime")
    j.call(text="Il est 10 h.")
    j.end()
    return j


# ---------- a try ----------


def test_approval_answer_follows_the_case():
    assert runs.approval_answer(case(GD, approval="approve")) is True
    assert runs.approval_answer(case(GD, approval="refuse")) is False


def test_classify_passed_and_failed_by_verify():
    ok = runs.classify_trial(case(GD), 1, passing_journal().envs, "fr")
    assert (ok.status, ok.failing, ok.model_calls, ok.turn_ids, ok.has_trace) == (
        "passed",
        None,
        2,
        ["t1"],
        True,
    )
    j = J()
    j.start()
    j.call(text="Je ne sais pas.")
    j.end()
    ko = runs.classify_trial(case(GD), 2, j.envs, "fr")
    assert (ko.trial, ko.status, ko.failing.kind) == (2, "failed", "tool_called")
    assert ko.failing.reason_text == "get_datetime jamais appelé"


def test_classify_a_stop_midway_as_not_run_cancelled_with_its_trace():
    j = J()
    j.start()
    j.call()
    j.end(status="cancelled")
    out = runs.classify_trial(case(GD), 1, j.envs, "fr", stop_requested=True)
    assert (out.status, out.not_run_reason, out.reason_text) == ("not_run", "cancelled", "arrêté")
    assert out.has_trace and out.verdict is None and out.model_calls == 1


def test_classify_keeps_the_verdict_of_a_try_completed_before_the_stop():
    out = runs.classify_trial(case(GD), 1, passing_journal().envs, "fr", stop_requested=True)
    assert out.status == "passed"


def test_classify_a_cloud_refusal_for_the_cap_as_not_run_budget():
    j = J()
    j.start()
    j.add("harness_error", {"message_text": "m", "cause": "max_session_usd"})
    j.end(status="error")
    out = runs.classify_trial(case(GD), 1, j.envs, "fr", cap_usd=5.0)
    assert (out.status, out.not_run_reason) == ("not_run", "budget")
    assert out.reason_text == "plafond de dépense atteint (5,00 $)"
    en = runs.classify_trial(case(GD), 1, j.envs, "en", cap_usd=0.5)
    assert en.reason_text == "spending cap reached ($0.50)"


# ---------- a case's status, pass@k, pass^k ----------


def result(*statuses: str, k: int = 3) -> CaseResult:
    r = CaseResult(
        case_id="c1",
        title_text="T",
        brick="tools",
        brick_label_text="Outils",
        source="fourni",
        max_model_calls=3,
        k=k,
    )
    r.trials = [
        TrialOutcome(trial=i, status=s)
        if s != "not_run"
        else runs.not_run(i, "cancelled", "arrêté")
        for i, s in enumerate(statuses, 1)
    ]
    return runs.settle_case(r)


@pytest.mark.parametrize(
    ("statuses", "status", "successes", "ran", "at", "pow_"),
    [
        (("passed", "passed", "passed"), "passed", 3, 3, True, True),
        (("passed", "failed", "passed"), "passed", 2, 3, True, False),
        (("failed", "passed", "failed"), "failed", 1, 3, True, False),
        (("failed", "failed", "failed"), "failed", 0, 3, False, False),
        (("passed", "failed", "not_run"), "failed", 1, 2, True, False),  # 1/2, stopped
        (("passed", "not_run", "not_run"), "passed", 1, 1, True, None),  # first success
        (("failed", "not_run", "not_run"), "failed", 0, 1, None, False),  # first failure
        (("not_run", "not_run", "not_run"), "not_run", 0, 0, None, None),
    ],
)
def test_case_status_and_pass_at_k_and_pass_pow_k(statuses, status, successes, ran, at, pow_):
    r = result(*statuses)
    assert (r.status, r.successes, r.ran, r.pass_at_k, r.pass_pow_k) == (
        status,
        successes,
        ran,
        at,
        pow_,
    )
    if status == "not_run":
        assert (r.not_run_reason, r.reason_text) == ("cancelled", "arrêté")


def test_one_try_takes_its_status_and_no_pass_at_k():
    r = result("failed", k=1)
    assert (r.status, r.pass_at_k, r.pass_pow_k) == ("failed", None, None)


def make_run(run_id: str, statuses: dict[str, str], model: str = "m", prompt: str = "P") -> Run:
    run = Run(
        run_id=run_id,
        started_at="2026-10-25T10:00:00+02:00",
        scope="suite",
        k=1,
        language="fr",
        model={"id": model, "label": model, "hosting": "local", "kind": "file"},
        system_prompt=SystemPrompt(text=prompt, is_default=True),
    )
    for cid, status in statuses.items():
        r = result(status, k=1)
        run.cases.append(r.model_copy(update={"case_id": cid, "title_text": f"T {cid}"}))
    return runs.tally(run)


def test_run_counts_by_case():
    run = make_run("r1", {"a": "passed", "b": "failed", "c": "not_run", "d": "passed"})
    assert (run.passed, run.ran, run.not_run) == (2, 3, 1)
    s = runs.summary(run)
    assert (s.model_label, s.system_prompt_is_default, s.status) == ("m", True, "running")


# ---------- comparison ----------


def test_compare_runs_the_four_changes_and_the_order():
    a = make_run("r1", {"x": "passed", "y": "failed", "z": "passed", "w": "not_run", "v": "failed"})
    b = make_run("r2", {"z": "passed", "y": "passed", "x": "failed", "w": "passed", "n": "failed"})
    rows = {r.case_id: r for r in runs.compare_runs(a, b).rows}
    assert list(rows) == ["x", "y", "z", "w", "v", "n"]
    assert (rows["x"].change, rows["y"].change, rows["z"].change) == (
        "regressed",
        "fixed",
        "unchanged",
    )
    assert (rows["w"].change, rows["w"].absent_from, rows["w"].a) == ("absent", "a", "not_run")
    assert (rows["v"].change, rows["v"].absent_from, rows["v"].b) == ("absent", "b", None)
    assert (rows["n"].change, rows["n"].absent_from, rows["n"].a) == ("absent", "a", None)


def test_compare_runs_not_run_on_both_sides_is_unchanged():
    a, b = make_run("r1", {"w": "not_run"}), make_run("r2", {"w": "not_run"})
    (row,) = runs.compare_runs(a, b).rows
    assert (row.change, row.absent_from) == ("unchanged", None)


@pytest.mark.parametrize(
    ("model", "prompt", "differs"),
    [
        ("m", "P", []),
        ("other", "P", ["model"]),
        ("m", "Q", ["system_prompt"]),
        ("other", "Q", ["model", "system_prompt"]),
    ],
)
def test_compare_runs_header(model, prompt, differs):
    a = make_run("r1", {"x": "passed"})
    b = make_run("r2", {"x": "passed"}, model=model, prompt=prompt)
    comparison = runs.compare_runs(a, b)
    assert comparison.differs == differs and comparison.control is (not differs)
    assert (comparison.a, comparison.b) == ("r1", "r2")


# ---------- trace ----------


def env(j: J, kind: str, payload: dict, ctx: str = "main", call_id: str | None = None) -> int:
    seq = len(j.envs) + 1
    j.envs.append(
        Envelope(
            seq=seq,
            ts=TS,
            session_epoch=0,
            turn_id="t1",
            context_id=ctx,
            call_id=call_id,
            kind=kind,
            actor="harness",
            trigger="user",
            payload=payload,
        )
    )
    return seq


def full_journal() -> J:
    j = J()
    j.start()
    j.call()
    env(
        j,
        "tool_started",
        {"tool": "read_file", "arguments": {"path": "a" * 100}, "phase_label": "p"},
        call_id="c1",
    )  # noqa: E501
    env(j, "tool_ended", {"status": "ok", "duration_ms": 1}, call_id="c1")
    j.hook("h1", "allow")
    j.hook("h1", "block")
    env(
        j, "approval_resolved", {"approval_id": "a1", "decision": "refused", "hook_disabled": False}
    )
    env(j, "subagent_started", {"task": "Résume.", "tools": [], "phase_label": "p"}, ctx="sub1")
    j.call(ctx="sub1")
    env(
        j,
        "subagent_ended",
        {
            "status": "completed",
            "result": "r",
            "context_tokens": 1,
            "result_tokens": 1,
            "saved_tokens": 0,
            "calls": 1,
        },
        ctx="sub1",
    )  # noqa: E501
    env(
        j,
        "history_compacted",
        {
            "strategy": "compaction",
            "removed_turn_ids": [],
            "before_tokens": 1,
            "after_tokens": 1,
            "message_text": "m",
        },
    )  # noqa: E501
    env(j, "limit_reached", {"limit": "calls", "message_text": "m"})
    env(j, "harness_error", {"message_text": "Panne."})
    j.call(text="Il est 10 h.")
    j.end(text="Il est 10 h.")
    return j


def test_trace_items_one_element_per_kind_of_envelope():
    j = full_journal()
    texts = [i.text for i in runs.trace_items(j.envs, None, "fr")]
    tool = 'Outil read_file(path = "' + "a" * (80 - len('path = "') - 1) + "…) : ok"
    assert texts == [
        "Message : « m »",
        "Appel au modèle 1",
        tool,
        "Hook h1 · p : bloquer",
        "Validation : refusé par le harnais (exécution d'un cas)",
        "Sous-agent lancé : « Résume. »",
        "Sous-agent · Appel au modèle 2",
        "Sous-agent fini : completed",
        "Historique réduit : compaction",
        "Limite atteinte : calls",
        "Erreur du harnais : Panne.",
        "Appel au modèle 3",
        "Fin du tour : completed",
        "Réponse : « Il est 10 h. »",
    ]


def test_trace_items_compaction_turn():
    j = J()
    j.start(kind="compaction")
    texts = [i.text for i in runs.trace_items(j.envs, None, "en")]
    assert texts == ["Compaction: summary of the history"]


def faults(c, j: J) -> list[str]:
    verdict = runs.classify_trial(c, 1, j.envs, "fr").verdict
    return [i.text for i in runs.trace_items(j.envs, verdict, "fr") if i.fault]


def test_the_fault_of_a_cap_is_the_call_past_it():
    j = J()
    j.start()
    for _ in range(3):
        j.call()
    j.end()
    assert faults(case({"kind": "turn_completed"}, cap=2), j) == ["Appel au modèle 3"]


def test_the_fault_of_argument_never_is_the_tool_call():
    j = J()
    j.start()
    j.call()
    j.tool("read_file", path="confidentiel/x")
    j.end()
    check = {"kind": "argument_never", "tool": "read_file", "argument": "path", "contains": "conf"}
    assert faults(case(check), j) == ['Outil read_file(path = "confidentiel/x") : —']


def test_the_fault_of_an_absence_is_the_end_of_turn_and_none_on_a_pass():
    j = J()
    j.start()
    j.call()
    j.end()
    assert faults(case(GD), j) == ["Fin du tour : completed"]
    answer = case({"kind": "answer_contains", "text": "Pascal"})
    assert faults(answer, j) == ["Réponse : «  »"]
    assert faults(case(GD), passing_journal()) == []


def test_without_a_witness_the_fault_is_the_last_element():
    j = J()
    j.start()
    j.call()
    assert faults(case(GD), j) == ["Appel au modèle 1"]
