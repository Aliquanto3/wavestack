"""The runs of agent cases kept in memory (V1.5 CAP-4): their models, the classification
of a try, the aggregates (pass@k, pass^k), the comparison of two runs and a try's trace.

Pure: no I/O, no session, no clock. The executor (`session/agent_eval_runner.py`) fills
these models; the routes (`web/agent_eval_api.py`) dump them.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from wavestack.agent_eval.cases import AgentCase, NotRunReason, ProvenanceSource, RunStatus
from wavestack.agent_eval.checks import CaseVerdict, CheckVerdict, _Journal, verify
from wavestack.cloud import usd_price_fr
from wavestack.messages import msg
from wavestack.trace.catalog import ActiveModel
from wavestack.trace.envelope import Envelope

MAX_RUNS = 20  # finished runs kept; the oldest goes with its envelopes
PROMPT_START = 60  # characters of the system prompt in the view's header
ARGUMENTS_MAX = 80  # characters of a tool call's arguments in the trace
ANSWER_MAX = 300  # characters of the final answer in the trace
MESSAGE_MAX = 120  # characters of a turn's message in the trace

CaseStatus = Literal["pending", "running", "passed", "failed", "not_run"]
RunState = Literal["running", "done", "cancelled", "budget", "error"]
Change = Literal["regressed", "fixed", "unchanged", "absent"]


class TrialOutcome(BaseModel):
    trial: int  # 1..k
    status: RunStatus
    not_run_reason: NotRunReason | None = None
    reason_text: str | None = None  # why it was not run, in the run's language
    verdict: CaseVerdict | None = None  # None when not run before any turn
    failing: CheckVerdict | None = None  # the first check that fails (the cap included)
    model_calls: int = 0
    turn_ids: list[str] = []
    has_trace: bool = False  # envelopes exist (a try stopped midway included)


class CaseResult(BaseModel):
    case_id: str
    title_text: str
    brick: str | None
    brick_label_text: str | None
    source: ProvenanceSource
    max_model_calls: int
    k: int
    status: CaseStatus = "pending"
    not_run_reason: NotRunReason | None = None  # the case not run at all
    reason_text: str | None = None
    trials: list[TrialOutcome] = []
    successes: int = 0  # tries passed
    ran: int = 0  # tries run (passed + failed)
    pass_at_k: bool | None = None  # k = 3 only
    pass_pow_k: bool | None = None
    ignored_ids: list[str] = []  # ids of the case unknown to the session (decision 1)


class SystemPrompt(BaseModel):
    text: str
    is_default: bool


class Run(BaseModel):
    run_id: str
    started_at: str
    ended_at: str | None = None
    scope: Literal["suite", "case"]
    k: Literal[1, 3]
    language: Literal["fr", "en", "de"]
    model: ActiveModel | None = None
    system_prompt: SystemPrompt
    status: RunState = "running"
    error_text: str | None = None
    window_checked: bool = True  # False only with `check_window=False` (tests)
    cases: list[CaseResult] = []
    passed: int = 0  # counted by case
    ran: int = 0
    not_run: int = 0
    # The executor's own state, never dumped: « Arrêter » asked, and the case whose turns
    # carry `case_id` and `run_id`.
    stop_requested: bool = Field(default=False, exclude=True)
    case_tag: str | None = Field(default=None, exclude=True)


class RunSummary(BaseModel):
    run_id: str
    started_at: str
    ended_at: str | None
    scope: Literal["suite", "case"]
    k: int
    model_label: str | None
    system_prompt_is_default: bool
    status: RunState
    passed: int
    ran: int
    not_run: int


class TraceItem(BaseModel):
    seq: int
    context_id: str | None
    text: str
    fault: bool = False


class TrialTrace(BaseModel):
    items: list[TraceItem]
    failing: CheckVerdict | None
    model_calls: int


class CompareRow(BaseModel):
    case_id: str
    title_text: str
    a: RunStatus | None
    b: RunStatus | None
    change: Change
    absent_from: Literal["a", "b"] | None = None


class Comparison(BaseModel):
    a: str
    b: str
    differs: list[Literal["model", "system_prompt"]]
    control: bool
    rows: list[CompareRow]


# ---------- a try ----------


def approval_answer(case: AgentCase) -> bool:
    """The harness's answer to H5 during a case (decision 5): `approve` accepts."""
    return case.approval == "approve"


def _first_failing(verdict: CaseVerdict) -> CheckVerdict | None:
    return next((c for c in verdict.checks if not c.passed), None)


def _stopped_midway(envelopes: list[Envelope]) -> bool:
    """« Arrêter » reached the try: its last main turn did not end `completed` (or never
    ended)."""
    ended = [e for e in envelopes if e.kind == "turn_ended" and e.context_id in (None, "main")]
    return not ended or ended[-1].payload.get("status") != "completed"


