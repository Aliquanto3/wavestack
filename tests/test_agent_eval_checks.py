"""V1.5 story 1: `verify` on hand-built journals, each check both ways, the missing witness,
the sub-agent counted in the cap."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from wavestack.agent_eval.cases import AgentCase
from wavestack.agent_eval.checks import verify
from wavestack.trace.envelope import Envelope

TS = datetime(2026, 10, 25, tzinfo=UTC)


class J:
    """A journal under construction: one envelope per call, `seq` increasing."""

    def __init__(self) -> None:
        self.envs: list[Envelope] = []

    def add(self, kind: str, payload: dict, turn: str = "t1", ctx: str = "main") -> int:
        seq = len(self.envs) + 1
        actor = "user" if kind == "turn_started" else "harness"
        self.envs.append(
            Envelope(
                seq=seq,
                ts=TS,
                session_epoch=0,
                turn_id=turn,
                context_id=ctx,
                kind=kind,
                actor=actor,
                trigger="user",
                payload=payload,
            )
        )
        return seq

    def start(self, turn: str = "t1", kind: str = "message") -> int:
        return self.add("turn_started", {"message": "m", "kind": kind}, turn)

    def call(self, turn: str = "t1", ctx: str = "main", text: str = "") -> int:
        seq = self.add("model_call_started", {"phase_label": "p"}, turn, ctx)
        if text:
            self.add("model_delta", {"channel": "text", "text": text}, turn, ctx)
        return seq

    def tool(self, tool: str, turn: str = "t1", ctx: str = "main", **arguments) -> int:
        return self.add(
            "tool_started", {"tool": tool, "arguments": arguments, "phase_label": "p"}, turn, ctx
        )

    def hook(self, hook: str, decision: str, turn: str = "t1") -> int:
        return self.add(
            "hook_decided",
            {
                "hook": hook,
                "point": "before_tool",
                "decision": decision,
                "detail_text": "d",
                "hook_text": hook,
                "point_text": "p",
            },
            turn,
        )

    def end(self, turn: str = "t1", status: str = "completed", text: str | None = None) -> int:
        payload = {"status": status} | ({"text": text} if text is not None else {})
        return self.add("turn_ended", payload, turn)


def case(*checks: dict, cap: int = 5, **fields) -> AgentCase:
    return AgentCase.model_validate(
        {
            "id": "c1",
            "title_text": "T",
            "brick": "tools",
            "symptom_text": "S",
            "assertion_text": "A",
            "prompt": "P",
            "max_model_calls": cap,
            "checks": list(checks),
            "provenance": {"source": "fourni", "date": "2026-10-25"},
        }
        | fields
    )


def only(c: AgentCase, j: J, lang: str = "fr"):
    """The verdict of the case's single check (the cap is the last one)."""
    verdict = verify(c, j.envs, lang)
    return verdict.checks[0]


# ---------- tool_called ----------


def test_tool_called_passes_on_its_first_call():
    j = J()
    j.start()
    j.call()
    first = j.tool("get_datetime")
    j.tool("get_datetime")
    j.end()
    v = only(case({"kind": "tool_called", "tool": "get_datetime"}), j)
    assert (v.passed, v.seq, v.reason_text) == (True, first, "get_datetime appelé")
    assert v.kind == "tool_called" and v.params == {"tool": "get_datetime"}


def test_tool_called_fails_when_absent_on_the_witness():
    j = J()
    j.start()
    j.tool("list_files")
    end = j.end()
    v = only(case({"kind": "tool_called", "tool": "get_datetime"}), j)
    assert (v.passed, v.seq, v.reason_text) == (False, end, "get_datetime jamais appelé")


def test_tool_called_before_passes_in_order_and_when_before_is_never_called():
    j = J()
    j.start()
    s = j.tool("search_documents")
    j.tool("read_file")
    j.tool("search_documents")
    j.end()
    check = {"kind": "tool_called", "tool": "search_documents", "before": "read_file"}
    v = only(case(check), j)
    assert (v.passed, v.seq) == (True, s)
    assert v.reason_text == "search_documents appelé avant read_file"
    assert v.params == {"tool": "search_documents", "before": "read_file"}

    j2 = J()
    j2.start()
    j2.tool("search_documents")
    j2.end()
    assert only(case(check), j2).passed


