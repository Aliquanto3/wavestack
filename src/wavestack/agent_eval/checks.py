"""`verify(case, envelopes)`: a case's checks read in its journal (V1.5 CAP-1).

Pure, as a hook (AD-13): it reads only the envelopes it receives, never the `Journal`, the
disk, the model nor the clock. The texts come from `messages.yaml` in `lang`, as a hook's.

Envelopes read: those of the turns the case started (the prompt's turn, the compaction turn
if any, and the message sent again after it), every context (`main` and `sub{n}`). The
witness is the `turn_ended` of the last message turn: without it, every check fails
(« tour incomplet »). An expected event that is absent fails the check.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from wavestack import config
from wavestack.agent_eval.cases import (
    AgentCase,
    AnswerContainsCheck,
    ArgumentNeverCheck,
    Check,
    CheckKind,
    HookDecidedCheck,
    SubagentCalledCheck,
    ToolCalledCheck,
    ToolNotCalledCheck,
    TurnCompletedCheck,
)
from wavestack.messages import msg
from wavestack.trace.envelope import Envelope


class CheckVerdict(BaseModel):
    kind: CheckKind
    params: dict[str, Any]
    passed: bool
    reason_text: str
    # The envelope that decided: the faulty one, or the witness for an absence.
    seq: int | None = None


class CaseVerdict(BaseModel):
    case_id: str
    passed: bool  # every check passed, the cap included
    checks: list[CheckVerdict]
    model_calls: int


def _is_main(env: Envelope) -> bool:
    return env.context_id in (None, "main")


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else str(value)


class _Journal:
    """The case's envelopes in `seq` order, and what the checks share."""

    def __init__(self, envelopes: Iterable[Envelope]) -> None:
        self.events = sorted(envelopes, key=lambda e: e.seq)
        self.turns = [e for e in self.events if e.kind == "turn_started" and _is_main(e)]
        messages = [t for t in self.turns if t.payload.get("kind", "message") == "message"]
        self.last_turn_id = messages[-1].turn_id if messages else None
        self.witness = (
            next(
                (
                    e
                    for e in reversed(self.events)
                    if e.kind == "turn_ended" and _is_main(e) and e.turn_id == self.last_turn_id
                ),
                None,
            )
            if self.last_turn_id is not None
            else None
        )

    def of(self, kind: str) -> list[Envelope]:
        return [e for e in self.events if e.kind == kind]

    def tool_calls(self, tool: str) -> list[Envelope]:
        return [e for e in self.of("tool_started") if e.payload.get("tool") == tool]

    def answer(self) -> str:
        """The final answer: `turn_ended.text` when present, else the `text` deltas of the
        main context's last call in the last message turn."""
        assert self.witness is not None
        text = self.witness.payload.get("text")
        if text is not None:
            return text
        starts = [
            e
            for e in self.of("model_call_started")
            if _is_main(e) and e.turn_id == self.last_turn_id
        ]
        if not starts:
            return ""
        first = starts[-1].seq
        return "".join(
            e.payload.get("text", "")
            for e in self.of("model_delta")
            if _is_main(e)
            and first < e.seq < self.witness.seq
            and e.payload.get("channel") == "text"
        )


def _params(check: Check) -> dict[str, Any]:
    return check.model_dump(exclude={"kind"}, exclude_none=True)


def _verdict(check: Check, passed: bool, reason: str, seq: int | None) -> CheckVerdict:
    return CheckVerdict(
        kind=check.kind, params=_params(check), passed=passed, reason_text=reason, seq=seq
    )


def _tool_called(c: ToolCalledCheck, j: _Journal, lang: str) -> CheckVerdict:
    assert j.witness is not None
    calls = j.tool_calls(c.tool)
    if not calls:
        return _verdict(
            c, False, msg("agent_eval.tool_called.missing", lang, tool=c.tool), j.witness.seq
        )
    if c.before is not None:
        befores = j.tool_calls(c.before)
        if befores and befores[0].seq < calls[0].seq:
            reason = msg("agent_eval.tool_called.late", lang, tool=c.tool, before=c.before)
            return _verdict(c, False, reason, befores[0].seq)
        reason = msg("agent_eval.tool_called.in_order", lang, tool=c.tool, before=c.before)
        return _verdict(c, True, reason, calls[0].seq)
    return _verdict(c, True, msg("agent_eval.tool_called.passed", lang, tool=c.tool), calls[0].seq)


def _tool_not_called(c: ToolNotCalledCheck, j: _Journal, lang: str) -> CheckVerdict:
    assert j.witness is not None
    calls = j.tool_calls(c.tool)
    if calls:
        return _verdict(
            c, False, msg("agent_eval.tool_not_called.failed", lang, tool=c.tool), calls[0].seq
        )
    return _verdict(
        c, True, msg("agent_eval.tool_not_called.passed", lang, tool=c.tool), j.witness.seq
    )


def _argument_never(c: ArgumentNeverCheck, j: _Journal, lang: str) -> CheckVerdict:
    assert j.witness is not None
    wanted = c.contains.casefold()
    for call in j.tool_calls(c.tool):
        arguments = call.payload.get("arguments") or {}
        if c.argument in arguments:
            value = _as_text(arguments[c.argument])
            if wanted in value.casefold():
                reason = msg(
                    "agent_eval.argument_never.failed",
                    lang,
                    tool=c.tool,
                    argument=c.argument,
                    value=value,
                )
                return _verdict(c, False, reason, call.seq)
    reason = msg(
        "agent_eval.argument_never.passed",
        lang,
        tool=c.tool,
        argument=c.argument,
        contains=c.contains,
    )
    return _verdict(c, True, reason, j.witness.seq)