def not_run(trial: int, reason: NotRunReason, text: str) -> TrialOutcome:
    return TrialOutcome(trial=trial, status="not_run", not_run_reason=reason, reason_text=text)


def cancelled_text(lang: str) -> str:
    return msg("agent_eval.not_run.cancelled", lang)


def budget_text(cap_usd: float, lang: str) -> str:
    return msg("agent_eval.not_run.budget", lang, cap=usd_price_fr(cap_usd, lang))


def classify_trial(
    case: AgentCase,
    trial: int,
    envelopes: Iterable[Envelope],
    lang: str,
    *,
    stop_requested: bool = False,
    cap_usd: float | None = None,
) -> TrialOutcome:
    """A try's outcome on its envelopes: `not_run` (`cancelled`) when « Arrêter » reached
    it, `not_run` (`budget`) when a cloud call was refused for the session's cap, else
    `verify`'s verdict."""
    envelopes = sorted(envelopes, key=lambda e: e.seq)
    turn_ids = list(
        dict.fromkeys(
            e.turn_id
            for e in envelopes
            if e.kind == "turn_started" and e.context_id in (None, "main") and e.turn_id
        )
    )
    calls = sum(1 for e in envelopes if e.kind == "model_call_started")
    common = {"turn_ids": turn_ids, "has_trace": bool(envelopes), "model_calls": calls}
    if stop_requested and _stopped_midway(envelopes):
        return not_run(trial, "cancelled", cancelled_text(lang)).model_copy(update=common)
    if any(
        e.kind == "harness_error" and e.payload.get("cause") == "max_session_usd" for e in envelopes
    ):
        text = budget_text(cap_usd or 0.0, lang)
        return not_run(trial, "budget", text).model_copy(update=common)
    verdict = verify(case, envelopes, lang)
    return TrialOutcome(
        trial=trial,
        status="passed" if verdict.passed else "failed",
        verdict=verdict,
        failing=_first_failing(verdict),
        turn_ids=turn_ids,
        has_trace=bool(envelopes),
        model_calls=verdict.model_calls,
    )


# ---------- a case, a run ----------


def settle_case(result: CaseResult) -> CaseResult:
    """The case's status and aggregates from its tries, in place. The status: `not_run`
    without a try run (the first try's reason), else the strict majority of the tries run
    (k = 1: its try's). pass@k and pass^k for k = 3 only, final as soon as they are known."""
    trials = result.trials
    result.successes = sum(1 for t in trials if t.status == "passed")
    result.ran = sum(1 for t in trials if t.status in ("passed", "failed"))
    if result.ran == 0:
        first = next((t for t in trials if t.status == "not_run"), None)
        result.status = "not_run"
        result.not_run_reason = first.not_run_reason if first else None
        result.reason_text = first.reason_text if first else None
    else:
        result.status = "passed" if result.successes > result.ran / 2 else "failed"
        result.not_run_reason = result.reason_text = None
    if result.k == 3:
        failed = result.ran - result.successes
        complete = result.ran == result.k
        result.pass_at_k = True if result.successes else (False if complete else None)
        result.pass_pow_k = False if failed else (True if complete else None)
    else:
        result.pass_at_k = result.pass_pow_k = None
    return result


def tally(run: Run) -> Run:
    """The run's counts, by case, in place."""
    run.passed = sum(1 for c in run.cases if c.status == "passed")
    run.ran = sum(1 for c in run.cases if c.status in ("passed", "failed"))
    run.not_run = sum(1 for c in run.cases if c.status == "not_run")
    return run


def summary(run: Run) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        started_at=run.started_at,
        ended_at=run.ended_at,
        scope=run.scope,
        k=run.k,
        model_label=run.model.label if run.model is not None else None,
        system_prompt_is_default=run.system_prompt.is_default,
        status=run.status,
        passed=run.passed,
        ran=run.ran,
        not_run=run.not_run,
    )


# ---------- comparison ----------


def _played(status: str | None) -> str | None:
    return status if status in ("passed", "failed") else None


def compare_runs(a: Run, b: Run) -> Comparison:
    """A and B case by case: A's cases in their order, then B's absent from A. A case
    `not_run` counts as absent; absent from both (not run twice): `unchanged`."""
    in_a = {c.case_id: c for c in a.cases}
    in_b = {c.case_id: c for c in b.cases}
    rows = []
    for case_id in [*in_a, *(i for i in in_b if i not in in_a)]:
        ca, cb = in_a.get(case_id), in_b.get(case_id)
        sa = ca.status if ca is not None else None
        sb = cb.status if cb is not None else None
        pa, pb = _played(sa), _played(sb)
        absent_from = None
        if pa is None and pb is None:
            change = "unchanged"
        elif pa is None:
            change, absent_from = "absent", "a"
        elif pb is None:
            change, absent_from = "absent", "b"
        elif pa == pb:
            change = "unchanged"
        else:
            change = "regressed" if pa == "passed" else "fixed"
        rows.append(
            CompareRow(
                case_id=case_id,
                title_text=(ca or cb).title_text,  # type: ignore[union-attr]
                a=sa if sa in ("passed", "failed", "not_run") else None,
                b=sb if sb in ("passed", "failed", "not_run") else None,
                change=change,
                absent_from=absent_from,
            )
        )
    differs: list[Literal["model", "system_prompt"]] = []
    model_a = a.model.id if a.model is not None else None
    model_b = b.model.id if b.model is not None else None
    if model_a != model_b:
        differs.append("model")
    if a.system_prompt.text != b.system_prompt.text:
        differs.append("system_prompt")
    return Comparison(a=a.run_id, b=b.run_id, differs=differs, control=not differs, rows=rows)


