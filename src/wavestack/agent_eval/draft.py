"""« En faire un cas » (V1.5 CAP-3): the draft of a case rebuilt from a finished turn of the
journal, and the case the form turns it into.

Pure, as `verify` (AD-13): it reads only the envelopes it receives. The draft is a function of
the original turn's `turn_started` (`seq` `S`): the configuration and the history read the
envelopes of `seq < S`; the tools, calls and answer read those of the turns the case would
play (`verdict_turn_ids`). One pass over the journal, sorted by `seq`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from wavestack.agent_eval.cases import AgentCase, HistoryExchange, Provenance
from wavestack.agent_eval.checks import _Journal
from wavestack.trace.catalog import ActiveModel, TurnStatus
from wavestack.trace.envelope import Envelope

RefusalReason = Literal["unknown_turn", "not_a_message", "case_turn", "unfinished"]
NotKept = Literal["mcp_lazy", "rag_rerank"]
HistoryNote = Literal["compacted", "unavailable"]
Approval = Literal["refuse", "approve"]
OnOverflow = Literal["none", "compaction", "sliding_window"]


class DraftRefused(Exception):
    """The turn cannot become a case."""

    def __init__(self, reason: RefusalReason) -> None:
        super().__init__(reason)
        self.reason: RefusalReason = reason


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SystemPromptDraft(_Model):
    text: str
    is_default: bool


class ToolCallDraft(_Model):
    seq: int
    tool: str
    arguments: dict[str, Any]
    status: str | None = None
    context_id: str | None = None


class HookDecisionDraft(_Model):
    hook: str
    decision: str


class CaseDraft(_Model):
    turn_id: str
    seq: int
    date: str
    origin_status: TurnStatus
    model: ActiveModel | None = None
    prompt: str
    bricks: list[str]
    tools: list[str]
    hooks: list[str]
    skills: list[str]
    mcp_servers: list[str]
    not_kept: list[NotKept]
    window: int | None = None
    system_prompt: SystemPromptDraft
    history: list[HistoryExchange]
    history_available: bool
    history_note: HistoryNote | None = None
    approval: Approval
    on_overflow: OnOverflow
    verdict_turn_ids: list[str]
    tool_calls: list[ToolCallDraft]
    hooks_decided: list[HookDecisionDraft]
    subagent_called: bool
    model_calls: int
    answer_text: str
    suggested_max_model_calls: int


class CaseForm(_Model):
    """What the formatter types (the route's body); `checks` are validated by the route."""

    turn_id: str
    title_text: str
    symptom_text: str
    assertion_text: str
    prompt: str
    include_history: bool
    freeze_system_prompt: bool
    approval: Approval
    on_overflow: OnOverflow
    max_model_calls: int
    checks: list[dict[str, Any]]


def _is_main(env: Envelope) -> bool:
    return env.context_id in (None, "main")


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value if isinstance(value, dict) else {}


class _HistoryState:
    """The main chat's history as the session holds it, rebuilt from the journal."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str]] = []  # (turn_id, user, assistant)
        self.unavailable = False
        self.compacted = False

    def snapshot(self) -> tuple[tuple[tuple[str, str, str], ...], bool, bool]:
        return tuple(self.entries), self.unavailable, self.compacted

    def restore(self, snap: tuple[tuple[tuple[str, str, str], ...], bool, bool]) -> None:
        entries, self.unavailable, self.compacted = snap
        self.entries = list(entries)

    def clear(self) -> None:
        self.entries, self.unavailable, self.compacted = [], False, False


class _Turn:
    """What the pass learns about a main-context turn."""

    __slots__ = ("ended_seq", "kind", "message", "status", "text", "calls", "buffer")

    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        self.message = message
        self.status: str | None = None
        self.ended_seq: int | None = None
        self.text: str | None = None  # `turn_ended.text`
        self.calls = 0  # main-context model calls
        self.buffer: list[str] = []  # text deltas of the last main call

    def answer(self) -> str | None:
        """`None` when it cannot be found (no text kept, no call)."""
        if self.text is not None:
            return self.text
        if not self.calls:
            return None
        return "".join(self.buffer)


def reconstitute_draft(envelopes: Sequence[Envelope], turn_id: str) -> CaseDraft:
    """The draft of the case of `turn_id`. Raises `DraftRefused`."""
    events = sorted(envelopes, key=lambda e: e.seq)
    start = next(
        (e for e in events if e.kind == "turn_started" and _is_main(e) and e.turn_id == turn_id),
        None,
    )
    if start is None:
        raise DraftRefused("unknown_turn")
    if start.payload.get("kind", "message") != "message":
        raise DraftRefused("not_a_message")
    if start.payload.get("case_id"):
        raise DraftRefused("case_turn")
    origin_end = next(
        (e for e in events if e.kind == "turn_ended" and _is_main(e) and e.turn_id == turn_id),
        None,
    )
    if origin_end is None:
        raise DraftRefused("unfinished")
    s = start.seq

    # ---- the single pass over the envelopes before the turn (and the turns' own events) ----
    history = _HistoryState()
    turns: dict[str, _Turn] = {}
    message_ids: list[str] = []  # the main message turns before `s`, in order
    snapshots: dict[str, Any] = {}
    last_bricks: Envelope | None = None
    last_window: Envelope | None = None
    compactions: list[Envelope] = []  # history_compacted events before `s`
    by_turn: dict[str, list[Envelope]] = {}

    for e in events:
        if e.turn_id is not None and e.kind in _TURN_KINDS:
            by_turn.setdefault(e.turn_id, []).append(e)
        if e.seq > s:
            continue
        kind = e.kind
        if kind == "bricks_changed":
            last_bricks = e
        elif kind == "context_window_state":
            last_window = e
        elif kind in ("conversation_cleared", "harness_reset"):
            history.clear()
        elif kind == "turn_started" and _is_main(e) and e.turn_id is not None:
            info = _Turn(e.payload.get("kind", "message"), e.payload.get("message", ""))
            turns[e.turn_id] = info
            if info.kind == "message":
                replay_of = e.payload.get("replay_of")
                if replay_of:
                    if replay_of in snapshots:
                        history.restore(snapshots[replay_of])
                    else:
                        history.entries, history.unavailable = [], True
                snapshots[e.turn_id] = history.snapshot()
                if e.seq < s:
                    message_ids.append(e.turn_id)
        elif kind == "model_call_started" and _is_main(e) and e.turn_id in turns:
            turns[e.turn_id].calls += 1
            turns[e.turn_id].buffer = []
        elif kind == "model_delta" and _is_main(e) and e.turn_id in turns:
            if e.payload.get("channel") == "text":
                turns[e.turn_id].buffer.append(e.payload.get("text", ""))
        elif kind == "turn_ended" and _is_main(e) and e.turn_id in turns:
            info = turns[e.turn_id]
            info.status, info.ended_seq = e.payload.get("status"), e.seq
            info.text = e.payload.get("text")
            if info.kind == "message" and info.status == "completed":
                answer = info.answer()
                if answer is None:
                    history.unavailable = True
                else:
                    history.entries.append((e.turn_id, info.message, answer))
        elif kind == "history_compacted":
            compactions.append(e)
            removed = set(e.payload.get("removed_turn_ids") or [])
            history.entries = [x for x in history.entries if x[0] not in removed]
            history.compacted = True
            if e.payload.get("strategy") == "compaction":
                summary = e.payload.get("summary_text")
                holder = turns.get(e.turn_id) if e.turn_id is not None else None
                if summary is None or holder is None or e.turn_id is None:
                    history.unavailable = True
                else:
                    history.entries.insert(0, (e.turn_id, holder.message, summary))

    # The history of the draft: what the session held when the turn started...
    state = history.snapshot()
    verdict_ids = [turn_id]
    on_overflow: OnOverflow = "none"
    previous = message_ids[-1] if message_ids else None
    prev = turns.get(previous) if previous else None
    if (
        previous is not None
        and prev is not None
        and prev.status == "overflow"
        and prev.message == start.payload.get("message")
        and prev.ended_seq is not None
    ):
        between = [c for c in compactions if c.seq > prev.ended_seq]
        if between:
            applied = between[-1]
            on_overflow = applied.payload.get("strategy", "none")
            compaction_turn = applied.turn_id
            verdict_ids = [previous]
            if (
                on_overflow == "compaction"
                and compaction_turn is not None
                and compaction_turn != previous
                and compaction_turn in turns
                and turns[compaction_turn].kind == "compaction"
            ):
                verdict_ids.append(compaction_turn)
            verdict_ids.append(turn_id)
            # ...or, after an overflow, what it held before the strategy: it must overflow again.
            state = snapshots[previous]
    entries, unavailable, compacted = state

    # ---- configuration ----
    bricks_payload = _dict(last_bricks.payload) if last_bricks is not None else {}
    cards = [_dict(c) for c in bricks_payload.get("bricks") or []]
    by_id = {c.get("id"): c for c in cards}

    def enabled(card_id: str) -> list[str]:
        return [
            o["id"]
            for o in (_dict(x) for x in by_id.get(card_id, {}).get("options") or [])
            if o.get("enabled")
        ]

    wanted = [c["id"] for c in cards if c.get("wanted")]
    not_kept: list[NotKept] = []
    mcp = by_id.get("mcp", {})
    if mcp.get("wanted") and mcp.get("mode") == "lazy":
        not_kept.append("mcp_lazy")
    rerank = _dict(by_id.get("rag", {}).get("rerank"))
    if by_id.get("rag", {}).get("wanted") and rerank.get("enabled"):
        not_kept.append("rag_rerank")
    system = _dict(bricks_payload.get("system_prompt"))
    window_payload = last_window.payload if last_window is not None else {}
    window = (
        window_payload.get("configured")
        if window_payload.get("hosting") in ("file", "server")
        else None
    )

    # ---- what the case's turns did ----
    ends = {turn_id: origin_end.seq} | {
        i: turns[i].ended_seq for i in verdict_ids if i != turn_id and i in turns
    }
    case_events = sorted(
        (e for i in verdict_ids for e in by_turn.get(i, []) if e.seq <= (ends.get(i) or e.seq)),
        key=lambda e: e.seq,
    )
    ended = {
        e.call_id: e.payload.get("status")
        for e in case_events
        if e.kind == "tool_ended" and e.call_id is not None
    }
    tool_calls = [
        ToolCallDraft(
            seq=e.seq,
            tool=e.payload.get("tool", ""),
            arguments=dict(e.payload.get("arguments") or {}),
            status=ended.get(e.call_id) if e.call_id is not None else None,
            context_id=e.context_id,
        )
        for e in case_events
        if e.kind == "tool_started"
    ]
    model_calls = sum(1 for e in case_events if e.kind == "model_call_started")
    journal = _Journal(case_events)
    approved = any(
        e.kind == "approval_resolved" and e.payload.get("decision") == "approved"
        for e in case_events
    )
    return CaseDraft(
        turn_id=turn_id,
        seq=s,
        date=start.ts.isoformat(),
        origin_status=origin_end.payload.get("status", "error"),
        model=_model(start.payload.get("active_model")),
        prompt=start.payload.get("message", ""),
        bricks=wanted,
        tools=enabled("tools"),
        hooks=enabled("hooks"),
        skills=enabled("skills"),
        mcp_servers=enabled("mcp"),
        not_kept=not_kept,
        window=window,
        system_prompt=SystemPromptDraft(
            text=system.get("text", ""), is_default=bool(system.get("is_default", True))
        ),
        history=[]
        if unavailable
        else [HistoryExchange(user=u, assistant=a) for _, u, a in entries],
        history_available=not unavailable,
        history_note="unavailable" if unavailable else ("compacted" if compacted else None),
        approval="approve" if approved else "refuse",
        on_overflow=on_overflow,
        verdict_turn_ids=verdict_ids,
        tool_calls=tool_calls,
        hooks_decided=[
            HookDecisionDraft(
                hook=e.payload.get("hook", ""), decision=e.payload.get("decision", "")
            )
            for e in case_events
            if e.kind == "hook_decided"
        ],
        subagent_called=any(e.kind == "subagent_started" for e in case_events),
        model_calls=model_calls,
        answer_text=journal.answer(),
        suggested_max_model_calls=max(1, model_calls),
    )


# The kinds the draft reads inside the case's turns.
_TURN_KINDS = frozenset(
    {
        "turn_started",
        "turn_ended",
        "tool_started",
        "tool_ended",
        "hook_decided",
        "subagent_started",
        "model_call_started",
        "model_delta",
        "approval_resolved",
    }
)


def _model(value: Any) -> ActiveModel | None:
    return ActiveModel.model_validate(value) if value else None


def to_case(draft: CaseDraft, form: CaseForm, case_id: str) -> AgentCase:
    """The case the form describes. Raises `pydantic.ValidationError` on an invalid value."""
    return AgentCase.model_validate(
        {
            "id": case_id,
            "title_text": form.title_text,
            "symptom_text": form.symptom_text,
            "assertion_text": form.assertion_text,
            "prompt": form.prompt,
            "history": (
                [h.model_dump() for h in draft.history]
                if form.include_history and draft.history_available
                else []
            ),
            "bricks": draft.bricks,
            "tools": draft.tools,
            "hooks": draft.hooks,
            "skills": draft.skills,
            "mcp_servers": draft.mcp_servers,
            "window": draft.window,
            "system_prompt": draft.system_prompt.text if form.freeze_system_prompt else None,
            "approval": form.approval,
            "on_overflow": form.on_overflow,
            "max_model_calls": form.max_model_calls,
            "checks": form.checks,
            "provenance": Provenance(
                source="séance",
                date=draft.date,
                model=draft.model,
                turn_id=draft.turn_id,
                system_prompt_text=draft.system_prompt.text,
                fixed_in=None,
            ).model_dump(),
        }
    )