def test_tool_called_before_fails_when_the_other_comes_first():
    j = J()
    j.start()
    r = j.tool("read_file")
    j.tool("search_documents")
    j.end()
    v = only(case({"kind": "tool_called", "tool": "search_documents", "before": "read_file"}), j)
    assert (v.passed, v.seq) == (False, r)
    assert v.reason_text == "read_file appelé avant search_documents"


# ---------- tool_not_called ----------


def test_tool_not_called_both_ways():
    check = {"kind": "tool_not_called", "tool": "read_file"}
    j = J()
    j.start()
    j.tool("list_files")
    end = j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq, v.reason_text) == (True, end, "read_file jamais appelé")

    j = J()
    j.start()
    bad = j.tool("read_file", ctx="sub1", path="x")  # a sub-agent's call counts too
    j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq, v.reason_text) == (False, bad, "read_file appelé")


# ---------- argument_never ----------


def test_argument_never_passes_when_no_call_matches():
    check = {
        "kind": "argument_never",
        "tool": "read_file",
        "argument": "path",
        "contains": "rapport_2025",
    }
    j = J()
    j.start()
    j.tool("read_file", path="notes.md")
    j.tool("read_file", other="rapport_2025.txt")  # another argument
    j.tool("list_files", path="rapport_2025")  # another tool
    end = j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq) == (True, end)
    assert v.reason_text == "read_file jamais appelé avec « rapport_2025 » dans path"


def test_argument_never_fails_ignoring_case_and_on_non_text_values():
    check = {
        "kind": "argument_never",
        "tool": "read_file",
        "argument": "path",
        "contains": "Rapport_2025",
    }
    j = J()
    j.start()
    j.tool("read_file", path="notes.md")
    bad = j.tool("read_file", path="docs/RAPPORT_2025.txt")
    j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq) == (False, bad)
    assert v.reason_text == "read_file appelé avec path = « docs/RAPPORT_2025.txt »"

    j = J()
    j.start()
    bad = j.tool("calc", n=42)
    j.end()
    v = only(case({"kind": "argument_never", "tool": "calc", "argument": "n", "contains": "42"}), j)
    assert (v.passed, v.seq) == (False, bad)


# ---------- model_calls_max ----------


def test_model_calls_max_counts_the_sub_agents_calls():
    j = J()
    j.start()
    j.call()
    j.add("subagent_started", {"task": "t", "tools": [], "phase_label": "p"}, ctx="sub1")
    j.call(ctx="sub1")
    third = j.call(ctx="sub1")
    j.call()
    j.end()
    verdict = verify(case({"kind": "subagent_called"}, cap=2), j.envs)
    cap = verdict.checks[-1]
    assert verdict.model_calls == 4
    assert (cap.kind, cap.params, cap.passed, cap.seq) == (
        "model_calls_max",
        {"max": 2},
        False,
        third,
    )
    assert cap.reason_text == "4 appels au modèle pour un plafond de 2"
    assert verdict.checks[0].passed and not verdict.passed


def test_model_calls_max_passes_at_the_cap():
    j = J()
    j.start()
    j.call()
    end = j.end()
    verdict = verify(case({"kind": "turn_completed"}, cap=1), j.envs)
    cap = verdict.checks[-1]
    assert (cap.passed, cap.seq, cap.reason_text) == (
        True,
        end,
        "1 appel au modèle pour un plafond de 1",
    )
    assert verdict.passed and verdict.case_id == "c1" and verdict.model_calls == 1


# ---------- answer_contains ----------


def test_answer_contains_reads_the_last_main_calls_text_deltas():
    check = {"kind": "answer_contains", "text": "code  tlv-7731-qz"}
    j = J()
    j.start()
    j.call(text="Le code TLV-0000 ?")  # an earlier call: not the answer
    j.call(ctx="sub1", text="Code TLV-7731-QZ")  # the sub-agent: not the answer
    j.call()
    j.add("model_delta", {"channel": "reasoning", "text": "code TLV-7731-QZ"})
    j.add("model_delta", {"channel": "text", "text": "Le code\n  TLV-77"})
    j.add("model_delta", {"channel": "text", "text": "31-QZ."})
    end = j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq) == (True, end)
    assert v.reason_text == "la réponse contient « code  tlv-7731-qz »"