def _answer_contains(c: AnswerContainsCheck, j: _Journal, lang: str) -> CheckVerdict:
    assert j.witness is not None
    passed = _normalized(c.text) in _normalized(j.answer())
    key = "passed" if passed else "failed"
    return _verdict(
        c, passed, msg(f"agent_eval.answer_contains.{key}", lang, text=c.text), j.witness.seq
    )


def _hook_decided(c: HookDecidedCheck, j: _Journal, lang: str) -> CheckVerdict:
    assert j.witness is not None
    found = [
        e
        for e in j.of("hook_decided")
        if e.payload.get("hook") == c.hook and e.payload.get("decision") == c.decision
    ]
    decision = msg(f"agent_eval.decisions.{c.decision}", lang)
    if found:
        reason = msg("agent_eval.hook_decided.passed", lang, hook=c.hook, decision=decision)
        return _verdict(c, True, reason, found[0].seq)
    reason = msg("agent_eval.hook_decided.failed", lang, hook=c.hook, decision=decision)
    return _verdict(c, False, reason, j.witness.seq)


def _subagent_called(c: SubagentCalledCheck, j: _Journal, lang: str) -> CheckVerdict:
    assert j.witness is not None
    found = j.of("subagent_started")
    if found:
        return _verdict(c, True, msg("agent_eval.subagent_called.passed", lang), found[0].seq)
    return _verdict(c, False, msg("agent_eval.subagent_called.failed", lang), j.witness.seq)


def _turn_completed(c: TurnCompletedCheck, j: _Journal, lang: str, case: AgentCase) -> CheckVerdict:
    """Every turn of the case ends `completed`, and no `harness_error`. A turn refused for
    an overflow that `on_overflow` then handled (a later message turn exists) is the planned
    path of the case, not a fault: neither its status nor its errors count."""
    assert j.witness is not None
    ended = {e.turn_id: e for e in j.of("turn_ended") if _is_main(e)}
    last_seq = j.witness.seq
    tolerated: set[str | None] = set()
    for turn in j.turns:
        end = ended.get(turn.turn_id)
        if end is None:
            return _verdict(c, False, msg("agent_eval.incomplete", lang), last_seq)
        status = end.payload.get("status")
        if status == "overflow" and case.on_overflow != "none" and turn.turn_id != j.last_turn_id:
            tolerated.add(turn.turn_id)
            continue
        if status != "completed":
            reason = msg("agent_eval.turn_completed.status", lang, status=status)
            return _verdict(c, False, reason, end.seq)
    for error in j.of("harness_error"):
        if error.turn_id not in tolerated:
            reason = msg(
                "agent_eval.turn_completed.error",
                lang,
                message=error.payload.get("message_text", ""),
            )
            return _verdict(c, False, reason, error.seq)
    return _verdict(c, True, msg("agent_eval.turn_completed.passed", lang), last_seq)


def _model_calls_max(
    case: AgentCase, j: _Journal, calls: list[Envelope], lang: str
) -> CheckVerdict:
    assert j.witness is not None
    cap = case.max_model_calls
    passed = len(calls) <= cap
    reason = msg("agent_eval.model_calls_max", lang, count=len(calls), max=cap)
    seq = j.witness.seq if passed else calls[cap].seq
    return CheckVerdict(
        kind="model_calls_max", params={"max": cap}, passed=passed, reason_text=reason, seq=seq
    )


def verify(
    case: AgentCase, envelopes: Iterable[Envelope], lang: str = config.DEFAULT_LANGUAGE
) -> CaseVerdict:
    """The case's verdict on its envelopes: its checks in order, then `model_calls_max`
    (every `model_call_started`, the sub-agent's included). Without the witness, every check
    fails with « tour incomplet » and `seq` `None`."""
    j = _Journal(envelopes)
    calls = j.of("model_call_started")
    if j.witness is None:
        reason = msg("agent_eval.incomplete", lang)
        verdicts = [_verdict(c, False, reason, None) for c in case.checks]
        verdicts.append(
            CheckVerdict(
                kind="model_calls_max",
                params={"max": case.max_model_calls},
                passed=False,
                reason_text=reason,
                seq=None,
            )
        )
        return CaseVerdict(case_id=case.id, passed=False, checks=verdicts, model_calls=len(calls))
    verdicts = []
    for c in case.checks:
        if isinstance(c, ToolCalledCheck):
            verdicts.append(_tool_called(c, j, lang))
        elif isinstance(c, ToolNotCalledCheck):
            verdicts.append(_tool_not_called(c, j, lang))
        elif isinstance(c, ArgumentNeverCheck):
            verdicts.append(_argument_never(c, j, lang))
        elif isinstance(c, AnswerContainsCheck):
            verdicts.append(_answer_contains(c, j, lang))
        elif isinstance(c, HookDecidedCheck):
            verdicts.append(_hook_decided(c, j, lang))
        elif isinstance(c, SubagentCalledCheck):
            verdicts.append(_subagent_called(c, j, lang))
        else:
            verdicts.append(_turn_completed(c, j, lang, case))
    verdicts.append(_model_calls_max(case, j, calls, lang))
    return CaseVerdict(
        case_id=case.id,
        passed=all(v.passed for v in verdicts),
        checks=verdicts,
        model_calls=len(calls),
    )