# ---------- trace ----------


def _cut(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _arguments(arguments: object) -> str:
    if not isinstance(arguments, dict):
        return ""
    return _cut(", ".join(f'{k} = "{v}"' for k, v in arguments.items()), ARGUMENTS_MAX)


def _decision(decision: str, lang: str) -> str:
    if decision in ("block", "ask_human"):
        return msg(f"agent_eval.decisions.{decision}", lang)
    return decision


def trace_items(
    envelopes: Iterable[Envelope], verdict: CaseVerdict | None, lang: str
) -> list[TraceItem]:
    """A try's trace in `seq` order, its texts from `messages.yaml`; the faulty element is
    the last whose `seq` is at most the failing check's (the last element when that check
    has no `seq`); none for a try passed."""
    events = sorted(envelopes, key=lambda e: e.seq)
    ended_tools = {
        e.call_id: e.payload.get("status") for e in events if e.kind == "tool_ended" and e.call_id
    }
    journal = _Journal(events)
    items: list[TraceItem] = []
    calls = 0

    def add(env: Envelope, key: str, **kw: object) -> None:
        text = msg(f"agent_eval.trace.{key}", lang, **kw)
        sub = env.context_id not in (None, "main")
        if sub and not key.startswith("subagent_"):
            text = msg("agent_eval.trace.sub", lang, text=text)
        items.append(TraceItem(seq=env.seq, context_id=env.context_id, text=text))

    for env in events:
        p, kind, main = env.payload, env.kind, env.context_id in (None, "main")
        if kind == "turn_started" and main:
            if p.get("kind") == "compaction":
                add(env, "compaction")
            else:
                add(env, "message", text=_cut(p.get("message", ""), MESSAGE_MAX))
        elif kind == "model_call_started":
            calls += 1
            add(env, "model_call", n=calls)
        elif kind == "tool_started":
            status = ended_tools.get(env.call_id, "—")
            arguments = _arguments(p.get("arguments"))
            add(env, "tool", tool=p.get("tool", ""), arguments=arguments, status=status)
        elif kind == "hook_decided" and p.get("decision") != "allow":
            add(
                env,
                "hook",
                hook=p.get("hook_text") or p.get("hook", ""),
                point=p.get("point_text") or p.get("point", ""),
                decision=_decision(p.get("decision", ""), lang),
            )
        elif kind == "approval_resolved":
            decision = p.get("decision", "")
            label = (
                msg(f"hooks.h2.approval.{decision}", lang)
                if decision in ("approved", "refused", "cancelled")
                else decision
            )
            add(env, "approval", decision=label)
        elif kind == "subagent_started":
            add(env, "subagent_started", task=_cut(p.get("task", ""), MESSAGE_MAX))
        elif kind == "subagent_ended":
            add(env, "subagent_ended", status=p.get("status", ""))
        elif kind == "history_compacted":
            add(env, "compacted", strategy=p.get("strategy", ""))
        elif kind == "limit_reached":
            add(env, "limit", limit=p.get("limit", ""))
        elif kind == "harness_error":
            add(env, "error", message=_cut(p.get("message_text", ""), MESSAGE_MAX))
        elif kind == "turn_ended" and main:
            add(env, "ended", status=p.get("status", ""))
            if journal.witness is not None and env.seq == journal.witness.seq:
                add(env, "answer", text=_cut(journal.answer(), ANSWER_MAX))
    failing = _first_failing(verdict) if verdict is not None and not verdict.passed else None
    if failing is not None and items:
        _mark_fault(items, failing)
    return items


def _mark_fault(items: list[TraceItem], failing: CheckVerdict) -> None:
    if failing.seq is None:
        items[-1].fault = True
        return
    before = [i for i in items if i.seq <= failing.seq]
    if not before:
        items[0].fault = True
        return
    top = before[-1].seq
    same = [i for i in before if i.seq == top]
    # The answer element shares the end of turn's `seq`: it is the fault of an answer check.
    pick = same[-1] if failing.kind == "answer_contains" else same[0]
    pick.fault = True