def test_answer_contains_fails_when_only_earlier_calls_or_reasoning_hold_it():
    check = {"kind": "answer_contains", "text": "TLV-7731-QZ"}
    j = J()
    j.start()
    j.call(text="TLV-7731-QZ")
    j.call(text="Je ne sais pas.")
    j.add("model_delta", {"channel": "reasoning", "text": "TLV-7731-QZ"})
    end = j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq) == (False, end)
    assert v.reason_text == "la réponse ne contient pas « TLV-7731-QZ »"


def test_answer_contains_prefers_turn_ended_text():
    check = {"kind": "answer_contains", "text": "TLV-7731-QZ"}
    j = J()
    j.start()
    j.call(text="TLV-7731-QZ")
    j.end(text="[masqué]")  # withheld then blocked by a guardrail
    assert not only(case(check), j).passed
    j = J()
    j.start()
    j.call(text="rien")
    j.end(text="voici TLV-7731-QZ")
    assert only(case(check), j).passed


def test_answer_contains_reads_the_message_sent_again_after_a_compaction():
    check = {"kind": "answer_contains", "text": "TLV-7731-QZ"}
    j = J()
    j.start("t1")
    j.end("t1", status="overflow")
    j.start("t2", kind="compaction")
    j.call("t2", text="résumé TLV-7731-QZ")
    j.end("t2")
    j.start("t3")
    j.call("t3", text="Je ne sais pas")
    j.end("t3")
    assert not only(case(check, on_overflow="compaction"), j).passed


# ---------- hook_decided ----------


def test_hook_decided_both_ways():
    check = {"kind": "hook_decided", "hook": "h1", "decision": "block"}
    j = J()
    j.start()
    j.hook("h1", "allow")
    blocked = j.hook("h1", "block")
    j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq, v.reason_text) == (True, blocked, "h1 a décidé : bloquer")

    j = J()
    j.start()
    j.hook("h1", "allow")
    j.hook("h5", "block")
    end = j.end()
    v = only(case(check), j)
    assert (v.passed, v.seq, v.reason_text) == (False, end, "h1 n'a jamais décidé : bloquer")


def test_hook_decided_ask_human_and_its_reason_in_english():
    j = J()
    j.start()
    j.hook("h5", "ask_human")
    j.end()
    v = only(case({"kind": "hook_decided", "hook": "h5", "decision": "ask_human"}), j, "en")
    assert v.passed and v.reason_text == "h5 decided: ask for approval"


# ---------- subagent_called ----------


def test_subagent_called_both_ways():
    j = J()
    j.start()
    sub = j.add("subagent_started", {"task": "t", "tools": [], "phase_label": "p"}, ctx="sub1")
    j.end()
    v = only(case({"kind": "subagent_called"}), j)
    assert (v.passed, v.seq, v.reason_text) == (True, sub, "sous-agent appelé")

    j = J()
    j.start()
    j.tool("delegate")  # the call alone is not the sub-agent's start
    end = j.end()
    v = only(case({"kind": "subagent_called"}), j)
    assert (v.passed, v.seq, v.reason_text) == (False, end, "sous-agent jamais appelé")


# ---------- turn_completed ----------


def test_turn_completed_passes_when_every_turn_completes():
    j = J()
    j.start()
    end = j.end()
    v = only(case({"kind": "turn_completed"}), j)
    assert (v.passed, v.seq, v.reason_text) == (True, end, "tours finis sans erreur")


@pytest.mark.parametrize("status", ["limit", "error", "blocked", "overflow"])
def test_turn_completed_fails_on_another_status(status):
    j = J()
    j.start()
    end = j.end(status=status)
    v = only(case({"kind": "turn_completed"}), j)
    assert (v.passed, v.seq, v.reason_text) == (False, end, f"un tour a fini en « {status} »")


def test_turn_completed_fails_on_a_harness_error():
    j = J()
    j.start()
    err = j.add("harness_error", {"message_text": "boum", "source": "harness"})
    j.end()
    v = only(case({"kind": "turn_completed"}), j)
    assert (v.passed, v.seq, v.reason_text) == (False, err, "erreur du harnais : boum")


