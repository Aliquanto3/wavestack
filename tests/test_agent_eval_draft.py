"""V1.5 story 3: `reconstitute_draft` and `to_case` on hand-built journals."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from wavestack.agent_eval.draft import CaseForm, DraftRefused, reconstitute_draft, to_case
from wavestack.trace.envelope import Envelope

TS = datetime(2026, 10, 25, 9, 30, tzinfo=UTC)
MODEL = {"id": "m1", "label": "Fake", "hosting": "local", "kind": "file"}


def card(card_id: str, wanted: bool = True, options: tuple[tuple[str, bool], ...] = (), **extra):
    return {
        "id": card_id,
        "label_text": card_id,
        "category": "context",
        "category_text": "c",
        "hosting_text": "h",
        "explanation_text": [],
        "wanted": wanted,
        "available": True,
        "pending": False,
        "options": [
            {"id": i, "label_text": i, "enabled": on, "hosting_text": "h", "network": False}
            for i, on in options
        ],
    } | extra


class J:
    def __init__(self) -> None:
        self.envs: list[Envelope] = []

    def add(
        self, kind: str, payload: dict, turn: str | None = None, ctx: str = "main", **kw
    ) -> int:
        seq = len(self.envs) + 1
        self.envs.append(
            Envelope(
                seq=seq,
                ts=TS,
                session_epoch=0,
                turn_id=turn,
                context_id=ctx,
                kind=kind,
                actor="harness",
                trigger="user",
                payload=payload,
                **kw,
            )
        )
        return seq

    def bricks(self, cards=None, text: str = "Sys", default: bool = True) -> int:
        cards = (
            cards
            if cards is not None
            else [
                card("short_memory"),
                card("tools", options=(("get_datetime", True), ("calc", False))),
            ]
        )
        return self.add(
            "bricks_changed",
            {"bricks": cards, "system_prompt": {"text": text, "is_default": default}},
        )

    def window(self, hosting: str = "file", configured: int = 4096) -> int:
        return self.add(
            "context_window_state",
            {
                "configured": configured,
                "default": 4096,
                "window": configured,
                "window_source": "configured",
                "hosting": hosting,
                "read_note_text": "n",
                "choices": [],
            },
        )

    def start(self, turn: str, message: str = "Bonjour", **payload) -> int:
        return self.add(
            "turn_started",
            {"message": message, "kind": "message", "active_model": MODEL} | payload,
            turn,
        )

    def call(self, turn: str, text: str = "", ctx: str = "main") -> int:
        seq = self.add("model_call_started", {"phase_label": "p"}, turn, ctx)
        if text:
            self.add("model_delta", {"channel": "text", "text": text}, turn, ctx)
        return seq

    def end(self, turn: str, status: str = "completed", text: str | None = None) -> int:
        payload = {"status": status} | ({"text": text} if text is not None else {})
        return self.add("turn_ended", payload, turn)

    def exchange(self, turn: str, message: str, answer: str, status: str = "completed") -> None:
        self.start(turn, message)
        self.call(turn, answer)
        self.end(turn, status)

    def tool(
        self, turn: str, tool: str, ctx: str = "main", call_id: str | None = None, **args
    ) -> int:
        return self.add(
            "tool_started",
            {"tool": tool, "arguments": args, "phase_label": "p"},
            turn,
            ctx,
            call_id=call_id,
        )

    def compaction(self, turn: str, removed: list[str], summary: str | None) -> None:
        self.add(
            "turn_started",
            {"message": "Résume", "kind": "compaction", "active_model": MODEL},
            turn,
        )
        self.add(
            "history_compacted",
            {
                "strategy": "compaction",
                "removed_turn_ids": removed,
                "summary_text": summary,
                "before_tokens": 10,
                "after_tokens": 5,
                "message_text": "m",
            },
            turn,
        )
        self.end(turn)

    def sliding(self, removed: list[str], turn: str | None = None) -> int:
        return self.add(
            "history_compacted",
            {
                "strategy": "sliding_window",
                "removed_turn_ids": removed,
                "before_tokens": 10,
                "after_tokens": 5,
                "message_text": "m",
            },
            turn,
        )


def draft(j: J, turn: str):
    return reconstitute_draft(j.envs, turn)


def simple() -> J:
    j = J()
    j.bricks()
    j.window()
    j.start("t1", "Quelle heure ?")
    j.call("t1")
    j.tool("t1", "get_datetime", call_id="t1.main.c1.k1", tz="UTC")
    j.add("tool_ended", {"status": "ok", "duration_ms": 1}, "t1", call_id="t1.main.c1.k1")
    j.call("t1", "Il est midi.")
    j.end("t1")
    return j


# ---------- configuration ----------


def test_the_configuration_and_the_provenance_come_from_the_turn():
    d = draft(simple(), "t1")
    assert d.turn_id == "t1" and d.seq == 3
    assert d.date == "2026-10-25T09:30:00+00:00"
    assert d.model is not None and d.model.id == "m1"
    assert d.prompt == "Quelle heure ?"
    assert d.bricks == ["short_memory", "tools"]
    assert d.tools == ["get_datetime"]  # `calc` is off
    assert d.hooks == d.skills == d.mcp_servers == []
    assert d.window == 4096
    assert d.system_prompt.text == "Sys" and d.system_prompt.is_default
    assert d.origin_status == "completed"


def test_the_last_bricks_changed_before_the_turn_is_the_one_read():
    j = J()
    j.bricks([card("short_memory")], text="Avant")
    j.start("t1")
    j.end("t1")
    j.bricks([card("tools", options=(("calc", True),))], text="Après")
    d = draft(j, "t1")
    assert d.bricks == ["short_memory"]
    assert d.system_prompt.text == "Avant"


def test_a_brick_not_wanted_is_not_listed():
    j = J()
    j.bricks([card("tools", wanted=False), card("rag")])
    j.start("t1")
    j.end("t1")
    assert draft(j, "t1").bricks == ["rag"]


def test_not_kept_lists_lazy_mcp_and_rag_reranking_when_their_brick_is_wanted():
    rerank = {
        "label_text": "r",
        "enabled": True,
        "available": True,
        "hosting_text": "h",
    }
    j = J()
    j.bricks([card("mcp", mode="lazy"), card("rag", rerank=rerank)])
    j.start("t1")
    j.end("t1")
    assert draft(j, "t1").not_kept == ["mcp_lazy", "rag_rerank"]
    k = J()
    k.bricks([card("mcp", wanted=False, mode="lazy"), card("rag", wanted=False, rerank=rerank)])
    k.start("t1")
    k.end("t1")
    assert draft(k, "t1").not_kept == []
    m = J()
    m.bricks([card("mcp", mode="full"), card("rag", rerank=rerank | {"enabled": False})])
    m.start("t1")
    m.end("t1")
    assert draft(m, "t1").not_kept == []


@pytest.mark.parametrize(
    ("hosting", "expected"), [("file", 2048), ("server", 2048), ("cloud", None)]
)
def test_the_window_is_configured_for_a_local_or_served_model_only(hosting, expected):
    j = J()
    j.window(hosting, 2048)
    j.start("t1")
    j.end("t1")
    assert draft(j, "t1").window == expected


# ---------- what the turn did ----------


def test_the_tool_calls_keep_their_order_arguments_status_and_context():
    j = J()
    j.start("t1")
    j.call("t1")
    j.tool("t1", "get_datetime", call_id="c1", tz="UTC", fmt="iso")
    j.add("tool_ended", {"status": "error", "duration_ms": 1}, "t1", call_id="c1")
    j.tool("t1", "calc", ctx="sub1", call_id="c2", expr="1+1")
    j.tool("t1", "calc", call_id="c3")
    j.end("t1")
    calls = draft(j, "t1").tool_calls
    assert [(c.seq, c.tool, c.arguments, c.status, c.context_id) for c in calls] == [
        (3, "get_datetime", {"tz": "UTC", "fmt": "iso"}, "error", "main"),
        (5, "calc", {"expr": "1+1"}, None, "sub1"),
        (6, "calc", {}, None, "main"),
    ]


def test_model_calls_count_every_context_and_the_cap_suggestion_is_at_least_one():
    j = J()
    j.start("t1")
    j.call("t1")
    j.call("t1", ctx="sub1")
    j.call("t1")
    j.end("t1")
    d = draft(j, "t1")
    assert d.model_calls == 3 and d.suggested_max_model_calls == 3
    k = J()
    k.start("t1")
    k.end("t1")
    assert draft(k, "t1").model_calls == 0
    assert draft(k, "t1").suggested_max_model_calls == 1


def test_the_answer_is_rebuilt_from_the_deltas_when_the_output_was_not_withheld():
    d = draft(simple(), "t1")
    assert d.answer_text == "Il est midi."
    j = J()
    j.start("t1")
    j.call("t1", "brouillon")
    j.end("t1", text="Réponse retenue")
    assert draft(j, "t1").answer_text == "Réponse retenue"


def test_hooks_and_subagents_are_read():
    j = J()
    j.start("t1")
    j.add(
        "hook_decided",
        {
            "hook": "h5",
            "point": "before_tool",
            "decision": "ask_human",
            "detail_text": "d",
            "hook_text": "h",
            "point_text": "p",
        },
        "t1",
    )
    j.end("t1")
    d = draft(j, "t1")
    assert [(h.hook, h.decision) for h in d.hooks_decided] == [("h5", "ask_human")]
    assert not d.subagent_called
    j.add("subagent_started", {"task": "x", "tools": [], "phase_label": "p"}, "t1", ctx="sub1")
    assert draft(j, "t1").subagent_called is False  # after the turn's end: not read
    k = J()
    k.start("t1")
    k.add("subagent_started", {"task": "x", "tools": [], "phase_label": "p"}, "t1", ctx="sub1")
    k.end("t1")
    assert draft(k, "t1").subagent_called


@pytest.mark.parametrize("status", ["limit", "error", "cancelled", "overflow", "blocked"])
def test_a_turn_that_did_not_complete_is_accepted_with_its_status(status):
    j = J()
    j.start("t1")
    j.end("t1", status)
    assert draft(j, "t1").origin_status == status


def test_later_envelopes_do_not_change_the_draft():
    j = simple()
    before = draft(j, "t1")
    j.bricks([card("rag")], text="Plus tard")
    j.window("cloud", 100)
    j.exchange("t2", "Autre", "Autre réponse")
    j.add("model_delta", {"channel": "text", "text": "tard"}, "t1")
    assert draft(j, "t1") == before


# ---------- refusals ----------


def test_refusals():
    j = J()
    j.add("turn_started", {"message": "Résume", "kind": "compaction"}, "tc")
    j.end("tc")
    j.start("tcase", case_id="c1")
    j.end("tcase")
    j.start("tun")
    for turn, reason in [
        ("nope", "unknown_turn"),
        ("tc", "not_a_message"),
        ("tcase", "case_turn"),
        ("tun", "unfinished"),
    ]:
        with pytest.raises(DraftRefused) as refused:
            draft(j, turn)
        assert refused.value.reason == reason


# ---------- approval ----------


@pytest.mark.parametrize(
    ("decision", "expected"),
    [("approved", "approve"), ("refused", "refuse"), ("cancelled", "refuse"), (None, "refuse")],
)
def test_approval_is_read_from_the_resolution(decision, expected):
    j = J()
    j.start("t1")
    if decision:
        j.add(
            "approval_resolved",
            {"approval_id": "a", "decision": decision, "hook_disabled": False},
            "t1",
        )
    j.end("t1")
    assert draft(j, "t1").approval == expected


# ---------- history ----------


def test_the_history_is_rebuilt_without_the_withheld_text():
    j = J()
    j.bricks()
    for i in (1, 2, 3):
        j.exchange(f"t{i}", f"q{i}", f"a{i}")
    j.start("t4", "q4")
    j.end("t4")
    d = draft(j, "t4")
    assert d.history_available and d.history_note is None
    assert [(h.user, h.assistant) for h in d.history] == [("q1", "a1"), ("q2", "a2"), ("q3", "a3")]


def test_clearing_the_conversation_or_resetting_empties_the_history():
    for kind in ("conversation_cleared", "harness_reset"):
        j = J()
        j.exchange("t1", "q1", "a1")
        j.add(kind, {})
        j.exchange("t2", "q2", "a2")
        j.start("t3")
        j.end("t3")
        assert [h.user for h in draft(j, "t3").history] == ["q2"]


def test_a_turn_that_did_not_complete_is_not_in_the_history():
    j = J()
    j.exchange("t1", "q1", "a1")
    j.exchange("t2", "q2", "a2", status="blocked")
    j.exchange("t3", "q3", "a3", status="limit")
    j.start("t4")
    j.end("t4")
    assert [h.user for h in draft(j, "t4").history] == ["q1"]


def test_a_replayed_turn_starts_from_the_history_before_its_origin():
    j = J()
    j.exchange("t1", "q1", "a1")
    j.exchange("t2", "q2", "a2")
    j.exchange("t3", "q3", "a3")
    j.start("t4", "q2 bis", replay_of="t2")
    j.end("t4", "limit")
    assert [h.user for h in draft(j, "t4").history] == ["q1"]
    j.start("t5", "autre")
    j.end("t5")
    assert [h.user for h in draft(j, "t5").history] == ["q1"]  # t4 did not complete the exchange


def test_a_completed_replay_is_added_after_the_truncation():
    j = J()
    j.exchange("t1", "q1", "a1")
    j.exchange("t2", "q2", "a2")
    j.start("t3", "q2 bis", replay_of="t2")
    j.call("t3", "a2 bis")
    j.end("t3")
    j.start("t4")
    j.end("t4")
    assert [(h.user, h.assistant) for h in draft(j, "t4").history] == [
        ("q1", "a1"),
        ("q2 bis", "a2 bis"),
    ]


def test_a_sliding_window_removes_the_exchanges_it_removed():
    j = J()
    for i in (1, 2, 3):
        j.exchange(f"t{i}", f"q{i}", f"a{i}")
    j.sliding(["t1", "t2"])
    j.start("t4")
    j.end("t4")
    d = draft(j, "t4")
    assert [h.user for h in d.history] == ["q3"]
    assert d.history_note == "compacted" and d.history_available


def test_a_compaction_puts_the_summary_first():
    j = J()
    for i in (1, 2, 3):
        j.exchange(f"t{i}", f"q{i}", f"a{i}")
    j.compaction("tc", ["t1", "t2"], "Résumé des deux")
    j.start("t4")
    j.end("t4")
    d = draft(j, "t4")
    assert [(h.user, h.assistant) for h in d.history] == [
        ("Résume", "Résumé des deux"),
        ("q3", "a3"),
    ]
    assert d.history_note == "compacted"


def test_a_compaction_without_summary_makes_the_history_unavailable():
    j = J()
    j.exchange("t1", "q1", "a1")
    j.compaction("tc", ["t1"], None)
    j.start("t2")
    j.end("t2")
    d = draft(j, "t2")
    assert d.history == [] and not d.history_available and d.history_note == "unavailable"


def test_a_completed_turn_without_answer_makes_the_history_unavailable():
    j = J()
    j.start("t1", "q1")
    j.end("t1")  # completed, no call, no text
    j.start("t2")
    j.end("t2")
    d = draft(j, "t2")
    assert not d.history_available and d.history_note == "unavailable"
    # A clear gives the history back.
    j.add("conversation_cleared", {})
    j.start("t3")
    j.end("t3")
    assert draft(j, "t3").history_available


# ---------- overflow ----------


def overflowed(strategy: str, same_message: bool = True) -> J:
    j = J()
    j.exchange("t1", "q1", "a1")
    j.start("t2", "Question longue")
    j.end("t2", "overflow")
    if strategy == "compaction":
        j.compaction("tc", ["t1"], "Résumé")
    else:
        j.sliding(["t1"])
    j.start("t3", "Question longue" if same_message else "Autre")
    j.call("t3", "ok")
    j.end("t3")
    return j


def test_a_message_sent_again_after_a_compaction_plays_the_three_turns():
    d = draft(overflowed("compaction"), "t3")
    assert d.on_overflow == "compaction"
    assert d.verdict_turn_ids == ["t2", "tc", "t3"]
    assert [h.user for h in d.history] == ["q1"]  # before the strategy
    assert d.history_note is None


def test_a_message_sent_again_after_a_sliding_window_plays_two_turns():
    d = draft(overflowed("sliding_window"), "t3")
    assert d.on_overflow == "sliding_window"
    assert d.verdict_turn_ids == ["t2", "t3"]
    assert [h.user for h in d.history] == ["q1"]


def test_another_message_after_an_overflow_is_a_plain_turn():
    d = draft(overflowed("compaction", same_message=False), "t3")
    assert d.on_overflow == "none" and d.verdict_turn_ids == ["t3"]
    assert [(h.user, h.assistant) for h in d.history] == [("Résume", "Résumé")]
    assert d.history_note == "compacted"


# ---------- to_case ----------


def form(**kw) -> CaseForm:
    return CaseForm.model_validate(
        {
            "turn_id": "t1",
            "title_text": "Titre",
            "symptom_text": "Symptôme",
            "assertion_text": "Assertion",
            "prompt": "Quelle heure ?",
            "include_history": True,
            "freeze_system_prompt": False,
            "approval": "refuse",
            "on_overflow": "none",
            "max_model_calls": 3,
            "checks": [{"kind": "tool_not_called", "tool": "get_datetime"}],
        }
        | kw
    )


def test_to_case_maps_the_draft_and_the_form():
    j = J()
    j.bricks()
    j.window()
    j.exchange("t0", "q0", "a0")
    j.start("t1", "Quelle heure ?")
    j.end("t1", "limit")
    d = draft(j, "t1")
    case = to_case(d, form(approval="approve", on_overflow="compaction"), "u123")
    assert case.id == "u123" and case.title_text == "Titre"
    assert case.prompt == "Quelle heure ?"
    assert [(h.user, h.assistant) for h in case.history] == [("q0", "a0")]
    assert case.bricks == ["short_memory", "tools"] and case.tools == ["get_datetime"]
    assert case.window == 4096
    assert case.system_prompt is None
    assert case.approval == "approve" and case.on_overflow == "compaction"
    assert case.max_model_calls == 3
    p = case.provenance
    assert p.source == "séance" and p.turn_id == "t1" and p.date == d.date
    assert p.model is not None and p.model.id == "m1"
    assert p.system_prompt_text == "Sys" and p.fixed_in is None


def test_to_case_omits_the_history_when_unchecked_or_unavailable():
    j = J()
    j.exchange("t0", "q0", "a0")
    j.start("t1")
    j.end("t1")
    d = draft(j, "t1")
    assert to_case(d, form(include_history=False), "u1").history == []
    assert len(to_case(d, form(), "u1").history) == 1
    k = J()
    k.compaction("tc", [], None)
    k.start("t1")
    k.end("t1")
    assert to_case(draft(k, "t1"), form(), "u1").history == []


def test_to_case_freezes_the_system_prompt_on_request_and_always_keeps_it_in_provenance():
    j = J()
    j.bricks(text="Tu es un agent.", default=False)
    j.start("t1")
    j.end("t1")
    d = draft(j, "t1")
    plain = to_case(d, form(), "u1")
    assert plain.system_prompt is None
    assert plain.provenance.system_prompt_text == "Tu es un agent."
    assert to_case(d, form(freeze_system_prompt=True), "u1").system_prompt == "Tu es un agent."


def test_a_session_case_needs_no_positive_check_and_a_bad_form_is_refused():
    j = J()
    j.start("t1")
    j.end("t1")
    d = draft(j, "t1")
    assert to_case(d, form(), "u1").checks[0].kind == "tool_not_called"
    with pytest.raises(ValidationError):
        to_case(d, form(max_model_calls=0), "u1")
    with pytest.raises(ValidationError):
        to_case(d, form(), "draft")  # a session case's id starts with `u`