def test_turn_completed_tolerates_the_overflow_on_overflow_handles():
    def journal() -> J:
        j = J()
        j.start("t1")
        j.add("harness_error", {"message_text": "débordement", "source": "harness"}, "t1")
        j.end("t1", status="overflow")
        j.start("t2", kind="compaction")
        j.end("t2")
        j.start("t3")
        j.end("t3")
        return j

    assert only(case({"kind": "turn_completed"}, on_overflow="compaction"), journal()).passed
    v = only(case({"kind": "turn_completed"}), journal())  # `on_overflow: none`
    assert not v.passed and v.reason_text == "un tour a fini en « overflow »"


def test_turn_completed_fails_when_an_earlier_turn_never_ended():
    j = J()
    j.start("t1", kind="compaction")
    j.start("t2")
    end = j.end("t2")
    v = only(case({"kind": "turn_completed"}), j)
    assert (v.passed, v.seq, v.reason_text) == (False, end, "tour incomplet")


# ---------- the witness ----------


ALL_CHECKS = [
    {"kind": "tool_called", "tool": "get_datetime"},
    {"kind": "tool_not_called", "tool": "read_file"},
    {"kind": "argument_never", "tool": "read_file", "argument": "path", "contains": "x"},
]


def test_without_the_witness_every_check_fails_incomplete():
    j = J()
    j.start()
    j.call()
    j.tool("get_datetime")  # would pass, but the turn never ended (cancelled, truncated)
    verdict = verify(case(*ALL_CHECKS), j.envs)
    assert not verdict.passed and verdict.model_calls == 1
    assert [(v.kind, v.passed, v.seq, v.reason_text) for v in verdict.checks] == [
        ("tool_called", False, None, "tour incomplet"),
        ("tool_not_called", False, None, "tour incomplet"),
        ("argument_never", False, None, "tour incomplet"),
        ("model_calls_max", False, None, "tour incomplet"),
    ]


def test_the_witness_is_the_last_message_turns_end():
    # The first message turn ended, the message sent again did not: incomplete.
    j = J()
    j.start("t1")
    j.end("t1", status="overflow")
    j.start("t2", kind="compaction")
    j.end("t2")
    j.start("t3")
    j.tool("get_datetime", turn="t3")
    verdict = verify(case({"kind": "tool_not_called", "tool": "read_file"}), j.envs)
    assert verdict.checks[0].reason_text == "tour incomplet"
    # No turn at all: incomplete too, in German.
    verdict = verify(case({"kind": "subagent_called"}), [], "de")
    assert [v.reason_text for v in verdict.checks] == ["unvollständige Runde"] * 2


def test_envelopes_are_read_in_seq_order():
    j = J()
    j.start()
    j.tool("search_documents")
    j.tool("read_file")
    j.end()
    check = {"kind": "tool_called", "tool": "search_documents", "before": "read_file"}
    shuffled = J()
    shuffled.envs = list(reversed(j.envs))  # the witness first, `read_file` before
    assert only(case(check), shuffled).passed


# ---------- the case's model ----------


@pytest.mark.parametrize(
    "fields",
    [
        {"checks": []},
        {"checks": [{"kind": "subagent_called"}] * 4},
        {"checks": [{"kind": "model_calls_max"}]},  # never written: `max_model_calls`
        {"checks": [{"kind": "judge"}]},  # the catalogue is closed
        {"checks": [{"kind": "hook_decided", "hook": "h1", "decision": "allow"}]},
        {"max_model_calls": 0},
        {"approval": "maybe"},
        {"on_overflow": "truncate"},
        {"extra": 1},
        {"id": "x1", "provenance": {"source": "séance", "date": "2026-10-25"}},
    ],
)
def test_an_invalid_case_is_refused(fields):
    base = {"kind": "subagent_called"}
    with pytest.raises(ValidationError):
        case(base, **fields)


def test_a_case_keeps_its_defaults():
    c = case({"kind": "subagent_called"})
    assert (c.approval, c.on_overflow, c.window, c.system_prompt, c.history, c.bricks, c.tools) == (
        "refuse",
        "none",
        None,
        None,
        [],
        [],
        None,
    )
